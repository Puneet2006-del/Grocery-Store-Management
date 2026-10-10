# Zero-Waste Grocery: Progress Tracker

Status key: ✅ done | 🟡 in progress | ⬜ not started

## Overall view

| Milestone | Ends when (finish line) | Weight* | Done | Status |
|---|---|---|---|---|
| **M1: Data Foundation** | Data in MySQL, APIs return it, React inventory page shows it | 20% | 100% | ✅ Complete (tagged `milestone-1`) |
| **M2: Intelligence Layer** | Forecast, shelf-life, spoilage-risk and stockout/excess outputs exist with measured accuracy | 25% | 100% | ✅ Complete (tag `milestone-2`) |
| **M3: Agentic Decision Engine** | Agents + orchestrator produce evidence-backed proposals; planner approve/modify/reject works; simulated ERP/WMS/POS log actions | 30% | ~15% | 🟡 In progress |
| **M4: Dashboard, Integration, Evaluation** | Full planner workflow in React, end-to-end scenarios run, evaluation report vs baselines | 25% | 0% | ⬜ |

**Overall project progress: about 49%** (20% from M1 + 25% from M2 + 0.15 x 30% from M3). 
*Weights are our own estimate of effort. Change them if your team sees it differently.

---

## Milestone 1: Data Foundation (Week 1)

**Finish line:** a working retail data foundation that Milestones 2 and 3 can consume.

### Completion criteria (from the project brief)

- [x] Data for multiple stores and perishable products is available (4 stores, 16 SKUs, 12 months)
- [x] The ingestion pipeline can load the dataset into MySQL (clean, validate, load, reconcile all run)
- [x] Product, sales and inventory APIs return valid data
- [x] The React page displays inventory from the backend

### Task checklist

| # | Task | Status |
|---|---|---|
| 1 | Project setup (repo, folders, Docker MySQL, Python venv) | ✅ |
| 2 | MySQL schema, 11 tables | ✅ |
| 3 | Master data: stores and products loaded | ✅ |
| 4 | Weather (Open-Meteo or synthetic) and events (public holidays + local) loaded | ✅ |
| 5 | Main simulation: prices, promotions, sales, batches, receipts, waste, snapshots (FIFO, reconciles) | ✅ |
| 6 | Noise injection (missing values, duplicates, bad formats, delayed feed) | ✅ |
| 7 | Cleaning pipeline + data-quality report + stock reconciliation | ✅ |
| 8 | Load cleaned data into MySQL + row-count verification | ✅ |
| 9 | Spring Boot project connected to MySQL (port 3307) | ✅ |
| 10 | APIs: stores, products, inventory (with days to expiry), sales (paginated) | ✅ |
| 11 | CORS (Swagger dropped: springdoc not confirmed compatible with Spring Boot 4.1, not a completion criterion) | ✅ |
| 12 | React inventory page (filters, expiry colour-coding) | ✅ |
| 13 | Integration test, README, git tag `milestone-1` | ✅ |

**All four completion criteria are met.** Milestone 1 is complete and tagged `milestone-1`.

---

## Milestone 2: Intelligence Layer

**Finish line:** models that produce measurable predictions, stored where Milestone 3 can read them.

| # | Task | Status |
|---|---|---|
| 1 | Feature engineering: daily store/SKU panel from MySQL (`intelligence/dataset.py`) | ✅ |
| 2 | Baseline forecasts + rolling backtest (`intelligence/baselines.py`): best baseline WAPE 29.8% | ✅ |
| 3 | Demand-forecasting model, 1-7 days ahead (`intelligence/forecast_model.py`) | ✅ |
| 4 | Forecast accuracy: model WAPE 25.5% vs best baseline 29.8% (14.4% lower), noise floor 24.0% | ✅ |
| 5 | Remaining shelf-life per batch: current stock (`risk_engine.py`) and history rebuilt from sales and receipts (`batch_state.py`: 100% match with snapshots) | ✅ |
| 6 | Spoilage-risk estimate per batch. Backtest over 50 past days: AUC 0.983 vs rule 0.974; flagged-HIGH precision 65% vs rule 41%; predicted 2,311 vs actual 2,018 units written off | ✅ |
| 7 | Stockout and excess-stock detection. Backtest: AUC 0.945 vs rule 0.907; caught 52 of 84 real stockouts (62%) vs rule 40 (48%) at similar precision | ✅ |
| 8 | Predictions stored in MySQL and exposed through the API | ✅ |

