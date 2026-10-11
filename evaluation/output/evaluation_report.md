# Evaluation report

Test window: 2026-08-06 to 2026-09-23 (49 days), 4 stores, 16 perishable SKUs. The demand model was trained only on earlier data.

## 1. Demand forecast accuracy (Milestone 2)

| Method | WAPE vs true demand (%) | Bias (%) |
|---|---|---|
| gbm_naive | 25.4 | -4.3 |
| gbm_censor_aware | 25.5 | -5.7 |
| weekday_avg | 29.8 | -2.0 |
| ma7 | 30.7 | -1.7 |
| seasonal_naive | 37.2 | -1.9 |
| naive | 38.8 | -1.3 |

## 2. Policy comparison under normal conditions (service level 70%)

Every policy faces the same real demand. Waste % is waste divided by units sold plus wasted. Intervals come from resampling store/SKU pairs.

| Policy | Waste % | Waste cost (INR) | Fill rate % | Lost units | Profit (INR) | Profit vs legacy (95% interval) |
|---|---|---|---|---|---|---|
| Legacy ordering rule (baseline) | 1.9 | 171,013 | 98.5 | 1,118 | 2,274,218 | baseline |
| Legacy + fixed 30% markdown rule | 1.8 | 167,061 | 97.3 | 2,195 | 1,934,246 | -339,972 (-481,152 to -208,483) |
| Forecast-driven ordering | 1.6 | 179,215 | 99.3 | 476 | 2,301,113 | +26,896 (-3,892 to +62,633) |
| Full POC (forecast + agents) | 1.2 | 122,443 | 99.4 | 456 | 2,335,418 | +61,200 (+27,541 to +102,886) |

Simulator check: the legacy rule in the simulator gives waste 1.9% and fill rate 98.5%; the real history for the same weeks was waste 3.3% and fill rate 98.4%.

## 3. Choosing the service level

The service level sets how much safety stock the forecast-driven policies hold. It was chosen on the seven weeks before the test window, as the highest-profit level that keeps the fill rate at 99% or better, and then applied unchanged to the test window. Higher levels cut lost sales but raise waste.

| Service level | Waste % | Fill rate % | Profit (INR) |
|---|---|---|---|
| legacy rule | 2.21 | 98.50 | 2,239,907 |
| 50% | 0.69 | 98.57 | 2,356,017 |
| 60% | 0.90 | 98.96 | 2,340,516 |
| 70% | 1.10 | 99.23 | 2,315,581 |
| 80% | 1.47 | 99.56 | 2,284,451 |
| 90% | 2.13 | 99.72 | 2,188,887 |
| 95% | 2.91 | 99.77 | 2,082,669 |

Chosen: **70%**.

## 4. Stress scenarios

### Heatwave: dairy demand +10% to +45% for 7 days

| Policy | Waste % | Waste cost (INR) | Fill rate % | Lost units | Profit (INR) | Profit vs legacy (95% interval) |
|---|---|---|---|---|---|---|
| Legacy ordering rule (baseline) | 1.8 | 171,069 | 98.4 | 1,158 | 2,287,067 | baseline |
| Legacy + fixed 30% markdown rule | 1.7 | 167,061 | 97.3 | 2,235 | 1,945,077 | -341,990 (-484,028 to -211,275) |
| Forecast-driven ordering | 1.6 | 179,215 | 99.3 | 547 | 2,313,217 | +26,149 (-4,367 to +61,966) |
| Full POC (forecast + agents) | 1.1 | 120,913 | 99.3 | 507 | 2,349,760 | +62,693 (+28,006 to +106,288) |

### Festival: demand +35% for 3 days

| Policy | Waste % | Waste cost (INR) | Fill rate % | Lost units | Profit (INR) | Profit vs legacy (95% interval) |
|---|---|---|---|---|---|---|
| Legacy ordering rule (baseline) | 1.9 | 181,363 | 98.1 | 1,392 | 2,314,919 | baseline |
| Legacy + fixed 30% markdown rule | 1.8 | 175,041 | 96.9 | 2,586 | 1,964,388 | -350,531 (-493,602 to -219,215) |
| Forecast-driven ordering | 1.7 | 185,021 | 98.9 | 803 | 2,344,430 | +29,510 (+2,004 to +62,361) |
| Full POC (forecast + agents) | 1.1 | 121,403 | 99.1 | 702 | 2,388,491 | +73,572 (+34,214 to +122,030) |

### Delhi-Central: no deliveries for 3 days

| Policy | Waste % | Waste cost (INR) | Fill rate % | Lost units | Profit (INR) | Profit vs legacy (95% interval) |
|---|---|---|---|---|---|---|
| Legacy ordering rule (baseline) | 1.7 | 156,879 | 97.2 | 2,017 | 2,233,492 | baseline |
| Legacy + fixed 30% markdown rule | 1.6 | 139,995 | 96.1 | 3,123 | 1,943,346 | -290,145 (-407,672 to -183,665) |
| Forecast-driven ordering | 1.6 | 170,369 | 98.1 | 1,399 | 2,265,760 | +32,269 (-383 to +67,788) |
| Full POC (forecast + agents) | 1.1 | 117,731 | 98.5 | 1,079 | 2,316,578 | +83,086 (+39,502 to +131,575) |

## Method and limitations

- Closed-loop replay of real simulated demand; differences between policies come only from decisions.
- Demand is simulated and the demand model's assumptions are close to how the simulator generates it, so real-world gains would be smaller.
- The markdown effect (+3% demand per 1% off) is assumed and matches the simulator's promotion effect.
- The planner is assumed to approve every recommendation; in practice some are modified or rejected.
- Profit counts margin on sales minus the cost of wasted units, transfers and urgent orders. It does not value customer goodwill lost to stockouts, which favours lower service levels.
- Single simulated trajectory; intervals come from resampling store/SKU pairs, not from repeated simulations.
- Damaged-on-arrival units and supplier transit loss are not modelled in the replay (they affect all policies equally).
