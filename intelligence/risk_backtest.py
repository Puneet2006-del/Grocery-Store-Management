"""Backtest of the spoilage-risk and stockout predictions against what really happened.

For each day in the last ~7 weeks (the "as-of" day):
  1. rebuild the batches on the shelf at the end of that day (batch_state.py)
  2. take the demand forecast (with range) a model trained only on earlier data would have made
  3. run the risk engine (risk_engine.simulate_series)
  4. compare with the real outcome: units written off per batch, and shortfall before the next delivery

A simple rule-based method is scored alongside, as a yardstick:
  batch rule   at risk when the stock ahead of the batch exceeds recent daily sales x days left
  stockout rule at risk when days of cover (stock / recent daily sales) is shorter than the gap to delivery

Run:  python intelligence/risk_backtest.py        (takes a few minutes)
"""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

import risk_engine
from baselines import TEST_DAYS
from batch_state import load_inputs, replay
from dataset import TRUTH_FILE, build_panel
from forecast_model import FEATURES, build_rows
from forecast_next_week import fit_all, predict_all, widen

OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(exist_ok=True)
risk_engine.N_SIM = 500            # fewer simulations to keep the backtest fast
SEED = 42


def prepare_forecasts(panel):
    n = panel["date"].nunique()
    test_start = n - TEST_DAYS
    rows = build_rows(panel, censor_aware=False)
    train = rows[(rows["target"] < test_start) & rows["y_obs"].notna()]
    test = rows[(rows["origin"] >= test_start - 1) & (rows["origin"] <= n - 8)].copy()   # all 7 horizons exist
    models = fit_all(train)
    mean, lo, hi = predict_all(models, test)
    obs = test["y_obs"].to_numpy()
    seen = ~np.isnan(obs)
    k = next((k for k in np.arange(1.0, 2.51, 0.05)
              if ((obs >= widen(mean, lo, hi, k)[0]) & (obs <= widen(mean, lo, hi, k)[1]))[seen].mean() >= 0.80), 2.5)
    lo, hi = widen(mean, lo, hi, k)
    test["predicted_qty"], test["lower_qty"], test["upper_qty"] = mean, lo, hi
    return test, test_start, n


def auc(y, score):
    return roc_auc_score(y, score) if len(set(y)) == 2 else np.nan


