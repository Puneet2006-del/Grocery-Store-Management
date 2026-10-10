"""Shared data for the agents: stock, forecasts, risk, prices, stores and business rules.

Everything is read from MySQL once per run, as of the latest risk run (sku_risk.run_date).
"""
from dataclasses import dataclass, field
from math import asin, cos, radians, sin, sqrt

import numpy as np
import pandas as pd

from db import read_table

# Used when a rule is missing from the business_rules table
RULE_DEFAULTS = {
    "service_level_target": "0.95", "min_confidence": "0.50", "order_pack_size": "5",
    "spoilage_trigger_pct": "15", "max_markdown_pct": "50", "markdown_steps": "10,20,30,40,50",
    "min_price_over_cost_pct": "5", "markdown_uplift_per_pct": "0.03", "min_transfer_qty": "10",
    "max_transfer_km": "40", "transfer_fixed_cost": "150", "transfer_cost_per_unit_km": "0.15",
    "min_days_left_at_receiver": "2", "require_planner_approval": "true",
    "expedite_cost_per_unit": "2.0",
}
RULE_DESCRIPTIONS = {"expedite_cost_per_unit": "Extra cost per unit of an urgent top-up order (INR)"}
Z80 = 2.563  # P90 - P10 = 2.563 standard deviations for a normal distribution


@dataclass
class Context:
    run_date: pd.Timestamp
    stores: pd.DataFrame
    products: pd.DataFrame
    rules: dict
    forecasts: dict = field(default_factory=dict)    # (store, sku) -> dict of 7-day arrays
    batches: dict = field(default_factory=dict)      # (store, sku) -> DataFrame of batches in stock
    sku_risk: pd.DataFrame = None
    batch_risk: pd.DataFrame = None
    prices: dict = field(default_factory=dict)       # (store, sku) -> current shelf price


def parse_rules(raw: dict) -> dict:
    merged = {**RULE_DEFAULTS, **raw}
    rules = {k: float(v) for k, v in merged.items() if k not in ("markdown_steps", "require_planner_approval")}
    rules["markdown_steps"] = [float(x) for x in merged["markdown_steps"].split(",")]
    rules["require_planner_approval"] = str(merged["require_planner_approval"]).lower() == "true"
    return rules


def load_context() -> Context:
    sku_risk = read_table("sku_risk", ["run_date", "next_delivery_date"])
    run_date = sku_risk["run_date"].max()
    sku_risk = sku_risk[sku_risk["run_date"] == run_date].set_index(["store_id", "sku_id"])
    batch_risk = read_table("batch_risk", ["run_date", "expiry_date"])
    batch_risk = batch_risk[batch_risk["run_date"] == run_date]
    products = read_table("products").set_index("sku_id")
    stores = read_table("stores").set_index("store_id")
    rules_df = read_table("business_rules")
    ctx = Context(run_date, stores, products, parse_rules(dict(zip(rules_df["rule_key"], rules_df["rule_value"]))),
                  sku_risk=sku_risk, batch_risk=batch_risk)

    fc = read_table("demand_forecasts", ["run_date", "forecast_date"])
    fc = fc[fc["run_date"] == run_date]
    for key, g in fc.groupby(["store_id", "sku_id"]):
        g = g.sort_values("horizon")
        lo, hi = g["lower_qty"].to_numpy(float), g["upper_qty"].to_numpy(float)
        ctx.forecasts[key] = {"mu": g["predicted_qty"].to_numpy(float), "lo": lo, "hi": hi,
                              "sd": np.maximum((hi - lo) / Z80, 1e-3),
                              "dates": [d.date().isoformat() for d in g["forecast_date"]]}
    for key, g in batch_risk.groupby(["store_id", "sku_id"]):
        ctx.batches[key] = g.sort_values("days_to_expiry").reset_index(drop=True)

    prices = read_table("prices", ["effective_date"])
    prices = prices[prices["effective_date"] <= run_date].sort_values("effective_date")
    for key, g in prices.groupby(["store_id", "sku_id"]):
        ctx.prices[key] = float(g["price"].iloc[-1])
    return ctx


def distance_km(ctx: Context, a: str, b: str) -> float:
    la1, lo1, la2, lo2 = (radians(float(x)) for x in (ctx.stores.loc[a, "lat"], ctx.stores.loc[a, "lon"],
                                                     ctx.stores.loc[b, "lat"], ctx.stores.loc[b, "lon"]))
    h = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * asin(sqrt(h))
