"""Grade every stage against the hidden answer key, per scenario, Jev against the baseline.

Run from the experiment folder: ../../.venv/bin/python scripts/evaluate.py
"""
import os
from collections import Counter, defaultdict

from paths import path
from tables import read_csv


def alert_metrics(key, decisions):
    act = {d["alert_id"]: d["action"] for d in decisions}
    tp = [k for k in key if k["disposition"] == "true_positive"]
    incidents = defaultdict(list)
    for k in tp:
        incidents[k["incident_id"]].append(act[k["alert_id"]])
    benign = [k for k in key if k["disposition"] != "true_positive"]
    surfaced = sum(1 for a in act.values() if a != "close")
    return {
        "alerts": len(key),
        "tp_alerts": len(tp),
        "missed_alerts": sum(1 for k in tp if act[k["alert_id"]] == "close"),
        "real_incidents": len(incidents),
        "missed_incidents": sum(1 for acts in incidents.values() if all(a == "close" for a in acts)),
        "under_prioritized_incidents": sum(1 for acts in incidents.values() if "escalate" not in acts),
        "surfaced": surfaced,
        "queue_reduction": round(1 - surfaced / len(key), 4) if key else 0.0,
        "benign_total": len(benign),
        "benign_closed": sum(1 for k in benign if act[k["alert_id"]] == "close"),
        "benign_surfaced": sum(1 for k in benign if act[k["alert_id"]] != "close"),
    }


def scenario_table(key, decisions):
    act = {d["alert_id"]: d["action"] for d in decisions}
    table = defaultdict(Counter)
    for k in key:
        table[k["scenario"]][(k["disposition"], act[k["alert_id"]])] += 1
    return {s: dict(c) for s, c in table.items()}


def _print_alert_section(name, key, decisions):
    m = alert_metrics(key, decisions)
    print(f"\n{name}")
    print(f"  missed real alerts: {m['missed_alerts']} of {m['tp_alerts']}; "
          f"real incidents with no surfaced alert: {m['missed_incidents']} of {m['real_incidents']}; "
          f"incidents with no escalated alert: {m['under_prioritized_incidents']}")
    print(f"  queue: {m['surfaced']} of {m['alerts']} alerts reach a person ({m['queue_reduction']:.0%} fewer); "
          f"benign alerts closed {m['benign_closed']} of {m['benign_total']}")
    return scenario_table(key, decisions)


def main():
    key = read_csv(path("answer_key.csv"))
    sections = {}
    for name, file in (("Rules-only baseline", "decisions_alerts_baseline.csv"), ("Jev policy", "decisions_alerts.csv")):
        if os.path.exists(path(file)):
            sections[name] = _print_alert_section(name, key, read_csv(path(file)))
    for name, table in sections.items():
        print(f"\nBy scenario, {name}: disposition/action counts")
        for scenario in sorted(table):
            cells = ", ".join(f"{d[:2]}:{a[:3]}={n}" for (d, a), n in sorted(table[scenario].items()))
            print(f"  {scenario:<26} {cells}")


if __name__ == "__main__":
    main()
