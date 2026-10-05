"""Main simulation: generates prices, promotions, sales, batches, receipts,
inventory snapshots and waste TOGETHER so they are consistent.

Per store/SKU/day:
  demand = base x store size x weekday x weather x event x promo x noise
  morning : expired batches are written off (waste), then a delivery may arrive
  day     : customers buy FIFO (oldest expiry first); unmet demand = lost sales
  evening : on-hand stock is snapshotted

Outputs go to data-pipeline/data/truth/ (clean ground truth, never edited).
Run from data-pipeline/generate:  python generate_simulation.py
"""
import math

import numpy as np
import pandas as pd

from config import END_DATE, RAW, SEED, START_DATE

TRUTH = RAW.parent / "truth"
TRUTH.mkdir(parents=True, exist_ok=True)

rng = np.random.default_rng(SEED)
dates = pd.date_range(START_DATE, END_DATE)
N = len(dates)
DOW = dates.dayofweek.to_numpy()          # Mon=0 ... Sun=6

stores = pd.read_csv(RAW / "stores.csv")
products = pd.read_csv(RAW / "products.csv")
weather = pd.read_csv(RAW / "weather.csv", parse_dates=["weather_date"])
events = pd.read_csv(RAW / "events.csv", parse_dates=["event_date"])

# ------------------------------------------------------------ assumptions
BASE_DEMAND = {  # units/day at a store with size multiplier 1.0
    "P01": 30, "P02": 12, "P03": 28, "P04": 14,
    "P05": 60, "P06": 28, "P07": 16, "P08": 24,
    "P09": 35, "P10": 18, "P11": 14, "P12": 20,
    "P13": 14, "P14": 20, "P15": 8, "P16": 7,
}
STORE_SIZE = {"S01": 1.2, "S02": 1.1, "S03": 0.9, "S04": 0.8}
STORE_PRICE_MULT = {"urban": 1.05, "suburban": 1.0}
WEEKDAY = np.array([0.90, 0.90, 0.93, 0.97, 1.08, 1.25, 1.20])
WEEKDAY = WEEKDAY / WEEKDAY.mean()
TEMP_COEF = {"P08": 0.030, "P06": 0.015, "P05": 0.005, "P15": -0.008}  # per deg C from 25
RAIN_EFFECT = {"produce": 0.20, "dairy": 0.05, "bakery": 0.10, "meat": 0.10}
DELIVERY_DAYS = {                       # weekdays with a delivery (Mon=0)
    "produce": [0, 2, 4, 5],
    "dairy": [0, 2, 4, 6],
    "bakery": [0, 1, 2, 3, 4, 5, 6],
    "meat": [1, 3, 5, 6],
}
SAFETY = {"produce": 1.25, "dairy": 1.30, "bakery": 1.10, "meat": 1.05}
DAMAGE_RATE = 0.015                     # share of each delivery damaged on arrival
TRANSIT_LOSS_PROB = {"produce": 0.30, "dairy": 0.0, "bakery": 0.0, "meat": 0.0}

# ---------------------------------------------------- weather/event arrays
def city_series(df, col, fill):
    out = {}
    for city, g in df.groupby("city"):
        s = g.set_index("weather_date")[col].reindex(dates)
        out[city] = (s.interpolate().bfill().ffill() if fill == "interp" else s.fillna(0)).to_numpy()
    return out


TEMP = city_series(weather, "temp_c", "interp")
RAIN = city_series(weather, "rain_mm", "zero")
date_idx = {d: i for i, d in enumerate(dates)}
EVENT = {c: np.ones(N) for c in stores["city"].unique()}
for r in events.itertuples():
    i = date_idx.get(r.event_date)
    if i is not None and r.city in EVENT:
        EVENT[r.city][i] = max(EVENT[r.city][i], r.expected_impact)


# ----------------------------------------------------- promos and prices
def make_promos():
    k = int(rng.integers(5, 9))
    starts = np.sort(rng.choice(np.arange(5, N - 10), size=k, replace=False))
    promos, last_end = [], -10
    for s in starts:
        if s <= last_end + 3:
            continue
        e = min(int(s) + int(rng.integers(3, 8)) - 1, N - 1)
        promos.append((int(s), e, int(rng.choice([10, 15, 20, 25, 30]))))
        last_end = e
    return promos


