"""Closed-loop simulator for comparing replenishment and markdown policies.

The same real demand (from the simulation's ground truth) is replayed under each policy, so
differences come only from the decisions. Each day, per store and SKU:
  morning   expired stock is written off, transfers and top-ups arrive, a scheduled delivery is ordered
  day       customers buy oldest stock first; unmet demand is lost
  evening   the policy may start a markdown, move stock to another store or order an urgent top-up

Policies
  legacy    order-up-to level = last 7 days' sales x cover days x safety factor (the rule that produced the history)
  rule      legacy ordering + a fixed rule: 30% off when a batch has 2 days or less left
  forecast  ordering from the demand model's forecast and range at a 95% service level
  poc       forecast ordering + the agents' markdown, transfer and urgent top-up decisions
"""
import copy
import math
import warnings
from dataclasses import dataclass, field
from statistics import NormalDist

import numpy as np
import pandas as pd

DELIVERY_DAYS = {"produce": [0, 2, 4, 5], "dairy": [0, 2, 4, 6],
                 "bakery": [0, 1, 2, 3, 4, 5, 6], "meat": [1, 3, 5, 6]}
LEGACY_SAFETY = {"produce": 1.25, "dairy": 1.30, "bakery": 1.10, "meat": 1.05}
RULE_MARKDOWN_PCT = 30.0
RULE_MARKDOWN_DAYS = 2
Z80 = 2.563
METRICS = ["demand", "sold", "lost", "revenue", "cogs", "waste_units", "waste_cost", "purchased",
           "stockout_days", "transfer_cost", "expedite_cost", "markdown_days", "n_markdown",
           "n_transfer", "n_topup"]


@dataclass
class Series:
    store: str
    sku: str
    cat: str
    shelf: int
    cost: float
    demand: np.ndarray            # real demand per day index
    price: np.ndarray             # regular shelf price per day index
    obs: np.ndarray               # observed sales; history before the window, simulated sales inside it
    cov: dict                     # dow, month, is_weekend, discount_pct, event_impact, temp_c, rain_mm
    batches: list = field(default_factory=list)   # dicts: id, exp (day index), rem, cost
    pending: dict = field(default_factory=dict)   # day index -> batches arriving that morning
    markdown: dict | None = None                  # {"pct": .., "ids": {..}}
    m: dict = field(default_factory=lambda: {k: 0.0 for k in METRICS})


class ForecastEngine:
    """Predicts the next 7 days of demand for every series from the sales seen so far."""

    def __init__(self, models, widen_fn, widen_k, features, categories):
        self.models, self.widen, self.k = models, widen_fn, widen_k
        self.features, self.cats = features, categories

    def update(self, series, t):
        rows, keys = [], []
        for key, s in series.items():
            o = s.obs
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                roll = {w: np.nanmean(o[max(0, t - w + 1): t + 1]) for w in (7, 14, 28)}
                for h in range(1, 8):
                    tgt = t + h
                    lags = [o[tgt - 7], o[tgt - 14], o[tgt - 21], o[tgt - 28]]
                    c = s.cov
                    rows.append({
                        "horizon": h, "dow": c["dow"][tgt], "month": c["month"][tgt],
                        "is_weekend": int(c["is_weekend"][tgt]), "discount_pct": c["discount_pct"][tgt],
                        "event_impact": c["event_impact"][tgt], "temp_c": c["temp_c"][tgt], "rain_mm": c["rain_mm"][tgt],
                        "last_obs": o[t], "r7": roll[7], "r14": roll[14], "r28": roll[28],
                        "lag7": lags[0], "lag14": lags[1], "lag21": lags[2], "lag28": lags[3],
                        "lag_wd_mean": np.nanmean(lags), "store": s.store, "sku": s.sku,
                        "category": s.cat, "shelf_life_days": s.shelf})
            keys.append(key)
        df = pd.DataFrame(rows)
        for col in ("store", "sku", "category"):
            df[col] = pd.Categorical(df[col], categories=self.cats[col])
        X = df[self.features]
        mean = np.clip(self.models["mean"].predict(X), 0, None)
        lo = np.clip(self.models["lo"].predict(X), 0, None)
        hi = np.clip(self.models["hi"].predict(X), 0, None)
        lo, hi = np.minimum(lo, mean), np.maximum(hi, mean)
        lo, hi = self.widen(mean, lo, hi, self.k)
        out = {}
        for i, key in enumerate(keys):
            sl = slice(i * 7, i * 7 + 7)
            out[key] = {"mu": mean[sl], "lo": lo[sl], "hi": hi[sl],
                        "sd": np.maximum((hi[sl] - lo[sl]) / Z80, 1e-3)}
        return out


