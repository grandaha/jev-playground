"""Grade every stage against the hidden answer key, per scenario, Jev against the baseline.

Run from the experiment folder: ../../.venv/bin/python scripts/evaluate.py
"""
import os
from collections import Counter, defaultdict
from itertools import combinations

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


def stage_accuracy(key, alerts, answers):
    """For real alerts: how often Jev's stage, and the detector's claimed tactic, match the true tactic."""
    claimed = {a["alert_id"]: a["claimed_tactic"] for a in alerts}
    real = [k for k in key if k["disposition"] == "true_positive"]
    jev = sum(1 for k in real if answers.get(k["alert_id"], {}).get("stage") == k["true_tactic"])
    detector = sum(1 for k in real if claimed[k["alert_id"]] == k["true_tactic"])
    return {"real_alerts": len(real), "jev_correct": jev, "detector_correct": detector}


def _print_alert_section(name, key, decisions):
    m = alert_metrics(key, decisions)
    print(f"\n{name}")
    print(f"  missed real alerts: {m['missed_alerts']} of {m['tp_alerts']}; "
          f"real incidents with no surfaced alert: {m['missed_incidents']} of {m['real_incidents']}; "
          f"incidents with no escalated alert: {m['under_prioritized_incidents']}")
    print(f"  queue: {m['surfaced']} of {m['alerts']} alerts reach a person ({m['queue_reduction']:.0%} fewer); "
          f"benign alerts closed {m['benign_closed']} of {m['benign_total']}")
    return scenario_table(key, decisions)


def grouping_metrics(key, groups):
    incident = {k["alert_id"]: k["incident_id"] for k in key}
    by_group, by_incident = defaultdict(list), defaultdict(list)
    for aid, g in groups.items():
        by_group[g].append(aid)
    for aid, inc in incident.items():
        if inc:
            by_incident[inc].append(aid)
    linked = {pair for members in by_group.values() for pair in combinations(sorted(members), 2)}
    truth = {pair for members in by_incident.values() for pair in combinations(sorted(members), 2)}
    correct = linked & truth
    merged = sum(1 for members in by_group.values() if len({incident[a] for a in members if incident[a]}) > 1)
    scenario = {k["alert_id"]: k.get("scenario", "") for k in key}
    by_scenario = defaultdict(lambda: {"wrong_links": 0, "missed_links": 0})
    for label, pairs in (("wrong_links", linked - truth), ("missed_links", truth - linked)):
        for a, b in pairs:
            owner = scenario[a] if scenario[a] == scenario[b] else "cross-scenario"
            by_scenario[owner][label] += 1
    return {"pairs_linked": len(linked), "true_pairs": len(truth), "correct_pairs": len(correct),
            "precision": len(correct) / len(linked) if linked else 1.0,
            "recall": len(correct) / len(truth) if truth else 1.0, "merged_incidents": merged,
            "by_scenario": {s: dict(v) for s, v in by_scenario.items()}}


def ranking_metrics(ranked, key, ks=(10, 20)):
    scenario_of = {k["compromised_user"]: k["scenario"] for k in key if k["compromised_user"]}
    compromised = set(scenario_of)
    users = [u for u, _ in ranked]
    hits = {k: sum(1 for u in users[:k] if u in compromised) for k in ks}
    first = next((i for i, u in enumerate(users, 1) if u in compromised), None)
    by_scenario = {}
    for user, scenario in scenario_of.items():
        row = by_scenario.setdefault(scenario, {"compromised": 0, **{f"top_{k}": 0 for k in ks}})
        row["compromised"] += 1
        for k in ks:
            row[f"top_{k}"] += 1 if user in users[:k] else 0
    return {"compromised": len(compromised), "top_k": hits, "first_hit_rank": first, "by_scenario": by_scenario}


def main():
    key =read_csv(path("answer_key.csv"))
    sections = {}
    for name, file in (("Rules-only baseline", "decisions_alerts_baseline.csv"), ("Jev policy", "decisions_alerts.csv")):
        if os.path.exists(path(file)):
            sections[name] = _print_alert_section(name, key, read_csv(path(file)))
    if os.path.exists(path("answers_alerts.csv")):
        answers = {r["alert_id"]: r for r in read_csv(path("answers_alerts.csv"))}
        s = stage_accuracy(key, read_csv(path("alerts.csv")), answers)
        print(f"\nStage accuracy on {s['real_alerts']} real alerts: Jev {s['jev_correct']}, "
              f"the detector's claimed tactic {s['detector_correct']}")
    for name, file in (("Baseline grouping (shared entity, 72 hours)", "groups_baseline.csv"),
                       ("Jev grouping", "groups_jev.csv")):
        if os.path.exists(path(file)):
            groups = {r["alert_id"]: r["group_id"] for r in read_csv(path(file))}
            g = grouping_metrics(key, groups)
            print(f"\n{name}: {len(set(groups.values()))} groups; linked pairs {g['pairs_linked']}, "
                  f"correct {g['correct_pairs']} of {g['true_pairs']} true pairs "
                  f"(precision {g['precision']:.0%}, recall {g['recall']:.0%}); "
                  f"groups that hold two different real incidents: {g['merged_incidents']}")
            for s, v in sorted(g["by_scenario"].items()):
                print(f"    {s:<26} wrong links {v['wrong_links']}, missed links {v['missed_links']}")
    for name, file in (("Account risk with Jev", "output_account_risk.csv"),
                       ("Account risk, detector severity only", "output_account_risk_baseline.csv")):
        if os.path.exists(path(file)):
            ranked = [(r["user"], float(r["score"])) for r in read_csv(path(file))]
            m = ranking_metrics(ranked, key)
            print(f"\n{name}: {m['compromised']} compromised accounts; "
                  + ", ".join(f"top {k}: {n}" for k, n in m["top_k"].items()) + f"; first hit at rank {m['first_hit_rank']}")
            for s, v in sorted(m["by_scenario"].items()):
                print(f"    {s:<26} " + ", ".join(f"{label} {n}" for label, n in v.items()))
    for name, table in sections.items():
        print(f"\nBy scenario, {name}: disposition/action counts")
        for scenario in sorted(table):
            cells = ", ".join(f"{d[:2]}:{a[:3]}={n}" for (d, a), n in sorted(table[scenario].items()))
            print(f"  {scenario:<26} {cells}")


if __name__ == "__main__":
    main()
