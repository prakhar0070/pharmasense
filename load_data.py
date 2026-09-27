import pandas as pd
import sqlite3
import os

CSV_DIR = "csv_data"
DB_PATH = "pharmasense.db"

TABLES = [
    "compounds", "clinical_trials", "trial_sites",
    "lab_results", "adverse_events", "research_documents",
    "agent_interaction_logs"
]

def load_all():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    dfs = {}
    for t in TABLES:
        df = pd.read_csv(f"{CSV_DIR}/{t}.csv")
        df.to_sql(t, conn, index=False)
        dfs[t] = df
        print(f"Loaded {t}: {len(df)} rows -> {DB_PATH}")
    conn.commit()
    return conn, dfs

def check_integrity(dfs):
    print("\n--- Referential integrity checks ---")
    issues = 0

    bad = set(dfs["adverse_events"]["trial_id"]) - set(dfs["clinical_trials"]["trial_id"])
    print(f"adverse_events.trial_id not in clinical_trials: {len(bad)}")
    issues += len(bad)

    bad = set(dfs["trial_sites"]["trial_id"]) - set(dfs["clinical_trials"]["trial_id"])
    print(f"trial_sites.trial_id not in clinical_trials: {len(bad)}")
    issues += len(bad)

    bad = set(dfs["clinical_trials"]["compound_id"]) - set(dfs["compounds"]["compound_id"])
    print(f"clinical_trials.compound_id not in compounds: {len(bad)}")
    issues += len(bad)

    bad = set(dfs["lab_results"]["compound_id"]) - set(dfs["compounds"]["compound_id"])
    print(f"lab_results.compound_id not in compounds: {len(bad)}")
    issues += len(bad)

    bad = set(dfs["adverse_events"]["site_id"]) - set(dfs["trial_sites"]["site_id"])
    print(f"adverse_events.site_id not in trial_sites: {len(bad)}")
    issues += len(bad)

    rd_ids = dfs["research_documents"]["compound_id"].dropna()
    bad = set(rd_ids) - set(dfs["compounds"]["compound_id"])
    print(f"research_documents.compound_id not in compounds: {len(bad)}")
    issues += len(bad)

    rd_tids = dfs["research_documents"]["trial_id"].dropna()
    bad = set(rd_tids) - set(dfs["clinical_trials"]["trial_id"])
    print(f"research_documents.trial_id not in clinical_trials: {len(bad)}")
    issues += len(bad)

    print(f"\nTotal orphaned foreign keys: {issues}")
    return issues

if __name__ == "__main__":
    conn, dfs = load_all()
    check_integrity(dfs)
    conn.close()