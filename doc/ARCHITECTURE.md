# PharmaSense AI — Architecture & Trade-offs

## 1. What this system does

PharmaSense AI is a multi-agent GenAI assistant for a fictional pharma R&D and clinical
operations team. It routes natural-language questions to one of five specialist agents,
grounds answers in real structured and unstructured data, and can classify and escalate
adverse-event safety signals autonomously.

## 2. Five-layer architecture

| Layer | What it does | Technology used | Reference-stack equivalent |
|---|---|---|---|
| **Application** | Chat UI the user interacts with | Streamlit | Dataiku Agent Hub app |
| **Orchestration** | Router classifies intent, fans out to specialists, Report Writer merges results | Hand-rolled Python router (`router.py`) | Dataiku Agent Hub orchestration / LangGraph |
| **Agent + Tool** | 5 specialist agents, each with its own instructions + tools | Plain Python functions (`tools.py`) | Dataiku LLM Mesh tool calling / LangChain |
| **Retrieval** | Embeddings + vector search over research documents | sentence-transformers (`all-MiniLM-L6-v2`) + FAISS | Snowflake Cortex Search |
| **Data** | 7 structured + unstructured tables | SQLite (`pharmasense.db`) | Snowflake / Postgres |

Each layer is independently swappable — the pattern (not the specific product) is what
makes this production-style: the Data layer could become Postgres, the Retrieval layer
could become pgvector, and neither change touches the Orchestration or Agent layers above
them.

## 3. Orchestration patterns implemented

Three patterns are demonstrated, matching Step 6 of the project brief:

1. **Single-agent tool use** — a structured question ("Which Phase II oncology trials are
   below 60% enrollment?") is routed directly to the Trial Data Analyst, which calls
   `sql_query_tool` and returns a grounded answer.
2. **Single-agent (RAG)** — a research question is routed to the Literature & Document
   Research agent, which calls `vector_search_tool` and returns cited passages.
3. **Parallel fan-out / fan-in** — a "full picture" question runs the Trial Data Analyst
   and Literature Research agent *simultaneously*, then the Report Writer merges both
   outputs into one report with a combined citation list.

Every routing decision is logged to `agent_run_log.jsonl`, giving a full audit trail of
which agent(s) handled each question and which tool(s) they called.

## 4. Guardrails and evaluation (Step 7)

- **PII redaction**: `redact_patient_ids()` strips patient-code-style identifiers before
  text reaches an LLM or is shown outside the AE Triage tool chain.
- **Prompt-injection screening**: `screen_for_prompt_injection()` flags retrieved document
  text containing instruction-like patterns (e.g. "ignore previous instructions") before
  it is trusted.
- **Medical-advice refusal**: `refuse_medical_advice()` detects out-of-scope
  treatment/dosing questions and redirects to a qualified clinician instead of answering.
- **Auto-escalation**: any adverse event marked "Serious" is escalated to a human reviewer
  automatically via `escalation_notifier_tool`, with no LLM judgment call in the loop for
  that specific rule.
- **Evaluation (rule-based router)**: a 25-question golden set spans SQL, RAG, AE-triage,
  similarity, and guardrail categories. Measured result: **24/25 (96%) pass rate**,
  perfectly consistent across repeated runs (fully deterministic).
- **Evaluation (LLM-driven router)**: the same golden set run against real LLM
  function-calling (Groq, `openai/gpt-oss-20b`, free tier) scores **18-21/22 (82-95%)**
  depending on the run — genuinely variable, because the model occasionally writes a
  flawed SQL query or skips a tool call on an ambiguous question. Added simple retry
  logic (retry the LLM call if every tool call it made returned an internal error), which
  measurably helps but does not eliminate the variance, since a retry can itself produce
  a different flawed output. This is a first-hand, measured demonstration of LLM
  non-determinism, not a code defect -- the rule-based version scores higher specifically
  *because* it has no non-determinism to begin with.

## 5. Alternative approaches considered and rejected

1. **Dataiku LLM Mesh + Snowflake Cortex (the reference stack)** — rejected for this build
   in favor of the open-source equivalents (SQLite, sentence-transformers, FAISS) to keep
   the project runnable locally with zero infrastructure cost or account setup, while
   preserving the exact same five-layer architecture. Trade-off: loses Dataiku's built-in
   governance/cost dashboards, which had to be replicated manually in `run_eval.py`.
2. **A framework-based orchestrator (LangGraph / CrewAI)** — rejected in favor of a
   hand-rolled Python router. Trade-off: a framework would handle state persistence and
   retries out of the box, but a hand-rolled router is fully transparent and easier to
   explain and debug line-by-line in an interview setting — every routing decision is
   plain, inspectable Python rather than framework-internal graph state.
3. **A validated cheminformatics similarity model (e.g. RDKit fingerprints)** for
   `compound_similarity_tool` — rejected in favor of a simple weighted-distance heuristic
   over molecular weight, solubility, toxicity score, and shared target protein. Trade-off:
   faster to build and fully explainable, but not chemically rigorous — noted as a real
   limitation, not a hidden one.

## 6. Current limitations (as of the LLM upgrade)

- **NL-to-SQL is now genuinely LLM-generated** rather than pattern-matched, which removes
  the earlier ceiling on question phrasing -- but it surfaced a real, specific issue during
  testing: the LLM initially wrote PostgreSQL-style cast syntax (`::float`) against a
  SQLite database, which failed. Fixed by explicitly stating the SQL dialect and giving a
  correct example in the router's system prompt -- a genuine, real-world prompt-engineering
  lesson, not a hypothetical one.
- **Groq's free tier has rate limits** (requests/tokens per minute) that a production
  deployment would need to account for with retries/backoff, which isn't implemented yet.
- **The evaluation's cost/latency numbers from the rule-based version used a simplified
  cost proxy**; the LLM version now logs real token counts and latency via
  `llm_usage_log.jsonl`, though Groq's free tier itself has $0 cost, so a paid-tier cost
  comparison (OpenAI/Anthropic) would need to be run separately for a realistic cost
  discussion.
- **The golden-set check is still exact-substring matching**, which remains stricter than
  production RAG evaluation (faithfulness/relevance scoring via RAGAS or similar).

## 7. What would change at 10x data volume or user load

- **Data layer**: SQLite would be replaced with Postgres or Snowflake — SQLite has no
  built-in concurrent-write support, which becomes a real constraint once multiple users
  or agents write simultaneously (e.g. concurrent escalation logging).
- **Retrieval layer**: FAISS's flat (brute-force) index would be replaced with an
  approximate-nearest-neighbor index (HNSW) or a managed vector store (pgvector,
  Pinecone) once the corpus grows past a few hundred thousand chunks, since flat search
  is O(n) per query.
- **Orchestration**: the hand-rolled router would need real state management (e.g.
  LangGraph) to handle longer multi-step agent conversations, retries, and partial
  failures gracefully — the current version has no retry logic.
- **Observability**: `agent_run_log.jsonl` (a flat file) would move to a proper logging
  pipeline (e.g. a time-series DB or logging service) to support real-time dashboards
  and alerting rather than manual file inspection.
