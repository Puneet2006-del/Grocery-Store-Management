"""Live daily feed: bring the database up to date, one simulated day at a time.

Continues the retail simulation from the last day in the database up to today (or --until):
  - refreshes weather (real forecast service, synthetic seasonal fallback) and holidays
  - plans upcoming promotions
  - simulates each missing day for every store and SKU with the same demand and ordering rules as
    the original history: expiry write-offs, scheduled deliveries, FIFO sales, waste, stock snapshots
  - writes the new rows to MySQL and keeps batches.qty_remaining equal to the stock on the shelf

In a real deployment this file would be replaced by the daily feeds from the POS, ERP and waste systems.
Everything after it (forecasts, risk, agents, dashboard) stays the same.

Run:  python pipeline/live_feed.py                (catches up to today)
      python pipeline/live_feed.py --until 2026-10-11
"""
import argparse
import math
import sys
import zlib
from datetime import date, timedelta
from pathlib import Path

import holidays
import numpy as np
import pandas as pd
import requests
from sqlalchemy import text

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(ROOT / "intelligence")]

from dataset import TRUTH_FILE, build_panel  # noqa: E402
from db import engine, read_table  # noqa: E402

# ---- rules copied from the original simulation (generate_simulation.py) so the feed behaves the same
BASE_DEMAND = {"P01": 30, "P02": 12, "P03": 28, "P04": 14, "P05": 60, "P06": 28, "P07": 16, "P08": 24,
               "P09": 35, "P10": 18, "P11": 14, "P12": 20, "P13": 14, "P14": 20, "P15": 8, "P16": 7}
STORE_SIZE = {"S01": 1.2, "S02": 1.1, "S03": 0.9, "S04": 0.8}
WEEKDAY = np.array([0.90, 0.90, 0.93, 0.97, 1.08, 1.25, 1.20])
WEEKDAY = WEEKDAY / WEEKDAY.mean()
TEMP_COEF = {"P08": 0.030, "P06": 0.015, "P05": 0.005, "P15": -0.008}
RAIN_EFFECT = {"produce": 0.20, "dairy": 0.05, "bakery": 0.10, "meat": 0.10}
DELIVERY_DAYS = {"produce": [0, 2, 4, 5], "dairy": [0, 2, 4, 6], "bakery": [0, 1, 2, 3, 4, 5, 6], "meat": [1, 3, 5, 6]}
SAFETY = {"produce": 1.25, "dairy": 1.30, "bakery": 1.10, "meat": 1.05}
DAMAGE_RATE = 0.015
TRANSIT_LOSS_PROB = {"produce": 0.30, "dairy": 0.0, "bakery": 0.0, "meat": 0.0}
HOLIDAY_IMPACT = {"diwali": 1.40, "holi": 1.30, "dussehra": 1.20, "raksha": 1.20, "christmas": 1.20,
                  "eid": 1.25, "republic": 1.05, "independence": 1.05}
FORECAST_DAYS = 7          # weather and promotions are prepared this far ahead of the last simulated day


def d_(ts):
    return pd.Timestamp(ts).date()


# ------------------------------------------------------------------------ weather
def fetch_open_meteo(lat, lon):
    r = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": lat, "longitude": lon, "daily": "temperature_2m_mean,precipitation_sum",
        "past_days": 14, "forecast_days": 9, "timezone": "Asia/Kolkata"}, timeout=30)
    r.raise_for_status()
    d = r.json()["daily"]
    return pd.DataFrame({"weather_date": pd.to_datetime(d["time"]), "temp_c": d["temperature_2m_mean"],
                         "rain_mm": d["precipitation_sum"]})


def synthetic_weather(days, rng, city_offset=0.0):
    rows = []
    for day in days:
        temp = 25 + 11 * math.sin(2 * math.pi * (day.dayofyear - 64) / 365) + city_offset + rng.normal(0, 1.5)
        rain = rng.gamma(2.0, 8.0) if rng.random() < (0.45 if day.month in (7, 8, 9) else 0.04) else 0.0
        rows.append((day, round(temp, 1), round(float(rain), 1)))
    return pd.DataFrame(rows, columns=["weather_date", "temp_c", "rain_mm"])


