"""The five agents.

Demand and freshness agents describe the situation for one store and SKU.
Replenishment, markdown and transfer agents each propose options and score them by
expected net benefit and confidence, compared with doing nothing.

  expected net benefit = average, over 2,000 simulated futures, of
      (profit with the action) - (profit without it) - cost of the action
      profit = revenue - cost of every unit sold or written off
  confidence = share of those futures in which the action comes out ahead
"""
import math
import zlib
from dataclasses import dataclass, field

import numpy as np

from agent_context import Context, distance_km
from simcore import N_SIM, draw_base_demand, fifo_run, profit


@dataclass
class Option:
    agent: str
    action_type: str                    # REPLENISH / MARKDOWN / TRANSFER
    quantity: int | None = None
    markdown_pct: float | None = None
    counterpart_store_id: str | None = None
    net_benefit: float = 0.0
    confidence: float = 0.0
    waste_avoided: float = 0.0
    lost_sales_avoided: float = 0.0
    feasible: bool = True
    notes: str = ""
    action_offset_days: int = 0         # 0 = tonight, 1 = from opening tomorrow
    timing_note: str = ""
    detail: dict = field(default_factory=dict)


def rng_for(*parts) -> np.random.Generator:
    return np.random.default_rng(zlib.crc32("|".join(parts).encode()))


# ------------------------------------------------------------- assessment agents
def demand_view(ctx: Context, key):
    f = ctx.forecasts[key]
    return {"dates": f["dates"], "mean": f["mu"].round(1).tolist(), "p10": f["lo"].round(1).tolist(),
            "p90": f["hi"].round(1).tolist(), "total_7d": float(f["mu"].sum())}


def freshness_view(ctx: Context, key):
    risk = ctx.sku_risk.loc[key]
    b = ctx.batches.get(key)
    batches = [] if b is None else [
        {"batch_id": r.batch_id, "qty": int(r.qty_remaining), "days_to_expiry": int(r.days_to_expiry),
         "expected_unsold": float(r.expected_unsold), "unsold_pct": float(r.unsold_pct),
         "risk_level": r.risk_level} for r in b.itertuples()]
    return {"on_hand_qty": int(risk["on_hand_qty"]), "days_of_cover": None if risk["days_of_cover"] != risk["days_of_cover"] else float(risk["days_of_cover"]),
            "stockout_prob": float(risk["stockout_prob"]), "excess_pct": float(risk["excess_pct"]),
            "expected_unsold": float(risk["expected_unsold"]), "alert_type": risk["alert_type"],
            "severity": risk["severity"], "batches": batches}


def _batch_arrays(b):
    dte = b["days_to_expiry"].to_numpy(int)
    return b["qty_remaining"].to_numpy(float), np.ones(len(b), int), dte


# ------------------------------------------------------------------- markdown
def markdown_options(ctx: Context, key):
    store, sku = key
    b = ctx.batches.get(key)
    if b is None or b.empty:
        return []
    R, cost = ctx.rules, float(ctx.products.loc[sku, "cost"])
    price = ctx.prices.get(key, float(ctx.products.loc[sku, "base_price"]))
    qty, start, dte = _batch_arrays(b)
    days = int(dte.max())
    f = ctx.forecasts[key]
    base = draw_base_demand(f["mu"], f["sd"], days, N_SIM, rng_for("markdown", store, sku))
    sold0, unsold0, _ = fifo_run(qty, start, dte, base)
    profit0 = profit(sold0, unsold0, np.full(days, price), cost)

    options = []
    for pct in R["markdown_steps"]:
        new_price = price * (1 - pct / 100)
        notes, feasible = [], True
        if pct > R["max_markdown_pct"]:
            feasible = False
            notes.append(f"above the {R['max_markdown_pct']:.0f}% markdown limit")
        floor = cost * (1 + R["min_price_over_cost_pct"] / 100)
        if new_price < floor:
            feasible = False
            notes.append(f"price {new_price:.2f} would fall below the floor {floor:.2f}")
        lift = 1 + R["markdown_uplift_per_pct"] * pct
        sold1, unsold1, _ = fifo_run(qty, start, dte, base * lift)
        delta = profit(sold1, unsold1, np.full(days, new_price), cost) - profit0
        options.append(Option(
            agent="markdown", action_type="MARKDOWN", markdown_pct=pct, net_benefit=float(delta.mean()),
            confidence=float((delta > 0).mean()), waste_avoided=float((unsold0.sum(0) - unsold1.sum(0)).mean()),
            feasible=feasible, notes="; ".join(notes), action_offset_days=1,
            timing_note="Apply from opening tomorrow and keep until the current batches are sold",
            detail={"old_price": round(price, 2), "new_price": round(new_price, 2), "demand_lift": round(lift, 2)}))
    return options


