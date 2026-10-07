"""Shelf-life, spoilage-risk, stockout and excess-stock detection.

Starts from today's stock (batches with expiry dates) and the 7-day demand forecast
with its range (demand_forecasts), then plays the next days forward 2,000 times with
random demand drawn from the forecast range.

Rules used in the simulation
  - customers buy FIFO (oldest expiry first), as in the retail simulator
  - a batch can be sold up to the day BEFORE its expiry date; leftovers are written off on that date
  - no new deliveries are added, so batch risk is not affected by orders (FIFO sells old stock first)
  - forecast days beyond day 7 repeat the 7-day pattern (same weekday, same demand)
  - daily demand is gamma-distributed with mean and spread taken from the forecast range;
    days are assumed independent

Outputs
  batch_risk  per batch: expected units sold and unsold, spoilage probability, risk level
  sku_risk    per store and SKU: stockout probability before next delivery, excess %, alert

Run:  python intelligence/risk_engine.py        (needs forecast_next_week.py to have run first)
"""
import numpy as np
import pandas as pd
from sqlalchemy import inspect, text

from db import engine, read_table

SEED = 42
N_SIM = 2000

# Delivery weekdays by category (Mon=0). In the simulator this is the ERP delivery schedule.
DELIVERY_DAYS = {"produce": [0, 2, 4, 5], "dairy": [0, 2, 4, 6],
                 "bakery": [0, 1, 2, 3, 4, 5, 6], "meat": [1, 3, 5, 6]}

# Business thresholds (configurable)
BATCH_HIGH, BATCH_MED = 0.30, 0.10          # share of batch expected to expire unsold
STOCKOUT_HIGH, STOCKOUT_MED = 0.60, 0.30    # probability of running out before next delivery
EXCESS_HIGH, EXCESS_MED = 0.35, 0.15        # share of on-hand stock expected to expire unsold
SPOILAGE_UNSOLD_SHARE = 0.10                # spoilage_prob = P(unsold > 10% of the batch)
Z80 = 2.563                                 # P90 - P10 = 2.563 standard deviations (normal)


def next_delivery(as_of, category):
    for d in range(1, 8):
        day = as_of + pd.Timedelta(days=d)
        if day.dayofweek in DELIVERY_DAYS[category]:
            return day
    raise ValueError("no delivery day")


def level(x, high, med):
    return "HIGH" if x >= high else "MEDIUM" if x >= med else "LOW"


def simulate_series(batches, fc, as_of, d_next, rng):
    """batches: rows with batch_id, expiry_date, qty_remaining. fc: 7 forecast rows ordered by horizon."""
    batches = batches.sort_values("expiry_date").reset_index(drop=True)
    qty = np.tile(batches["qty_remaining"].to_numpy(float)[:, None], (1, N_SIM))
    dte = (batches["expiry_date"] - as_of).dt.days.to_numpy()
    mu = fc["predicted_qty"].to_numpy(float)
    sd = np.maximum((fc["upper_qty"].to_numpy(float) - fc["lower_qty"].to_numpy(float)) / Z80, 1e-3)
    unsold = np.zeros_like(qty)
    window = (d_next - as_of).days - 1            # days that must be covered before the next delivery
    stockout = np.zeros(N_SIM, bool)
    shortfall = np.zeros(N_SIM)

    for d in range(1, int(dte.max()) + 1):
        m, s = mu[(d - 1) % 7], sd[(d - 1) % 7]
        demand = rng.gamma(min((m / s) ** 2, 1e4), s * s / m, N_SIM) if m > 0.05 else np.zeros(N_SIM)
        for i in np.where(dte == d)[0]:           # expiry date reached: leftovers are written off
            unsold[i] = qty[i]
            qty[i] = 0
        left = demand.copy()
        for i in range(len(batches)):             # FIFO sales
            take = np.minimum(qty[i], left)
            qty[i] -= take
            left -= take
        if d <= window:
            stockout |= left > 1e-9
            shortfall += left
    return unsold, stockout, shortfall, mu, window


def save(df, table, run_date):
    out = df.copy()
    for c in out.columns:
        if "date" in c:
            out[c] = pd.to_datetime(out[c]).dt.date
    with engine.begin() as conn:
        if inspect(conn).has_table(table):
            conn.execute(text(f"DELETE FROM {table} WHERE run_date = :d"), {"d": run_date.date()})
        out.to_sql(table, conn, if_exists="append", index=False, chunksize=2000)


