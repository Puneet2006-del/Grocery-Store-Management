"""Demand-forecasting model: gradient boosting, 1 to 7 days ahead, one model for all stores and SKUs.

For every origin day t and horizon h (1-7) it predicts demand on day t+h from
  - recent sales history (last value, 7/14/28-day averages, same weekday 1-4 weeks back)
  - what is known about the target day (weekday, promotion, event, weather)
  - store, SKU, category and shelf life

Stockout handling: on days when the shelf ran empty, observed sales understate demand.
Two versions are trained to show the effect:
  gbm_censor_aware  stockout days are treated as missing in the history and left out of training
  gbm_naive         stockout days are used as if they were real demand

Weather uses the actual values as a stand-in for a weather forecast.
Same backtest as baselines.py (last 56 days, horizons 1-7).

Run:  python intelligence/forecast_model.py
"""
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance

from baselines import HORIZON, METHODS, TEST_DAYS, backtest, score
from dataset import TRUTH_FILE, build_panel

SEED = 42
OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(exist_ok=True)

FEATURES = ["horizon", "dow", "month", "is_weekend", "discount_pct", "event_impact", "temp_c", "rain_mm",
            "last_obs", "r7", "r14", "r28", "lag7", "lag14", "lag21", "lag28", "lag_wd_mean",
            "store", "sku", "category", "shelf_life_days"]


def build_rows(panel: pd.DataFrame, censor_aware: bool) -> pd.DataFrame:
    frames = []
    for (store, sku), g in panel.groupby(["store_id", "sku_id"], sort=False):
        raw = g["qty_sold"].to_numpy(float)
        stock = g["stockout"].to_numpy(bool)
        true = g["true_demand"].to_numpy(float)
        hist = raw.copy()
        if censor_aware:
            hist[stock] = np.nan
        s = pd.Series(hist)
        roll = {w: s.rolling(w, min_periods=1).mean().to_numpy() for w in (7, 14, 28)}
        n = len(g)
        for h in range(1, HORIZON + 1):
            t = np.arange(28, n - h)
            tgt = t + h
            lags = np.column_stack([hist[tgt - 7], hist[tgt - 14], hist[tgt - 21], hist[tgt - 28]])
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                wd_mean = np.nanmean(lags, axis=1)
            frames.append(pd.DataFrame({
                "origin": t, "target": tgt, "horizon": h,
                "dow": g["dow"].to_numpy()[tgt], "month": g["month"].to_numpy()[tgt],
                "is_weekend": g["is_weekend"].to_numpy()[tgt].astype(int),
                "discount_pct": g["discount_pct"].to_numpy()[tgt],
                "event_impact": g["event_impact"].to_numpy()[tgt],
                "temp_c": g["temp_c"].to_numpy()[tgt], "rain_mm": g["rain_mm"].to_numpy()[tgt],
                "last_obs": hist[t], "r7": roll[7][t], "r14": roll[14][t], "r28": roll[28][t],
                "lag7": lags[:, 0], "lag14": lags[:, 1], "lag21": lags[:, 2], "lag28": lags[:, 3],
                "lag_wd_mean": wd_mean,
                "store": store, "sku": sku, "category": g["category"].iloc[0],
                "shelf_life_days": g["shelf_life_days"].iloc[0],
                "date": g["date"].to_numpy()[tgt],
                "y_obs": raw[tgt], "y_true": true[tgt], "censored": stock[tgt],
            }))
    rows = pd.concat(frames, ignore_index=True)
    for c in ["store", "sku", "category"]:
        rows[c] = rows[c].astype("category")
    return rows


def make_model():
    return HistGradientBoostingRegressor(
        loss="poisson", learning_rate=0.05, max_iter=500, max_leaf_nodes=24, min_samples_leaf=50,
        l2_regularization=1.0, early_stopping=True, n_iter_no_change=25,
        categorical_features="from_dtype", random_state=SEED)


