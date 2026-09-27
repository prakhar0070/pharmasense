"""
Stage 2/6 (upgraded): LLM-driven Router.

Replaces the rule-based classify_intent()/trial_data_analyst() with real
LLM function-calling: the LLM sees all available tools and decides which
one(s) to call, with what arguments, based on the actual question -- not
keyword matching. This is genuine "Agentic AI" per the guide's definition.
"""

import json
from llm import call_llm
from tools import (
    sql_query_tool,
    ae_severity_classifier_tool,
    compound_similarity_tool,
    citation_formatter_tool,
    escalation_notifier_tool,
)
from search_tool import vector_search_tool
from router import report_writer, log_step  # reuse the working Report Writer + logger

with open("agents/tool_specs.json") as f:
    TOOL_SPECS = json.load(f)

# Map each tool name to its actual Python function
TOOL_FUNCTIONS = {
    "sql_query_tool": sql_query_tool,
    "vector_search_tool": vector_search_tool,
    "ae_severity_classifier_tool": ae_severity_classifier_tool,
    "compound_similarity_tool": compound_similarity_tool,
    "citation_formatter_tool": citation_formatter_tool,
    "escalation_notifier_tool": escalation_notifier_tool,
}

ROUTER_SYSTEM_PROMPT = """You are the Router/Planner for PharmaSense AI, a multi-agent \
system for pharma R&D and clinical operations. Given a user's question, decide which \
tool(s) to call to answer it. You may call more than one tool if the question needs \
both structured data (SQL) and literature/research context -- this is the "full \
picture" pattern. Always call at least one tool before answering; never guess an answer \
without calling a tool first.

For sql_query_tool, write a real, safe, parameterized SELECT query against this SQLite \
database (SQLite syntax only -- do NOT use PostgreSQL-style casts like ::float; for \
float division, multiply one operand by 1.0 instead, e.g. (actual_enrollment * 1.0 / \
target_enrollment) < 0.6). Schema:
- compounds(compound_id, compound_name, target_protein, therapeutic_area, molecular_weight_da, solubility_mg_ml, toxicity_score)
- clinical_trials(trial_id, compound_id, therapeutic_area, trial_phase, target_enrollment, actual_enrollment)
- trial_sites(site_id, trial_id, ...)
- adverse_events(event_id, trial_id, site_id, severity, seriousness, causality_assessment, ...)
"""


def llm_route(question: str, session_id: str = "llm-session", max_retries: int = 2):
    """
    Real LLM-driven routing: the model sees the tool specs and decides what to call.

    LLMs are non-deterministic -- the same question can occasionally produce a
    malformed or failing tool call on one run and a correct one on the next.
    max_retries adds simple retry logic: if every executed tool call comes back
    with an error, retry the whole LLM call up to max_retries times before
    giving up. This is standard practice for production agentic systems.
    """
    tool_list = [
        {"name": name, "description": spec["description"], "parameters": spec["parameters"]}
        for name, spec in TOOL_SPECS.items()
    ]

    last_result = None
    for attempt in range(max_retries + 1):
        response = call_llm(
            prompt=question,
            system=ROUTER_SYSTEM_PROMPT,
            tools=tool_list,
        )

        log_step(session_id, "llm_decision", {
            "question": question,
            "attempt": attempt + 1,
            "tool_calls": response["tool_calls"],
            "usage": response["usage"],
        })

        if not response["tool_calls"]:
            return {"agent": "LLM Router", "tool_used": None, "result": response["text"]}

        results = {}
        for call in response["tool_calls"]:
            fn = TOOL_FUNCTIONS.get(call["name"])
            if fn is None:
                results[call["name"]] = {"error": f"Unknown tool: {call['name']}"}
                continue
            try:
                tool_result = fn(**call["arguments"])
                results[call["name"]] = tool_result
            except Exception as e:
                results[call["name"]] = {"error": str(e)}

        log_step(session_id, "tools_executed", {"tools": list(results.keys())})

        # Check if every result came back with an internal error -- if so, and
        # we have retries left, try again (the LLM may write a working query
        # on the next attempt).
        all_failed = all(isinstance(r, dict) and "error" in r for r in results.values())
        last_result = results
        if not all_failed or attempt == max_retries:
            break
        log_step(session_id, "retry", {"attempt": attempt + 1, "reason": "all tool calls errored"})

    results = last_result
    if len(results) > 1:
        sections = {name: {"result": r} for name, r in results.items()}
        merged = report_writer(sections, question)
        return {"agent": "Report Writer (LLM-routed)", "tool_used": list(results.keys()), "result": merged}

    tool_name = list(results.keys())[0]
    return {"agent": "LLM Router", "tool_used": tool_name, "result": results[tool_name]}


if __name__ == "__main__":
    test_questions = [
        "Which Phase II oncology trials are below 60% enrollment right now?",
        "What has our internal research said about JAK2 inhibitors and cardiotoxicity?",
    ]
    for q in test_questions:
        print("=" * 70)
        print("Q:", q)
        r = llm_route(q, session_id="llm-test")
        print(f"Agent: {r['agent']} | Tool(s): {r['tool_used']}")
        print(json.dumps(r["result"], indent=2, default=str)[:500])
        print()
