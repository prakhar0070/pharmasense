"""
Stage 5: Router / Planner orchestration.

Demonstrates three patterns from the guide's Step 6:
  1. Single-agent tool use       (one specialist handles the whole question)
  2. Sequential hand-off         (Trial Data Analyst -> Report Writer)
  3. Parallel fan-out / fan-in   (Trial Data Analyst + Literature Research run
                                   together, then Report Writer merges them)

This is a hand-rolled router (no framework) so every decision is visible and
easy to explain in an interview -- exactly what the guide recommends.
"""

import json
import re
from datetime import datetime

from tools import (
    sql_query_tool,
    ae_severity_classifier_tool,
    compound_similarity_tool,
    citation_formatter_tool,
    escalation_notifier_tool,
)
from search_tool import vector_search_tool

LOG_PATH = "agent_run_log.jsonl"


def log_step(session_id, step_name, detail):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "session_id": session_id,
        "step": step_name,
        "detail": detail,
    }
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


# ---------------------------------------------------------------------------
# Specialist agent functions (each wraps the tools it's allowed to call)
# ---------------------------------------------------------------------------

def trial_data_analyst(question: str):
    """Small rule-based NL->SQL for demo purposes; a real production build would
    use an LLM here to generate SQL dynamically instead of matching patterns by
    hand. This covers the guide's example questions plus a few common variants
    -- enough to demo the pattern, not a full NL2SQL engine."""
    q = question.lower()

    if "enrollment" in q and "phase ii" in q and "oncology" in q and "below" in q:
        result = sql_query_tool(
            "SELECT trial_id, therapeutic_area, trial_phase, target_enrollment, actual_enrollment "
            "FROM clinical_trials WHERE trial_phase = ? AND therapeutic_area = ? "
            "AND (actual_enrollment * 1.0 / target_enrollment) < 0.6",
            ("Phase II", "Oncology"),
        )
        return {"agent": "Trial Data Analyst", "tool_used": "sql_query_tool", "result": result}

    trial_match = re.search(r"TRL-\d{4,}", question, re.IGNORECASE)
    if trial_match and ("site" in q):
        result = sql_query_tool(
            "SELECT * FROM trial_sites WHERE trial_id = ?", (trial_match.group(0),)
        )
        return {"agent": "Trial Data Analyst", "tool_used": "sql_query_tool", "result": result}

    if trial_match and ("target enrollment" in q or "actual enrollment" in q):
        result = sql_query_tool(
            "SELECT trial_id, target_enrollment, actual_enrollment FROM clinical_trials WHERE trial_id = ?",
            (trial_match.group(0),),
        )
        return {"agent": "Trial Data Analyst", "tool_used": "sql_query_tool", "result": result}

    if "phase iii" in q and "which" in q:
        result = sql_query_tool(
            "SELECT trial_id, therapeutic_area, trial_phase FROM clinical_trials WHERE trial_phase = ?",
            ("Phase III",),
        )
        return {"agent": "Trial Data Analyst", "tool_used": "sql_query_tool", "result": result}

    # Generic fallback: look up by real compound_id (always CMP-XXXX in this dataset)
    match = re.search(r"CMP-\d{4}", question, re.IGNORECASE)
    if match:
        cid = match.group(0)
        result = sql_query_tool(
            "SELECT * FROM compounds WHERE compound_id = ?", (cid,)
        )
        return {"agent": "Trial Data Analyst", "tool_used": "sql_query_tool", "result": result}

    # Also try matching a compound_name (e.g. "DKU-1011", "VLX-1000", "AGN-1045")
    # mentioned in the question, then pull its trial status.
    name_match = re.search(r"\b[A-Z]{2,4}-\d{3,4}\b", question)
    if name_match:
        candidate = name_match.group(0)
        result = sql_query_tool(
            "SELECT t.trial_id, t.trial_phase, t.target_enrollment, t.actual_enrollment "
            "FROM clinical_trials t JOIN compounds c ON t.compound_id = c.compound_id "
            "WHERE c.compound_name = ?",
            (candidate,),
        )
        if result.get("row_count", 0) > 0:
            return {"agent": "Trial Data Analyst", "tool_used": "sql_query_tool", "result": result}
        else:
            return {"agent": "Trial Data Analyst", "tool_used": "sql_query_tool",
                    "result": {"note": f"{candidate} has no associated clinical trials in the database."}}

    # Last-resort fallback: total counts for "how many X" questions
    count_map = {
        "clinical trial": "clinical_trials", "compound": "compounds",
        "adverse event": "adverse_events", "research document": "research_documents",
    }
    if "how many" in q:
        for phrase, table in count_map.items():
            if phrase in q:
                result = sql_query_tool(f"SELECT COUNT(*) as total FROM {table}")
                return {"agent": "Trial Data Analyst", "tool_used": "sql_query_tool", "result": result}

    return {"agent": "Trial Data Analyst", "tool_used": None, "result": {"note": "No structured match rule fired for this question -- in production this would fall through to an LLM-generated SQL query."}}


