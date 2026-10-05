"""Validate and load weather.csv and events.csv into MySQL. Safe to re-run.

Run from project root:  python data-pipeline/ingest/load_weather_events.py
"""
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
DB_URL = "mysql+pymysql://root:root@localhost:3307/zerowaste"
engine = create_engine(DB_URL)


def upsert(df: pd.DataFrame, table: str, keys: list[str]) -> None:
    cols = list(df.columns)
    placeholders = ", ".join(f":{c}" for c in cols)
    updates = ", ".join(f"{c}=VALUES({c})" for c in cols if c not in keys)
    sql = text(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {updates}"
    )
    with engine.begin() as conn:
        conn.execute(sql, df.to_dict("records"))


def main() -> None:
    weather = pd.read_csv(RAW / "weather.csv", parse_dates=["weather_date"])
    events = pd.read_csv(RAW / "events.csv", parse_dates=["event_date"])

    # --- validate
    assert not weather.duplicated(["weather_date", "city"]).any(), "Duplicate weather rows"
    assert weather["temp_c"].between(-5, 55).all(), "Temperature out of range"
    assert (weather["rain_mm"] >= 0).all(), "Negative rainfall"
    assert events["event_id"].is_unique, "Duplicate event_id"
    assert events["expected_impact"].between(0.5, 3.0).all(), "Impact out of range"
    print("Validation passed.")

    weather["weather_date"] = weather["weather_date"].dt.date
    events["event_date"] = events["event_date"].dt.date

    upsert(weather, "weather", ["weather_date", "city"])
    upsert(events, "events", ["event_id"])

    with engine.connect() as conn:
        n_w = conn.execute(text("SELECT COUNT(*) FROM weather")).scalar()
        n_e = conn.execute(text("SELECT COUNT(*) FROM events")).scalar()
    print(f"Loaded. weather={n_w}, events={n_e}")


if __name__ == "__main__":
    main()
