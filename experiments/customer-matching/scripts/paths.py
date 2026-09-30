"""Where the pipeline reads and writes. One sample dataset lives in data/, sorted by stage."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent       # experiments/customer-matching
REPO = ROOT.parents[1]                                # repo root (holds .env)
DATA = ROOT / os.environ.get("MATCH_DATA", "data")    # MATCH_DATA=other_folder runs the pipeline on another folder


def path(name):
    """data/<stage>/<name>. source: generated inputs and answer key. golden: final records. reports: html.
    work: everything in between (normalized records, candidates, model answers, decisions, groups, masters)."""
    if name in ("accounts.csv", "contacts.csv", "answer_key.csv"):
        stage = "source"
    elif name.startswith("golden_") and name.endswith(".csv"):
        stage = "golden"
    elif name.endswith(".html"):
        stage = "reports"
    else:
        stage = "work"
    folder = DATA / stage
    folder.mkdir(parents=True, exist_ok=True)
    return folder / name
