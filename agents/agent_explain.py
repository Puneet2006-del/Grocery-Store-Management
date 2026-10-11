"""Explains WHY a store and SKU is heading for excess stock or a stockout.

Three kinds of evidence are combined:
  1. Demand drivers: the demand model is asked "what if" questions about the coming days
     (what if the weekday were average, the weather normal, there were no holiday, no promotion?).
     The difference is how much each factor moves the forecast. This is what the model attributes,
     not proof of cause.
  2. Recent sales: the trend over the last 7 days against the 3 weeks before.
  3. Stock facts: how much was delivered, what the order was sized on, how long the stock lasts.

Needs intelligence/output/forecast_models.joblib (saved by forecast_next_week.py). Without it,
only the sales trend and stock facts are given.
"""
from pathlib import Path

import holidays
import joblib
import numpy as np
import pandas as pd

from db import read_table

ROOT = Path(__file__).resolve().parents[1]
MODEL_FILE = ROOT / "intelligence" / "output" / "forecast_models.joblib"
DAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
# must match intelligence/forecast_model.py FEATURES (the columns the saved model was trained on)
FEATURES = ["horizon", "dow", "month", "is_weekend", "discount_pct", "event_impact", "temp_c", "rain_mm",
            "last_obs", "r7", "r14", "r28", "lag7", "lag14", "lag21", "lag28", "lag_wd_mean",
            "store", "sku", "category", "shelf_life_days"]
MIN_EFFECT_PCT = 3.0       # drivers smaller than this are not worth mentioning
MIN_TREND_PCT = 8.0


def _days(dates):
    return ", ".join(f"{DAY[d.dayofweek]} {d.day} {d.strftime('%b')}" for d in dates)


