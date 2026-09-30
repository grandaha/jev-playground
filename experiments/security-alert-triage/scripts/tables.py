"""CSV helpers shared by every stage."""
import csv
from pathlib import Path


def read_csv(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def write_csv(p, rows, columns=None):
    cols = columns or (list(rows[0]) if rows else [])
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def require(p, hint):
    if not Path(p).exists():
        raise SystemExit(f"{Path(p).name} is missing; {hint}")
    return p


def read_alerts(p):
    rows = read_csv(p)
    if not rows:
        raise SystemExit(f"{Path(p).name} has no alerts; run generate.py first")
    return rows