def run_variant(panel, name, censor_aware, test_start):
    rows = build_rows(panel, censor_aware)
    train = rows[(rows["target"] < test_start) & rows["y_obs"].notna()]
    if censor_aware:
        train = train[~train["censored"]]
    test = rows[rows["origin"] >= test_start - 1]
    model = make_model().fit(train[FEATURES], train["y_obs"])
    pred = np.clip(model.predict(test[FEATURES]), 0, None)
    res = pd.DataFrame({"method": name, "store_id": test["store"].astype(str).to_numpy(),
                        "sku_id": test["sku"].astype(str).to_numpy(),
                        "category": test["category"].astype(str).to_numpy(), "date": test["date"].to_numpy(),
                        "horizon": test["horizon"].to_numpy(), "pred": pred,
                        "actual_true": test["y_true"].to_numpy(), "actual_obs": test["y_obs"].to_numpy()})
    print(f"  {name}: trained on {len(train):,} rows, tested on {len(test):,} rows ({model.n_iter_} trees)")
    return res, model, test


if __name__ == "__main__":
    panel = build_panel()
    test_start = panel["date"].nunique() - TEST_DAYS

    print("Training...")
    res_aware, model_aware, test_aware = run_variant(panel, "gbm_censor_aware", True, test_start)
    res_naive, _, _ = run_variant(panel, "gbm_naive", False, test_start)
    base = backtest(panel)
    allres = pd.concat([base, res_naive, res_aware], ignore_index=True)

    order = ["gbm_censor_aware", "gbm_naive"] + METHODS
    overall = score(allres, ["method"]).loc[order]
    print("\nOVERALL (WAPE vs true demand; lower is better)")
    print(overall.to_string())
    if TRUTH_FILE.exists():  # best any forecaster could do: knowing the exact expected demand
        tr = pd.read_csv(TRUTH_FILE, parse_dates=["sale_date"])
        tr = tr[tr["sale_date"] >= np.sort(panel["date"].unique())[test_start]]
        floor = 100 * (tr["expected_demand"] - tr["true_demand"]).abs().sum() / tr["true_demand"].sum()
        print(f"\nNoise floor (perfect knowledge of expected demand): {floor:.1f}% WAPE")
    best_base = overall.loc[METHODS, "wape_true_%"].min()
    gain = 100 * (best_base - overall.loc["gbm_censor_aware", "wape_true_%"]) / best_base
    print(f"\nBest baseline: {best_base:.1f}% | model: {overall.loc['gbm_censor_aware', 'wape_true_%']:.1f}% "
          f"-> {gain:.1f}% lower error than the best baseline")

    show = ["gbm_censor_aware", "gbm_naive", "weekday_avg", "ma7"]
    for by in ["category", "horizon"]:
        t = score(allres, [by, "method"]).reset_index().pivot(index=by, columns="method", values="wape_true_%")[show]
        print(f"\nWAPE vs true demand by {by} (%)")
        print(t.to_string())

    sample = test_aware.dropna(subset=["y_obs"]).sample(n=min(15000, len(test_aware)), random_state=SEED)
    imp = permutation_importance(model_aware, sample[FEATURES], sample["y_obs"], n_repeats=3,
                                 random_state=SEED, scoring="neg_mean_absolute_error")
    imp_df = pd.Series(imp.importances_mean, index=FEATURES).sort_values(ascending=False)
    print("\nMost important features (error increase when shuffled):")
    print(imp_df.head(8).round(3).to_string())

    out = pd.concat([
        overall.reset_index().assign(view="overall", key="all"),
        score(allres, ["category", "method"]).reset_index().assign(view="category").rename(columns={"category": "key"}),
        score(allres, ["horizon", "method"]).reset_index().assign(view="horizon").rename(columns={"horizon": "key"}),
    ], ignore_index=True)
    out.to_csv(OUT / "model_metrics.csv", index=False)
    imp_df.rename("importance").to_csv(OUT / "feature_importance.csv")
    print(f"\nSaved: {OUT / 'model_metrics.csv'} and feature_importance.csv")