class Explainer:
    def __init__(self, run_date, stores, products):
        self.run_date = pd.Timestamp(run_date)
        self.stores, self.products = stores, products
        saved = joblib.load(MODEL_FILE) if MODEL_FILE.exists() else None
        self.model = saved["models"]["mean"] if saved else None
        self.rows = saved["todo"] if saved and pd.Timestamp(saved["run_date"]) == self.run_date else None
        if self.rows is not None:
            self.rows = self.rows.assign(store=self.rows["store"].astype(str), sku=self.rows["sku"].astype(str))
        lo = self.run_date - pd.Timedelta(days=35)
        sales = read_table("sales", ["sale_date"])
        self.sales = {k: g.sort_values("sale_date") for k, g in sales[sales["sale_date"] > lo].groupby(["store_id", "sku_id"])}
        rec = read_table("receipts", ["received_date"])
        self.receipts = {k: g.sort_values("received_date") for k, g in
                         rec[rec["received_date"] > self.run_date - pd.Timedelta(days=10)].groupby(["store_id", "sku_id"])}
        wx = read_table("weather", ["weather_date"])
        recent = wx[(wx["weather_date"] <= self.run_date) & (wx["weather_date"] > self.run_date - pd.Timedelta(days=14))]
        self.recent_temp = recent.groupby("city")["temp_c"].mean().to_dict()
        ev = read_table("events", ["event_date"])
        self.events = ev[(ev["event_date"] > self.run_date) & (ev["event_date"] <= self.run_date + pd.Timedelta(days=8))]
        self.promos = read_table("promotions", ["start_date", "end_date"])
        self.holiday_names = holidays.India(years=[self.run_date.year, self.run_date.year + 1])

    # ------------------------------------------------------------------ model effects
    def _effects(self, key, days):
        if self.model is None or self.rows is None:
            return None
        rows = self.rows[(self.rows["store"] == key[0]) & (self.rows["sku"] == key[1])].sort_values("horizon")
        if rows.empty:
            return None
        X = rows[FEATURES].copy()
        base = self.model.predict(X)
        eff = {}
        by_day = []
        for d in range(7):
            X2 = X.copy()
            X2["dow"] = d
            X2["is_weekend"] = int(d >= 5)
            by_day.append(self.model.predict(X2))
        eff["weekday"] = base - np.mean(by_day, axis=0)
        city = self.stores.loc[key[0], "city"]
        X2 = X.copy()
        X2["temp_c"] = self.recent_temp.get(city, float(X["temp_c"].mean()))
        X2["rain_mm"] = 0.0
        eff["weather"] = base - self.model.predict(X2)
        X2 = X.copy()
        X2["event_impact"] = 1.0
        eff["event"] = base - self.model.predict(X2)
        X2 = X.copy()
        X2["discount_pct"] = 0.0
        eff["promo"] = base - self.model.predict(X2)
        n = slice(0, days)
        return {"base": base[n], "eff": {k: v[n] for k, v in eff.items()}, "rows": rows.iloc[n], "city": city}

    # ---------------------------------------------------------------------- main entry
    def explain(self, key, alert_type, days, fresh, next_delivery=None):
        store, sku = key
        stock = int(fresh["on_hand_qty"])
        name = self.products.loc[sku, "name"]
        cat = self.products.loc[sku, "category"]
        res = self._effects(key, days)
        drivers, stock_facts = [], []
        demand_window = float(res["base"].sum()) if res else None

        if res:
            neutral_total = float((res["base"] - sum(res["eff"].values())).sum()) or 1.0
            dates = [self.run_date + pd.Timedelta(days=int(h)) for h in res["rows"]["horizon"]]

            # weekday pattern
            e = res["eff"]["weekday"]
            pct = 100 * e.sum() / max(float((res["base"] - e).sum()), 1e-6)
            if abs(pct) >= MIN_EFFECT_PCT:
                slow = [d for d, v, b in zip(dates, e, res["base"]) if v / max(b - v, 1e-6) <= -0.05]
                busy = [d for d, v, b in zip(dates, e, res["base"]) if v / max(b - v, 1e-6) >= 0.05]
                parts = []
                if slow:
                    parts.append(f"slower than the weekly average on {_days(slow)}")
                if busy:
                    parts.append(f"busier on {_days(busy)}")
                drivers.append({"factor": "weekday", "effect_pct": round(pct, 1), "effect_units": round(float(e.sum()), 1),
                                "text": f"Weekday pattern: demand is {' and '.join(parts)} "
                                        f"({pct:+.0f}% overall across the next {days} day(s))"})
            # weather
            e = res["eff"]["weather"]
            pct = 100 * e.sum() / max(float((res["base"] - e).sum()), 1e-6)
            if abs(pct) >= MIN_EFFECT_PCT:
                rows = res["rows"]
                rain, temp = float(rows["rain_mm"].sum()), float(rows["temp_c"].mean())
                recent = self.recent_temp.get(res["city"], temp)
                why = []
                if rain >= 2:
                    why.append(f"about {rain:.0f} mm of rain is forecast")
                if abs(temp - recent) >= 1.5:
                    why.append(f"temperatures of about {temp:.0f}°C are {'above' if temp > recent else 'below'} the recent {recent:.0f}°C")
                drivers.append({"factor": "weather", "effect_pct": round(pct, 1), "effect_units": round(float(e.sum()), 1),
                                "text": f"Weather: {', '.join(why) or 'forecast conditions'} ({pct:+.0f}% demand for {name})"})
            # holidays and events
            e = res["eff"]["event"]
            pct = 100 * e.sum() / max(float((res["base"] - e).sum()), 1e-6)
            if abs(pct) >= MIN_EFFECT_PCT:
                names = []
                for d, imp in zip(dates, res["rows"]["event_impact"]):
                    if imp > 1.0:
                        names.append(f"{self.holiday_names.get(d.date(), 'a local event')} ({DAY[d.dayofweek]} {d.day} {d.strftime('%b')})")
                drivers.append({"factor": "event", "effect_pct": round(pct, 1), "effect_units": round(float(e.sum()), 1),
                                "text": f"Holiday or event: {', '.join(names)} ({pct:+.0f}% demand)"})
            # planned promotion
            e = res["eff"]["promo"]
            pct = 100 * e.sum() / max(float((res["base"] - e).sum()), 1e-6)
            if abs(pct) >= MIN_EFFECT_PCT:
                disc = float(res["rows"]["discount_pct"].max())
                drivers.append({"factor": "promotion", "effect_pct": round(pct, 1), "effect_units": round(float(e.sum()), 1),
                                "text": f"Planned promotion of {disc:.0f}% off lifts demand ({pct:+.0f}%)"})

        # recent sales trend, and a promotion that has just ended
        s = self.sales.get(key)
        avg7 = None
        if s is not None and len(s) >= 14:
            last7 = float(s["qty_sold"].tail(7).mean())
            prev = float(s["qty_sold"].iloc[:-7].tail(21).mean())
            avg7 = last7
            if prev > 0:
                tr = 100 * (last7 / prev - 1)
                if abs(tr) >= MIN_TREND_PCT:
                    drivers.append({"factor": "trend", "effect_pct": round(tr, 1), "effect_units": None,
                                    "text": f"Recent sales: {last7:.0f}/day over the last 7 days against {prev:.0f}/day in the 3 weeks "
                                            f"before ({tr:+.0f}%)"})
            ended = self.promos[(self.promos["store_id"] == store) & (self.promos["sku_id"] == sku)
                                & (self.promos["end_date"] <= self.run_date)
                                & (self.promos["end_date"] > self.run_date - pd.Timedelta(days=7))]
            if len(ended) and alert_type == "EXCESS_STOCK":
                r = ended.iloc[-1]
                drivers.append({"factor": "promotion_ended", "effect_pct": None, "effect_units": None,
                                "text": f"A {int(r['discount_pct'])}% promotion ended on {r['end_date'].day} {r['end_date'].strftime('%b')}; "
                                        f"it boosted last week's sales, so orders sized on that week came out too high"})

        # stock side
        rc = self.receipts.get(key)
        if rc is not None and len(rc):
            last = rc.iloc[-1]
            ago = (self.run_date - last["received_date"]).days
            stock_facts.append(f"The latest delivery was {int(last['qty'])} units, {ago} day(s) ago "
                               f"({last['received_date'].day} {last['received_date'].strftime('%b')}).")
        if avg7 is not None and demand_window is not None and days > 0:
            fc = demand_window / days
            stock_facts.append(f"The current ordering rule sizes orders on the last 7 days' average ({avg7:.0f}/day), but the forecast for the next "
                               f"{days} day(s) is {fc:.0f}/day ({100 * (fc / avg7 - 1) if avg7 else 0:+.0f}%).")

        sold_today = None
        if s is not None and len(s) and s["sale_date"].iloc[-1] == self.run_date:
            sold_today = int(s["qty_sold"].iloc[-1])
        if alert_type == "EXCESS_STOCK":
            risky = [b for b in fresh["batches"] if b["unsold_pct"] >= 10]
            parts = []
            for b in risky:
                if b["days_to_expiry"] <= 1:
                    parts.append(f"{b['qty']} unit{'s' if b['qty'] != 1 else ''} expire tomorrow and can no longer be sold")
                else:
                    parts.append(f"{b['qty']} unit{'s' if b['qty'] != 1 else ''} expire in {b['days_to_expiry']} days (about {b['expected_unsold']:.0f} unlikely to sell)")
            headline = (f"{fresh['expected_unsold']:.0f} of the {stock} units on hand ({fresh['excess_pct']:.0f}%) are expected to expire unsold"
                        + (": " + "; ".join(parts) if parts else "") + ".")
            if demand_window:
                stock_facts.insert(0, f"About {demand_window:.0f} units are expected to sell over the next {days} day(s), "
                                      f"against {stock} on hand.")
        else:
            cover = stock / max(demand_window / days, 1e-6) if demand_window else 0
            nd = f" and the next delivery is not until {next_delivery}" if next_delivery else ""
            headline = (f"{stock} units on hand cover only about {cover:.1f} day(s) of expected demand{nd}."
                        if demand_window else f"Stock is low{nd}.")
            if sold_today is not None:
                stock_facts.insert(0, f"{sold_today} units were sold today (the last 7 days average "
                                      f"{avg7:.0f}/day)." if avg7 else f"{sold_today} units were sold today.")
        # keep only reasons that fit the problem: for excess stock, factors that LOWER demand (or a promotion that
        # just ended); for a stockout, factors that RAISE it. Other factors are context, not causes.
        want_down = alert_type == "EXCESS_STOCK"
        fitting = [d for d in drivers if d["factor"] == "promotion_ended"
                   or (d["effect_pct"] is not None and (d["effect_pct"] < 0) == want_down)]
        ranked = sorted(fitting, key=lambda d: -abs(d["effect_pct"] or 99))
        if not ranked:
            stock_facts.append("No external factor (weather, holiday, promotion, weekday) stands out; the gap comes from how much "
                               "was delivered compared with what is expected to sell.")
        return {"headline": headline, "drivers": ranked[:4], "stock_facts": stock_facts,
                "note": "Demand drivers show what the forecasting model attributes to each factor; they are indications, not proof of cause."}
