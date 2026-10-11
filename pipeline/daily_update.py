"""Daily update: brings the whole system up to date. Run once a day, in the evening after the stores close.

  1. live feed       simulate the days since the last data day, refresh weather, holidays, promotions
  2. forecasts       retrain the demand model and forecast the next 7 days with a confidence range
  3. risk            spoilage, stockout and excess-stock assessment of every batch and SKU
  4. agents          recommendations for the planner (older unreviewed ones are marked EXPIRED)

Run:  python pipeline/daily_update.py
      python pipeline/daily_update.py --until 2026-10-11     (simulate up to a chosen date instead of today)

Schedule it on Windows (daily at 22:00), after replacing the paths:
  schtasks /create /tn "ZeroWasteDaily" /sc daily /st 22:00 /tr "C:\\path\\to\\venv\\Scripts\\python.exe C:\\path\\to\\pipeline\\daily_update.py"
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STEPS = [
    ("Live data feed", "pipeline/live_feed.py"),
    ("Demand forecasts", "intelligence/forecast_next_week.py"),
    ("Spoilage and stockout risk", "intelligence/risk_engine.py"),
    ("Agent recommendations", "agents/orchestrator.py"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", type=str, default=None)
    args = ap.parse_args()
    t_all = time.time()
    for i, (name, script) in enumerate(STEPS, 1):
        print(f"\n=== Step {i}/{len(STEPS)}: {name} ===", flush=True)
        cmd = [sys.executable, str(ROOT / script)]
        if script.endswith("live_feed.py") and args.until:
            cmd += ["--until", args.until]
        t0 = time.time()
        result = subprocess.run(cmd, cwd=str(ROOT))
        if result.returncode != 0:
            print(f"\nStep {i} ({name}) failed. Fix the error above and run the update again; "
                  f"finished steps do not need to be repeated by hand.")
            sys.exit(result.returncode)
        print(f"--- done in {time.time() - t0:.0f}s", flush=True)
    print(f"\nDaily update finished in {time.time() - t_all:.0f}s. Refresh the dashboard.")


if __name__ == "__main__":
    main()
