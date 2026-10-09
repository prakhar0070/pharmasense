"""
llm.py - Groq LLM wrapper with automatic fallback when a model returns 404.

Drop-in replacement for the call_llm / _call_groq functions used by
llm_router.py:

    response = call_llm(prompt=question, system=ROUTER_SYSTEM_PROMPT,
                        tools=tool_list)

Returns the assistant message object (resp.choices[0].message), so you can use
response.content and response.tool_calls as usual.
"""

import json
import os

from groq import BadRequestError, Groq, NotFoundError

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Models are tried in this order. Check https://console.groq.com/docs/models
# and edit this list if Groq retires or renames a model.
DEFAULT_MODEL = "llama-3.3-70b-versatile"
FALLBACK_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]


def _get_secret(name, default=None):
    """Read a setting from Streamlit secrets first, then environment variables."""
    try:
        import streamlit as st

        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.getenv(name, default)


def _get_client():
    api_key = _get_secret("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is missing. Set it in .env (local) or in "
            "Streamlit Cloud -> Settings -> Secrets."
        )

    # Only pass base_url if you really need a custom one.
    # Correct value is "https://api.groq.com" (the SDK adds /openai/v1 itself).
    base_url = _get_secret("GROQ_BASE_URL")
    if base_url:
        return Groq(api_key=api_key, base_url=base_url)
    return Groq(api_key=api_key)


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

def call_llm(prompt, system=None, tools=None, model=None, temperature=0.2):
    """Send a prompt to Groq and return the assistant message."""
    # Model priority: function argument > GROQ_MODEL setting > DEFAULT_MODEL
    chosen = model or _get_secret("GROQ_MODEL") or DEFAULT_MODEL

    # Try the chosen model first, then the fallbacks (without duplicates)
    candidates = [chosen] + [m for m in FALLBACK_MODELS if m != chosen]

    last_error = None
    for name in candidates:
        try:
            return _call_groq(prompt, system, tools, name, temperature)
        except NotFoundError as e:
            # 404 = model not found / retired. Try the next one.
            last_error = e
            print(f"[llm] Model '{name}' not found, trying next...")
            continue
        except BadRequestError as e:
            # 400 = request rejected (bad tool format, tool call failed, etc.)
            last_error = e
            print(f"[llm] 400 BadRequest from '{name}': {e}")
            if tools:
                # Last resort: retry once without tools so the app still answers.
                try:
                    print("[llm] Retrying without tools...")
                    return _call_groq(prompt, system, None, name, temperature)
                except BadRequestError as e2:
                    last_error = e2
            continue

    # All configured models failed -> ask Groq which models exist right now
    try:
        available = _list_available_models()
    except Exception as e:
        print(f"[llm] Could not list models: {e}")
        available = []

    for name in available:
        if name in candidates:
            continue
        try:
            print(f"[llm] Trying auto-discovered model '{name}'...")
            return _call_groq(prompt, system, tools, name, temperature)
        except (NotFoundError, BadRequestError) as e:
            last_error = e
            print(f"[llm] '{name}' failed: {e}")
            continue

    print(f"[llm] FINAL ERROR: {last_error}")
    raise RuntimeError(
        f"No Groq model worked. Last error: {last_error}"
    ) from last_error


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _list_available_models():
    """Ask Groq for the chat models currently available to this API key."""
    client = _get_client()
    skip = ("whisper", "guard", "tts", "playai", "embed", "orpheus", "safeguard")

    names = []
    for m in client.models.list().data:
        mid = m.id
        if any(s in mid.lower() for s in skip):
            continue
        if getattr(m, "active", True) is False:
            continue
        names.append(mid)

    def rank(n):
        n = n.lower()
        if "llama" in n and any(k in n for k in ("70b", "versatile", "scout", "maverick")):
            return (0, n)
        if "llama" in n or "gpt-oss" in n:
            return (1, n)
        return (2, n)

    names.sort(key=rank)
    print("[llm] Available models:", names)
    return names


def _normalize_tools(tools):
    """Convert tools into the OpenAI/Groq format if they are in another shape."""
    if not tools:
        return None

    fixed = []
    for t in tools:
        if not isinstance(t, dict):
            continue

        # Already correct: {"type": "function", "function": {...}}
        if t.get("type") == "function" and "function" in t:
            fn = t["function"]
            params = fn.get("parameters") or {"type": "object", "properties": {}}
            params.setdefault("type", "object")
            params.setdefault("properties", {})
            fn["parameters"] = params
            fixed.append(t)
            continue

        # Flat shape: {"name": ..., "description": ..., "parameters"/"input_schema": {...}}
        if "name" in t:
            params = (
                t.get("parameters")
                or t.get("input_schema")
                or {"type": "object", "properties": {}}
            )
            params.setdefault("type", "object")
            params.setdefault("properties", {})
            fixed.append(
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": params,
                    },
                }
            )

    return fixed or None


def _call_groq(prompt, system, tools, model, temperature=0.2):
    client = _get_client()

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }

    # tools must be in OpenAI function-calling format:
    # [{"type": "function", "function": {"name": ..., "description": ..., "parameters": {...}}}]
    tools = _normalize_tools(tools)
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    resp = client.chat.completions.create(**kwargs)
    msg = resp.choices[0].message

    # Convert tool calls into plain dicts
    tool_calls = []
    for tc in (getattr(msg, "tool_calls", None) or []):
        raw_args = tc.function.arguments or "{}"
        try:
            parsed_args = json.loads(raw_args)
        except Exception:
            parsed_args = {}
        tool_calls.append(
            {
                "id": tc.id,
                "name": tc.function.name,
                "arguments": parsed_args,
                "function": {"name": tc.function.name, "arguments": raw_args},
            }
        )

    # Token usage as a plain dict
    u = getattr(resp, "usage", None)
    prompt_t = getattr(u, "prompt_tokens", 0) or 0
    completion_t = getattr(u, "completion_tokens", 0) or 0
    usage = {
        "prompt_tokens": prompt_t,
        "completion_tokens": completion_t,
        "total_tokens": getattr(u, "total_tokens", prompt_t + completion_t) or 0,
        "input_tokens": prompt_t,
        "output_tokens": completion_t,
    }

    text = msg.content or ""
    return {
        "content": text,
        "text": text,
        "tool_calls": tool_calls,
        "usage": usage,
        "model": model,
        "message": msg,
    }