if __name__ == "__main__":
    panel = build_panel()
    dates = np.sort(panel["date"].unique())
    end = pd.Timestamp(dates[-1])

    print("Training forecast models on data before the test window...")
    test, test_start, n = prepare_forecasts(panel)
    origins = sorted(test["origin"].unique())
    origin_dates = {t: pd.Timestamp(dates[t]) for t in origins}

    print(f"Rebuilding batch stock for {len(origins)} as-of days "
          f"({origin_dates[origins[0]].date()} to {origin_dates[origins[-1]].date()})...")
    inputs = load_inputs()
    states, _, _ = replay(inputs, capture_dates=origin_dates.values())

    products = inputs_p = pd.read_sql("SELECT sku_id, category, cost FROM products", risk_engine.engine).set_index("sku_id")
    waste = inputs["waste"]
    expired = waste[waste["reason"] == "expired"].groupby("batch_id")["qty"].sum()
    truth = pd.read_csv(TRUTH_FILE, parse_dates=["sale_date"])
    lost = truth.set_index(["store_id", "sku_id", "sale_date"])["lost_sales"]
    qty_by = {k: g["qty_sold"].to_numpy(float) for k, g in panel.groupby(["store_id", "sku_id"])}
    rng = np.random.default_rng(SEED)

    print("Running the risk engine on each past day...")
    fc_groups = test.groupby([test["store"].astype(str), test["sku"].astype(str), "origin"], observed=True)
    batch_rows, sku_rows = [], []
    for (store, sku, t), fc in fc_groups:
        o = origin_dates[t]
        b = states[(store, sku)].get(o)
        cat = products.loc[sku, "category"]
        d_next = risk_engine.next_delivery(o, cat)
        window = (d_next - o).days - 1
        fc = fc.sort_values("horizon")
        recent = qty_by[(store, sku)][max(0, t - 6): t + 1]
        ma7 = np.nanmean(recent) if np.any(~np.isnan(recent)) else 0.0
        if b is None or b.empty:
            stock, so_prob = 0, (1.0 if window > 0 else 0.0)
        else:
            b = b.sort_values("expiry_date").reset_index(drop=True)
            unsold, stockout, shortfall, mu, window = risk_engine.simulate_series(b, fc, o, d_next, rng)
            stock, so_prob = float(b["qty_remaining"].sum()), float(stockout.mean())
            cum = b["qty_remaining"].cumsum().to_numpy(float)
            for i, r in b.iterrows():
                dte = int((r["expiry_date"] - o).days)
                if r["expiry_date"] > end:      # outcome not observable inside the data
                    continue
                q = float(r["qty_remaining"])
                batch_rows.append((o, r["batch_id"], store, sku, dte, q, unsold[i].mean(),
                                   (unsold[i] > 0.10 * q).mean(), float(expired.get(r["batch_id"], 0)),
                                   cum[i] / (max(ma7, 0.1) * max(dte - 1, 0.5))))
        if window >= 1 and d_next - pd.Timedelta(days=1) <= end:
            days = pd.date_range(o + pd.Timedelta(days=1), d_next - pd.Timedelta(days=1))
            actual_short = float(sum(lost.get((store, sku, d), 0) for d in days))
            sku_rows.append((o, store, sku, window, stock, so_prob, actual_short,
                             window - stock / max(ma7, 0.1)))

    bd = pd.DataFrame(batch_rows, columns=["as_of", "batch_id", "store_id", "sku_id", "days_to_expiry", "qty",
                                           "pred_unsold", "spoilage_prob", "actual_unsold", "rule_score"])
    sd = pd.DataFrame(sku_rows, columns=["as_of", "store_id", "sku_id", "window_days", "stock", "stockout_prob",
                                         "actual_shortfall", "rule_score"])
    bd["pred_pct"] = bd["pred_unsold"] / bd["qty"]
    bd["act_pct"] = bd["actual_unsold"] / bd["qty"]
    bd["risk_level"] = np.where(bd["pred_pct"] >= risk_engine.BATCH_HIGH, "HIGH",
                                np.where(bd["pred_pct"] >= risk_engine.BATCH_MED, "MEDIUM", "LOW"))
    bd.to_csv(OUT / "risk_backtest_batches.csv", index=False)
    sd.to_csv(OUT / "risk_backtest_skus.csv", index=False)

    summary = []
    print(f"\n=== SPOILAGE RISK PER BATCH ({len(bd):,} batch predictions, as-of days "
          f"{origin_dates[origins[0]].date()} to {origin_dates[origins[-1]].date()}) ===")
    for label, sub in [("preventable (2+ days left)", bd[bd["days_to_expiry"] >= 2]), ("all batches", bd)]:
        act_over10 = (sub["act_pct"] > 0.10).astype(int)
        act_high = sub["act_pct"] >= risk_engine.BATCH_HIGH
        flag = sub["risk_level"] == "HIGH"
        rule_flag = sub["rule_score"] > 1
        prec = act_high[flag].mean() if flag.any() else np.nan
        rec = flag[act_high].mean() if act_high.any() else np.nan
        rprec = act_high[rule_flag].mean() if rule_flag.any() else np.nan
        rrec = rule_flag[act_high].mean() if act_high.any() else np.nan
        print(f"\n[{label}] {len(sub):,} batches, {int(act_high.sum())} actually lost 30%+ of their units")
        print(f"  Units written off: predicted {sub['pred_unsold'].sum():,.0f} vs actual {sub['actual_unsold'].sum():,.0f}"
              f" | mean abs error per batch {np.abs(sub['pred_unsold'] - sub['actual_unsold']).mean():.1f} units")
        print(f"  Ranking quality (AUC, 1.0 perfect, 0.5 random): engine {auc(act_over10, sub['spoilage_prob']):.3f}"
              f" | rule {auc(act_over10, sub['rule_score']):.3f}")
        print(f"  Flagging HIGH risk: engine precision {prec * 100:.0f}% recall {rec * 100:.0f}%"
              f" | rule precision {rprec * 100:.0f}% recall {rrec * 100:.0f}%")
        summary.append((label, len(sub), sub["pred_unsold"].sum(), sub["actual_unsold"].sum(),
                        auc(act_over10, sub["spoilage_prob"]), auc(act_over10, sub["rule_score"]),
                        prec, rec, rprec, rrec))
        if label.startswith("preventable"):
            cal = sub.groupby("risk_level").agg(batches=("qty", "size"), predicted_pct=("pred_pct", "mean"),
                                                actual_pct=("act_pct", "mean")).reindex(["LOW", "MEDIUM", "HIGH"])
            print("  Calibration: average share of batch written off, by predicted risk level")
            print((cal.assign(predicted_pct=lambda x: (x["predicted_pct"] * 100).round(1),
                              actual_pct=lambda x: (x["actual_pct"] * 100).round(1))).to_string())

    sd["actual_stockout"] = (sd["actual_shortfall"] > 0).astype(int)
    print(f"\n=== STOCKOUT BEFORE NEXT DELIVERY ({len(sd):,} predictions, "
          f"{int(sd['actual_stockout'].sum())} real stockouts = {sd['actual_stockout'].mean() * 100:.1f}%) ===")
    if sd["actual_stockout"].sum() > 0:
        flag = sd["stockout_prob"] >= risk_engine.STOCKOUT_MED
        rflag = sd["rule_score"] > 0
        a = sd["actual_stockout"].astype(bool)
        print(f"  Ranking quality (AUC): engine {auc(sd['actual_stockout'], sd['stockout_prob']):.3f}"
              f" | rule {auc(sd['actual_stockout'], sd['rule_score']):.3f}")
        print(f"  Alert at probability >= {risk_engine.STOCKOUT_MED:.0%}: engine flagged {int(flag.sum())}, "
              f"caught {int((flag & a).sum())} of {int(a.sum())} real stockouts "
              f"(precision {a[flag].mean() * 100 if flag.any() else float('nan'):.0f}%)")
        print(f"  Rule flagged {int(rflag.sum())}, caught {int((rflag & a).sum())} of {int(a.sum())} "
              f"(precision {a[rflag].mean() * 100 if rflag.any() else float('nan'):.0f}%)")
        sd["bin"] = pd.cut(sd["stockout_prob"], [-0.01, 0.1, 0.3, 0.6, 1.0], labels=["0-10%", "10-30%", "30-60%", "60-100%"])
        cal = sd.groupby("bin", observed=True).agg(predictions=("stockout_prob", "size"),
                                                   predicted=("stockout_prob", "mean"),
                                                   actual_rate=("actual_stockout", "mean"))
        print("  Calibration: predicted probability vs how often stockouts really happened")
        print(cal.assign(predicted=lambda x: (x["predicted"] * 100).round(1),
                         actual_rate=lambda x: (x["actual_rate"] * 100).round(1)).to_string())
    pd.DataFrame(summary, columns=["subset", "batches", "pred_unsold", "actual_unsold", "auc_engine", "auc_rule",
                                   "high_precision", "high_recall", "rule_precision", "rule_recall"]
                 ).to_csv(OUT / "risk_backtest_summary.csv", index=False)
    print(f"\nSaved results to {OUT}")
