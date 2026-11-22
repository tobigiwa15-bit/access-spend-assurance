"""
Phase 2, step 1: load the generated CSVs into BigQuery, unchanged.

Every CSV in data/ becomes a table in the asa_raw dataset, with every column
loaded as text (STRING). The raw layer is a faithful copy of the source, like
importing a file into ACL with every field as character: nothing is converted,
so nothing is silently lost. dbt's staging models then give each column its
proper type, and that conversion is visible, tested code.

Why not let BigQuery guess the types? It would read a bank account number such
as 0123456789 as the integer 123456789 and drop the leading zero, which would
quietly break the "vendor bank account matches an employee's" check.

The answer key is loaded too, for scoring the checks in Phase 3. The agent
never gets access to asa_raw.

Rerunning replaces every table, so it is safe to run as often as you like.

Run from the project folder, with .venv active:
    python load/load_raw.py
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

DATASET = f"{PROJECT}.asa_raw"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Print who we are running as, so it's clear this is the builder service account.
credentials, _ = google.auth.default()
print(f"Running as {getattr(credentials, 'service_account_email', 'your own Google login')}")
client = bigquery.Client(project=PROJECT, credentials=credentials)

# Create the dataset if it doesn't exist. Same location as the payment monitor.
dataset = bigquery.Dataset(DATASET)
dataset.location = "US"
dataset.description = "Raw synthetic data, loaded as text exactly as generated"
client.create_dataset(dataset, exists_ok=True)

csv_files = sorted(DATA_DIR.glob("*.csv"))
if not csv_files:
    raise SystemExit("No CSVs in data/. Run python generate/generate_data.py first.")

for path in csv_files:
    # Read the header row to build a schema with every column as STRING.
    with open(path, newline="", encoding="utf-8") as f:
        header = next(csv.reader(f))
    schema = [bigquery.SchemaField(name, "STRING") for name in header]

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,                  # the header row
        schema=schema,
        write_disposition="WRITE_TRUNCATE",   # replace the table on every run
    )
    with open(path, "rb") as f:
        job = client.load_table_from_file(f, f"{DATASET}.{path.stem}", job_config=job_config)
    job.result()   # wait for the load to finish, and raise if it failed

    table = client.get_table(f"{DATASET}.{path.stem}")
    print(f"{path.stem:<16} {table.num_rows:>8,} rows loaded")