def refresh_weather(stores, first_day, last_day, rng):
    """Weather for first_day..last_day for every city. Actuals and the 7-day forecast share the table;
    forecast rows are overwritten by later runs."""
    days = pd.date_range(first_day, last_day)
    frames, source = [], {}
    for i, (city, g) in enumerate(stores.groupby("city")):
        df = None
        try:
            api = fetch_open_meteo(float(g["lat"].iloc[0]), float(g["lon"].iloc[0]))
            df = api[api["weather_date"].isin(days)]
            source[city] = "real forecast service"
        except Exception as e:  # offline, API change, ...
            source[city] = f"synthetic seasonal ({e.__class__.__name__})"
        have = set() if df is None else set(df["weather_date"])
        missing = [x for x in days if x not in have]
        if missing:
            syn = synthetic_weather(missing, rng, city_offset=i * 0.3)
            df = syn if df is None else pd.concat([df, syn], ignore_index=True)
            if source[city].startswith("real"):
                source[city] += " + synthetic for missing days"
        df = df.assign(city=city)
        df["temp_c"] = pd.to_numeric(df["temp_c"]).round(1)
        df["rain_mm"] = pd.to_numeric(df["rain_mm"]).fillna(0).round(1)
        frames.append(df)
    w = pd.concat(frames, ignore_index=True)
    w["weather_date"] = pd.to_datetime(w["weather_date"]).dt.date
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM weather WHERE weather_date >= :a AND weather_date <= :b"),
                     {"a": d_(first_day), "b": d_(last_day)})
        w[["weather_date", "city", "temp_c", "rain_mm"]].to_sql("weather", conn, if_exists="append", index=False)
    return source


def refresh_events(stores, until):
    """Public holidays for the next 30 days (the model and the reasons use them)."""
    ev = read_table("events", ["event_date"])
    last = ev["event_date"].max()
    cities = sorted(stores["city"].unique())
    nxt = int(ev["event_id"].str[1:].astype(int).max()) + 1 if len(ev) else 1
    hol = holidays.India(years=sorted({last.year, until.year, (until + timedelta(days=30)).year}))
    rows = []
    for day, name in sorted(hol.items()):
        ts = pd.Timestamp(day)
        if not (last < ts <= pd.Timestamp(until) + pd.Timedelta(days=30)):
            continue
        impact = next((v for k, v in HOLIDAY_IMPACT.items() if k in name.lower()), 1.10)
        for city in cities:
            rows.append((f"E{nxt:04d}", day, city, "holiday", impact))
            nxt += 1
    if rows:
        pd.DataFrame(rows, columns=["event_id", "event_date", "city", "event_type", "expected_impact"]).to_sql(
            "events", engine, if_exists="append", index=False)
    return len(rows)


# ---------------------------------------------------------------------- promotions
def plan_promotions(series, last_day, rng):
    promos = read_table("promotions", ["start_date", "end_date"])
    counter = int(promos["promo_id"].str[1:].astype(int).max()) if len(promos) else 0
    horizon = pd.Timestamp(last_day) + pd.Timedelta(days=FORECAST_DAYS)
    last_end = promos.groupby(["store_id", "sku_id"])["end_date"].max().to_dict()
    new = []
    for key in series:
        day = max(last_end.get(key, pd.Timestamp(last_day)) + pd.Timedelta(days=4), pd.Timestamp(last_day) + pd.Timedelta(days=1))
        while True:
            start = day + pd.Timedelta(days=int(rng.geometric(1 / 55)))
            if start > horizon:
                break
            end = start + pd.Timedelta(days=int(rng.integers(3, 8)) - 1)
            counter += 1
            new.append((f"P{counter:05d}", key[1], key[0], start.date(), end.date(), int(rng.choice([10, 15, 20, 25, 30]))))
            day = end + pd.Timedelta(days=3)
    if new:
        pd.DataFrame(new, columns=["promo_id", "sku_id", "store_id", "start_date", "end_date", "discount_pct"]).to_sql(
            "promotions", engine, if_exists="append", index=False)
    return len(new)