# ------------------------------------------------------------------- transfer
def transfer_options(ctx: Context, key):
    store, sku = key
    b = ctx.batches.get(key)
    if b is None or b.empty:
        return []
    R, cost = ctx.rules, float(ctx.products.loc[sku, "cost"])
    qty, start, dte = _batch_arrays(b)
    days = int(dte.max())
    f = ctx.forecasts[key]
    base = draw_base_demand(f["mu"], f["sd"], days, N_SIM, rng_for("transfer", store, sku))
    _, unsold, _ = fifo_run(qty, start, dte, base)
    eligible = (dte - 1) >= R["min_days_left_at_receiver"]
    if not eligible.any():
        return [Option(agent="transfer", action_type="TRANSFER", feasible=False,
                       notes=f"no batch has {R['min_days_left_at_receiver']:.0f}+ days left on arrival")]
    unsold_elig = unsold[eligible].sum(axis=0)
    pack = int(R["order_pack_size"])
    q = int(min(qty[eligible].sum(), math.floor(np.percentile(unsold_elig, 75) / pack) * pack))
    if q < R["min_transfer_qty"]:
        return [Option(agent="transfer", action_type="TRANSFER", quantity=q, feasible=False,
                       notes=f"rescuable surplus is below the minimum transfer of {R['min_transfer_qty']:.0f} units")]

    # ship the freshest eligible units: they are the ones this store would waste, and last longest at the receiver
    order = np.argsort(-dte[eligible])
    left, ship_min = q, 99
    for i in order:
        take = min(left, qty[eligible][i])
        if take > 0:
            ship_min = min(ship_min, int(dte[eligible][i]))
        left -= take
    window = int(min(7, ship_min - 1))

    options = []
    for other in ctx.stores.index:
        if other == store or (other, sku) not in ctx.forecasts:
            continue
        dist = distance_km(ctx, store, other)
        if dist > R["max_transfer_km"]:
            options.append(Option(agent="transfer", action_type="TRANSFER", quantity=q, counterpart_store_id=other,
                                  feasible=False, notes=f"{dist:.0f} km exceeds the {R['max_transfer_km']:.0f} km limit"))
            continue
        g = ctx.forecasts[(other, sku)]
        mean_b, var_b = float(g["mu"][:window].sum()), float((g["sd"][:window] ** 2).sum())
        rng = rng_for("receiver", store, other, sku)
        demand_b = rng.gamma(max(mean_b ** 2 / var_b, 1e-3), var_b / max(mean_b, 1e-6), N_SIM) if mean_b > 0.05 else np.zeros(N_SIM)
        stock_b = float(ctx.batches[(other, sku)]["qty_remaining"].sum()) if (other, sku) in ctx.batches else 0.0
        absorbed = np.minimum(q, np.maximum(0, demand_b - stock_b))     # what the receiver would otherwise have to order
        rescued = np.minimum(np.minimum(q, unsold_elig), absorbed)
        transfer_cost = R["transfer_fixed_cost"] + R["transfer_cost_per_unit_km"] * dist * q
        net = rescued * cost - transfer_cost
        options.append(Option(
            agent="transfer", action_type="TRANSFER", quantity=q, counterpart_store_id=other,
            net_benefit=float(net.mean()), confidence=float((net > 0).mean()), waste_avoided=float(rescued.mean()),
            notes=f"{dist:.0f} km, {window} sellable days at the receiver", action_offset_days=0,
            timing_note="Dispatch tonight so the stock arrives before opening tomorrow",
            detail={"distance_km": round(dist, 1), "transfer_cost": round(transfer_cost, 2),
                    "receiver_stock": stock_b, "receiver_expected_demand": round(mean_b, 1)}))
    return options


# --------------------------------------------------------------- replenishment
def replenishment_options(ctx: Context, key):
    store, sku = key
    risk = ctx.sku_risk.loc[key]
    window = int((risk["next_delivery_date"] - ctx.run_date).days - 1)
    if window < 1:
        return []
    R = ctx.rules
    cost = float(ctx.products.loc[sku, "cost"])
    price = ctx.prices.get(key, float(ctx.products.loc[sku, "base_price"]))
    f = ctx.forecasts[key]
    base = draw_base_demand(f["mu"], f["sd"], window, N_SIM, rng_for("replenish", store, sku))
    b = ctx.batches.get(key)
    if b is None or b.empty:
        shortfall = base.sum(axis=0)
    else:
        qty, start, dte = _batch_arrays(b)
        shortfall = fifo_run(qty, start, dte, base)[2].sum(axis=0)
    pack = int(R["order_pack_size"])
    q = int(math.ceil(np.quantile(shortfall, R["service_level_target"]) / pack) * pack)
    if q <= 0:
        return []
    lost = np.minimum(q, shortfall)
    net = lost * (price - cost) - q * R["expedite_cost_per_unit"]
    return [Option(
        agent="replenishment", action_type="REPLENISH", quantity=q, net_benefit=float(net.mean()),
        confidence=float((net > 0).mean()), lost_sales_avoided=float(lost.mean()),
        notes=f"covers the {window} day(s) before the next delivery at a {R['service_level_target']:.0%} service level",
        action_offset_days=0, timing_note="Place tonight as an urgent top-up so it arrives before opening",
        detail={"days_until_next_delivery": window + 1, "stockout_prob": float(risk["stockout_prob"])})]
