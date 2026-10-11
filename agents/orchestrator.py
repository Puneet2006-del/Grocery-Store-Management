"""Orchestrator: compare the agents' options, apply business rules, propose one action per store and SKU.

For each store/SKU with an alert from the risk engine:
  1. demand and freshness agents describe the situation
  2. the relevant agents propose options
       STOCKOUT_RISK -> replenishment      EXCESS_STOCK -> markdown and transfer
  3. options that break a business rule, or fall below the minimum confidence, are ruled out
  4. the feasible option with the highest expected net benefit is chosen
     (no recommendation if nothing has a positive benefit)
  5. recommendation, evidence and all options considered are saved to MySQL

Run:  python agents/orchestrator.py        (needs the risk engine to have run)
Re-running replaces PROPOSED recommendations; ones a planner already decided are left alone.
Unreviewed recommendations from earlier days are marked EXPIRED so nobody acts on stale advice.
"""
import json
from datetime import timedelta

import pandas as pd
from sqlalchemy import text

import agent_logic as agents
from agent_context import RULE_DEFAULTS, RULE_DESCRIPTIONS, load_context
from agent_explain import Explainer
from db import engine

AGENTS_FOR = {"STOCKOUT_RISK": [agents.replenishment_options],
              "EXCESS_STOCK": [agents.markdown_options, agents.transfer_options]}


def ensure_rules():
    """Add any rule that is missing from business_rules (existing values are never changed)."""
    with engine.begin() as conn:
        have = {r[0] for r in conn.execute(text("SELECT rule_key FROM business_rules"))}
        for k, v in RULE_DEFAULTS.items():
            if k not in have:
                conn.execute(text("INSERT INTO business_rules (rule_key, rule_value, description) "
                                  "VALUES (:k, :v, :d)"), {"k": k, "v": v, "d": RULE_DESCRIPTIONS.get(k, "")})


def describe(opt, ctx, key, product, store_name):
    if opt.action_type == "MARKDOWN":
        d = opt.detail
        return (f"Mark down {product} at {store_name} by {opt.markdown_pct:.0f}% "
                f"({d['old_price']:.2f} to {d['new_price']:.2f} INR)")
    if opt.action_type == "TRANSFER":
        return (f"Move {opt.quantity} units of {product} from {store_name} to "
                f"{ctx.stores.loc[opt.counterpart_store_id, 'name']}")
    return f"Place an urgent top-up order of {opt.quantity} units of {product} for {store_name}"


def decide(ctx, key):
    store, sku = key
    risk = ctx.sku_risk.loc[key]
    options = []
    for fn in AGENTS_FOR[risk["alert_type"]]:
        options += fn(ctx, key)
    for o in options:                                  # rule: minimum confidence
        if o.feasible and o.confidence < ctx.rules["min_confidence"]:
            o.feasible = False
            o.notes = (o.notes + "; " if o.notes else "") + f"confidence {o.confidence:.0%} is below the minimum {ctx.rules['min_confidence']:.0%}"
    ok = [o for o in options if o.feasible and o.net_benefit > 0]
    best = max(ok, key=lambda o: (o.net_benefit, o.confidence)) if ok else None
    return options, best


