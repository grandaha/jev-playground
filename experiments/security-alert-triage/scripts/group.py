"""Group alerts into incidents: candidate pairs, the baseline, and (Task 6) Jev's link judgments.

Run from the experiment folder: ../../.venv/bin/python scripts/group.py baseline
Writes data/work/candidate_pairs.csv and data/work/groups_baseline.csv.
"""
import sys
from collections import defaultdict
from itertools import combinations

from enrich import entities, hours_apart
from paths import path
from tables import read_alerts, write_csv

WINDOW_HOURS = 72
OBVIOUS_MINUTES = 30


def candidate_pairs(alerts, window_hours=WINDOW_HOURS):
    """Alert pairs that share a user, host or address within the window, with the entities they share."""
    by_entity = defaultdict(list)
    for a in alerts:
        for e in entities(a):
            by_entity[e].append(a)
    shared = defaultdict(set)
    for e, members in by_entity.items():
        for a, b in combinations(members, 2):
            if hours_apart(a, b) <= window_hours:
                shared[tuple(sorted((a["alert_id"], b["alert_id"])))].add(e)
    return {pair: sorted(es) for pair, es in shared.items()}


def obvious_link(a, b):
    """Same user and same host within 30 minutes: no question needed."""
    return (bool(a["user"]) and a["user"] == b["user"] and bool(a["host"]) and a["host"] == b["host"]
            and hours_apart(a, b) * 60 <= OBVIOUS_MINUTES)


def cluster(ids, links):
    """Union-find. Returns {alert_id: group_id}, with groups numbered in order of their first member."""
    parent = {i: i for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in links:
        parent[find(a)] = find(b)
    names, out = {}, {}
    for i in sorted(ids):
        root = find(i)
        names.setdefault(root, f"GRP-{len(names) + 1:04d}")
        out[i] = names[root]
    return out


def baseline_groups(alerts):
    """The rules-only baseline: every candidate pair is linked."""
    return cluster([a["alert_id"] for a in alerts], candidate_pairs(alerts).keys())


def write_groups(groups, filename):
    write_csv(path(filename), [{"alert_id": i, "group_id": g} for i, g in sorted(groups.items())], ["alert_id", "group_id"])


def main(argv):
    alerts = read_alerts(path("alerts.csv"))
    if argv == ["baseline"]:
        pairs = candidate_pairs(alerts)
        write_csv(path("candidate_pairs.csv"),
                  [{"alert_a": a, "alert_b": b, "shared": " ".join(s)} for (a, b), s in sorted(pairs.items())],
                  ["alert_a", "alert_b", "shared"])
        groups = baseline_groups(alerts)
        write_groups(groups, "groups_baseline.csv")
        print(f"baseline: {len(pairs)} candidate pairs, {len(set(groups.values()))} groups from {len(alerts)} alerts")
    else:
        raise SystemExit("usage: group.py baseline")


if __name__ == "__main__":
    main(sys.argv[1:])
