"""Pick a master record per multi-record group: highest-trust source system first, then most recent update.

Run from repo root: .venv/bin/python experiments/customer-matching/master.py accounts|contacts
Writes data/masters_<table>.csv (group_id, master_id, members, reason). No Jev calls.
"""
import csv
import sys
from collections import defaultdict

from paths import path
# Most trusted first. Assumed order (Dave did not specify it); change here and rerun, no Jev calls are involved.
SOURCE_RANK = ["erp", "billing", "crm", "web_form", "trade_show"]


def main(table):
    idc = f"{table[:-1]}_id"
    norm = {r[idc]: r for r in csv.DictReader(open(path(f"{table}_norm.csv")))}
    groups = defaultdict(list)
    for r in csv.DictReader(open(path(f"groups_{table}.csv"))):
        groups[r["group_id"]].append(r["record_id"])

    def rank(i):
        s = norm[i]["source_system"]
        return SOURCE_RANK.index(s) if s in SOURCE_RANK else len(SOURCE_RANK)

    rows = []
    for g, ids in sorted(groups.items()):
        if len(ids) < 2:
            continue
        # best source first, then newest update, then lowest id so the result is deterministic
        best = min(ids, key=lambda i: (rank(i), -int(norm[i]["updated_at"].replace("-", "")), i))
        tied = [i for i in ids if rank(i) == rank(best)]
        why = f"source {norm[best]['source_system']}" + (
            f", newest of {len(tied)} from that source ({norm[best]['updated_at']})" if len(tied) > 1
            else " (only one from the best source)")
        rows.append({"group_id": g, "master_id": best, "members": " ".join(ids), "reason": why})
    with open(path(f"masters_{table}.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["group_id", "master_id", "members", "reason"])
        w.writeheader()
        w.writerows(rows)
    print(f"{table}: {len(rows)} multi-record groups mastered")


if __name__ == "__main__":
    main(sys.argv[1])