def make_price_series(start_price):
    changes = np.sort(rng.choice(np.arange(30, N - 1), size=3, replace=False))
    arr = np.empty(N)
    rows, p, prev = [(0, round(start_price, 2))], start_price, 0
    for c in changes:
        p = round(p * rng.uniform(0.95, 1.07), 2)
        rows.append((int(c), p))
    for j, (idx, price) in enumerate(rows):
        end = rows[j + 1][0] if j + 1 < len(rows) else N
        arr[idx:end] = price
    return arr, rows


# ---------------------------------------------------------------- main loop
price_rows, promo_rows = [], []
sales_rows, truth_rows, snap_rows = [], [], []
receipt_rows, waste_rows, batch_rows = [], [], []
promo_counter, receipt_counter = 0, 0

for st in stores.itertuples():
    for pr in products.itertuples():
        cat, shelf = pr.category, int(pr.shelf_life_days)

        # ---- prices and promotions
        price_arr, p_rows = make_price_series(pr.base_price * STORE_PRICE_MULT[st.type])
        for idx, price in p_rows:
            price_rows.append((pr.sku_id, st.store_id, dates[idx].date(), price))
        disc = np.zeros(N)
        promo_id_at = [None] * N
        for s, e, d in make_promos():
            promo_counter += 1
            pid = f"P{promo_counter:05d}"
            promo_rows.append((pid, pr.sku_id, st.store_id, dates[s].date(), dates[e].date(), d))
            disc[s:e + 1] = d
            for t in range(s, e + 1):
                promo_id_at[t] = pid

        # ---- expected and realised demand
        sku_factor = rng.uniform(0.85, 1.15)
        base = BASE_DEMAND[pr.sku_id] * STORE_SIZE[st.store_id] * sku_factor
        temp_mult = np.clip(1 + TEMP_COEF.get(pr.sku_id, 0) * (TEMP[st.city] - 25), 0.7, 1.4)
        rain_mult = 1 - RAIN_EFFECT[cat] * np.minimum(RAIN[st.city] / 20, 1)
        event_mult = EVENT[st.city] ** (0.5 if cat == "meat" else 1.0)
        promo_mult = 1 + 0.03 * disc
        expected = base * WEEKDAY[DOW] * temp_mult * rain_mult * event_mult * promo_mult
        noisy = expected * rng.gamma(20, 1 / 20, N)          # day-to-day variation
        demand = rng.poisson(noisy)

        # ---- day-by-day inventory simulation
        deliveries = DELIVERY_DAYS[cat]
        active, history = [], [base] * 7
        for t in range(N):
            d = dates[t].date()

            # morning: write off expired stock
            still = []
            for b in active:
                if b["exp"] <= t:
                    waste_rows.append((d, st.store_id, pr.sku_id, b["id"], b["rem"], "expired",
                                       round(b["rem"] * pr.cost, 2)))
                    b["rem"] = 0
                else:
                    still.append(b)
            active = still

            # morning: delivery (replenishment rule = trailing 7-day mean x cover x safety)
            if t == 0 or DOW[t] in deliveries:
                gap = next(k for k in range(1, 8) if (DOW[t] + k) % 7 in deliveries)
                cover = gap + (1.0 if shelf >= 7 else 0.5)      # days of demand to cover
                target = np.mean(history[-7:]) * cover * SAFETY[cat]
                order = max(0, math.ceil(target - sum(b["rem"] for b in active)))
                if order > 0:
                    lag = 1 if (shelf >= 5 and rng.random() < TRANSIT_LOSS_PROB[cat]) else 0
                    damaged = int(rng.binomial(order, DAMAGE_RATE))
                    bid = f"B-{st.store_id}-{pr.sku_id}-{d:%Y%m%d}"
                    b = {"id": bid, "recv": t, "exp": t + shelf - lag,
                         "qty": order, "rem": order - damaged}
                    receipt_counter += 1
                    receipt_rows.append((f"R{receipt_counter:07d}", pr.sku_id, st.store_id, bid, d,
                                         order, round(pr.cost * rng.uniform(0.97, 1.03), 2)))
                    if damaged:
                        waste_rows.append((d, st.store_id, pr.sku_id, bid, damaged, "damaged",
                                           round(damaged * pr.cost, 2)))
                    batch_rows.append(b)
                    active.append(b)

            # daytime: FIFO sales
            active.sort(key=lambda x: x["exp"])
            want, sold = int(demand[t]), 0
            for b in active:
                take = min(want - sold, b["rem"])
                b["rem"] -= take
                sold += take
                if sold == want:
                    break
            active = [b for b in active if b["rem"] > 0]
            history.append(sold)

            price_today = round(price_arr[t] * (1 - disc[t] / 100), 2)
            sales_rows.append((d, st.store_id, pr.sku_id, sold, price_today,
                               round(sold * price_today, 2), promo_id_at[t]))
            truth_rows.append((d, st.store_id, pr.sku_id, want, want - sold, round(expected[t], 2)))
            snap_rows.append((d, st.store_id, pr.sku_id, sum(b["rem"] for b in active)))

