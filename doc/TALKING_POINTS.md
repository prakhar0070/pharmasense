# PharmaSense AI — Interview Talking Points Cheat Sheet

*Review 5 minutes before any interview. Each answer references a real decision made while
building this project — not a general description.*

---

## Must-have skill: LLMs, prompt engineering, RAG & vector databases

**The decision I made:** I built the RAG layer using `sentence-transformers`
(`all-MiniLM-L6-v2`) for embeddings and FAISS for vector search, wrapped in a single
`vector_search_tool(query, k)` function that every agent calls the same way.

**Why (trade-off considered):** I chose a local, free embedding model over a hosted API
(like OpenAI embeddings) so the RAG layer has zero per-query embedding cost and runs
fully offline once built — important for a portfolio project I want to demo without
worrying about API bills. The trade-off is that `all-MiniLM-L6-v2` is a smaller, less
powerful model than something like OpenAI's `text-embedding-3-large` — I'd upgrade to
that for a production system with a real budget, since it improves retrieval quality
on ambiguous queries.

**Proof point:** A query for "JAK2 inhibitors and cardiotoxicity" correctly retrieved
the compound VLX-1000's literature review even though the passage didn't contain those
exact words together — that's genuine semantic matching, not keyword search.

---

## Must-have skill: Agent tooling & orchestration

**The decision I made:** I built two versions of the router deliberately: a rule-based
version first (`router.py`) to validate the orchestration pattern at zero cost, then
upgraded to genuine LLM-driven function-calling (`llm_router.py`) using Groq's free tier,
where the model itself sees all tool specs and decides which to call and with what
arguments.

**Why (trade-off considered):** Building the rule-based version first let me validate the
orchestration pattern (single-agent, parallel fan-out, Report Writer merge) cheaply and
quickly. Once that was proven, swapping in real LLM tool-calling was a contained change --
only the routing logic changed, not the tools or agents underneath. This staged approach
is itself a defensible engineering decision: prove the pattern, then add the expensive/
complex part.

**Proof point:** Running the same 22-question golden set against the LLM router multiple
times produced different pass rates each time (82%, then 95%, then 82% again) with
DIFFERENT questions failing each run — direct, measured proof of LLM non-determinism, not
a hypothesis. I added retry logic in response (retry the LLM call if every tool call it
made returned an internal error), which measurably helps but doesn't eliminate the
variance. In a production system with a paid, more capable model (GPT-4o, Claude) I'd
expect meaningfully higher consistency, plus I'd add output validation before executing
any LLM-generated SQL.

---

## Must-have skill: Building AI Agents; writing multi-page agent instructions; defining tools

**The decision I made:** I wrote a full instructions.md for each of 5 specialist agents
(identity & scope, tools, when-to-use-which-tool, output format, escalation/refusal
rules, worked examples), plus a validated JSON tool spec for every tool.

**Why (trade-off considered):** I gave each agent explicit refusal rules — e.g. the
Literature agent will not give medical advice even if the retrieved documents contain
clinical language — because a portfolio project that never says "I can't do that" isn't
demonstrating real guardrail design. The trade-off is more upfront writing time, but it's
exactly what the job post asks for directly ("write multi-page agent instructions").

**Proof point:** The Adverse Event Triage agent's instructions require it to escalate
ANY event marked "Serious," with no exceptions — and `ae_severity_classifier_tool` +
`escalation_notifier_tool` implement that rule in code, tested against both
serious and routine cases.

---

## Must-have skill: Evaluating tech choices, architecture, and trade-offs

**The decision I made:** I built a 25-question golden set spanning SQL, RAG, AE-triage,
similarity, and guardrail categories, and a runner that scores pass rate, latency, and
estimated cost per run.

**Why (trade-off considered):** I used exact-substring matching for correctness rather
than a fuzzier faithfulness score, because it's simple and fast to build — but this
caught a real limitation during testing: a semantically-correct RAG answer failed the
check because it didn't repeat an exact keyword. That's a genuine, first-hand example of
why production RAG systems use faithfulness/relevance scoring (like RAGAS) instead of
exact-match — I didn't just read about that trade-off, I hit it.

**Proof point:** 24/25 (96%) pass rate, ~0.6s average latency per question, on a system
with zero framework dependencies for the orchestration layer.

---

## Must-have skill: Dataiku / LLM Mesh & Snowflake (optional/nice-to-have)

**The decision I made:** I wrapped every LLM call behind a single governed function,
`call_llm(prompt, system, tools, model)`, in `llm.py` — every agent calls this same entry
point, and it supports swapping providers (OpenAI, Anthropic, or Groq) via one config
line, with per-call token/latency/cost logging built in from day one.

**Why (trade-off considered):** I chose Groq as my actual provider for this project
because it offers a genuinely free tier (no credit card, no expiring trial credit) with
fast inference and OpenAI-compatible function-calling — letting me build and fully test
real agentic behavior at zero cost. The trade-off is Groq's free tier only exposes
open-weight models (like `openai/gpt-oss-20b`), not frontier proprietary models — for a
production system I'd swap in GPT-4o or Claude via the same `call_llm()` interface with
no other code changes, since the provider is fully abstracted behind that one function.

**Proof point:** `llm_usage_log.jsonl` shows real, per-call token counts and latency for
every question asked — genuine observability, not an estimate.

---

## Rehearsal order (as the guide suggests)

1. **Problem** — pharma R&D/clinical ops team needs one assistant across structured data,
   literature, and safety triage instead of three separate tools.
2. **Data** — 7 linked tables, verified zero orphaned foreign keys.
3. **Architecture** — walk through the 5-layer table in ARCHITECTURE.md.
4. **Live demo** — run through all 4 example questions in the Streamlit app, one per
   orchestration pattern.
5. **Results** — 96% golden-set pass rate, real citations, real escalation logging.
6. **What I'd improve next** — swap the rule-based router for real LLM-driven tool-calling
   (OpenAI/Anthropic function calling), and adopt faithfulness-based RAG scoring (RAGAS)
   instead of exact-match.