# ------------------------------------------------------------------------ the feed
def recover_factors(panel, products):
    """Per store/SKU demand level: the hidden random factor of the original simulation,
    recovered from the ground-truth expected demand (or estimated from recent sales if that is missing)."""
    cat = products["category"]
    p = panel.copy()
    tm = np.clip(1 + p["sku_id"].map(TEMP_COEF).fillna(0) * (p["temp_c"] - 25), 0.7, 1.4)
    rm = 1 - p["sku_id"].map(cat).map(RAIN_EFFECT) * np.minimum(p["rain_mm"] / 20, 1)
    em = p["event_impact"] ** np.where(p["sku_id"].map(cat) == "meat", 0.5, 1.0)
    formula = (p["sku_id"].map(BASE_DEMAND) * p["store_id"].map(STORE_SIZE) * WEEKDAY[p["dow"].to_numpy()]
               * tm * rm * em * (1 + 0.03 * p["discount_pct"]))
    p["formula"] = formula
    if TRUTH_FILE.exists():
        t = pd.read_csv(TRUTH_FILE, parse_dates=["sale_date"]).rename(columns={"sale_date": "date"})
        p = p.merge(t[["date", "store_id", "sku_id", "expected_demand"]], on=["date", "store_id", "sku_id"], how="left")
        ratio = (p["expected_demand"] / p["formula"]).replace([np.inf, -np.inf], np.nan)
    else:
        recent = p[(p["date"] > p["date"].max() - pd.Timedelta(days=56)) & ~p["stockout"]]
        ratio = recent["qty_sold"] / recent["formula"]
        p = recent
    p["ratio"] = ratio
    return p.groupby(["store_id", "sku_id"])["ratio"].median().clip(0.5, 1.5).to_dict()