# ---------------------------------------------------------------- write out
def save(rows, cols, name):
    df = pd.DataFrame(rows, columns=cols)
    df.to_csv(TRUTH / name, index=False)
    print(f"  {name:28s} {len(df):>7,} rows")
    return df


print("Writing data/truth/ ...")
prices = save(price_rows, ["sku_id", "store_id", "effective_date", "price"], "prices.csv")
promos = save(promo_rows, ["promo_id", "sku_id", "store_id", "start_date", "end_date", "discount_pct"], "promotions.csv")
sales = save(sales_rows, ["sale_date", "store_id", "sku_id", "qty_sold", "unit_price", "revenue", "promo_id"], "sales.csv")
receipts = save(receipt_rows, ["receipt_id", "sku_id", "store_id", "batch_id", "received_date", "qty", "unit_cost"], "receipts.csv")
waste = save(waste_rows, ["waste_date", "store_id", "sku_id", "batch_id", "qty", "reason", "cost"], "waste.csv")
snaps = save(snap_rows, ["snapshot_date", "store_id", "sku_id", "on_hand_qty"], "inventory_snapshots.csv")
batches = save(
    [(b["id"], b["id"].split("-")[2], b["id"].split("-")[1], dates[b["recv"]].date(),
      (dates[0] + pd.Timedelta(days=b["exp"])).date(), b["qty"], b["rem"]) for b in batch_rows],
    ["batch_id", "sku_id", "store_id", "received_date", "expiry_date", "qty_received", "qty_remaining"],
    "batches.csv",
)
truth = save(truth_rows, ["sale_date", "store_id", "sku_id", "true_demand", "lost_sales", "expected_demand"],
             "ground_truth_demand.csv")

# ---------------------------------------------------------------- checks
print("\nReconciliation (receipts - sales - waste == closing stock):")
key = ["store_id", "sku_id"]
chk = (receipts.groupby(key)["qty"].sum().rename("received").to_frame()
       .join(sales.groupby(key)["qty_sold"].sum().rename("sold"))
       .join(waste.groupby(key)["qty"].sum().rename("wasted"))
       .join(snaps[snaps["snapshot_date"] == snaps["snapshot_date"].max()]
             .set_index(key)["on_hand_qty"].rename("closing"))
       .join(batches.groupby(key)["qty_remaining"].sum().rename("batch_remaining")).fillna(0))
chk["ok"] = (chk["received"] - chk["sold"] - chk["wasted"] == chk["closing"]) & (chk["closing"] == chk["batch_remaining"])
print(f"  {int(chk['ok'].sum())} of {len(chk)} store/SKU pairs reconcile")

print("\nSummary by category:")
cat = products.set_index("sku_id")["category"]
s = sales.assign(category=sales["sku_id"].map(cat))
w = waste.assign(category=waste["sku_id"].map(cat))
r = receipts.assign(category=receipts["sku_id"].map(cat))
t = truth.assign(category=truth["sku_id"].map(cat))
summary = pd.DataFrame({
    "waste_%_of_received": (w.groupby("category")["qty"].sum() / r.groupby("category")["qty"].sum() * 100).round(1),
    "fill_rate_%": ((1 - t.groupby("category")["lost_sales"].sum() / t.groupby("category")["true_demand"].sum()) * 100).round(1),
    "stockout_days_%": (t.assign(so=t["lost_sales"] > 0).groupby("category")["so"].mean() * 100).round(1),
})
print(summary.to_string())
