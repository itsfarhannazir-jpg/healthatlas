"""Absolute project paths: work regardless of the current working directory."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RAW = DATA / "raw"
REJECTED = DATA / "rejected" / "rejected_records.json"
DATABASE = DATA / "pakistan_health.db"
CSV = DATA / "pakistan_health_clean.csv"
CHARTS = ROOT / "charts"
REPORT = ROOT / "REPORT.md"
STATIC = ROOT / "static"
