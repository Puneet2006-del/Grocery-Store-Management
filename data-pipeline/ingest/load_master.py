"""Validate and load master data (stores, products) into MySQL.

Safe to re-run: uses INSERT ... ON DUPLICATE KEY UPDATE.
Run from the project root:  python data-pipeline/ingest/load_master.py
"""
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
DB_URL = "mysql+pymysql://root:root@localhost:3307/zerowaste"

engine = create_engine(DB_URL)


def validate_stores(df: pd.DataFrame) -> None:
    assert df["store_id"].is_unique, "Duplicate store_id"
    assert df[["name", "city"]].notna().all().all(), "Missing store name/city"


def validate_products(df: pd.DataFrame) -> None:
    assert df["sku_id"].is_unique, "Duplicate sku_id"
    assert (df["shelf_life_days"] > 0).all(), "shelf_life_days must be > 0"
    assert (df["cost"] > 0).all(), "cost must be > 0"
    assert (df["base_price"] > df["cost"]).all(), "base_price must exceed cost"


def upsert(df: pd.DataFrame, table: str, key: str) -> None:
    cols = list(df.columns)
    col_list = ", ".join(cols)
    placeholders = ", ".join(f":{c}" for c in cols)
    updates = ", ".join(f"{c}=VALUES({c})" for c in cols if c != key)
    sql = text(
        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {updates}"
    )
    with engine.begin() as conn:
        conn.execute(sql, df.to_dict("records"))


def main() -> None:
    stores = pd.read_csv(RAW / "stores.csv")
    products = pd.read_csv(RAW / "products.csv")

    validate_stores(stores)
    validate_products(products)
    print("Validation passed.")

    upsert(stores, "stores", "store_id")
    upsert(products, "products", "sku_id")

    with engine.connect() as conn:
        n_stores = conn.execute(text("SELECT COUNT(*) FROM stores")).scalar()
        n_products = conn.execute(text("SELECT COUNT(*) FROM products")).scalar()
    print(f"Loaded. stores={n_stores}, products={n_products}")


if __name__ == "__main__":
    main()
