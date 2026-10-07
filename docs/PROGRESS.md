# Zero-Waste Grocery: Progress Tracker

Status key: ✅ done | 🟡 in progress | ⬜ not started

## Overall view

| Milestone | Ends when (finish line) | Weight* | Done | Status |
|---|---|---|---|---|
| **M1: Data Foundation** | Data in MySQL, APIs return it, React inventory page shows it | 20% | ~85% | 🟡 Nearly done |
| **M2: Intelligence Layer** | Forecast, shelf-life, spoilage-risk and stockout/excess outputs exist with measured accuracy | 25% | 0% | ⬜ |
| **M3: Agentic Decision Engine** | Agents + orchestrator produce evidence-backed proposals; planner approve/modify/reject works; simulated ERP/WMS/POS log actions | 30% | 0% | ⬜ |
| **M4: Dashboard, Integration, Evaluation** | Full planner workflow in React, end-to-end scenarios run, evaluation report vs baselines | 25% | 0% | ⬜ |

**Overall project progress: about 17%** (0.85 x 20%). M1 percentage = 11 of 13 tasks done.
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
| 11 | CORS + Swagger/OpenAPI docs | 🟡 CORS done, Swagger optional |
| 12 | React inventory page (filters, expiry colour-coding) | ✅ |
| 13 | Integration test, README, git tag `milestone-1` | ⬜ |

**All four completion criteria are met.** Remaining: optional Swagger, README, full-flow test, git tag `milestone-1`.

---

## Milestone 2: Intelligence Layer

**Finish line:** models that produce measurable predictions, stored where Milestone 3 can read them.

| # | Task | Status |
|---|---|---|
| 1 | Feature engineering (lags, weekday, weather, events, promos) | ⬜ |
| 2 | Baseline forecasts (naive, moving average) for comparison | ⬜ |
| 3 | Demand-forecasting model, short-term, per store and SKU | ⬜ |
| 4 | Forecast accuracy measured (e.g. WAPE) against baselines and `ground_truth_demand.csv` | ⬜ |
| 5 | Remaining shelf-life calculation per batch | ⬜ |
| 6 | Spoilage-risk estimate per batch (expected unsold units before expiry) | ⬜ |
| 7 | Stockout and excess-stock detection | ⬜ |
| 8 | Predictions stored in MySQL and exposed through the API | ⬜ |

---

## Milestone 3: Agentic Decision Engine

**Finish line:** every affected SKU and store gets one evidence-backed proposed action, and the planner controls execution.

| # | Task | Status |
|---|---|---|
| 1 | Demand and freshness agents | ⬜ |
| 2 | Replenishment, markdown and inter-store transfer agents | ⬜ |
| 3 | Orchestrator comparing options and choosing one action per SKU/store | ⬜ |
| 4 | Configurable business rules (margin floor, max markdown, transfer limits) | ⬜ |
| 5 | Recommendation format: timing, quantity or markdown level, confidence, expected effect, evidence | ⬜ |
| 6 | Planner approval APIs: approve, modify, reject | ⬜ |
| 7 | Simulated ERP, WMS and POS interfaces | ⬜ |
| 8 | Decision log and feedback log | ⬜ |

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
