"""Where the experiment reads and writes. One dataset lives in data/, sorted by stage."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent       # experiments/security-alert-triage
REPO = ROOT.parents[1]                                # repo root (holds .env)
DATA = ROOT / os.environ.get("TRIAGE_DATA", "data")   # TRIAGE_DATA=data_holdout runs another dataset

SOURCE_FILES = {"employees.csv", "alerts.csv", "answer_key.csv"}


def path(name):
    """data/<stage>/<name>. source: generated inputs and answer key. output: final results.
    reports: html. work: everything in between."""
    if name in SOURCE_FILES:
        stage = "source"
    elif name.endswith(".html"):
        stage = "reports"
    elif name.startswith("output_"):
        stage = "output"
    else:
        stage = "work"
    folder = DATA / stage
    folder.mkdir(parents=True, exist_ok=True)
    return folder / name