def build_row(ctx, key, options, best, explainer=None):
    store, sku = key
    product, store_name = ctx.products.loc[sku, "name"], ctx.stores.loc[store, "name"]
    fresh, demand = agents.freshness_view(ctx, key), agents.demand_view(ctx, key)
    others = sorted([o for o in options if o is not best and o.feasible and o.net_benefit > 0],
                    key=lambda o: -o.net_benefit)
    why = ""
    if others:
        r = others[0]
        alt = (f"a {r.markdown_pct:.0f}% markdown" if r.action_type == "MARKDOWN" else
               f"a transfer to {ctx.stores.loc[r.counterpart_store_id, 'name']}" if r.action_type == "TRANSFER" else "a top-up order")
        why = f" The next best option, {alt}, was worth {r.net_benefit:,.0f} INR."
    if best.action_type == "REPLENISH":
        problem = (f"There is a {fresh['stockout_prob']:.0%} chance {product} at {store_name} runs out before the next "
                   f"delivery on {ctx.sku_risk.loc[key, 'next_delivery_date'].date()}.")
        effect = f"Avoids about {best.lost_sales_avoided:.0f} units of lost sales."
    else:
        problem = (f"{fresh['excess_pct']:.0f}% of the {fresh['on_hand_qty']} units of {product} at {store_name} "
                   f"({fresh['expected_unsold']:.0f} units) are expected to expire unsold.")
        effect = f"Avoids about {best.waste_avoided:.0f} units of waste."
    summary = f"{effect} Net benefit about {best.net_benefit:,.0f} INR at {best.confidence:.0%} confidence."
    reasons, why_text = None, ""
    if explainer is not None:
        risk = ctx.sku_risk.loc[key]
        if risk["alert_type"] == "EXCESS_STOCK":
            risky = [b for b in fresh["batches"] if b["risk_level"] in ("HIGH", "MEDIUM")]
            days = int(min(7, max(1, max(b["days_to_expiry"] for b in risky) - 1))) if risky else 3
        else:
            days = max(1, int((risk["next_delivery_date"] - ctx.run_date).days - 1))
        try:
            reasons = explainer.explain(key, risk["alert_type"], days, fresh, str(risk["next_delivery_date"].date()))
            items = [x.rstrip(".") for x in ([d["text"] for d in reasons["drivers"][:2]] or reasons["stock_facts"][:2])]
            why_text = " Why: " + "; ".join(items) + "."
        except Exception as e:          # an explanation problem must never block the recommendation itself
            print(f"  (no explanation for {product} at {store_name}: {e.__class__.__name__}: {e})")
    rationale = f"{problem}{why_text} {describe(best, ctx, key, product, store_name)}. {summary}{why}"
    evidence = {
        "demand_agent": demand, "freshness_agent": fresh,
        "options_considered": [{"agent": o.agent, "action": o.action_type, "quantity": o.quantity,
                                "markdown_pct": o.markdown_pct, "to_store": o.counterpart_store_id,
                                "net_benefit": round(o.net_benefit, 2), "confidence": round(o.confidence, 3),
                                "feasible": o.feasible, "notes": o.notes, "chosen": o is best} for o in options],
        "rules_applied": {k: ctx.rules[k] for k in ctx.rules if k != "markdown_steps"},
        "reasons": reasons,
        "method": "Monte Carlo, 2000 simulated futures; benefit compared with doing nothing",
    }
    action_date = (ctx.run_date + timedelta(days=best.action_offset_days)).date()
    return {
        "run_date": ctx.run_date.date(), "store_id": store, "sku_id": sku, "action_type": best.action_type,
        "action_date": action_date, "timing_note": best.timing_note, "quantity": best.quantity,
        "markdown_pct": best.markdown_pct, "counterpart_store_id": best.counterpart_store_id,
        "confidence": round(best.confidence, 3), "expected_waste_avoided_units": round(best.waste_avoided, 2),
        "expected_lost_sales_avoided_units": round(best.lost_sales_avoided, 2),
        "expected_net_benefit": round(best.net_benefit, 2), "effect_summary": summary[:255],
        "rationale": rationale, "evidence": json.dumps(evidence),
    }, rationale


