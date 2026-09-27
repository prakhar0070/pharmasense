"""
Stage 7 (Streamlit version): Demo UI for PharmaSense AI.

Run with:
    streamlit run streamlit_app.py

Then it opens automatically in your browser at http://localhost:8501
"""

import streamlit as st
from router import route

st.set_page_config(page_title="PharmaSense AI", page_icon="🧬", layout="centered")

st.title("🧬 PharmaSense AI")
st.caption("Multi-agent GenAI assistant for R&D and clinical operations (portfolio demo)")

# Example questions -- one per orchestration pattern, matching the guide's examples
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

# Chat history in session state
if "messages" not in st.session_state:
    st.session_state.messages = []

# Render existing history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if msg.get("meta"):
            st.caption(msg["meta"])

# Handle either a typed question or an example button click
typed_question = st.chat_input("Ask PharmaSense AI a question...")
question = selected_question or typed_question

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        with st.spinner("Routing to the right agent..."):
            response = route(question, session_id="streamlit-session")
        result = response.get("result")
        answer_text = result if isinstance(result, str) else str(result)
        meta = f"agent: {response.get('agent')} · tool: {response.get('tool_used')}"

        st.write(answer_text)
        st.caption(meta)

    st.session_state.messages.append({"role": "assistant", "content": answer_text, "meta": meta})

with st.sidebar:
    st.subheader("About this demo")
    st.write(
        "PharmaSense AI routes natural-language questions to 5 specialist agents: "
        "Trial Data Analyst, Literature & Document Research, Adverse Event Triage, "
        "Compound Similarity, and Report Writer."
    )
    st.write("Architecture: SQLite + FAISS + rule-based router (LLM upgrade in progress).")
    if st.button("Clear conversation"):
        st.session_state.messages = []
        st.rerun()
