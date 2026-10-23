"""Onboard shops that were added from the screen (status PENDING).

A new shop has no history, so this
  1. creates 12 weeks of start-up history for it (same demand, ordering and waste rules as the other shops),
     ending on the latest data day, with weather for its city and public holidays
  2. retrains the forecasts, assesses risk and runs the agents, so recommendations exist straight away
  3. marks the shop READY (or FAILED with the reason, so it can be retried from the screen)

The backend starts this automatically when a shop is added. In a real deployment, step 1 would be replaced
by importing the shop's own sales and stock history from its POS.

Run by hand:  python pipeline/onboard_shops.py
              python pipeline/onboard_shops.py --skip-pipeline     (history only, quicker)
"""
import argparse
import math
import subprocess
import sys
import zlib
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(ROOT / "intelligence"), str(HERE)]

import live_feed as LF  # noqa: E402
from dataset import TRUTH_FILE  # noqa: E402
from db import engine, read_table  # noqa: E402

HISTORY_DAYS = 84
PIPELINE = [("Training demand forecasts", "intelligence/forecast_next_week.py"),
            ("Assessing spoilage and stockout risk", "intelligence/risk_engine.py"),
            ("Preparing recommendations", "agents/orchestrator.py")]


def set_status(store_ids, status, message):
    with engine.begin() as conn:
        for sid in store_ids:
            conn.execute(text("UPDATE stores SET status = :s, status_message = :m WHERE store_id = :id"),
                         {"s": status, "m": (message or "")[:250], "id": sid})


def pending_shops():
    return read_table("stores").query("status == 'PENDING'")


def has_history(store_id):
    with engine.connect() as conn:
        return conn.execute(text("SELECT COUNT(*) FROM inventory_snapshots WHERE store_id = :s"), {"s": store_id}).scalar() > 0


def ensure_city_data(city, lat, lon, start, last, rng):
    """Weather and public holidays for a shop's city over its history and the coming week."""
    need = pd.date_range(start, pd.Timestamp(last) + pd.Timedelta(days=LF.FORECAST_DAYS))
    wx = read_table("weather", ["weather_date"])
    have = set(wx.loc[wx["city"] == city, "weather_date"])
    missing = [d for d in need if d not in have]
    if missing:
        df, source = None, "synthetic seasonal"
        try:
            api = LF.fetch_open_meteo(lat, lon, past_days=92)
            df = api[api["weather_date"].isin(missing)]
            source = "real forecast service"
        except Exception as e:
            source = f"synthetic seasonal ({e.__class__.__name__})"
        got = set() if df is None else set(df["weather_date"])
        rest = [d for d in missing if d not in got]
        parts = [df] if df is not None and len(df) else []
        if rest:
            parts.append(LF.synthetic_weather(rest, rng))
        w = pd.concat(parts, ignore_index=True).assign(city=city)
        w["temp_c"] = pd.to_numeric(w["temp_c"]).round(1)
        w["rain_mm"] = pd.to_numeric(w["rain_mm"]).fillna(0).round(1)
        w["weather_date"] = pd.to_datetime(w["weather_date"]).dt.date
        w[["weather_date", "city", "temp_c", "rain_mm"]].to_sql("weather", engine, if_exists="append", index=False)
        print(f"  weather for {city}: {len(missing)} days ({source})")
    ev = read_table("events", ["event_date"])
    have_ev = set(ev.loc[ev["city"] == city, "event_date"])
    others = ev[(ev["city"] != city) & (ev["event_type"] == "holiday")]
    if len(others):
        ref = others[others["city"] == others["city"].iloc[0]]
        ref = ref[(ref["event_date"] >= pd.Timestamp(start)) & ~ref["event_date"].isin(have_ev)]
        if len(ref):
            nxt = int(ev["event_id"].str[1:].astype(int).max()) + 1
            rows = [(f"E{nxt + i:04d}", r.event_date.date(), city, "holiday", float(r.expected_impact)) for i, r in enumerate(ref.itertuples())]
            pd.DataFrame(rows, columns=["event_id", "event_date", "city", "event_type", "expected_impact"]).to_sql(
                "events", engine, if_exists="append", index=False)
            print(f"  holidays for {city}: {len(rows)}")