if __name__ == "__main__":
    fc_all = read_table("demand_forecasts", ["run_date", "forecast_date"])
    run_date = fc_all["run_date"].max()
    fc_all = fc_all[fc_all["run_date"] == run_date]
    batches = read_table("batches", ["received_date", "expiry_date"])
    batches = batches[(batches["qty_remaining"] > 0) & (batches["expiry_date"] > run_date)]
    products = read_table("products").set_index("sku_id")
    names = read_table("stores").set_index("store_id")["name"]
    rng = np.random.default_rng(SEED)

    batch_rows, sku_rows = [], []
    for (store, sku), fc in fc_all.groupby(["store_id", "sku_id"]):
        p = products.loc[sku]
        fc = fc.sort_values("horizon")
        d_next = next_delivery(run_date, p["category"])
        b = batches[(batches["store_id"] == store) & (batches["sku_id"] == sku)]
        if b.empty:  # nothing on the shelf: certain shortfall until the next delivery
            window = (d_next - run_date).days - 1
            sku_rows.append((run_date, store, sku, 0, fc["predicted_qty"].sum(), 0.0, d_next,
                             1.0 if window > 0 else 0.0, fc["predicted_qty"].head(max(window, 0)).sum(),
                             0.0, 0.0, 0.0, "STOCKOUT_RISK" if window > 0 else "OK",
                             "HIGH" if window > 0 else "LOW"))
            continue
        unsold, stockout, shortfall, mu, window = simulate_series(b, fc, run_date, d_next, rng)
        b = b.sort_values("expiry_date").reset_index(drop=True)
        cost = float(p["cost"])
        exp_unsold = unsold.mean(axis=1)
        for i, r in b.iterrows():
            q = float(r["qty_remaining"])
            pct = exp_unsold[i] / q
            batch_rows.append((run_date, r["batch_id"], store, sku, r["expiry_date"],
                               int((r["expiry_date"] - run_date).days), int(q), q - exp_unsold[i],
                               exp_unsold[i], pct * 100, (unsold[i] > SPOILAGE_UNSOLD_SHARE * q).mean(),
                               exp_unsold[i] * cost, level(pct, BATCH_HIGH, BATCH_MED)))
        stock = float(b["qty_remaining"].sum())
        excess = exp_unsold.sum() / stock
        so_prob = float(stockout.mean())
        so_sev, ex_sev = level(so_prob, STOCKOUT_HIGH, STOCKOUT_MED), level(excess, EXCESS_HIGH, EXCESS_MED)
        if so_sev != "LOW" and (ex_sev == "LOW" or so_sev == "HIGH"):
            alert, sev = "STOCKOUT_RISK", so_sev
        elif ex_sev != "LOW":
            alert, sev = "EXCESS_STOCK", ex_sev
        else:
            alert, sev = "OK", "LOW"
        sku_rows.append((run_date, store, sku, int(stock), float(fc["predicted_qty"].sum()),
                         stock / max(mu.mean(), 1e-6), d_next, so_prob, float(shortfall.mean()),
                         float(exp_unsold.sum()), excess * 100, float(exp_unsold.sum() * cost), alert, sev))

    batch_df = pd.DataFrame(batch_rows, columns=[
        "run_date", "batch_id", "store_id", "sku_id", "expiry_date", "days_to_expiry", "qty_remaining",
        "expected_sold", "expected_unsold", "unsold_pct", "spoilage_prob", "expected_waste_cost", "risk_level"])
    sku_df = pd.DataFrame(sku_rows, columns=[
        "run_date", "store_id", "sku_id", "on_hand_qty", "forecast_7d_qty", "days_of_cover", "next_delivery_date",
        "stockout_prob", "expected_shortfall", "expected_unsold", "excess_pct", "expected_waste_cost",
        "alert_type", "severity"])
    for c, nd in [("expected_sold", 2), ("expected_unsold", 2), ("unsold_pct", 1), ("spoilage_prob", 3),
                  ("expected_waste_cost", 2)]:
        batch_df[c] = batch_df[c].round(nd)
    for c, nd in [("forecast_7d_qty", 2), ("days_of_cover", 2), ("stockout_prob", 3), ("expected_shortfall", 2),
                  ("expected_unsold", 2), ("excess_pct", 1), ("expected_waste_cost", 2)]:
        sku_df[c] = sku_df[c].round(nd)

    save(batch_df, "batch_risk", run_date)
    save(sku_df, "sku_risk", run_date)

    print(f"Stock as of {run_date.date()} | {len(batch_df)} batches, {len(sku_df)} store/SKU pairs "
          f"| {N_SIM:,} simulations each\n")
    print("Batch risk levels:", batch_df["risk_level"].value_counts().to_dict())
    print("SKU alerts:", sku_df.groupby(["alert_type", "severity"]).size().to_dict())
    print(f"\nExpected write-off if nothing is done: {batch_df['expected_unsold'].sum():,.0f} units, "
          f"cost {batch_df['expected_waste_cost'].sum():,.0f} INR "
          f"({batch_df['expected_unsold'].sum() / batch_df['qty_remaining'].sum() * 100:.0f}% of stock on hand)")

    late = batch_df["days_to_expiry"] <= 1
    print(f"  of which unavoidable (expires tomorrow, cannot be sold under the simulator's rule): "
          f"{batch_df.loc[late, 'expected_unsold'].sum():,.0f} units, {batch_df.loc[late, 'expected_waste_cost'].sum():,.0f} INR")
    print(f"  of which preventable (2+ days left, markdown/transfer can still help): "
          f"{batch_df.loc[~late, 'expected_unsold'].sum():,.0f} units, {batch_df.loc[~late, 'expected_waste_cost'].sum():,.0f} INR")

    top = batch_df.sort_values("expected_waste_cost", ascending=False).head(8).copy()
    top["product"] = top["sku_id"].map(products["name"])
    top["store"] = top["store_id"].map(names)
    print("\nHighest-risk batches (by expected waste cost)")
    print(top[["store", "product", "expiry_date", "qty_remaining", "expected_unsold", "unsold_pct",
               "spoilage_prob", "risk_level"]].assign(expiry_date=lambda x: x["expiry_date"].dt.date)
          .to_string(index=False))
    alerts = sku_df[sku_df["alert_type"] != "OK"].sort_values(["alert_type", "severity", "expected_waste_cost"],
                                                              ascending=[True, True, False]).head(10).copy()
    if len(alerts):
        alerts["product"] = alerts["sku_id"].map(products["name"])
        alerts["store"] = alerts["store_id"].map(names)
        print("\nTop SKU alerts")
        print(alerts[["store", "product", "alert_type", "severity", "on_hand_qty", "days_of_cover",
                      "stockout_prob", "excess_pct"]].to_string(index=False))
