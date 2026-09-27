"""
Stage 7 (LLM-upgraded): Demo UI for PharmaSense AI, now using real LLM-driven routing.

Run with:
    python -m streamlit run streamlit_app_llm.py
"""

import streamlit as st
from llm_router import llm_route

st.set_page_config(page_title="PharmaSense AI", page_icon="🧬", layout="centered")

st.title("🧬 PharmaSense AI")
st.caption("Multi-agent GenAI assistant — now with real LLM-driven tool routing (Groq)")

EXAMPLES = {
    "Trial enrollment (SQL agent)": "Which Phase II oncology trials are below 60% enrollment right now?",
    "Literature search (RAG agent)": "What has our internal research said about JAK2 inhibitors and cardiotoxicity?",
    "Compound similarity": "What compounds are similar to CMP-0001?",
    "Full picture (parallel multi-agent)": "Give me the full picture on DKU-1011: trial status and research findings.",
}

st.subheader("Try an example")
cols = st.columns(2)
selected_question = None
for i, (label, question) in enumerate(EXAMPLES.items()):
    if cols[i % 2].button(label, use_container_width=True):
        selected_question = question

st.divider()

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if msg.get("meta"):
            st.caption(msg["meta"])

typed_question = st.chat_input("Ask PharmaSense AI a question...")
question = selected_question or typed_question

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        with st.spinner("LLM is deciding which tool(s) to call..."):
            response = llm_route(question, session_id="streamlit-llm-session")
        result = response.get("result")
        answer_text = result if isinstance(result, str) else str(result)
        meta = f"agent: {response.get('agent')} · tool(s): {response.get('tool_used')}"

        st.write(answer_text)
        st.caption(meta)

    st.session_state.messages.append({"role": "assistant", "content": answer_text, "meta": meta})

with st.sidebar:
    st.subheader("About this demo")
    st.write(
        "PharmaSense AI now uses a real LLM (via Groq, free tier) to decide which "
        "specialist tool(s) to call for each question -- genuine function-calling, "
        "not hardcoded rules."
    )
    st.write("Architecture: SQLite + FAISS + LLM-driven router (Groq openai/gpt-oss-20b).")
    if st.button("Clear conversation"):
        st.session_state.messages = []
        st.rerun()