def simulate(last_day, until, seed):
    rng = np.random.default_rng(seed)
    stores = read_table("stores").set_index("store_id")
    products = read_table("products").set_index("sku_id")
    panel = build_panel()
    factors = recover_factors(panel, products)
    series = sorted(factors)

    source = refresh_weather(stores.reset_index(), pd.Timestamp(last_day) + pd.Timedelta(days=1),
                             pd.Timestamp(until) + pd.Timedelta(days=FORECAST_DAYS), rng)
    n_events = refresh_events(stores, until)
    n_promos = plan_promotions(series, until, rng)

    weather = read_table("weather", ["weather_date"]).set_index(["weather_date", "city"])
    events = read_table("events", ["event_date"]).groupby(["event_date", "city"])["expected_impact"].max()
    promos = read_table("promotions", ["start_date", "end_date"])
    prices = read_table("prices", ["effective_date"]).sort_values("effective_date")
    price_now = prices.groupby(["store_id", "sku_id"]).tail(1).set_index(["store_id", "sku_id"])["price"].astype(float).to_dict()
    promo_by = {k: g[["start_date", "end_date", "discount_pct", "promo_id"]].to_numpy() for k, g in promos.groupby(["store_id", "sku_id"])}
    recent_sales = read_table("sales", ["sale_date"])
    recent_sales = recent_sales[recent_sales["sale_date"] > pd.Timestamp(last_day) - pd.Timedelta(days=7)]
    hist = {k: g.sort_values("sale_date")["qty_sold"].astype(float).tolist() for k, g in recent_sales.groupby(["store_id", "sku_id"])}
    batches_db = read_table("batches", ["received_date", "expiry_date"])
    active = {}
    for r in batches_db[batches_db["qty_remaining"] > 0].itertuples():
        active.setdefault((r.store_id, r.sku_id), []).append(
            {"id": r.batch_id, "exp": r.expiry_date, "rem": int(r.qty_remaining), "new": False})
    receipts = read_table("receipts")
    receipt_n = int(receipts["receipt_id"].str[1:].astype(int).max()) if len(receipts) else 0

    sales_rows, truth_rows, snap_rows, waste_rows, receipt_rows, batch_rows, price_rows = [], [], [], [], [], [], []
    changed = {}
    days = pd.date_range(pd.Timestamp(last_day) + pd.Timedelta(days=1), pd.Timestamp(until))
    for day in days:
        for (store, sku) in series:
            p = products.loc[sku]
            cat, shelf, cost = p["category"], int(p["shelf_life_days"]), float(p["cost"])
            city = stores.loc[store, "city"]
            wx = weather.loc[(day, city)]
            ev = float(events.get((day, city), 1.0))
            disc, promo_id = 0.0, None
            for s, e, dsc, pid in promo_by.get((store, sku), []):
                if s <= day <= e:
                    disc, promo_id = float(dsc), pid
            tm = float(np.clip(1 + TEMP_COEF.get(sku, 0) * (wx["temp_c"] - 25), 0.7, 1.4))
            rm = 1 - RAIN_EFFECT[cat] * min(wx["rain_mm"] / 20, 1)
            expected = (BASE_DEMAND[sku] * STORE_SIZE[store] * factors[(store, sku)] * WEEKDAY[day.dayofweek] * tm * rm
                        * ev ** (0.5 if cat == "meat" else 1.0) * (1 + 0.03 * disc))
            want = int(rng.poisson(expected * rng.gamma(20, 1 / 20)))

            if rng.random() < 1 / 60 and (store, sku) in price_now:      # occasional price revision
                price_now[(store, sku)] = round(price_now[(store, sku)] * rng.uniform(0.95, 1.07), 2)
                price_rows.append((sku, store, day.date(), price_now[(store, sku)]))

            act = active.setdefault((store, sku), [])
            keep = []
            for b in act:                                                  # morning: write off expired stock
                if b["exp"] <= day:
                    if b["rem"] > 0:
                        waste_rows.append((day.date(), store, sku, b["id"], b["rem"], "expired", round(b["rem"] * cost, 2)))
                    b["rem"] = 0
                    changed[b["id"]] = b
                else:
                    keep.append(b)
            act[:] = keep

            if day.dayofweek in DELIVERY_DAYS[cat]:                       # scheduled delivery, legacy ordering rule
                gap = next(k for k in range(1, 8) if (day.dayofweek + k) % 7 in DELIVERY_DAYS[cat])
                h = hist.get((store, sku), [])[-7:]
                avg = float(np.mean(h)) if h else BASE_DEMAND[sku] * STORE_SIZE[store]
                target = avg * (gap + (1.0 if shelf >= 7 else 0.5)) * SAFETY[cat]
                order = max(0, math.ceil(target - sum(b["rem"] for b in act)))
                if order > 0:
                    lag = 1 if (shelf >= 5 and rng.random() < TRANSIT_LOSS_PROB[cat]) else 0
                    damaged = int(rng.binomial(order, DAMAGE_RATE))
                    bid = f"B-{store}-{sku}-{day:%Y%m%d}"
                    b = {"id": bid, "exp": day + pd.Timedelta(days=shelf - lag), "rem": order - damaged, "new": True}
                    receipt_n += 1
                    receipt_rows.append((f"R{receipt_n:07d}", sku, store, bid, day.date(), order, round(cost * rng.uniform(0.97, 1.03), 2)))
                    batch_rows.append((bid, sku, store, day.date(), b["exp"].date(), order))
                    if damaged:
                        waste_rows.append((day.date(), store, sku, bid, damaged, "damaged", round(damaged * cost, 2)))
                    act.append(b)
                    changed[bid] = b

            act.sort(key=lambda b: b["exp"])
            sold = 0
            for b in act:                                                  # daytime: oldest stock first
                take = min(want - sold, b["rem"])
                b["rem"] -= take
                sold += take
                changed[b["id"]] = b
                if sold == want:
                    break
            act[:] = [b for b in act if b["rem"] > 0]
            price = round(price_now[(store, sku)] * (1 - disc / 100), 2)
            sales_rows.append((day.date(), store, sku, sold, price, round(sold * price, 2), promo_id))
            truth_rows.append((day.date(), store, sku, want, want - sold, round(expected, 2)))
            snap_rows.append((day.date(), store, sku, sum(b["rem"] for b in act)))
            hist.setdefault((store, sku), []).append(float(sold))

    cols = {
        "sales": (sales_rows, ["sale_date", "store_id", "sku_id", "qty_sold", "unit_price", "revenue", "promo_id"]),
        "inventory_snapshots": (snap_rows, ["snapshot_date", "store_id", "sku_id", "on_hand_qty"]),
        "prices": (price_rows, ["sku_id", "store_id", "effective_date", "price"]),
    }
    batch_df = pd.DataFrame(batch_rows, columns=["batch_id", "sku_id", "store_id", "received_date", "expiry_date", "qty_received"])
    batch_df["qty_remaining"] = [changed[b]["rem"] for b in batch_df["batch_id"]]
    with engine.begin() as conn:                                           # parents first
        batch_df.to_sql("batches", conn, if_exists="append", index=False)
        pd.DataFrame(receipt_rows, columns=["receipt_id", "sku_id", "store_id", "batch_id", "received_date", "qty", "unit_cost"]
                     ).to_sql("receipts", conn, if_exists="append", index=False)
        pd.DataFrame(waste_rows, columns=["waste_date", "store_id", "sku_id", "batch_id", "qty", "reason", "cost"]
                     ).to_sql("waste", conn, if_exists="append", index=False)
        for name, (rows, c) in cols.items():
            if rows:
                pd.DataFrame(rows, columns=c).to_sql(name, conn, if_exists="append", index=False, chunksize=2000)
        old = [{"q": b["rem"], "id": bid} for bid, b in changed.items() if not b["new"]]
        if old:
            conn.execute(text("UPDATE batches SET qty_remaining = :q WHERE batch_id = :id"), old)
    if TRUTH_FILE.exists():
        pd.DataFrame(truth_rows, columns=["sale_date", "store_id", "sku_id", "true_demand", "lost_sales", "expected_demand"]
                     ).to_csv(TRUTH_FILE, mode="a", header=False, index=False)

    s = pd.DataFrame(sales_rows, columns=cols["sales"][1])
    w = pd.DataFrame(waste_rows, columns=["waste_date", "store_id", "sku_id", "batch_id", "qty", "reason", "cost"])
    t = pd.DataFrame(truth_rows, columns=["d", "s", "k", "demand", "lost", "exp"])
    return {"days": len(days), "sold": int(s["qty_sold"].sum()), "waste": int(w["qty"].sum()),
            "fill": 100 * (1 - t["lost"].sum() / max(t["demand"].sum(), 1)), "weather": source,
            "events": n_events, "promos": n_promos, "batches": len(batch_rows)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", type=str, default=None, help="last day to simulate (default: today)")
    args = ap.parse_args()
    until = pd.Timestamp(args.until or date.today()).normalize()
    with engine.connect() as conn:
        last = pd.Timestamp(conn.execute(text("SELECT MAX(snapshot_date) FROM inventory_snapshots")).scalar())
    if last >= until:
        print(f"Already up to date: data runs to {last.date()}.")
        return
    print(f"Data runs to {last.date()}. Simulating {last.date() + timedelta(days=1)} to {until.date()} ...")
    r = simulate(last, until, seed=zlib.crc32(str(last.date()).encode()))
    print(f"Simulated {r['days']} day(s): {r['sold']:,} units sold, {r['waste']:,} units wasted, "
          f"fill rate {r['fill']:.1f}%, {r['batches']} deliveries.")
    print(f"Planned {r['promos']} promotions and added {r['events']} holiday rows.")
    for city, src in r["weather"].items():
        print(f"Weather {city}: {src}")
    print(f"Data now runs to {until.date()}.")


if __name__ == "__main__":
    main()