def build_history(shop, rng):
    sid, city = shop["store_id"], shop["city"]
    with engine.connect() as conn:
        last = pd.Timestamp(conn.execute(text("SELECT MAX(snapshot_date) FROM inventory_snapshots")).scalar())
    start = last - pd.Timedelta(days=HISTORY_DAYS - 1)
    ensure_city_data(city, float(shop["lat"]), float(shop["lon"]), start, last, rng)

    products = read_table("products").set_index("sku_id")
    weather = read_table("weather", ["weather_date"])
    weather = weather[weather["city"] == city].set_index("weather_date")
    events = read_table("events", ["event_date"])
    events = events[events["city"] == city].groupby("event_date")["expected_impact"].max()
    size, urban = float(shop["size_factor"]), shop["type"] == "urban"
    skus = list(products.index)
    factor = {k: rng.uniform(0.85, 1.15) for k in skus}
    price = {k: round(float(products.loc[k, "base_price"]) * (1.05 if urban else 1.0), 2) for k in skus}

    promos_db = read_table("promotions")
    counter = int(promos_db["promo_id"].str[1:].astype(int).max()) if len(promos_db) else 0
    promos, promo_rows = {k: [] for k in skus}, []
    for k in skus:                                                   # random promotion windows, about one every 55 days
        day = start
        while True:
            s0 = day + pd.Timedelta(days=int(rng.geometric(1 / 55)))
            if s0 > last + pd.Timedelta(days=LF.FORECAST_DAYS):
                break
            e0 = s0 + pd.Timedelta(days=int(rng.integers(3, 8)) - 1)
            counter += 1
            disc = int(rng.choice([10, 15, 20, 25, 30]))
            promos[k].append((s0, e0, disc, f"P{counter:05d}"))
            promo_rows.append((f"P{counter:05d}", k, sid, s0.date(), e0.date(), disc))
            day = e0 + pd.Timedelta(days=3)

    receipts = read_table("receipts")
    receipt_n = int(receipts["receipt_id"].str[1:].astype(int).max()) if len(receipts) else 0
    base_level = {k: LF.BASE_DEMAND[k] * size for k in skus}
    active, hist, changed = {k: [] for k in skus}, {k: [float(base_level[k])] * 7 for k in skus}, {}   # ordering starts from the base level
    sales_rows, truth_rows, snap_rows, waste_rows, receipt_rows, batch_rows = [], [], [], [], [], []
    price_rows = [(k, sid, start.date(), price[k]) for k in skus]

    for day in pd.date_range(start, last):
        wx = weather.loc[day] if day in weather.index else None
        for sku in skus:
            p = products.loc[sku]
            cat, shelf, cost = p["category"], int(p["shelf_life_days"]), float(p["cost"])
            temp, rain = (float(wx["temp_c"]), float(wx["rain_mm"])) if wx is not None else (25.0, 0.0)
            ev = float(events.get(day, 1.0))
            disc, promo_id = 0.0, None
            for s0, e0, dsc, pid in promos[sku]:
                if s0 <= day <= e0:
                    disc, promo_id = float(dsc), pid
            tm = float(np.clip(1 + LF.TEMP_COEF.get(sku, 0) * (temp - 25), 0.7, 1.4))
            rm = 1 - LF.RAIN_EFFECT[cat] * min(rain / 20, 1)
            expected = (LF.BASE_DEMAND[sku] * size * factor[sku] * LF.WEEKDAY[day.dayofweek] * tm * rm
                        * ev ** (0.5 if cat == "meat" else 1.0) * (1 + 0.03 * disc))
            want = int(rng.poisson(expected * rng.gamma(20, 1 / 20)))
            if rng.random() < 1 / 60:
                price[sku] = round(price[sku] * rng.uniform(0.95, 1.07), 2)
                price_rows.append((sku, sid, day.date(), price[sku]))

            act = active[sku]
            keep = []
            for b in act:                                            # morning: expired stock is written off
                if b["exp"] <= day:
                    if b["rem"] > 0:
                        waste_rows.append((day.date(), sid, sku, b["id"], b["rem"], "expired", round(b["rem"] * cost, 2)))
                    b["rem"] = 0
                else:
                    keep.append(b)
            act[:] = keep
            if day.dayofweek in LF.DELIVERY_DAYS[cat]:              # scheduled delivery, same ordering rule as the other shops
                gap = next(k for k in range(1, 8) if (day.dayofweek + k) % 7 in LF.DELIVERY_DAYS[cat])
                h = hist[sku][-7:]
                avg = max(float(np.mean(h)), 0.25 * base_level[sku])      # a bad week never switches ordering off
                target = avg * (gap + (1.0 if shelf >= 7 else 0.5)) * LF.SAFETY[cat]
                order = max(0, math.ceil(target - sum(b["rem"] for b in act)))
                if order > 0:
                    lag = 1 if (shelf >= 5 and rng.random() < LF.TRANSIT_LOSS_PROB[cat]) else 0
                    damaged = int(rng.binomial(order, LF.DAMAGE_RATE))
                    bid = f"B-{sid}-{sku}-{day:%Y%m%d}"
                    b = {"id": bid, "exp": day + pd.Timedelta(days=shelf - lag), "rem": order - damaged}
                    receipt_n += 1
                    receipt_rows.append((f"R{receipt_n:07d}", sku, sid, bid, day.date(), order, round(cost * rng.uniform(0.97, 1.03), 2)))
                    batch_rows.append((bid, sku, sid, day.date(), b["exp"].date(), order))
                    if damaged:
                        waste_rows.append((day.date(), sid, sku, bid, damaged, "damaged", round(damaged * cost, 2)))
                    act.append(b)
                    changed[bid] = b
            act.sort(key=lambda b: b["exp"])
            sold = 0
            for b in act:                                            # daytime: oldest stock first
                take = min(want - sold, b["rem"])
                b["rem"] -= take
                sold += take
                if sold == want:
                    break
            act[:] = [b for b in act if b["rem"] > 0]
            pr = round(price[sku] * (1 - disc / 100), 2)
            sales_rows.append((day.date(), sid, sku, sold, pr, round(sold * pr, 2), promo_id))
            truth_rows.append((day.date(), sid, sku, want, want - sold, round(expected, 2)))
            snap_rows.append((day.date(), sid, sku, sum(b["rem"] for b in act)))
            hist[sku].append(float(sold))

    bdf = pd.DataFrame(batch_rows, columns=["batch_id", "sku_id", "store_id", "received_date", "expiry_date", "qty_received"])
    bdf["qty_remaining"] = [changed[b]["rem"] for b in bdf["batch_id"]]
    with engine.begin() as conn:                                     # parents first
        bdf.to_sql("batches", conn, if_exists="append", index=False)
        pd.DataFrame(receipt_rows, columns=["receipt_id", "sku_id", "store_id", "batch_id", "received_date", "qty", "unit_cost"]
                     ).to_sql("receipts", conn, if_exists="append", index=False)
        pd.DataFrame(waste_rows, columns=["waste_date", "store_id", "sku_id", "batch_id", "qty", "reason", "cost"]
                     ).to_sql("waste", conn, if_exists="append", index=False)
        pd.DataFrame(promo_rows, columns=["promo_id", "sku_id", "store_id", "start_date", "end_date", "discount_pct"]
                     ).to_sql("promotions", conn, if_exists="append", index=False)
        pd.DataFrame(price_rows, columns=["sku_id", "store_id", "effective_date", "price"]).to_sql("prices", conn, if_exists="append", index=False)
        pd.DataFrame(sales_rows, columns=["sale_date", "store_id", "sku_id", "qty_sold", "unit_price", "revenue", "promo_id"]
                     ).to_sql("sales", conn, if_exists="append", index=False, chunksize=2000)
        pd.DataFrame(snap_rows, columns=["snapshot_date", "store_id", "sku_id", "on_hand_qty"]
                     ).to_sql("inventory_snapshots", conn, if_exists="append", index=False, chunksize=2000)
    if TRUTH_FILE.exists():
        pd.DataFrame(truth_rows, columns=["sale_date", "store_id", "sku_id", "true_demand", "lost_sales", "expected_demand"]
                     ).to_csv(TRUTH_FILE, mode="a", header=False, index=False)
    sold_total = sum(r[3] for r in sales_rows)
    waste_total = sum(r[4] for r in waste_rows)
    print(f"  {sid}: {HISTORY_DAYS} days, {sold_total:,} units sold, {waste_total:,} wasted "
          f"({100 * waste_total / max(sold_total + waste_total, 1):.1f}%)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-pipeline", action="store_true", help="create the history only (for testing)")
    args = ap.parse_args()
    handled_any = False
    while len(pending_shops()):
        shops = pending_shops()
        ids = list(shops["store_id"])
        print(f"Onboarding {', '.join(ids)} ...")
        try:
            for _, shop in shops.iterrows():
                if has_history(shop["store_id"]):
                    continue                                          # a retry: the history already exists
                set_status([shop["store_id"]], "PENDING", f"Creating {HISTORY_DAYS} days of start-up history")
                build_history(shop, np.random.default_rng(zlib.crc32(shop["store_id"].encode())))
            if args.skip_pipeline:
                set_status(ids, "READY", "History created (forecast step skipped)")
            else:
                for label, script in PIPELINE:
                    set_status(ids, "PENDING", label + " (this takes a few minutes)")
                    print(f"  {label} ...", flush=True)
                    r = subprocess.run([sys.executable, str(ROOT / script)], cwd=str(ROOT), capture_output=True, text=True)
                    if r.returncode != 0:
                        tail = (r.stderr or r.stdout).strip().splitlines()[-1:] or ["unknown error"]
                        raise RuntimeError(f"{label} failed: {tail[0]}")
                set_status(ids, "READY", "Ready")
            handled_any = True
            print(f"{', '.join(ids)} ready.")
        except Exception as e:
            print(f"Onboarding failed: {e}")
            set_status(ids, "FAILED", str(e))
            break
    if not handled_any and not len(pending_shops()):
        print("No shops are waiting to be set up.")


if __name__ == "__main__":
    main()
