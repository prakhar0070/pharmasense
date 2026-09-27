"""
Evaluation runner for the LLM-driven router (llm_router.py).

Same golden set as run_eval.py, but now scored against real LLM decisions
instead of rule-based logic -- this checks whether the LLM chooses the
RIGHT tool for each question, not just whether a hardcoded rule fires.
"""

import json
import time
from llm_router import llm_route

GOLDEN_SET_PATH = "golden_set.json"
REPORT_PATH = "evaluation_report_llm.json"


def run_question(q):
    start = time.time()
    error = None
    result_text = ""
    tool_used = None

    try:
        r = llm_route(q["question"], session_id=f"eval-{q['id']}")
        tool_used = r.get("tool_used")
        result = r.get("result")
        result_text = result if isinstance(result, str) else json.dumps(result, default=str)
    except Exception as e:
        error = str(e)

    latency = time.time() - start

    passed = error is None and all(
        exp.lower() in result_text.lower() for exp in q["expected_contains"]
    )

    return {
        "id": q["id"],
        "category": q["category"],
        "passed": passed,
        "tool_used": tool_used,
        "latency_sec": round(latency, 3),
        "error": error,
    }


def run_all():
    with open(GOLDEN_SET_PATH) as f:
        golden_set = json.load(f)

    # Skip guardrail-category questions here -- those test the separate
    # guardrails.py module directly, not tool routing.
    testable = [q for q in golden_set if q["category"] != "guardrail"]

    results = []
    for q in testable:
        print(f"Running {q['id']} ({q['category']})...")
        results.append(run_question(q))

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    avg_latency = sum(r["latency_sec"] for r in results) / total
    failures = [r for r in results if not r["passed"]]

    report = {
        "total_questions": total,
        "passed": passed,
        "pass_rate": round(passed / total, 3),
        "avg_latency_sec": round(avg_latency, 3),
        "failures": failures,
        "all_results": results,
    }

    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\nLLM Router pass rate: {passed}/{total} ({report['pass_rate']*100:.1f}%)")
    print(f"Avg latency: {report['avg_latency_sec']}s per question")
    if failures:
        print(f"\nFailed questions ({len(failures)}):")
        for f_ in failures:
            print(f"  {f_['id']} ({f_['category']}): tool_used={f_['tool_used']}, error={f_['error']}")

    return report


if __name__ == "__main__":
    run_all()
