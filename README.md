# PharmaSense AI — Agentic GenAI + RAG Portfolio Project

A multi-agent GenAI assistant for pharma R&D and clinical operations. Routes
natural-language questions to 5 specialist agents, grounds answers in real
structured and unstructured data, and can autonomously triage adverse events.

Built as a portfolio project mapped to a Data Scientist / GenAI Consultant
job description. See `docs/ARCHITECTURE.md` for full architecture and
trade-offs, and `docs/TALKING_POINTS.md` for the interview narrative.

## Architecture

| Layer | Technology |
|---|---|
| Application | Streamlit |
| Orchestration | Hand-rolled Python router (rule-based + real LLM function-calling) |
| Agent + Tool | Plain Python functions, 5 specialist agents |
| Retrieval | sentence-transformers + FAISS |
| Data | SQLite (7 linked tables) |

## Setup

```bash
pip install -r requirements.txt
python load_data.py          # loads CSVs into pharmasense.db, checks integrity
python build_rag.py          # builds the vector search index
cp .env.example .env         # then fill in your own API key (Groq is free)
python llm.py                # test your LLM connection
python -m streamlit run streamlit_app_llm.py   # launch the live demo
```

## Evaluation

```bash
python run_eval.py           # rule-based router: 24/25 (96%) pass rate
python run_eval_llm.py       # LLM-driven router: ~82-95% (real LLM variance)
```

## Project structure

- `load_data.py`, `build_rag.py` — data + RAG pipeline setup
- `tools.py`, `search_tool.py` — the 6 agent tools
- `router.py` — rule-based orchestration (baseline)
- `llm_router.py`, `llm.py` — real LLM-driven orchestration
- `guardrails.py` — PII redaction, injection screening, refusal rules
- `agents/` — agent instruction briefs + tool specs
- `docs/` — architecture doc + interview talking points

All data is synthetic and fictional (no real compounds, trials, or patients).