def literature_research(question: str):
    passages = vector_search_tool(question, k=3)
    citations = citation_formatter_tool(passages)
    return {
        "agent": "Literature & Document Research",
        "tool_used": "vector_search_tool",
        "result": {"passages": passages, "citations": citations},
    }


def ae_triage(severity: str, seriousness: str, causality: str, event_id: str, trial_id: str):
    classification = ae_severity_classifier_tool(severity, seriousness, causality)
    escalation = None
    if classification["escalate"]:
        escalation = escalation_notifier_tool(
            event_id=event_id, trial_id=trial_id,
            priority=classification["priority"], reason=classification["reason"],
        )
    return {"agent": "Adverse Event Triage", "tool_used": "ae_severity_classifier_tool", "result": {
        "classification": classification, "escalation": escalation,
    }}


def compound_similarity_agent(compound_id: str):
    result = compound_similarity_tool(compound_id)
    return {"agent": "Compound Similarity", "tool_used": "compound_similarity_tool", "result": result}


def report_writer(sections: dict, question: str):
    """Merges outputs from multiple agents into one final report, per its instructions.md."""
    lines = [f"# Answer: {question}\n"]
    all_sources = []
    for section_title, payload in sections.items():
        lines.append(f"## {section_title}")
        lines.append(f"```\n{json.dumps(payload['result'], indent=2, default=str)[:1000]}\n```")
        if "citations" in payload.get("result", {}):
            all_sources.append(payload["result"]["citations"])
    if all_sources:
        lines.append("## Sources")
        lines.extend(all_sources)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Router / Planner
# ---------------------------------------------------------------------------

def classify_intent(question: str):
    """Rule-based intent classifier. A real system would use an LLM for this;
    the pattern (route -> specialist(s) -> merge) is what matters."""
    q = question.lower()
    intents = []
    if any(w in q for w in ["enrollment", "phase", "trial status", "site"]):
        intents.append("trial_data")
    if any(w in q for w in ["research", "literature", "study said", "found that", "what has"]):
        intents.append("literature")
    if any(w in q for w in ["adverse event", "triage", "serious", "side effect"]):
        intents.append("ae_triage")
    if any(w in q for w in ["similar", "comparable", "alternative compound"]):
        intents.append("similarity")
    if "full picture" in q or "everything" in q or ("trial" in q and "research" in q):
        intents = ["trial_data", "literature"]  # force parallel fan-out
    return intents or ["trial_data"]


def route(question: str, session_id: str = "demo-session"):
    intents = classify_intent(question)
    log_step(session_id, "intent_classified", {"question": question, "intents": intents})

    # Pattern 1: single-agent tool use
    if len(intents) == 1 and intents[0] == "trial_data":
        result = trial_data_analyst(question)
        log_step(session_id, "single_agent", result)
        return result

    if len(intents) == 1 and intents[0] == "literature":
        result = literature_research(question)
        log_step(session_id, "single_agent", result)
        return result

    if len(intents) == 1 and intents[0] == "similarity":
        match = re.search(r"(CMP-\d{4})", question, re.IGNORECASE)
        cid = match.group(1) if match else "CMP-0001"
        result = compound_similarity_agent(cid)
        log_step(session_id, "single_agent", result)
        return result

    # Pattern 3: parallel fan-out / fan-in (trial_data + literature together)
    if set(intents) == {"trial_data", "literature"}:
        trial_result = trial_data_analyst(question)
        lit_result = literature_research(question)
        log_step(session_id, "parallel_fanout", {"trial": trial_result, "literature": lit_result})

        merged = report_writer(
            {"Trial Status": trial_result, "Related Literature": lit_result},
            question,
        )
        log_step(session_id, "report_writer_merge", {"merged_length": len(merged)})
        return {"agent": "Report Writer", "tool_used": None, "result": merged}

    return {"agent": None, "tool_used": None, "result": {"error": "No matching orchestration pattern."}}


if __name__ == "__main__":
    print("=" * 70)
    print("PATTERN 1: Single-agent tool use")
    print("=" * 70)
    q1 = "Which Phase II oncology trials are below 60% enrollment right now?"
    r1 = route(q1, session_id="demo-1")
    print(f"Q: {q1}")
    print(json.dumps(r1, indent=2, default=str)[:600])

    print("\n" + "=" * 70)
    print("PATTERN 2: Single-agent (literature)")
    print("=" * 70)
    q2 = "What has our internal research said about JAK2 inhibitors and cardiotoxicity?"
    r2 = route(q2, session_id="demo-2")
    print(f"Q: {q2}")
    print(json.dumps(r2, indent=2, default=str)[:600])

    print("\n" + "=" * 70)
    print("PATTERN 3: Parallel fan-out / fan-in -> Report Writer merge")
    print("=" * 70)
    q3 = "Give me the full picture on this compound: trial status and research findings."
    r3 = route(q3, session_id="demo-3")
    print(f"Q: {q3}")
    print(r3["result"][:1200])

    print(f"\n\nFull run log written to {LOG_PATH}")
