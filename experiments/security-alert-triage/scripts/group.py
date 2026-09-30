"""Group alerts into incidents: candidate pairs, the baseline, and (Task 6) Jev's link judgments.

Run from the experiment folder: ../../.venv/bin/python scripts/group.py baseline
Writes data/work/candidate_pairs.csv and data/work/groups_baseline.csv.
"""
import sys
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations

from enrich import entities, hours_apart
from paths import path
from schema import ACTIONS
from tables import read_alerts, read_csv, write_csv

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


@dataclass(frozen=True)
class LinkPolicy:
    link_score: float = 1.8      # Jev's same-incident Score runs 0 to 2; 1.6 merged the two_incidents_one_user pairs (they score up to 1.78)
    coincidence_p: float = 0.5   # a shared entity judged a coincidence at or above this does not link


def decide_links(pairs, alerts_by_id, answers, policy=LinkPolicy()):
    rows = []
    for (a, b), shared in pairs.items():
        row = {"alert_a": a, "alert_b": b}
        if obvious_link(alerts_by_id[a], alerts_by_id[b]):
            rows.append({**row, "link": "yes", "rule": "obvious_link", "detail": "same user and host within 30 minutes"})
            continue
        ans = answers.get((a, b))
        if not ans or ans.get("error") or ans.get("score", "") == "":
            rows.append({**row, "link": "no", "rule": "no_jev_answer",
                         "detail": "unanswered pairs are not linked; each alert still gets its own decision"})
            continue
        score, coincidence = float(ans["score"]), float(ans["p_coincidence"])
        if score >= policy.link_score and coincidence < policy.coincidence_p:
            rows.append({**row, "link": "yes", "rule": "jev_link",
                         "detail": f"same-incident {score:.2f} >= {policy.link_score}, coincidence {coincidence:.2f}"})
        else:
            rows.append({**row, "link": "no", "rule": "jev_no_link",
                         "detail": f"same-incident {score:.2f}, coincidence {coincidence:.2f}; shared {' '.join(shared)}"})
    return rows


def jev_groups(alerts, link_rows):
    return cluster([a["alert_id"] for a in alerts], [(r["alert_a"], r["alert_b"]) for r in link_rows if r["link"] == "yes"])


_SEVERITY_BY_IMPACT = ["low", "medium", "high", "critical"]   # Jev's impact Score 0-3 rounded to a level
_SEVERITY_RANK = {"informational": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def _severity(decision):
    if decision["impact"] == "":
        return "informational"
    if float(decision["p_benign"]) >= 0.5:
        return "informational"
    return _SEVERITY_BY_IMPACT[min(3, max(0, round(float(decision["impact"]))))]


def incident_table(alerts, groups, decisions):
    dec = {d["alert_id"]: d for d in decisions}
    members = defaultdict(list)
    for a in alerts:
        members[groups[a["alert_id"]]].append(a)
    rows = []
    for g in sorted(members):
        ds = [dec[a["alert_id"]] for a in members[g]]
        rows.append({
            "group_id": g, "alerts": len(ds),
            "action": max((d["action"] for d in ds), key=ACTIONS.index),
            "severity": max((_severity(d) for d in ds), key=_SEVERITY_RANK.get),
            "users": " ".join(sorted({a["user"] for a in members[g] if a["user"]})),
            "max_p_true_positive": max((float(d["p_true_positive"]) for d in ds if d["p_true_positive"] != ""), default=0.0)})
    return rows


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
    elif argv == ["jev"]:
        by_id = {a["alert_id"]: a for a in alerts}
        pairs = candidate_pairs(alerts)
        answers = {(r["alert_a"], r["alert_b"]): r for r in read_csv(path("answers_links.csv"))}
        link_rows = decide_links(pairs, by_id, answers)
        write_csv(path("decisions_links.csv"), link_rows, ["alert_a", "alert_b", "link", "rule", "detail"])
        groups = jev_groups(alerts, link_rows)
        write_groups(groups, "groups_jev.csv")
        write_csv(path("output_incidents.csv"), incident_table(alerts, groups, read_csv(path("decisions_alerts.csv"))),
                  ["group_id", "alerts", "action", "severity", "users", "max_p_true_positive"])
        print(f"Jev grouping: {sum(1 for r in link_rows if r['link'] == 'yes')} of {len(link_rows)} pairs linked, "
              f"{len(set(groups.values()))} groups")
    else:
        raise SystemExit("usage: group.py baseline|jev")


if __name__ == "__main__":
    main(sys.argv[1:])
