"""
Stage 2 (properly done): The governed LLM access layer.

Every agent calls call_llm() instead of hitting an API directly.
"""

import os
import json
import time
from dotenv import load_dotenv

load_dotenv()

PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()
USAGE_LOG_PATH = "llm_usage_log.jsonl"

PRICING = {
    "openai": {"input": 0.00015, "output": 0.0006},
    "anthropic": {"input": 0.0008, "output": 0.004},
    "groq": {"input": 0.0, "output": 0.0},
}


def _log_usage(entry: dict):
    try:
        with open(USAGE_LOG_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def call_llm(prompt: str, system: str = "", tools: list = None, model: str = None):
    start = time.time()

    if PROVIDER == "groq":
        result = _call_groq(prompt, system, tools, model)
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
    import streamlit as st
    from openai import OpenAI

    # Fallback if an invalid/OpenAI model name was passed from upstream
    valid_groq_models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"]
    if not model or model not in valid_groq_models:
        model = "llama-3.3-70b-versatile"

    api_key = os.getenv("GROQ_API_KEY") or st.secrets.get("GROQ_API_KEY")

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
    import streamlit as st
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key)

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
    import streamlit as st
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY") or st.secrets.get("ANTHROPIC_API_KEY")
    client = anthropic.Anthropic(api_key=api_key)

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
    return {
        "type": "function",
        "function": {
            "name": spec["name"],
            "description": spec["description"],
            "parameters": spec["parameters"],
        },
    }


def _to_anthropic_tool_schema(spec):
    return {
        "name": spec["name"],
        "description": spec["description"],
        "input_schema": spec["parameters"],
    }


if __name__ == "__main__":
    print(f"Provider configured: {PROVIDER}")
    try:
        result = call_llm("Say 'PharmaSense AI LLM connection working' and nothing else.")
        print("Response:", result["text"])
        print("Usage:", result["usage"])
    except Exception as e:
        print(f"Error: {e}")
