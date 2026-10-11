"""Production forecast: next 7 days of demand per store and SKU, with an 80% range, saved to MySQL.

Steps
  1. Check how reliable the range is on the last 56 days (backtest, as in forecast_model.py)
  2. Train on ALL available history
  3. Forecast the 7 days after the last day in the database
  4. Write to the demand_forecasts table (create it first with db/schema_m2.sql)

Three models are used: the mean forecast (Poisson loss) plus a P10 and a P90 quantile model.
The range is widened by a factor chosen on the backtest so it really covers about 80% of outcomes.
It is the confidence information later shown with each recommendation.

For the future days it uses the weather forecast, public holidays and planned promotions stored in the
database; anything missing falls back to: no promotion, no event, no rain, temperature = last 7-day average.

Run:  python intelligence/forecast_next_week.py
"""
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sqlalchemy import inspect, text

from baselines import HORIZON, TEST_DAYS
from dataset import build_panel
from db import engine, read_table
from forecast_model import FEATURES, SEED, build_rows, make_model

MODEL_VERSION = "gbm_v1"
MODEL_FILE = Path(__file__).resolve().parent / "output" / "forecast_models.joblib"


def make_quantile(q):
    return HistGradientBoostingRegressor(
        loss="quantile", quantile=q, learning_rate=0.05, max_iter=400, max_leaf_nodes=24,
        min_samples_leaf=50, l2_regularization=1.0, early_stopping=True, n_iter_no_change=25,
        categorical_features="from_dtype", random_state=SEED)


def fit_all(train):
    X, y = train[FEATURES], train["y_obs"]
    return {"mean": make_model().fit(X, y), "lo": make_quantile(0.1).fit(X, y), "hi": make_quantile(0.9).fit(X, y)}


def predict_all(models, rows):
    mean = np.clip(models["mean"].predict(rows[FEATURES]), 0, None)
    lo = np.clip(models["lo"].predict(rows[FEATURES]), 0, None)
    hi = np.clip(models["hi"].predict(rows[FEATURES]), 0, None)
    return mean, np.minimum(lo, mean), np.maximum(hi, mean)   # keep lo <= mean <= hi


def widen(mean, lo, hi, k):
    """Stretch the range around the forecast by factor k."""
    return np.clip(mean - (mean - lo) * k, 0, None), mean + (hi - mean) * k


def interval_backtest(panel):
    """Check the P10-P90 range on the last 56 days and find a widening factor that reaches 80%.

    The factor is chosen using observed sales only (all a real retailer would have).
    """
    n = panel["date"].nunique()
    test_start = n - TEST_DAYS
    rows = build_rows(panel, censor_aware=False)
    train = rows[(rows["target"] < test_start) & rows["y_obs"].notna()]
    test = rows[(rows["origin"] >= test_start - 1)].copy()
    mean, lo, hi = predict_all(fit_all(train), test)
    obs = test["y_obs"].to_numpy()
    seen = ~np.isnan(obs)

    def cover(k, actual, mask):
        lo_k, hi_k = widen(mean, lo, hi, k)
        return ((actual >= lo_k) & (actual <= hi_k))[mask].mean()

    k = next((k for k in np.arange(1.0, 2.51, 0.05) if cover(k, obs, seen) >= 0.80), 2.5)
    true = test["y_true"].to_numpy()
    has_true = ~np.isnan(true)
    print(f"  Raw P10-P90 range: observed sales inside {cover(1.0, obs, seen) * 100:.1f}% of the time (ideal 80%)")
    print(f"  Widening the range by x{k:.2f} gives {cover(k, obs, seen) * 100:.1f}% on observed sales"
          + (f" and {cover(k, true, has_true) * 100:.1f}% on true demand" if has_true.any() else ""))
    lo_k, hi_k = widen(mean, lo, hi, k)
    print(f"  Average range width after widening: {(hi_k - lo_k).sum() / mean.sum() * 100:.0f}% of the forecast")
    return float(k)


