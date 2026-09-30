"""Group records into entities: union-find over pairs decided `merge`.

Run from repo root: .venv/bin/python experiments/customer-matching/cluster.py accounts|contacts
Writes data/groups_<table>.csv: record_id, group_id, group_size, rules (the rules of the merge
pairs touching that record, so every group traces back to pair decisions and their rules).
After accounts are clustered, re-run normalize.py: contacts then use the merged account id.
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).parent / "data"


def main(table):
    ids = [r[f"{table[:-1]}_id"] for r in csv.DictReader(open(DATA / f"{table}.csv"))]
    parent = {i: i for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    rules = defaultdict(set)
    for r in csv.DictReader(open(DATA / f"decisions_{table}.csv")):
        if r["decision"] == "merge":
            parent[find(r["id_a"])] = find(r["id_b"])
            rules[r["id_a"]].add(r["rule"])
            rules[r["id_b"]].add(r["rule"])
    groups = defaultdict(list)
    for i in ids:
        groups[find(i)].append(i)
    gid = {root: f"{table[0].upper()}G{n:05d}" for n, root in enumerate(sorted(groups), 1)}
    with open(DATA / f"groups_{table}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["record_id", "group_id", "group_size", "rules"])
        for root, members in groups.items():
            for m in sorted(members):
                w.writerow([m, gid[root], len(members), "+".join(sorted(rules[m]))])
    sizes = [len(m) for m in groups.values()]
    print(f"{table}: {len(ids)} records -> {len(groups)} groups (largest {max(sizes)})")


if __name__ == "__main__":
    main(sys.argv[1])
