"""Database access for the intelligence layer (Milestone 2)."""
import os

import pandas as pd
from sqlalchemy import create_engine

# Same MySQL as the backend (host port 3307). Override with the ZWG_DB_URL environment variable.
DB_URL = os.getenv("ZWG_DB_URL", "mysql+pymysql://root:root@localhost:3307/zerowaste")
engine = create_engine(DB_URL)


def read_table(name: str, parse_dates=None) -> pd.DataFrame:
    return pd.read_sql(f"SELECT * FROM {name}", engine, parse_dates=parse_dates)