def save(rows_with_options, run_date):
    with engine.begin() as conn:
        conn.execute(text("UPDATE recommendations SET status = 'EXPIRED' WHERE status = 'PROPOSED' AND run_date < :d"),
                     {"d": run_date.date()})                       # unreviewed recommendations from earlier days
        old = "SELECT rec_id FROM recommendations WHERE run_date = :d AND status = 'PROPOSED'"
        conn.execute(text(f"DELETE FROM recommendation_options WHERE rec_id IN ({old})"), {"d": run_date.date()})
        conn.execute(text("DELETE FROM recommendations WHERE run_date = :d AND status = 'PROPOSED'"), {"d": run_date.date()})
        for row, options, best in rows_with_options:
            res = conn.execute(text("""
                INSERT INTO recommendations (run_date, store_id, sku_id, action_type, action_date, timing_note,
                  quantity, markdown_pct, counterpart_store_id, confidence, expected_waste_avoided_units,
                  expected_lost_sales_avoided_units, expected_net_benefit, effect_summary, rationale, evidence)
                VALUES (:run_date, :store_id, :sku_id, :action_type, :action_date, :timing_note, :quantity,
                  :markdown_pct, :counterpart_store_id, :confidence, :expected_waste_avoided_units,
                  :expected_lost_sales_avoided_units, :expected_net_benefit, :effect_summary, :rationale, :evidence)
                """), row)
            rec_id = res.lastrowid
            for o in options:
                conn.execute(text("""
                    INSERT INTO recommendation_options (rec_id, agent, action_type, quantity, markdown_pct,
                      counterpart_store_id, expected_net_benefit, confidence, feasible, rule_notes, chosen)
                    VALUES (:r, :agent, :a, :q, :m, :c, :nb, :conf, :f, :n, :ch)
                    """), {"r": rec_id, "agent": o.agent, "a": o.action_type, "q": o.quantity, "m": o.markdown_pct,
                           "c": o.counterpart_store_id, "nb": round(o.net_benefit, 2), "conf": round(o.confidence, 3),
                           "f": o.feasible, "n": o.notes[:255], "ch": o is best})


if __name__ == "__main__":
    ensure_rules()
    ctx = load_context()
    decided = set()
    with engine.connect() as conn:
        for r in conn.execute(text("SELECT store_id, sku_id FROM recommendations WHERE run_date = :d "
                                   "AND status <> 'PROPOSED'"), {"d": ctx.run_date.date()}):
            decided.add((r[0], r[1]))
    try:
        explainer = Explainer(ctx.run_date, ctx.stores, ctx.products)
    except Exception as e:                      # explanations are optional; never block recommendations
        print(f"Note: explanations are switched off ({e.__class__.__name__}: {e})")
        explainer = None
    alerts = ctx.sku_risk[ctx.sku_risk["alert_type"] != "OK"]
    print(f"Stock as of {ctx.run_date.date()} | {len(alerts)} store/SKU pairs with alerts "
          f"({alerts['alert_type'].value_counts().to_dict()})\n")

    out, skipped = [], []
    for key in alerts.index:
        if key in decided:
            continue
        options, best = decide(ctx, key)
        if best is None:
            skipped.append(key)
            continue
        row, rationale = build_row(ctx, key, options, best, explainer)
        out.append((row, options, best))
    save(out, ctx.run_date)

    df = pd.DataFrame([r for r, _, _ in out])
    print(f"Saved {len(df)} recommendations ({len(skipped)} alerts had no beneficial, rule-compliant action)")
    if len(df):
        print("\nBy action:")
        print(df.groupby("action_type").agg(recommendations=("rec_id" if "rec_id" in df else "sku_id", "size"),
                                            net_benefit_inr=("expected_net_benefit", "sum"),
                                            waste_avoided_units=("expected_waste_avoided_units", "sum"),
                                            avg_confidence=("confidence", "mean")).round(2).to_string())
        print(f"\nTotal expected net benefit: {df['expected_net_benefit'].sum():,.0f} INR")
        print("\nTop recommendations")
        for row, _, _ in sorted(out, key=lambda x: -x[0]["expected_net_benefit"])[:5]:
            print(f"- [{row['action_type']}] {row['rationale']}")
    if skipped:
        print("\nAlerts with no recommendation")
    for key in skipped:
        b = ctx.batches.get(key)
        if b is not None and (b["days_to_expiry"] <= 1).all():
            why = "all stock expires tomorrow, too late to sell or move it"
        elif b is not None and (b["days_to_expiry"] <= 1).any():
            why = "part of the stock expires tomorrow (unavoidable) and nothing else clears the rules"
        else:
            why = "no option cleared the business rules and the minimum confidence"
        print(f"  - {ctx.products.loc[key[1], 'name']} at {ctx.stores.loc[key[0], 'name']}: {why}")