---

## Milestone 3: Agentic Decision Engine

**Finish line:** every affected SKU and store gets one evidence-backed proposed action, and the planner controls execution.

| # | Task | Status |
|---|---|---|
| 1 | Demand and freshness agents (`agents/agent_logic.py`) | 🟡 delivered, run pending |
| 2 | Replenishment, markdown and inter-store transfer agents (`agents/agent_logic.py`) | 🟡 delivered, run pending |
| 3 | Orchestrator comparing options and choosing one action per SKU/store (`agents/orchestrator.py`) | 🟡 delivered, run pending |
| 4 | Configurable business rules (margin floor, max markdown, transfer limits) | ✅ (`business_rules` table, read by the agents) |
| 5 | Recommendation format: timing, quantity or markdown level, confidence, expected effect, evidence | ✅ (`recommendations` table, `docs/M3_DESIGN.md`) |
| 6 | Planner approval APIs: approve, modify, reject (`RecommendationController`, rules API) | 🟡 delivered, run pending |
| 7 | Simulated ERP, WMS and POS interfaces (`integration/`, execute endpoint) | 🟡 delivered, run pending |
| 8 | Decision log (every decision and execution) and feedback log (execution results, planner outcomes) | 🟡 delivered, run pending |

---

## Milestone 4: Dashboard, Integration and Evaluation

**Finish line:** an integrated, demo-ready final-year project.

| # | Task | Status |
|---|---|---|
| 1 | Planner dashboard connected to backend | ⬜ |
| 2 | Review, modify, approve, reject workflow in the UI | ⬜ |
| 3 | End-to-end scenarios (e.g. heatwave, festival, delayed delivery) | ⬜ |
| 4 | Evaluation vs simple forecasting and rule-based approaches (waste, stockouts, margin) | ⬜ |
| 5 | Evaluation report | ⬜ |
| 6 | Final demo preparation | ⬜ |

---

## Project brief deliverables mapped to milestones

| Deliverable | Milestone |
|---|---|
| Prepared dataset and ingestion workflow | M1 |
| Demand-forecasting and spoilage-risk models | M2 |
| Multi-agent recommendation engine with orchestration and business rules | M3 |
| Planner dashboard (review, modify, approve, reject) | M3 (APIs) and M4 (UI) |
| Simulated ERP, WMS and POS interfaces with decision and feedback logs | M3 |
| Evaluation report vs simple forecasting and rule-based approaches | M4 |

---

## Update log

| Date | Update |
|---|---|
| 2026-10-05 | Setup, schema, master data, weather/events and simulation done. Ingestion scripts delivered, awaiting run. |
| 2026-10-05 | Ingestion pipeline run and verified: data loaded into MySQL. Data side of Milestone 1 complete. Starting Spring Boot backend. |
| 2026-10-07 | Spring Boot APIs (stores, products, inventory, sales) verified. React inventory page working against the live backend. All four M1 completion criteria met. |
| 2026-10-07 | Swagger dropped. Milestone 2 started: dataset builder and baseline forecast backtest delivered. |
| 2026-10-07 | Baselines run: best baseline WAPE 29.8% (weekday average). Forecast model delivered, awaiting run. |
| 2026-10-07 | Milestone 1 committed and tagged `milestone-1`. Milestone 1 complete. |
| 2026-10-07 | Forecast model run: WAPE 25.5% vs best baseline 29.8% (noise floor 24.0%). Production forecast with 80% range delivered. |
| 2026-10-07 | Production forecast saved. Spoilage-risk and stockout/excess engine delivered, awaiting run. |
| 2026-10-07 | Risk engine run. Batch-history reconstruction and risk backtest delivered, awaiting run. Remaining in M2: API for forecasts and risk tables. |
| 2026-10-07 | Risk backtest run (see tasks 5-7 for results). Spring Boot endpoints for forecasts and risk delivered, awaiting run. |
| 2026-10-07 | Milestone 2 complete: forecast and risk endpoints verified. Milestone 3 started: design document, tables and business rules delivered. |
| 2026-10-07 | M3 tables created (22 tables). Agents and orchestrator delivered, awaiting run. |
| 2026-10-07 | Planner workflow API delivered: recommendations, approve/modify/reject, decision log, business-rule editing. Awaiting run. |
| 2026-10-07 | Planner workflow verified. Simulated ERP/WMS/POS execution and feedback log delivered, awaiting run. |
