"""Load the cleaned tables (data/clean/) into MySQL and verify the row counts.

Safe to re-run: the 7 simulation tables are emptied first, then reloaded.
Stores, products, weather and events are NOT touched.

Run from project root:  python data-pipeline/ingest/load_clean_data.py
"""
import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

CLEAN = Path(__file__).resolve().parents[1] / "data" / "clean"
DB_URL = os.getenv("ZWG_DB_URL", "mysql+pymysql://root:root@localhost:3307/zerowaste")
engine = create_engine(DB_URL)

# parents first, so foreign keys are satisfied
LOAD_ORDER = {
    "promotions": ["start_date", "end_date"],
    "prices": ["effective_date"],
    "batches": ["received_date", "expiry_date"],
    "receipts": ["received_date"],
    "sales": ["sale_date"],
    "waste": ["waste_date"],
    "inventory_snapshots": ["snapshot_date"],
}

with engine.begin() as conn:
    is_mysql = conn.dialect.name == "mysql"
    if is_mysql:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for table in LOAD_ORDER:
            conn.execute(text(f"TRUNCATE TABLE {table}"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))

    for table, date_cols in LOAD_ORDER.items():
        df = pd.read_csv(CLEAN / f"{table}.csv", parse_dates=date_cols)
        for c in date_cols:
            df[c] = df[c].dt.date
        df.to_sql(table, conn, if_exists="append", index=False, chunksize=2000, method="multi")
        print(f"  loaded {table:22s} {len(df):>7,} rows")

print("\nVerification (CSV rows vs MySQL rows):")
ok = True
with engine.connect() as conn:
    for table in LOAD_ORDER:
        expected = len(pd.read_csv(CLEAN / f"{table}.csv"))
        actual = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        flag = "OK" if expected == actual else "MISMATCH"
        ok &= expected == actual
        print(f"  {table:22s} csv={expected:>7,}  db={actual:>7,}  {flag}")
print("\nAll tables loaded correctly." if ok else "\nCheck the mismatches above.")