def extend_panel(panel, days=HORIZON):
    """Add the next `days` days with what is known in advance: the weather forecast, public holidays and
    planned promotions (from the weather, events and promotions tables). Anything not in those tables falls
    back to: temperature = last 7-day average, no rain, no event, no promotion."""
    last = panel["date"].max()
    recent_temp = panel[panel["date"] > last - pd.Timedelta(days=7)].groupby("city")["temp_c"].mean()
    wx = read_table("weather", ["weather_date"])
    temp_of = {(r.weather_date, r.city): r.temp_c for r in wx.itertuples()}
    rain_of = {(r.weather_date, r.city): r.rain_mm for r in wx.itertuples()}
    ev = read_table("events", ["event_date"]).groupby(["event_date", "city"])["expected_impact"].max().to_dict()
    promos = read_table("promotions", ["start_date", "end_date"])
    parts = [panel]
    for d in range(1, days + 1):
        day = last + pd.Timedelta(days=d)
        f = panel.groupby(["store_id", "sku_id"], as_index=False).tail(1).copy()
        active = promos[(promos["start_date"] <= day) & (promos["end_date"] >= day)]
        disc = {(r.store_id, r.sku_id): float(r.discount_pct) for r in active.itertuples()}
        f["date"] = day
        f["qty_sold"] = np.nan
        f["on_hand_end"] = np.nan
        f["true_demand"] = np.nan
        f["stockout"] = False
        f["discount_pct"] = [disc.get((s, k), 0.0) for s, k in zip(f["store_id"], f["sku_id"])]
        f["event_impact"] = [float(ev.get((day, c), 1.0)) for c in f["city"]]
        f["rain_mm"] = [float(rain_of.get((day, c), 0.0)) for c in f["city"]]
        f["temp_c"] = [float(temp_of.get((day, c), recent_temp[c])) for c in f["city"]]
        f["dow"] = day.dayofweek
        f["month"] = day.month
        f["is_weekend"] = day.dayofweek >= 5
        parts.append(f)
    return pd.concat(parts, ignore_index=True).sort_values(["store_id", "sku_id", "date"]).reset_index(drop=True)


def save(df):
    run_date = df["run_date"].iloc[0]
    out = df.copy()
    for c in ["run_date", "forecast_date"]:
        out[c] = pd.to_datetime(out[c]).dt.date
    with engine.begin() as conn:
        if inspect(conn).has_table("demand_forecasts"):
            conn.execute(text("DELETE FROM demand_forecasts WHERE run_date = :d"), {"d": run_date.date()})
        out.to_sql("demand_forecasts", conn, if_exists="append", index=False, chunksize=2000)


if __name__ == "__main__":
    panel = build_panel()
    n_hist = panel["date"].nunique()
    last_day = panel["date"].max()

    print("Checking the forecast range on past data...")
    widen_k = interval_backtest(panel)

    print("\nTraining on all history and forecasting the next 7 days...")
    rows = build_rows(extend_panel(panel), censor_aware=False)
    train = rows[(rows["target"] < n_hist) & rows["y_obs"].notna()]
    models = fit_all(train)
    todo = rows[rows["origin"] == n_hist - 1].copy()
    mean, lo, hi = predict_all(models, todo)
    lo, hi = widen(mean, lo, hi, widen_k)

    result = pd.DataFrame({
        "run_date": last_day, "forecast_date": pd.to_datetime(todo["date"].to_numpy()),
        "horizon": todo["horizon"].to_numpy(), "store_id": todo["store"].astype(str).to_numpy(),
        "sku_id": todo["sku"].astype(str).to_numpy(), "predicted_qty": mean.round(2),
        "lower_qty": lo.round(2), "upper_qty": hi.round(2), "model_version": MODEL_VERSION,
    }).sort_values(["store_id", "sku_id", "horizon"]).reset_index(drop=True)
    save(result)
    MODEL_FILE.parent.mkdir(exist_ok=True)
    joblib.dump({"models": models, "widen_k": widen_k, "run_date": last_day, "todo": todo},
                MODEL_FILE)           # lets the agents explain each forecast
    print(f"Saved {len(result)} forecasts to demand_forecasts "
          f"(data up to {last_day.date()}, forecasting {result['forecast_date'].min().date()} "
          f"to {result['forecast_date'].max().date()})")

    print("\nExample: Milk 1L (P05) at Delhi-Central (S01)")
    ex = result[(result["store_id"] == "S01") & (result["sku_id"] == "P05")]
    print(ex[["forecast_date", "predicted_qty", "lower_qty", "upper_qty"]].to_string(index=False))
