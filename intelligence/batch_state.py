"""Rebuild the remaining stock of every batch on any past day, from receipts, sales and waste.

A retailer's systems rarely record which batch each sale came from. This replays the
history day by day (expire old stock, receive deliveries, sell oldest first) to estimate
what is left of each batch and when it expires.

Validation: the rebuilt on-hand stock is compared with the inventory snapshots, and the
rebuilt leftovers at expiry are compared with the waste records.

Run:  python intelligence/batch_state.py
"""
import numpy as np
import pandas as pd

from db import read_table


def load_inputs():
    return {
        "batches": read_table("batches", ["received_date", "expiry_date"]),
        "waste": read_table("waste", ["waste_date"]),
        "sales": read_table("sales", ["sale_date"]),
        "snapshots": read_table("inventory_snapshots", ["snapshot_date"]),
    }


def replay(inputs, capture_dates=()):
    """Returns (states, onhand, leftovers).

    states[(store, sku)][date]  -> DataFrame(batch_id, expiry_date, qty_remaining) at end of that day
    onhand                      -> DataFrame(date, store_id, sku_id, on_hand_replay)
    leftovers                   -> {batch_id: units written off at expiry}
    """
    batches, waste, sales = inputs["batches"], inputs["waste"], inputs["sales"]
    damaged = waste[waste["reason"] == "damaged"].groupby("batch_id")["qty"].sum()
    capture = set(pd.to_datetime(list(capture_dates)))
    all_days = pd.date_range(sales["sale_date"].min(), inputs["snapshots"]["snapshot_date"].max())
    sold_by = {k: g.set_index("sale_date")["qty_sold"].to_dict()
               for k, g in sales.groupby(["store_id", "sku_id"])}

    states, onhand_rows, leftovers = {}, [], {}
    for key, b in batches.groupby(["store_id", "sku_id"]):
        arrivals = {d: g for d, g in b.groupby("received_date")}
        sold = sold_by.get(key, {})
        active = []                                    # [batch_id, expiry_date, remaining]
        states[key] = {}
        for day in all_days:
            still = []
            for item in active:                        # 1. expiry: leftovers are written off
                if item[1] <= day:
                    leftovers[item[0]] = item[2]
                else:
                    still.append(item)
            active = still
            if day in arrivals:                        # 2. delivery (minus units damaged on arrival)
                for r in arrivals[day].itertuples():
                    active.append([r.batch_id, r.expiry_date, int(r.qty_received) - int(damaged.get(r.batch_id, 0))])
                active.sort(key=lambda x: x[1])
            want = sold.get(day, 0)                    # 3. sales, oldest expiry first
            want = 0 if pd.isna(want) else int(want)
            for item in active:
                take = min(item[2], want)
                item[2] -= take
                want -= take
            active = [x for x in active if x[2] > 0]
            onhand_rows.append((day, key[0], key[1], sum(x[2] for x in active)))
            if day in capture:
                states[key][day] = pd.DataFrame(
                    [(x[0], x[1], x[2]) for x in active], columns=["batch_id", "expiry_date", "qty_remaining"])
    onhand = pd.DataFrame(onhand_rows, columns=["date", "store_id", "sku_id", "on_hand_replay"])
    return states, onhand, leftovers


def validate(inputs, onhand, leftovers):
    snap = inputs["snapshots"].rename(columns={"snapshot_date": "date"})
    m = onhand.merge(snap, on=["date", "store_id", "sku_id"], how="inner")
    last_sale = inputs["sales"].groupby("store_id")["sale_date"].max()
    m = m[m["date"] <= m["store_id"].map(last_sale)]          # skip days of a delayed POS feed
    ok = (m["on_hand_replay"] == m["on_hand_qty"]).mean() * 100
    print(f"Rebuilt on-hand stock matches the inventory snapshots on {ok:.2f}% of {len(m):,} store/SKU/days "
          f"(delayed-feed days excluded)")

    exp = inputs["waste"][inputs["waste"]["reason"] == "expired"].groupby("batch_id")["qty"].sum()
    batches = inputs["batches"].set_index("batch_id")
    resolved = batches[batches["expiry_date"] <= inputs["snapshots"]["snapshot_date"].max()].index
    mine = pd.Series(leftovers).reindex(resolved).fillna(0)
    recorded = exp.reindex(resolved).fillna(0)
    match = (mine == recorded).mean() * 100
    print(f"Rebuilt leftovers at expiry match the waste records for {match:.2f}% of {len(resolved):,} expired batches")


if __name__ == "__main__":
    inp = load_inputs()
    _, onhand, left = replay(inp)
    validate(inp, onhand, left)
