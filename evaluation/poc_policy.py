"""The agents as a policy inside the simulator: each evening, run the risk engine and the
orchestrator's decision logic on the simulated stock, and carry out what they recommend
(assuming the planner approves every recommendation)."""
import math

import numpy as np
import pandas as pd

import agent_logic as A
import orchestrator as O
import risk_engine as R
from agent_context import Context


class PocPolicy:
    def __init__(self, stores, products, rules, n_sim=500, seed=42):
        self.stores, self.products, self.rules = stores, products, rules
        R.N_SIM = n_sim
        A.N_SIM = n_sim
        self.rng = np.random.default_rng(seed)

    def after_day(self, sim, d):
        as_of = pd.Timestamp(sim.dates[d])
        ctx = Context(run_date=as_of, stores=self.stores, products=self.products, rules=self.rules)
        risk_rows = {}
        for key, s in sim.series.items():
            f = sim.fc[key]
            ctx.forecasts[key] = {"mu": f["mu"], "lo": f["lo"], "hi": f["hi"], "sd": f["sd"],
                                  "dates": [(as_of + pd.Timedelta(days=i + 1)).date().isoformat() for i in range(7)]}
            ctx.prices[key] = float(s.price[d + 1]) if d + 1 < len(s.price) else float(s.price[d])
            d_next = R.next_delivery(as_of, s.cat)
            window = (d_next - as_of).days - 1
            stock = float(sum(b["rem"] for b in s.batches))
            if not s.batches:
                so = 1.0 if window > 0 else 0.0
                risk_rows[key] = dict(on_hand_qty=0, forecast_7d_qty=float(f["mu"].sum()), days_of_cover=0.0,
                                      next_delivery_date=d_next, stockout_prob=so, expected_shortfall=0.0,
                                      expected_unsold=0.0, excess_pct=0.0, expected_waste_cost=0.0,
                                      alert_type="STOCKOUT_RISK" if so > 0 else "OK", severity="HIGH" if so > 0 else "LOW")
                continue
            b = pd.DataFrame([{"batch_id": x["id"], "qty_remaining": x["rem"], "days_to_expiry": x["exp"] - d,
                               "expiry_date": as_of + pd.Timedelta(days=x["exp"] - d)} for x in s.batches]
                             ).sort_values("days_to_expiry").reset_index(drop=True)
            if s.markdown is not None:      # one action at a time: no new risk run while a markdown is active
                b["expected_unsold"], b["unsold_pct"], b["risk_level"] = 0.0, 0.0, "LOW"
                ctx.batches[key] = b
                continue
            fc_df = pd.DataFrame({"predicted_qty": f["mu"], "lower_qty": f["lo"], "upper_qty": f["hi"]})
            unsold, stockout, shortfall, mu, _ = R.simulate_series(b, fc_df, as_of, d_next, self.rng)
            exp_unsold = unsold.mean(axis=1)
            b["expected_unsold"] = exp_unsold
            b["unsold_pct"] = exp_unsold / b["qty_remaining"] * 100
            b["risk_level"] = [R.level(p / 100, R.BATCH_HIGH, R.BATCH_MED) for p in b["unsold_pct"]]
            ctx.batches[key] = b
            excess = exp_unsold.sum() / stock
            so_prob = float(stockout.mean())
            so_sev, ex_sev = R.level(so_prob, R.STOCKOUT_HIGH, R.STOCKOUT_MED), R.level(excess, R.EXCESS_HIGH, R.EXCESS_MED)
            if so_sev != "LOW" and (ex_sev == "LOW" or so_sev == "HIGH"):
                alert, sev = "STOCKOUT_RISK", so_sev
            elif ex_sev != "LOW":
                alert, sev = "EXCESS_STOCK", ex_sev
            else:
                alert, sev = "OK", "LOW"
            risk_rows[key] = dict(on_hand_qty=int(stock), forecast_7d_qty=float(f["mu"].sum()),
                                  days_of_cover=stock / max(float(mu.mean()), 1e-6), next_delivery_date=d_next,
                                  stockout_prob=so_prob, expected_shortfall=float(shortfall.mean()),
                                  expected_unsold=float(exp_unsold.sum()), excess_pct=excess * 100,
                                  expected_waste_cost=float(exp_unsold.sum() * s.cost), alert_type=alert, severity=sev)
        ctx.sku_risk = pd.DataFrame.from_dict(risk_rows, orient="index")
        ctx.sku_risk.index = pd.MultiIndex.from_tuples(ctx.sku_risk.index, names=["store_id", "sku_id"])

        for key in ctx.sku_risk.index[ctx.sku_risk["alert_type"] != "OK"]:
            if sim.series[key].markdown is not None:
                continue
            _, best = O.decide(ctx, key)
            if best is not None:
                self.apply(sim, key, best, d)

    def apply(self, sim, key, opt, d):
        s = sim.series[key]
        R_ = self.rules
        if opt.action_type == "MARKDOWN":
            s.markdown = {"pct": float(opt.markdown_pct), "ids": {b["id"] for b in s.batches}}
            s.m["n_markdown"] += 1
        elif opt.action_type == "REPLENISH":
            q = int(opt.quantity)
            s.pending.setdefault(d + 1, []).append(
                {"id": sim.new_id("U"), "exp": d + 1 + s.shelf, "rem": q, "cost": s.cost})
            s.m["purchased"] += q
            s.m["expedite_cost"] += q * R_["expedite_cost_per_unit"]
            s.m["n_topup"] += 1
        elif opt.action_type == "TRANSFER":
            dest = sim.series[(opt.counterpart_store_id, key[1])]
            left = int(opt.quantity)
            eligible = [b for b in s.batches if (b["exp"] - d) - 1 >= R_["min_days_left_at_receiver"]]
            for b in sorted(eligible, key=lambda x: -x["exp"]):      # freshest first
                take = min(left, b["rem"])
                if take <= 0:
                    continue
                b["rem"] -= take
                left -= take
                dest.pending.setdefault(d + 1, []).append(
                    {"id": sim.new_id("T"), "exp": b["exp"], "rem": take, "cost": b["cost"]})
            shipped = int(opt.quantity) - left
            s.batches = [b for b in s.batches if b["rem"] > 0]
            s.m["transfer_cost"] += R_["transfer_fixed_cost"] + R_["transfer_cost_per_unit_km"] * opt.detail["distance_km"] * shipped
            s.m["n_transfer"] += 1
