# Milestone 3 Design: Agentic Decision Engine

## Goal

For every store and SKU that needs attention, propose **one** action, with timing, quantity or markdown level, confidence, expected effect and supporting evidence. A planner approves, modifies or rejects it before anything is executed.

## How it fits together

```
MySQL (M1 data + M2 forecasts and risk)
        |
  Python agents (agents/)                       Spring Boot backend                React (Milestone 4)
  demand | freshness | replenishment            recommendations API                planner dashboard
  markdown | transfer                           approve / modify / reject
        |                                       decision log + feedback log
  Orchestrator: compare options,                simulated ERP / WMS / POS
  apply business rules, pick one  ----------->  (execute approved actions)
        |
  recommendations + recommendation_options (MySQL)
```

The Python side proposes. The Java side runs the workflow: planner decisions, logging and execution in the simulated systems.

## The agents

| Agent | Reads | Produces |
|---|---|---|
| Demand | demand_forecasts (mean and 80% range) | Expected and high-case demand until the next delivery |
| Freshness | batch_risk, sku_risk | Batches at risk, units likely to expire, days left |
| Replenishment | Demand and Freshness output, stock, delivery schedule | Order quantity to reach the service-level target, with timing |
| Markdown | Freshness output, prices, costs | Markdown level (from the allowed steps) with the best expected benefit |
| Transfer | Freshness output, other stores' stock and demand, distances | Move surplus from one store to another where it will sell in time |

Each option comes with an expected net benefit and a confidence value.

## Expected net benefit

Compared with doing nothing:

`profit = units sold x (price - cost) - units written off x cost`

Net benefit = profit with the action minus profit without it, less any action cost (transfer cost, markdown revenue given up). The "do nothing" case comes from the risk engine's simulation.

## Confidence

The share of simulated demand scenarios in which the action beats doing nothing. A confidence of 0.8 means the action came out ahead in 80% of the 2,000 simulated futures.

## Orchestrator

1. Collect every agent's option for a store and SKU.
2. Mark options infeasible when a business rule blocks them (for example a price below the floor, or a transfer that is too far).
3. Drop options below the minimum confidence.
4. Pick the feasible option with the highest expected net benefit.
5. Save the chosen recommendation, plus all options with the reason each was chosen or rejected.

## Recommendation format

| Field | Meaning |
|---|---|
| action_type | REPLENISH, MARKDOWN or TRANSFER |
| action_date and timing_note | When to act |
| quantity | Order or transfer quantity |
| markdown_pct | Markdown level |
| counterpart_store_id | Transfer destination |
| confidence | 0 to 1 |
| expected_waste_avoided_units, expected_lost_sales_avoided_units, expected_net_benefit | Expected effect |
| effect_summary and rationale | Plain-language explanation |
| evidence (JSON) | Forecast, risk numbers, batches and rules behind the decision |
| status | PROPOSED, APPROVED, MODIFIED, REJECTED or EXECUTED |

A transfer is recorded on the **source** store, with the destination in `counterpart_store_id`.

## Business rules (table `business_rules`, editable)

| Rule | Default |
|---|---|
| service_level_target | 0.95 |
| min_confidence | 0.50 |
| order_pack_size | 5 |
| spoilage_trigger_pct | 15 |
| max_markdown_pct | 50 |
| markdown_steps | 10,20,30,40,50 |
| min_price_over_cost_pct | 5 |
| markdown_uplift_per_pct | 0.03 |
| min_transfer_qty | 10 |
| max_transfer_km | 40 |
| transfer_fixed_cost | 150 INR |
| transfer_cost_per_unit_km | 0.15 INR |
| min_days_left_at_receiver | 2 |
| require_planner_approval | true |

## Planner workflow

```
PROPOSED -> APPROVED -> EXECUTED
         -> MODIFIED (planner changes quantity or markdown) -> EXECUTED
         -> REJECTED
```

Every decision is written to `decision_log` with the before and after values. After execution, outcomes go to `feedback_log`.

## Build order

| Step | What | Where |
|---|---|---|
| 1 | Design, tables, rules (this) | docs, db |
| 2 | Agents | Python `agents/` |
| 3 | Orchestrator, writes recommendations | Python |
| 4 | Recommendations and planner decision APIs, decision log | Spring Boot |
| 5 | Simulated ERP, WMS and POS, feedback log, execution on approval | Spring Boot |
| 6 | End-to-end check, tag `milestone-3` | |
