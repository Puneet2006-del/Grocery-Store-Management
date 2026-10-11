"""Evaluation: the POC against simpler approaches, replayed on the same real demand.

Policies compared (see sim_engine.py)
  1. Legacy ordering rule (baseline)       last-7-day average x cover x safety factor, no markdowns
  2. Legacy + fixed 30% markdown rule      the same ordering, plus 30% off when a batch has 2 days or less left
  3. Forecast-driven ordering              demand model forecast and range at a chosen service level
  4. Full POC                              forecast-driven ordering + markdown, transfer and urgent top-up agents

How the comparison is kept fair
  - The demand model is trained only on data before each window.
  - Every policy faces the same real demand (the simulation's ground truth).
  - The service level is chosen on the 7 weeks BEFORE the test window (highest profit that keeps the
    fill rate at 99% or better), then applied unchanged to the test window.
  - Markdowns lift demand by the assumed 3% per 1% (rule in business_rules). The planner is assumed
    to approve every recommendation.

Run:  python evaluation/run_evaluation.py                 (about 6 minutes)
      python evaluation/run_evaluation.py --scenarios     (adds heatwave, festival and delayed-delivery stress tests)
      python evaluation/run_evaluation.py --service-level 0.7   (skip the selection and use this level)
      python evaluation/run_evaluation.py --days 14       (shorter and faster)
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(HERE), str(ROOT / "agents"), str(ROOT / "intelligence")]

from agent_context import parse_rules  # noqa: E402
from baselines import TEST_DAYS  # noqa: E402
from batch_state import load_inputs, replay  # noqa: E402
from dataset import TRUTH_FILE, build_panel  # noqa: E402
from db import read_table  # noqa: E402
from forecast_model import FEATURES, build_rows  # noqa: E402
from forecast_next_week import fit_all, predict_all, widen  # noqa: E402
from poc_policy import PocPolicy  # noqa: E402
from sim_engine import ForecastEngine, NetworkSim, Series, clone, make_scenario  # noqa: E402

OUT = HERE / "output"
OUT.mkdir(exist_ok=True)
POLICIES = ["legacy", "rule", "forecast", "poc"]
NAMES = {"legacy": "Legacy ordering rule (baseline)", "rule": "Legacy + fixed 30% markdown rule",
         "forecast": "Forecast-driven ordering", "poc": "Full POC (forecast + agents)"}
SCENARIOS = ["normal", "heatwave", "festival", "delayed_delivery"]
SCENARIO_TEXT = {"normal": "Normal conditions", "heatwave": "Heatwave: dairy demand +10% to +45% for 7 days",
                 "festival": "Festival: demand +35% for 3 days", "delayed_delivery": "Delhi-Central: no deliveries for 3 days"}
LEVELS = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)
FILL_TARGET = 99.0


def summarize(res):
    t = res.drop(columns=["store_id", "sku_id", "category"]).sum()
    handled = t["sold"] + t["waste_units"]
    return {"waste_pct": 100 * t["waste_units"] / handled if handled else 0, "waste_units": t["waste_units"],
            "waste_cost": t["waste_cost"], "fill_rate": 100 * t["sold"] / t["demand"], "lost_units": t["lost"],
            "stockout_days": t["stockout_days"], "revenue": t["revenue"], "profit": t["profit"],
            "markdowns": t["n_markdown"], "transfers": t["n_transfer"], "topups": t["n_topup"],
            "transfer_cost": t["transfer_cost"], "expedite_cost": t["expedite_cost"]}


def paired_ci(base, other, col, reps=2000):
    key = ["store_id", "sku_id"]
    diff = other.sort_values(key)[col].to_numpy() - base.sort_values(key)[col].to_numpy()
    idx = np.random.default_rng(0).integers(0, len(diff), (reps, len(diff)))
    lo, hi = np.percentile(diff[idx].sum(axis=1), [2.5, 97.5])
    return diff.sum(), lo, hi


def fmt(x):
    return f"{x:,.0f}"


def setup(panel, inputs, products, stores, shift, days):
    """Train the demand model and build the starting state for one window."""
    dates = np.sort(panel["date"].unique())
    n = len(dates)
    start = n - TEST_DAYS - shift
    end = min(n - 8 - shift, start + days - 1)
    rows = build_rows(panel, censor_aware=False)
    train = rows[(rows["target"] < start) & rows["y_obs"].notna()]
    models = fit_all(train)
    test = rows[(rows["origin"] >= start - 1) & (rows["origin"] <= end)]
    mean, lo, hi = predict_all(models, test)
    obs = test["y_obs"].to_numpy()
    seen = ~np.isnan(obs)
    k = next((k for k in np.arange(1.0, 2.51, 0.05)
              if ((obs >= widen(mean, lo, hi, k)[0]) & (obs <= widen(mean, lo, hi, k)[1]))[seen].mean() >= 0.80), 2.5)
    engine = ForecastEngine(models, widen, float(k), FEATURES,
                            {c: train[c].cat.categories for c in ("store", "sku", "category")})
    cap = pd.Timestamp(dates[start - 1])
    states, _, _ = replay(inputs, capture_dates=[cap])
    day0 = pd.Timestamp(dates[0])
    base = {}
    for (store, sku), g in panel.groupby(["store_id", "sku_id"], sort=False):
        g = g.sort_values("date")
        o = g["qty_sold"].to_numpy(float).copy()
        o[start:] = np.nan
        cost = float(products.loc[sku, "cost"])
        init = states[(store, sku)].get(cap)
        batches = [] if init is None else [{"id": r.batch_id, "exp": int((r.expiry_date - day0).days),
                                            "rem": int(r.qty_remaining), "cost": cost} for r in init.itertuples()]
        base[(store, sku)] = Series(
            store=store, sku=sku, cat=g["category"].iloc[0], shelf=int(g["shelf_life_days"].iloc[0]), cost=cost,
            demand=np.nan_to_num(g["true_demand"].to_numpy(float)), price=g["unit_price"].to_numpy(float), obs=o,
            cov={c: g[c].to_numpy() for c in ("dow", "month", "is_weekend", "discount_pct", "event_impact", "temp_c", "rain_mm")},
            batches=batches)
    return {"dates": dates, "start": start, "end": end, "engine": engine, "base": base}


def run_policy(w, pol, scenario, rules, stores, products, n_sim):
    poc = PocPolicy(stores, products, rules, n_sim=n_sim) if pol == "poc" else None
    sim = NetworkSim(clone(w["base"]), w["dates"], pol, make_scenario(scenario, w["start"]), rules,
                     engine=w["engine"] if pol in ("forecast", "poc") else None, poc=poc)
    return sim.run(w["start"], w["end"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=TEST_DAYS - 7)
    ap.add_argument("--scenarios", action="store_true")
    ap.add_argument("--n-sim", type=int, default=500)
    ap.add_argument("--service-level", type=float, default=None, help="use this service level and skip the selection")
    args = ap.parse_args()

    panel = build_panel()
    inputs = load_inputs()
    products = read_table("products").set_index("sku_id")
    stores = read_table("stores").set_index("store_id")
    rules_df = read_table("business_rules")
    rules = parse_rules(dict(zip(rules_df["rule_key"], rules_df["rule_value"])))

    # ---- 1. choose the service level on the weeks before the test window
    sweep = None
    if args.service_level is not None:
        rules["service_level_target"] = args.service_level
    else:
        print("Step 1: choosing the service level on the weeks BEFORE the test window...")
        wv = setup(panel, inputs, products, stores, shift=args.days, days=args.days)
        print(f"  validation window {pd.Timestamp(wv['dates'][wv['start']]).date()} to {pd.Timestamp(wv['dates'][wv['end']]).date()}")
        legacy_v = summarize(run_policy(wv, "legacy", "normal", rules, stores, products, args.n_sim))
        recs = [{"service_level": "legacy rule", **{k: legacy_v[k] for k in ("waste_pct", "fill_rate", "profit")}}]
        for lvl in LEVELS:
            r2 = dict(rules)
            r2["service_level_target"] = lvl
            r = summarize(run_policy(wv, "poc", "normal", r2, stores, products, args.n_sim))
            recs.append({"service_level": f"{lvl:.0%}", "lvl": lvl, **{k: r[k] for k in ("waste_pct", "fill_rate", "profit")}})
        sweep = pd.DataFrame(recs)
        ok = sweep[(sweep["lvl"].notna()) & (sweep["fill_rate"] >= FILL_TARGET)]
        chosen = float(ok.loc[ok["profit"].idxmax(), "lvl"]) if len(ok) else float(sweep.loc[sweep["fill_rate"].idxmax(), "lvl"])
        print(sweep[["service_level", "waste_pct", "fill_rate", "profit"]].round({"waste_pct": 2, "fill_rate": 2, "profit": 0}).to_string(index=False))
        print(f"  -> chosen service level: {chosen:.0%} (highest profit with fill rate of {FILL_TARGET:.0f}% or better)\n")
        rules["service_level_target"] = chosen
    level = rules["service_level_target"]

    # ---- 2. evaluate on the test window
    print("Step 2: evaluating on the test window...")
    w = setup(panel, inputs, products, stores, shift=0, days=args.days)
    dates, start, end = w["dates"], w["start"], w["end"]
    print(f"  test window {pd.Timestamp(dates[start]).date()} to {pd.Timestamp(dates[end]).date()} "
          f"({end - start + 1} days), service level {level:.0%}")
    results = {}
    for scen in (SCENARIOS if args.scenarios else ["normal"]):
        print(f"\n=== Scenario: {SCENARIO_TEXT[scen]} ===")
        for pol in POLICIES:
            t0 = time.time()
            results[(scen, pol)] = run_policy(w, pol, scen, rules, stores, products, args.n_sim)
            print(f"  {NAMES[pol]:36s} done in {time.time() - t0:5.0f}s")

    sales = inputs["sales"][(inputs["sales"]["sale_date"] >= dates[start]) & (inputs["sales"]["sale_date"] <= dates[end])]
    waste = inputs["waste"][(inputs["waste"]["waste_date"] >= dates[start]) & (inputs["waste"]["waste_date"] <= dates[end])]
    truth = pd.read_csv(TRUTH_FILE, parse_dates=["sale_date"])
    truth = truth[(truth["sale_date"] >= dates[start]) & (truth["sale_date"] <= dates[end])]
    hist_waste = 100 * waste["qty"].sum() / (sales["qty_sold"].sum() + waste["qty"].sum())
    hist_fill = 100 * (1 - truth["lost_sales"].sum() / truth["true_demand"].sum())

    table = []
    for scen in {s for s, _ in results}:
        base_res = results[(scen, "legacy")]
        for pol in POLICIES:
            d_w = paired_ci(base_res, results[(scen, pol)], "waste_units")
            d_l = paired_ci(base_res, results[(scen, pol)], "lost")
            d_p = paired_ci(base_res, results[(scen, pol)], "profit")
            table.append({"scenario": scen, "policy": NAMES[pol], **summarize(results[(scen, pol)]),
                          "d_waste_units": d_w[0], "d_waste_lo": d_w[1], "d_waste_hi": d_w[2],
                          "d_lost_units": d_l[0], "d_lost_lo": d_l[1], "d_lost_hi": d_l[2],
                          "d_profit": d_p[0], "d_profit_lo": d_p[1], "d_profit_hi": d_p[2]})
    df = pd.DataFrame(table)
    df["service_level"] = level
    df.to_csv(OUT / "policy_results.csv", index=False)

    for scen in [s for s in SCENARIOS if s in df["scenario"].unique()]:
        sub = df[df["scenario"] == scen]
        print(f"\n===== {SCENARIO_TEXT[scen].upper()} =====")
        show = sub[["policy", "waste_pct", "waste_cost", "fill_rate", "lost_units", "profit", "markdowns", "transfers", "topups"]].copy()
        show.columns = ["Policy", "Waste %", "Waste cost", "Fill rate %", "Lost units", "Profit", "Markdowns", "Transfers", "Top-ups"]
        for c in ["Waste cost", "Lost units", "Profit"]:
            show[c] = show[c].map(fmt)
        print(show.round({"Waste %": 1, "Fill rate %": 1}).to_string(index=False))
        print("Change vs the legacy rule (95% interval from resampling store/SKU pairs):")
        for _, r in sub.iloc[1:].iterrows():
            print(f"  {r['policy']}: waste {r['d_waste_units']:+,.0f} units ({r['d_waste_lo']:+,.0f} to {r['d_waste_hi']:+,.0f}), "
                  f"lost sales {r['d_lost_units']:+,.0f} ({r['d_lost_lo']:+,.0f} to {r['d_lost_hi']:+,.0f}), "
                  f"profit {r['d_profit']:+,.0f} INR ({r['d_profit_lo']:+,.0f} to {r['d_profit_hi']:+,.0f})")
    b = df[df["scenario"] == "normal"].iloc[0]
    print(f"\nSimulator check: the legacy rule in the simulator gives waste {b['waste_pct']:.1f}% and fill rate {b['fill_rate']:.1f}%; "
          f"what really happened in the same weeks was waste {hist_waste:.1f}% and fill rate {hist_fill:.1f}%.")

    def md_table(sub):
        lines = ["| Policy | Waste % | Waste cost (INR) | Fill rate % | Lost units | Profit (INR) | Profit vs legacy (95% interval) |",
                 "|---|---|---|---|---|---|---|"]
        for _, r in sub.iterrows():
            ci = "baseline" if r["policy"] == NAMES["legacy"] else f"{r['d_profit']:+,.0f} ({r['d_profit_lo']:+,.0f} to {r['d_profit_hi']:+,.0f})"
            lines.append(f"| {r['policy']} | {r['waste_pct']:.1f} | {fmt(r['waste_cost'])} | {r['fill_rate']:.1f} | "
                         f"{fmt(r['lost_units'])} | {fmt(r['profit'])} | {ci} |")
        return "\n".join(lines)

    fm = ROOT / "intelligence" / "output" / "model_metrics.csv"
    forecast_md = "Run intelligence/forecast_model.py first."
    if fm.exists():
        m = pd.read_csv(fm)
        m = m[m["view"] == "overall"].sort_values("wape_true_%")
        forecast_md = "| Method | WAPE vs true demand (%) | Bias (%) |\n|---|---|---|\n" + "\n".join(
            f"| {r['method']} | {r['wape_true_%']} | {r['bias_true_%']} |" for _, r in m.iterrows())
    parts = [f"# Evaluation report\n\nTest window: {pd.Timestamp(dates[start]).date()} to {pd.Timestamp(dates[end]).date()} "
             f"({end - start + 1} days), {panel['store_id'].nunique()} stores, {panel['sku_id'].nunique()} perishable SKUs. "
             "The demand model was trained only on earlier data.\n",
             "## 1. Demand forecast accuracy (Milestone 2)\n\n" + forecast_md + "\n",
             f"## 2. Policy comparison under normal conditions (service level {level:.0%})\n\n"
             "Every policy faces the same real demand. Waste % is waste divided by units sold plus wasted. "
             "Intervals come from resampling store/SKU pairs.\n\n" + md_table(df[df["scenario"] == "normal"]) + "\n",
             f"Simulator check: the legacy rule in the simulator gives waste {b['waste_pct']:.1f}% and fill rate {b['fill_rate']:.1f}%; "
             f"the real history for the same weeks was waste {hist_waste:.1f}% and fill rate {hist_fill:.1f}%.\n"]
    if sweep is not None:
        s2 = sweep.copy()
        parts.append("## 3. Choosing the service level\n\nThe service level sets how much safety stock the forecast-driven "
                     "policies hold. It was chosen on the seven weeks before the test window, as the highest-profit "
                     f"level that keeps the fill rate at {FILL_TARGET:.0f}% or better, and then applied unchanged to the test window. "
                     "Higher levels cut lost sales but raise waste.\n\n| Service level | Waste % | Fill rate % | Profit (INR) |\n|---|---|---|---|\n"
                     + "\n".join(f"| {r['service_level']} | {r['waste_pct']:.2f} | {r['fill_rate']:.2f} | {fmt(r['profit'])} |" for _, r in s2.iterrows())
                     + f"\n\nChosen: **{level:.0%}**.\n")
    if args.scenarios:
        parts.append("## 4. Stress scenarios\n")
        for scen in SCENARIOS[1:]:
            parts.append(f"### {SCENARIO_TEXT[scen]}\n\n" + md_table(df[df["scenario"] == scen]) + "\n")
    parts.append("## Method and limitations\n\n"
                 "- Closed-loop replay of real simulated demand; differences between policies come only from decisions.\n"
                 "- Demand is simulated and the demand model's assumptions are close to how the simulator generates it, so real-world gains would be smaller.\n"
                 "- The markdown effect (+3% demand per 1% off) is assumed and matches the simulator's promotion effect.\n"
                 "- The planner is assumed to approve every recommendation; in practice some are modified or rejected.\n"
                 "- Profit counts margin on sales minus the cost of wasted units, transfers and urgent orders. It does not value customer goodwill lost to stockouts, which favours lower service levels.\n"
                 "- Single simulated trajectory; intervals come from resampling store/SKU pairs, not from repeated simulations.\n"
                 "- Damaged-on-arrival units and supplier transit loss are not modelled in the replay (they affect all policies equally).\n")
    (OUT / "evaluation_report.md").write_text("\n".join(parts), encoding="utf-8")
    print(f"\nSaved: {OUT / 'policy_results.csv'} and {OUT / 'evaluation_report.md'}")


if __name__ == "__main__":
    main()
