

import sqlite3
import pandas as pd
import json
from datetime import datetime

DB_PATH = "pharmasense.db"
ESCALATION_LOG = "escalations.log"


# ---------------------------------------------------------------------------
# 1. sql_query_tool
# ---------------------------------------------------------------------------
def sql_query_tool(query: str, params: tuple = ()):
    """
    Read-only, parameterized SQL tool.
    Refuses anything that isn't a SELECT, to keep agents from writing/deleting data.
    Always use params (?, ?, ...) instead of string-formatting values into query.
    """
    cleaned = query.strip().lower()
    if not cleaned.startswith("select"):
        return {"error": "Only SELECT statements are allowed through this tool."}

    forbidden = ["insert", "update", "delete", "drop", "alter", "attach", "pragma"]
    if any(word in cleaned for word in forbidden):
        return {"error": "Query contains a forbidden keyword."}

    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql(query, conn, params=params)
        conn.close()
        return {"rows": df.to_dict("records"), "row_count": len(df)}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# 2. ae_severity_classifier_tool
# ---------------------------------------------------------------------------
def ae_severity_classifier_tool(severity: str, seriousness: str, causality_assessment: str):
   
    severity = (severity or "").lower()
    seriousness = (seriousness or "").lower()
    causality = (causality_assessment or "").lower()

    escalate = False
    reason = []

    if seriousness == "serious":
        escalate = True
        reason.append("marked Serious")
    if severity == "severe":
        escalate = True
        reason.append("severity is Severe")
    if causality in ("related", "possibly related"):
        reason.append(f"causality: {causality_assessment}")

    priority = "HIGH" if escalate else ("MEDIUM" if severity == "moderate" else "LOW")

    return {
        "escalate": escalate,
        "priority": priority,
        "reason": "; ".join(reason) if reason else "Routine, no escalation criteria met.",
    }


# ---------------------------------------------------------------------------
# 3. compound_similarity_tool
# ---------------------------------------------------------------------------
def compound_similarity_tool(compound_id: str, top_n: int = 5):
 
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT * FROM compounds", conn)
    conn.close()

    if compound_id not in df["compound_id"].values:
        return {"error": f"compound_id {compound_id} not found."}

    target = df[df["compound_id"] == compound_id].iloc[0]

    def distance(row):
        num_dist = (
            abs(row["molecular_weight_da"] - target["molecular_weight_da"]) / 1000
            + abs(row["solubility_mg_ml"] - target["solubility_mg_ml"])
            + abs(row["toxicity_score"] - target["toxicity_score"]) * 10
        )
        bonus = 0
        if row["target_protein"] == target["target_protein"]:
            bonus -= 2
        if row["therapeutic_area"] == target["therapeutic_area"]:
            bonus -= 1
        return num_dist + bonus

    others = df[df["compound_id"] != compound_id].copy()
    others["similarity_distance"] = others.apply(distance, axis=1)
    top = others.sort_values("similarity_distance").head(top_n)

    return {
        "query_compound": target["compound_name"],
        "similar_compounds": top[[
            "compound_id", "compound_name", "target_protein",
            "therapeutic_area", "similarity_distance"
        ]].to_dict("records"),
    }


# ---------------------------------------------------------------------------
# 4. citation_formatter_tool
# ---------------------------------------------------------------------------
def citation_formatter_tool(passages: list):
   
    lines = []
    for i, p in enumerate(passages, start=1):
        lines.append(
            f"[{i}] {p['title']} (doc_id={p['doc_id']}, type={p['doc_type']}, date={p['date']})"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 5. escalation_notifier_tool
# ---------------------------------------------------------------------------
def escalation_notifier_tool(event_id: str, trial_id: str, priority: str, reason: str):
  
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event_id": event_id,
        "trial_id": trial_id,
        "priority": priority,
        "reason": reason,
        "status": "ESCALATED_TO_HUMAN_REVIEWER",
    }
    with open(ESCALATION_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


if __name__ == "__main__":
    print("=== Test 1: sql_query_tool ===")
    result = sql_query_tool(
        "SELECT trial_id, therapeutic_area, trial_phase, target_enrollment, actual_enrollment "
        "FROM clinical_trials WHERE trial_phase = ? AND therapeutic_area = ? "
        "AND (actual_enrollment * 1.0 / target_enrollment) < 0.6",
        ("Phase II", "Oncology"),
    )
    print(json.dumps(result, indent=2)[:800])

    print("\n=== Test 2: ae_severity_classifier_tool ===")
    print(ae_severity_classifier_tool("Severe", "Serious", "Related"))
    print(ae_severity_classifier_tool("Mild", "Non-serious", "Unrelated"))

    print("\n=== Test 3: compound_similarity_tool ===")
    print(json.dumps(compound_similarity_tool("CMP-0001", top_n=3), indent=2))

    print("\n=== Test 5: escalation_notifier_tool ===")
    print(escalation_notifier_tool("AE-00099", "TRL-0032", "HIGH", "marked Serious; severity is Severe"))
