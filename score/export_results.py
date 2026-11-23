"""
Phase 3: save each check's accuracy to results/accuracy_by_check.csv.

The figures are calculated in dbt (transform/models/scoring/), so this script
only copies the final table, score_accuracy_by_check, out of BigQuery into a
file that is committed to the repo. Every accuracy figure in the README can
then be traced to this file, and the file to code anyone can rerun:

    python generate/generate_data.py
    python load/load_raw.py
    cd transform; dbt build; cd ..
    python score/export_results.py

The file has no timestamp in it on purpose: rerunning on the same data gives a
byte-identical file, so git only shows a change when a number really changed.

Run from the project folder, with .venv active and .env loaded.
"""

import csv
import os
from pathlib import Path

import google.auth
from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv()
PROJECT = os.getenv("GCP_PROJECT_ID")
if not PROJECT:
    raise SystemExit("GCP_PROJECT_ID is missing from .env")

TABLE = f"{PROJECT}.asa_scoring.score_accuracy_by_check"
OUT_FILE = Path(__file__).resolve().parent.parent / "results" / "accuracy_by_check.csv"
N_CHECKS = 10

COLUMNS = [
    "check_name", "population", "flagged", "seeded_issues", "look_alikes",
    "tp", "fn", "fn_outside_population", "fp", "fp_look_alike", "fp_other", "tn",
    "precision", "recall", "false_positive_rate", "look_alike_fp_rate",
]

credentials, _ = google.auth.default()
print(f"Running as {getattr(credentials, 'service_account_email', 'your own Google login')}")
client = bigquery.Client(project=PROJECT, credentials=credentials)

rows = list(client.query(
    f"select {', '.join(COLUMNS)} from `{TABLE}` order by check_name"
).result())

# Refuse to write a partial file: a missing check would quietly drop out of the README.
if len(rows) != N_CHECKS:
    raise SystemExit(f"Expected {N_CHECKS} checks in {TABLE}, found {len(rows)}. Run dbt build first.")

OUT_FILE.parent.mkdir(exist_ok=True)
with open(OUT_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f, lineterminator="\n")
    writer.writerow(COLUMNS)
    for row in rows:
        # An empty rate (no look-alikes for that check, say) stays empty, never 0.
        writer.writerow(["" if row[c] is None else row[c] for c in COLUMNS])

print(f"Wrote {len(rows)} checks to {OUT_FILE.relative_to(OUT_FILE.parent.parent)}")
for row in rows:
    print(f"  {row['check_name']:<34} precision {row['precision']}  recall {row['recall']}"
          f"  FPR {row['false_positive_rate']}  look-alike FPR {row['look_alike_fp_rate']}")
