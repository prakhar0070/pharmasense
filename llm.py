"""
llm.py - Groq LLM wrapper with automatic fallback when a model returns 404.

Drop-in replacement for the call_llm / _call_groq functions used by
llm_router.py:

    response = call_llm(prompt=question, system=ROUTER_SYSTEM_PROMPT,
                        tools=tool_list)

Returns the assistant message object (resp.choices[0].message), so you can use
response.content and response.tool_calls as usual.
"""

import os

from groq import Groq, NotFoundError

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

    raise RuntimeError(
        "None of the configured Groq models were found. "
        "Update FALLBACK_MODELS in llm.py using https://console.groq.com/docs/models"
    ) from last_error


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

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
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message
