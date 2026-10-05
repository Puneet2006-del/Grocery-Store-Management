"""Create the 'raw feed' files by copying data/truth/ and injecting realistic mess.

Why: real retail feeds are delayed, incomplete and duplicated. Cleaning only
means something if there is something to clean. The clean originals stay in
data/truth/, so the pipeline can be checked against them later.

Run from data-pipeline/generate:  python inject_noise.py
"""
import numpy as np
import pandas as pd

from config import END_DATE, RAW, SEED

TRUTH = RAW.parent / "truth"
REPORTS = RAW.parent / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(SEED + 1)
injected = []          # answer key: what mess was added where


def pick(df, frac):
    return rng.choice(df.index.to_numpy(), size=max(1, int(len(df) * frac)), replace=False)


def blank(df, table, col, frac):
    idx = pick(df, frac)
    df.loc[idx, col] = np.nan
    injected.append((table, f"missing {col}", len(idx)))


def mixed_dates(df, table, col, frac):
    df[col] = df[col].astype(str)
    idx = pick(df, frac)
    df.loc[idx, col] = pd.to_datetime(df.loc[idx, col]).dt.strftime("%d/%m/%Y")
    injected.append((table, f"{col} in DD/MM/YYYY format", len(idx)))


def duplicate(df, table, frac):
    dup = df.loc[pick(df, frac)]
    injected.append((table, "duplicate rows", len(dup)))
    return pd.concat([df, dup], ignore_index=True)


# ------------------------------------------------------------------ sales
sales = pd.read_csv(TRUTH / "sales.csv", dtype={"promo_id": str})
cutoff = pd.Timestamp(END_DATE) - pd.Timedelta(days=2)
late = (sales["store_id"] == "S03") & (pd.to_datetime(sales["sale_date"]) > cutoff)
sales = sales[~late].reset_index(drop=True)
injected.append(("sales", "delayed POS feed: S03 missing last 2 days", int(late.sum())))

blank(sales, "sales", "unit_price", 0.015)
blank(sales, "sales", "revenue", 0.010)
neg = pick(sales[sales["qty_sold"] > 0], 0.002)
sales.loc[neg, "qty_sold"] *= -1
injected.append(("sales", "negative qty_sold (sign error)", len(neg)))
mixed_dates(sales, "sales", "sale_date", 0.02)
sid = pick(sales, 0.01)
sales["store_id"] = sales["store_id"].astype(str)
sales.loc[sid, "store_id"] = " " + sales.loc[sid, "store_id"].str.lower()
injected.append(("sales", "store_id lowercase/whitespace", len(sid)))
orph = sales.loc[pick(sales, 0.001)].copy()
orph["sku_id"] = "P99"
injected.append(("sales", "unknown sku_id (orphan rows)", len(orph)))
sales = pd.concat([sales, orph], ignore_index=True)
sales = duplicate(sales, "sales", 0.004)
sales.to_csv(RAW / "sales.csv", index=False)

# --------------------------------------------------------------- receipts
receipts = pd.read_csv(TRUTH / "receipts.csv")
blank(receipts, "receipts", "unit_cost", 0.01)
mixed_dates(receipts, "receipts", "received_date", 0.02)
receipts = duplicate(receipts, "receipts", 0.003)
receipts.to_csv(RAW / "receipts.csv", index=False)

# ------------------------------------------------------------------ waste
waste = pd.read_csv(TRUTH / "waste.csv")
blank(waste, "waste", "cost", 0.01)
ridx = pick(waste, 0.02)
waste.loc[ridx, "reason"] = waste.loc[ridx, "reason"].str.upper()
injected.append(("waste", "reason in UPPERCASE", len(ridx)))
waste = duplicate(waste, "waste", 0.003)
waste.to_csv(RAW / "waste.csv", index=False)

# -------------------------------------------------------------- snapshots
snaps = pd.read_csv(TRUTH / "inventory_snapshots.csv")
blank(snaps, "inventory_snapshots", "on_hand_qty", 0.01)
snaps = duplicate(snaps, "inventory_snapshots", 0.003)
snaps.to_csv(RAW / "inventory_snapshots.csv", index=False)

# ---------------------------------------- tables copied through unchanged
for name in ["prices", "promotions", "batches"]:
    pd.read_csv(TRUTH / f"{name}.csv").to_csv(RAW / f"{name}.csv", index=False)

key = pd.DataFrame(injected, columns=["table", "issue", "rows"])
key.to_csv(REPORTS / "noise_injected.csv", index=False)
print("Injected mess into data/raw/ (answer key: data/reports/noise_injected.csv):\n")
print(key.to_string(index=False))
