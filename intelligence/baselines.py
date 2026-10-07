"""Baseline demand forecasts, the yardstick every later model must beat.

Rolling-origin backtest: for each day in the test window, forecast the next 7 days
using only data up to that day, then compare with what happened.

Methods
  naive          repeat the last observed day
  seasonal_naive same weekday last week
  ma7            average of the last 7 days
  weekday_avg    average of the same weekday over the last 4 weeks

Scored against true demand (simulation only) and against observed sales.
Run:  python intelligence/baselines.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

from dataset import build_panel

HORIZON = 7
TEST_DAYS = 56
OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(exist_ok=True)


def last_observed(hist):
    ok = hist[~np.isnan(hist)]
    return ok[-1] if len(ok) else 0.0


def forecast(method, y, t, h):
    """Forecast for day t+h using observations y[0..t] only."""
    if method == "naive":
        return last_observed(y[: t + 1])
    if method == "seasonal_naive":
        v = y[t + h - 7]
        return v if not np.isnan(v) else last_observed(y[: t + 1])
    if method == "ma7":
        w = y[max(0, t - 6): t + 1]
        return np.nanmean(w) if np.any(~np.isnan(w)) else 0.0
    if method == "weekday_avg":
        idx = [t + h - 7 * k for k in range(1, 5) if t + h - 7 * k >= 0]
        w = y[idx]
        return np.nanmean(w) if np.any(~np.isnan(w)) else last_observed(y[: t + 1])
    raise ValueError(method)


METHODS = ["naive", "seasonal_naive", "ma7", "weekday_avg"]


def backtest(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    n_days = panel["date"].nunique()
    test_start = n_days - TEST_DAYS
    for (store, sku), g in panel.groupby(["store_id", "sku_id"]):
        y = g["qty_sold"].to_numpy(dtype=float)
        truth = g["true_demand"].to_numpy(dtype=float)
        cat = g["category"].iloc[0]
        dates = g["date"].to_numpy()
        for t in range(test_start - 1, n_days - 1):
            for h in range(1, HORIZON + 1):
                target = t + h
                if target < test_start or target >= n_days:
                    continue
                for m in METHODS:
                    rows.append((m, store, sku, cat, dates[target], h, forecast(m, y, t, h),
                                 truth[target], y[target]))
    return pd.DataFrame(rows, columns=["method", "store_id", "sku_id", "category", "date", "horizon",
                                       "pred", "actual_true", "actual_obs"])


def score(df: pd.DataFrame, by) -> pd.DataFrame:
    def f(g):
        obs = g.dropna(subset=["actual_obs"])
        tr = g.dropna(subset=["actual_true"])
        return pd.Series({
            "wape_true_%": 100 * (tr["pred"] - tr["actual_true"]).abs().sum() / tr["actual_true"].sum() if len(tr) else np.nan,
            "bias_true_%": 100 * (tr["pred"].sum() - tr["actual_true"].sum()) / tr["actual_true"].sum() if len(tr) else np.nan,
            "wape_obs_%": 100 * (obs["pred"] - obs["actual_obs"]).abs().sum() / obs["actual_obs"].sum(),
        })
    return df.groupby(by).apply(f, include_groups=False).round(1)


if __name__ == "__main__":
    panel = build_panel()
    res = backtest(panel)
    print(f"Backtest: {res['date'].min().date()} to {res['date'].max().date()}, "
          f"horizons 1-{HORIZON}, {res['store_id'].nunique() * res['sku_id'].nunique()} store/SKU series\n")

    overall = score(res, ["method"]).sort_values("wape_true_%")
    print("OVERALL (lower WAPE is better; bias > 0 means over-forecasting)")
    print(overall.to_string(), "\n")
    by_cat = score(res, ["category", "method"]).reset_index().pivot(
        index="category", columns="method", values="wape_true_%")[METHODS]
    print("WAPE vs true demand by category (%)")
    print(by_cat.to_string(), "\n")
    by_h = score(res, ["horizon", "method"]).reset_index().pivot(
        index="horizon", columns="method", values="wape_true_%")[METHODS]
    print("WAPE vs true demand by horizon, days ahead (%)")
    print(by_h.to_string())

    out = pd.concat([
        overall.reset_index().assign(view="overall", key="all"),
        score(res, ["category", "method"]).reset_index().assign(view="category").rename(columns={"category": "key"}),
        score(res, ["horizon", "method"]).reset_index().assign(view="horizon").rename(columns={"horizon": "key"}),
    ], ignore_index=True)
    out.to_csv(OUT / "baseline_metrics.csv", index=False)
    print(f"\nSaved: {OUT / 'baseline_metrics.csv'}")
