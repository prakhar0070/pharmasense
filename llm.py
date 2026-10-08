"""
Stage 2 (properly done): The governed LLM access layer.

Every agent calls call_llm() instead of hitting an API directly -- this is
the "single governed entry point" Step 2 of the guide asks for. It also
logs every call's model, tokens, latency, and estimated cost to
llm_usage_log.jsonl, which is your observability foundation for Step 7.

Set LLM_PROVIDER in your .env file to "openai" or "anthropic".
"""

import os
import json
import time
from dotenv import load_dotenv
import streamlit as st
load_dotenv()

PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()
USAGE_LOG_PATH = "llm_usage_log.jsonl"

# Rough public per-token prices (USD per 1K tokens) for cost logging.
# These are approximate -- check current pricing pages for exact numbers.
PRICING = {
    "openai": {"input": 0.00015, "output": 0.0006},      # gpt-4o-mini ballpark
    "anthropic": {"input": 0.0008, "output": 0.004},      # claude haiku ballpark
    "groq": {"input": 0.0, "output": 0.0},                # free tier
}


def _log_usage(entry: dict):
    with open(USAGE_LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def call_llm(prompt: str, system: str = "", tools: list = None, model: str = None):
    """
    The single governed entry point every agent calls.

    Returns a dict: {"text": ..., "tool_calls": [...] or None, "usage": {...}}
    tool_calls, when present, is a list of {"name": ..., "arguments": {...}}
    in a provider-agnostic shape, so router.py doesn't need to know which
    provider is behind this call.
    """
    start = time.time()

    if PROVIDER == "groq":
        result = _call_groq(prompt, system, tools, model or "llama-3.3-70b-versatile")
    elif PROVIDER == "openai":
        result = _call_openai(prompt, system, tools, model or "gpt-4o-mini")
    elif PROVIDER == "anthropic":
        result = _call_anthropic(prompt, system, tools, model or "claude-3-5-haiku-20241022")
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {PROVIDER}")

    latency = time.time() - start
    usage = result["usage"]
    price = PRICING.get(PROVIDER, {"input": 0, "output": 0})
    cost = (usage["input_tokens"] / 1000 * price["input"]) + (usage["output_tokens"] / 1000 * price["output"])

    _log_usage({
        "provider": PROVIDER,
        "model": result["model"],
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "latency_sec": round(latency, 3),
        "cost_usd_est": round(cost, 6),
    })

    result["usage"]["cost_usd_est"] = round(cost, 6)
    result["usage"]["latency_sec"] = round(latency, 3)
    return result


def _call_groq(prompt, system, tools, model):
    """Groq uses the OpenAI SDK format, just pointed at a different base_url."""
   from openai import OpenAI

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets["GROQ_API_KEY"]
        except Exception:
            api_key = None

    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=api_key,
    )

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    kwargs = {"model": model, "messages": messages}
    if tools:
        kwargs["tools"] = [_to_openai_tool_schema(t) for t in tools]

    resp = client.chat.completions.create(**kwargs)
    choice = resp.choices[0]

    tool_calls = None
    if choice.message.tool_calls:
        tool_calls = [
            {"name": tc.function.name, "arguments": json.loads(tc.function.arguments)}
            for tc in choice.message.tool_calls
        ]

    return {
        "text": choice.message.content,
        "tool_calls": tool_calls,
        "model": model,
        "usage": {
            "input_tokens": resp.usage.prompt_tokens,
            "output_tokens": resp.usage.completion_tokens,
        },
    }


def _call_openai(prompt, system, tools, model):
    from openai import OpenAI
    client = OpenAI()

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    kwargs = {"model": model, "messages": messages}
    if tools:
        kwargs["tools"] = [_to_openai_tool_schema(t) for t in tools]

    resp = client.chat.completions.create(**kwargs)
    choice = resp.choices[0]

    tool_calls = None
    if choice.message.tool_calls:
        tool_calls = [
            {"name": tc.function.name, "arguments": json.loads(tc.function.arguments)}
            for tc in choice.message.tool_calls
        ]

    return {
        "text": choice.message.content,
        "tool_calls": tool_calls,
        "model": model,
        "usage": {
            "input_tokens": resp.usage.prompt_tokens,
            "output_tokens": resp.usage.completion_tokens,
        },
    }


def _call_anthropic(prompt, system, tools, model):
    import anthropic
    client = anthropic.Anthropic()

    kwargs = {
        "model": model,
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    if tools:
        kwargs["tools"] = [_to_anthropic_tool_schema(t) for t in tools]

    resp = client.messages.create(**kwargs)

    text_parts = [b.text for b in resp.content if b.type == "text"]
    tool_calls = [
        {"name": b.name, "arguments": b.input}
        for b in resp.content if b.type == "tool_use"
    ] or None

    return {
        "text": "".join(text_parts) if text_parts else None,
        "tool_calls": tool_calls,
        "model": model,
        "usage": {
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
        },
    }


def _to_openai_tool_schema(spec):
    return {"type": "function", "function": {
        "name": spec["name"], "description": spec["description"], "parameters": spec["parameters"],
    }}


def _to_anthropic_tool_schema(spec):
    return {"name": spec["name"], "description": spec["description"], "input_schema": spec["parameters"]}


if __name__ == "__main__":
    print(f"Provider configured: {PROVIDER}")
    try:
        result = call_llm("Say 'PharmaSense AI LLM connection working' and nothing else.")
        print("Response:", result["text"])
        print("Usage:", result["usage"])
    except Exception as e:
        print(f"Error: {e}")
        print("\nMake sure you've created a .env file (copy .env.example) with a real API key.")
