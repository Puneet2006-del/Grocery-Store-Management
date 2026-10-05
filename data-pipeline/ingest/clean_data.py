"""Validate and clean the raw feeds.

Reads  data/raw/*.csv
Writes data/clean/*.csv                      cleaned tables, ready for MySQL
       data/reports/data_quality_report.csv  every issue found and how it was handled
       data/reports/quarantine_*.csv         rows that could not be repaired
       data/reports/reconciliation.csv       stock-balance check results

Run from project root:  python data-pipeline/ingest/clean_data.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parents[1] / "data"
RAW, CLEAN, REPORTS = BASE / "raw", BASE / "clean", BASE / "reports"
CLEAN.mkdir(parents=True, exist_ok=True)
REPORTS.mkdir(parents=True, exist_ok=True)

report = []   # (table, issue, rows, action)


def log(table, issue, n, action):
    n = int(n)
    if n:
        report.append((table, issue, n, action))


def read(name):
    return pd.read_csv(RAW / f"{name}.csv", dtype=str)


def parse_dates(s):
    """Accept YYYY-MM-DD and DD/MM/YYYY. Returns (dates, how many used the 2nd format)."""
    d = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
    alt = pd.to_datetime(s[d.isna()], format="%d/%m/%Y", errors="coerce")
    fixed = int(alt.notna().sum())
    return d.fillna(alt), fixed


def clean_dates(df, table, col):
    df[col], fixed = parse_dates(df[col])
    log(table, f"{col} not in ISO format", fixed, "parsed as DD/MM/YYYY")
    bad = df[col].isna()
    return df, bad


def norm_ids(df, table, cols):
    for c in cols:
        before = df[c].copy()
        df[c] = df[c].astype(str).str.strip().str.upper()
        log(table, f"{c} had whitespace/lowercase", (before != df[c]).sum(), "stripped and upper-cased")
    return df


def quarantine(df, mask, table, issue):
    n = int(mask.sum())
    if n:
        df[mask].to_csv(REPORTS / f"quarantine_{table}.csv", mode="a", index=False,
                        header=not (REPORTS / f"quarantine_{table}.csv").exists())
        log(table, issue, n, "removed to quarantine")
    return df[~mask].copy()


def dedupe(df, table, subset):
    n = df.duplicated(subset=subset).sum()
    log(table, "duplicate rows", n, f"kept first on {subset}")
    return df.drop_duplicates(subset=subset, keep="first")


# fresh quarantine files every run
for f in REPORTS.glob("quarantine_*.csv"):
    f.unlink()

stores = pd.read_csv(RAW / "stores.csv")
products = pd.read_csv(RAW / "products.csv")
STORES, SKUS = set(stores["store_id"]), set(products["sku_id"])
cost_of = products.set_index("sku_id")["cost"]

# ------------------------------------------------------------------ batches
batches = read("batches")
batches = norm_ids(batches, "batches", ["store_id", "sku_id"])
for c in ["received_date", "expiry_date"]:
    batches, _ = clean_dates(batches, "batches", c)
for c in ["qty_received", "qty_remaining"]:
    batches[c] = pd.to_numeric(batches[c], errors="coerce")
bad = (~batches["store_id"].isin(STORES) | ~batches["sku_id"].isin(SKUS)
       | (batches["expiry_date"] <= batches["received_date"])
       | (batches["qty_remaining"] < 0) | (batches["qty_remaining"] > batches["qty_received"])
       | batches[["received_date", "expiry_date", "qty_received"]].isna().any(axis=1))
batches = quarantine(batches, bad, "batches", "invalid batch (FK, expiry<=received or bad qty)")
batches = dedupe(batches, "batches", ["batch_id"])
BATCH_IDS = set(batches["batch_id"])

# ------------------------------------------------------------------ receipts
rec = read("receipts")
rec = norm_ids(rec, "receipts", ["store_id", "sku_id"])
rec, bad_date = clean_dates(rec, "receipts", "received_date")
rec["qty"] = pd.to_numeric(rec["qty"], errors="coerce")
rec["unit_cost"] = pd.to_numeric(rec["unit_cost"], errors="coerce")
rec = dedupe(rec, "receipts", ["receipt_id"])
bad = (bad_date.reindex(rec.index, fill_value=False) | ~rec["store_id"].isin(STORES) | ~rec["sku_id"].isin(SKUS)
       | ~rec["batch_id"].isin(BATCH_IDS) | ~(rec["qty"] > 0))
rec = quarantine(rec, bad, "receipts", "invalid receipt (date, FK or qty)")
miss = rec["unit_cost"].isna()
rec.loc[miss, "unit_cost"] = rec.loc[miss, "sku_id"].map(cost_of)
log("receipts", "missing unit_cost", miss.sum(), "filled with product standard cost")

# --------------------------------------------------------------------- waste
wst = read("waste")
wst = norm_ids(wst, "waste", ["store_id", "sku_id"])
wst, bad_date = clean_dates(wst, "waste", "waste_date")
before = wst["reason"].copy()
wst["reason"] = wst["reason"].str.strip().str.lower()
log("waste", "reason had wrong case", (before != wst["reason"]).sum(), "lower-cased")
wst["qty"] = pd.to_numeric(wst["qty"], errors="coerce")
wst["cost"] = pd.to_numeric(wst["cost"], errors="coerce")
wst = dedupe(wst, "waste", ["waste_date", "store_id", "sku_id", "batch_id", "reason"])
bad = (bad_date.reindex(wst.index, fill_value=False) | ~wst["store_id"].isin(STORES) | ~wst["sku_id"].isin(SKUS)
       | ~wst["batch_id"].isin(BATCH_IDS) | ~(wst["qty"] > 0) | ~wst["reason"].isin(["expired", "damaged"]))
wst = quarantine(wst, bad, "waste", "invalid waste row (date, FK, qty or reason)")
miss = wst["cost"].isna()
wst.loc[miss, "cost"] = (wst.loc[miss, "qty"] * wst.loc[miss, "sku_id"].map(cost_of)).round(2)
log("waste", "missing cost", miss.sum(), "filled as qty x product cost")

# --------------------------------------------------------------------- sales
sal = read("sales")
sal = norm_ids(sal, "sales", ["store_id", "sku_id"])
sal, bad_date = clean_dates(sal, "sales", "sale_date")
for c in ["qty_sold", "unit_price", "revenue"]:
    sal[c] = pd.to_numeric(sal[c], errors="coerce")
sal["promo_id"] = sal["promo_id"].replace({"": np.nan, "nan": np.nan})
neg = sal["qty_sold"] < 0
sal.loc[neg, "qty_sold"] = sal.loc[neg, "qty_sold"].abs()
log("sales", "negative qty_sold", neg.sum(), "sign corrected (abs)")
bad = (bad_date | ~sal["store_id"].isin(STORES) | ~sal["sku_id"].isin(SKUS) | sal["qty_sold"].isna())
sal = quarantine(sal, bad, "sales", "unknown store/SKU, bad date or missing qty")
sal = dedupe(sal, "sales", ["sale_date", "store_id", "sku_id"])
sal = sal.sort_values(["store_id", "sku_id", "sale_date"]).reset_index(drop=True)
# unit_price: derive from revenue/qty when possible, else carry forward within the SKU/store
miss = sal["unit_price"].isna()
derive = miss & sal["revenue"].notna() & (sal["qty_sold"] > 0)
sal.loc[derive, "unit_price"] = (sal.loc[derive, "revenue"] / sal.loc[derive, "qty_sold"]).round(2)
log("sales", "missing unit_price", derive.sum(), "derived as revenue / qty")
miss = sal["unit_price"].isna()
grp = sal.groupby(["store_id", "sku_id"])["unit_price"]
sal["unit_price"] = grp.ffill()
sal["unit_price"] = sal.groupby(["store_id", "sku_id"])["unit_price"].bfill()
log("sales", "missing unit_price (no revenue to derive from)", miss.sum(), "carried forward from previous day")
miss = sal["revenue"].isna()
sal.loc[miss, "revenue"] = (sal.loc[miss, "qty_sold"] * sal.loc[miss, "unit_price"]).round(2)
log("sales", "missing revenue", miss.sum(), "computed as qty x unit_price")

# delayed feed detection
last_sale = sal.groupby("store_id")["sale_date"].max()
for s, d in last_sale.items():
    lag = (last_sale.max() - d).days
    log("sales", f"DELAYED FEED: store {s} last sale {d.date()}", lag, "loaded as-is; flagged (not imputed)")
DELAYED = {s: d for s, d in last_sale.items() if d < last_sale.max()}

# ----------------------------------------------------------------- snapshots
snp = read("inventory_snapshots")
snp = norm_ids(snp, "inventory_snapshots", ["store_id", "sku_id"])
snp, bad_date = clean_dates(snp, "inventory_snapshots", "snapshot_date")
snp["on_hand_qty"] = pd.to_numeric(snp["on_hand_qty"], errors="coerce")
snp = quarantine(snp, bad_date | ~snp["store_id"].isin(STORES) | ~snp["sku_id"].isin(SKUS),
                 "inventory_snapshots", "invalid key or date")
snp = dedupe(snp, "inventory_snapshots", ["snapshot_date", "store_id", "sku_id"])

# expected closing stock from flows: cumulative(receipts - sales - waste)
all_dates = pd.date_range(snp["snapshot_date"].min(), snp["snapshot_date"].max())
idx = pd.MultiIndex.from_product([all_dates, sorted(STORES), sorted(SKUS)], names=["date", "store_id", "sku_id"])


def flow(df, date_col, qty_col):
    g = df.groupby([date_col, "store_id", "sku_id"])[qty_col].sum()
    g.index.names = ["date", "store_id", "sku_id"]
    return g.reindex(idx, fill_value=0)


net = flow(rec, "received_date", "qty") - flow(sal, "sale_date", "qty_sold") - flow(wst, "waste_date", "qty")
expected = net.groupby(level=["store_id", "sku_id"]).cumsum().rename("expected").reset_index()
snp = snp.merge(expected, left_on=["snapshot_date", "store_id", "sku_id"],
                right_on=["date", "store_id", "sku_id"], how="left").drop(columns="date")
miss = snp["on_hand_qty"].isna()
snp.loc[miss, "on_hand_qty"] = snp.loc[miss, "expected"]
log("inventory_snapshots", "missing on_hand_qty", miss.sum(), "rebuilt from receipts - sales - waste")

# reconciliation
snp["diff"] = snp["on_hand_qty"] - snp["expected"]
snp["explained_by_delay"] = snp.apply(
    lambda r: r["store_id"] in DELAYED and r["snapshot_date"] > DELAYED[r["store_id"]], axis=1)
mismatch = snp[snp["diff"] != 0]
unexplained = mismatch[~mismatch["explained_by_delay"]]
mismatch.to_csv(REPORTS / "reconciliation.csv", index=False)
log("inventory_snapshots", "stock-balance mismatch explained by delayed feed",
    int(mismatch["explained_by_delay"].sum()), "flagged in reconciliation.csv")
log("inventory_snapshots", "stock-balance mismatch UNEXPLAINED", len(unexplained), "investigate")
snp = snp.drop(columns=["expected", "diff", "explained_by_delay"])

# ------------------------------------------------- prices and promotions
prc = read("prices")
prc = norm_ids(prc, "prices", ["store_id", "sku_id"])
prc, _ = clean_dates(prc, "prices", "effective_date")
prc["price"] = pd.to_numeric(prc["price"], errors="coerce")
prc = quarantine(prc, ~prc["store_id"].isin(STORES) | ~prc["sku_id"].isin(SKUS) | ~(prc["price"] > 0)
                 | prc["effective_date"].isna(), "prices", "invalid price row")
prc = dedupe(prc, "prices", ["sku_id", "store_id", "effective_date"])

pro = read("promotions")
pro = norm_ids(pro, "promotions", ["store_id", "sku_id"])
for c in ["start_date", "end_date"]:
    pro, _ = clean_dates(pro, "promotions", c)
pro["discount_pct"] = pd.to_numeric(pro["discount_pct"], errors="coerce")
pro = quarantine(pro, ~pro["store_id"].isin(STORES) | ~pro["sku_id"].isin(SKUS)
                 | (pro["end_date"] < pro["start_date"]) | ~pro["discount_pct"].between(1, 90),
                 "promotions", "invalid promotion")
pro = dedupe(pro, "promotions", ["promo_id"])

# --------------------------------------------------------------------- save
outputs = {"batches": batches, "receipts": rec, "waste": wst, "sales": sal,
           "inventory_snapshots": snp, "prices": prc, "promotions": pro}
date_cols = {"batches": ["received_date", "expiry_date"], "receipts": ["received_date"],
             "waste": ["waste_date"], "sales": ["sale_date"], "inventory_snapshots": ["snapshot_date"],
             "prices": ["effective_date"], "promotions": ["start_date", "end_date"]}
int_cols = {"batches": ["qty_received", "qty_remaining"], "receipts": ["qty"], "waste": ["qty"],
            "sales": ["qty_sold"], "inventory_snapshots": ["on_hand_qty"]}
for name, df in outputs.items():
    for c in date_cols[name]:
        df[c] = df[c].dt.strftime("%Y-%m-%d")
    for c in int_cols.get(name, []):
        df[c] = df[c].astype(int)
    df.to_csv(CLEAN / f"{name}.csv", index=False)

rep = pd.DataFrame(report, columns=["table", "issue", "rows", "action"])
rep.to_csv(REPORTS / "data_quality_report.csv", index=False)
print("DATA QUALITY REPORT\n")
print(rep.to_string(index=False))
print("\nCLEAN TABLES (data/clean/):")
for name, df in outputs.items():
    print(f"  {name:22s} {len(df):>7,} rows")

print(f"\nStock-balance check: {len(unexplained)} unexplained mismatches "
      f"({int(mismatch['explained_by_delay'].sum())} explained by the delayed feed)")
if DELAYED:
    print("Delayed feeds: " + ", ".join(f"{s} (last data {d.date()})" for s, d in DELAYED.items()))