class NetworkSim:
    def __init__(self, series, dates, policy, scenario, rules, engine=None, poc=None):
        self.series, self.dates, self.policy = series, dates, policy
        self.scenario, self.rules, self.engine, self.poc = scenario, rules, engine, poc
        self.fc = {}
        self.z = NormalDist().inv_cdf(rules["service_level_target"])
        self.uplift = rules["markdown_uplift_per_pct"]
        self.serial = 0

    # ------------------------------------------------------------------ helpers
    def dow(self, d):
        return pd.Timestamp(self.dates[d]).dayofweek if d < len(self.dates) else (pd.Timestamp(self.dates[-1]).dayofweek + d - len(self.dates) + 1) % 7

    def is_delivery(self, s, d):
        sched = DELIVERY_DAYS[s.cat]
        skip = self.scenario["skip"]
        if skip(s.store, d):
            return False
        return self.dow(d) in sched or (skip(s.store, d - 1) and self.dow(d - 1) in sched)

    def gap(self, s, d):
        sched = DELIVERY_DAYS[s.cat]
        return next(k for k in range(1, 8) if (self.dow(d) + k) % 7 in sched)

    def new_id(self, prefix):
        self.serial += 1
        return f"{prefix}{self.serial}"

    def order_qty(self, s, d):
        on_hand = sum(b["rem"] for b in s.batches)
        cover = self.gap(s, d) + (1.0 if s.shelf >= 7 else 0.5)
        if self.policy in ("legacy", "rule"):
            w = s.obs[max(0, d - 7): d]
            avg = np.nanmean(w) if np.any(~np.isnan(w)) else 0.0
            target = avg * cover * LEGACY_SAFETY[s.cat]
        else:
            f = self.fc[(s.store, s.sku)]
            mean_sum, var_sum = 0.0, 0.0
            for i in range(math.ceil(cover)):
                wgt = min(1.0, cover - i)
                mean_sum += wgt * f["mu"][i]
                var_sum += (wgt * f["sd"][i]) ** 2
            target = mean_sum + self.z * math.sqrt(var_sum)
        return max(0, math.ceil(target - on_hand))

    # ----------------------------------------------------------------- one day
    def morning_and_sales(self, s, d):
        keep = []
        for b in s.batches:                                   # write off expired stock
            if b["exp"] <= d:
                s.m["waste_units"] += b["rem"]
                s.m["waste_cost"] += b["rem"] * b["cost"]
            else:
                keep.append(b)
        s.batches = keep + s.pending.pop(d, [])
        if self.is_delivery(s, d):                            # scheduled delivery
            q = self.order_qty(s, d)
            if q > 0:
                s.batches.append({"id": self.new_id("O"), "exp": d + s.shelf, "rem": q, "cost": s.cost})
                s.m["purchased"] += q
        s.batches.sort(key=lambda b: b["exp"])

        pct = s.markdown["pct"] if s.markdown else 0.0
        want = int(round(s.demand[d] * self.scenario["mult"](s, d) * (1 + self.uplift * pct)))
        sold = 0
        for b in s.batches:                                   # oldest expiry first
            take = min(b["rem"], want - sold)
            b["rem"] -= take
            sold += take
            if sold >= want:
                break
        s.batches = [b for b in s.batches if b["rem"] > 0]
        price = s.price[d] * (1 - pct / 100)
        m = s.m
        m["demand"] += want
        m["sold"] += sold
        m["lost"] += want - sold
        m["revenue"] += sold * price
        m["cogs"] += sold * s.cost
        m["stockout_days"] += 1 if want > sold else 0
        m["markdown_days"] += 1 if pct else 0
        s.obs[d] = sold

    def end_of_day(self, d):
        for s in self.series.values():                        # a markdown ends once its batches are gone
            if s.markdown and not (s.markdown["ids"] & {b["id"] for b in s.batches}):
                s.markdown = None
        if self.engine is not None:
            self.fc = self.engine.update(self.series, d)
        if self.policy == "rule":
            for s in self.series.values():
                near = [b for b in s.batches if b["exp"] - d <= RULE_MARKDOWN_DAYS]
                if s.markdown is None and near:
                    s.markdown = {"pct": RULE_MARKDOWN_PCT, "ids": {b["id"] for b in near}}
                    s.m["n_markdown"] += 1
        if self.policy == "poc":
            self.poc.after_day(self, d)

    def run(self, start, end):
        if self.engine is not None:
            self.fc = self.engine.update(self.series, start - 1)
        for d in range(start, end + 1):
            for s in self.series.values():
                self.morning_and_sales(s, d)
            self.end_of_day(d)
        return self.results()

    def results(self):
        rows = []
        for key, s in self.series.items():
            m = dict(s.m)
            m["profit"] = m["revenue"] - m["cogs"] - m["waste_cost"] - m["transfer_cost"] - m["expedite_cost"]
            rows.append({"store_id": key[0], "sku_id": key[1], "category": s.cat, **m})
        return pd.DataFrame(rows)


def make_scenario(name, start):
    """Shocks hit every policy equally. They start two weeks into the window."""
    s0 = start + 14
    none = {"mult": lambda s, d: 1.0, "skip": lambda store, d: False}
    if name == "normal":
        return none
    if name == "heatwave":      # +6 C for a week: dairy demand up, forecasts do not know in advance
        f = {"P05": 1.15, "P06": 1.25, "P07": 1.10, "P08": 1.45}
        return {"mult": lambda s, d: f.get(s.sku, 1.0) if s0 <= d < s0 + 7 else 1.0, "skip": none["skip"]}
    if name == "festival":      # three days of +35% demand everywhere
        return {"mult": lambda s, d: 1.35 if s0 <= d < s0 + 3 else 1.0, "skip": none["skip"]}
    if name == "delayed_delivery":   # Delhi-Central gets no deliveries for 3 days, then a catch-up
        return {"mult": none["mult"], "skip": lambda store, d: store == "S01" and s0 <= d < s0 + 3}
    raise ValueError(name)


def clone(series):
    return copy.deepcopy(series)
