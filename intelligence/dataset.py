"""Build the daily modelling table (one row per store, SKU and day) from MySQL.

Columns
  qty_sold      observed sales (NaN when the POS feed is missing for that day)
  stockout      True when end-of-day stock is 0, so observed sales may understate demand
  true_demand   real demand from the simulation (evaluation only, a real retailer never has this)
plus calendar, price, promotion, weather, event and product features.

Run for a quick summary:  python intelligence/dataset.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

from db import read_table

ROOT = Path(__file__).resolve().parents[1]
TRUTH_FILE = ROOT / "data-pipeline" / "data" / "truth" / "ground_truth_demand.csv"


def build_panel() -> pd.DataFrame:
    snaps = read_table("inventory_snapshots", ["snapshot_date"])
    sales = read_table("sales", ["sale_date"])
    promos = read_table("promotions", ["start_date", "end_date"])
    weather = read_table("weather", ["weather_date"])
    events = read_table("events", ["event_date"])
    stores = read_table("stores")
    products = read_table("products")

    # backbone: every store x SKU x day. A shop that joined later simply has empty (NaN) rows before it started.
    snaps = snaps.rename(columns={"snapshot_date": "date", "on_hand_qty": "on_hand_end"})
    grid = pd.MultiIndex.from_product([sorted(snaps["date"].unique()), sorted(snaps["store_id"].unique()),
                                       sorted(snaps["sku_id"].unique())], names=["date", "store_id", "sku_id"]).to_frame(index=False)
    panel = grid.merge(snaps[["date", "store_id", "sku_id", "on_hand_end"]], on=["date", "store_id", "sku_id"], how="left")
    panel = panel.merge(
        sales.rename(columns={"sale_date": "date"})[["date", "store_id", "sku_id", "qty_sold", "unit_price"]],
        on=["date", "store_id", "sku_id"], how="left")

    # promotions are planned in advance, so they are known for future days too
    promo_days = []
    for r in promos.itertuples():
        for d in pd.date_range(r.start_date, r.end_date):
            promo_days.append((d, r.store_id, r.sku_id, float(r.discount_pct)))
    promo_df = pd.DataFrame(promo_days, columns=["date", "store_id", "sku_id", "discount_pct"])
    panel = panel.merge(promo_df.drop_duplicates(["date", "store_id", "sku_id"]),
                        on=["date", "store_id", "sku_id"], how="left")
    panel["discount_pct"] = panel["discount_pct"].fillna(0.0)

    panel = panel.merge(stores[["store_id", "city", "type"]].rename(columns={"type": "store_type"}),
                        on="store_id", how="left")
    panel = panel.merge(products[["sku_id", "category", "shelf_life_days", "base_price"]], on="sku_id", how="left")
    panel = panel.merge(
        weather.rename(columns={"weather_date": "date"})[["date", "city", "temp_c", "rain_mm"]],
        on=["date", "city"], how="left")
    ev = (events.rename(columns={"event_date": "date"}).groupby(["date", "city"], as_index=False)["expected_impact"].max()
          .rename(columns={"expected_impact": "event_impact"}))
    panel = panel.merge(ev, on=["date", "city"], how="left")
    panel["event_impact"] = panel["event_impact"].fillna(1.0)

    panel = panel.sort_values(["store_id", "sku_id", "date"]).reset_index(drop=True)
    panel["unit_price"] = panel.groupby(["store_id", "sku_id"])["unit_price"].ffill().bfill()
    panel["dow"] = panel["date"].dt.dayofweek
    panel["month"] = panel["date"].dt.month
    panel["is_weekend"] = panel["dow"] >= 5
    panel["stockout"] = panel["on_hand_end"] == 0

    if TRUTH_FILE.exists():
        truth = pd.read_csv(TRUTH_FILE, parse_dates=["sale_date"]).rename(columns={"sale_date": "date"})
        panel = panel.merge(truth[["date", "store_id", "sku_id", "true_demand"]],
                            on=["date", "store_id", "sku_id"], how="left")
    else:
        panel["true_demand"] = np.nan
    return panel


if __name__ == "__main__":
    p = build_panel()
    print(f"Panel: {len(p):,} rows | {p['store_id'].nunique()} stores x {p['sku_id'].nunique()} SKUs | "
          f"{p['date'].min().date()} to {p['date'].max().date()}")
    print(f"Missing qty_sold (delayed feed): {int(p['qty_sold'].isna().sum())} rows")
    print(f"Stockout days (end stock = 0): {p['stockout'].mean() * 100:.1f}% of rows")
    print("\nColumns:", ", ".join(p.columns))
