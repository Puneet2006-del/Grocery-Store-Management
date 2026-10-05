"""Shared settings for all data generators. Import this instead of repeating values."""
from pathlib import Path

START_DATE = "2025-10-01"   # 12 months of history
END_DATE = "2026-09-30"
SEED = 42                   # fixed seed -> same dataset every run

ROOT = Path(__file__).resolve().parents[1]      # data-pipeline/
RAW = ROOT / "data" / "raw"
CLEAN = ROOT / "data" / "clean"
RAW.mkdir(parents=True, exist_ok=True)
CLEAN.mkdir(parents=True, exist_ok=True)
