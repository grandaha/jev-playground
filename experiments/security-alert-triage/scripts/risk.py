"""Account risk: impact times confidence per finding, rolled up per account over seven days.

Run from the experiment folder: ../../.venv/bin/python scripts/risk.py
Writes data/output/output_account_risk.csv (Jev) and output_account_risk_baseline.csv (detector severity).
Every account is scored at its worst seven-day window, because the incidents are spread over two weeks.
"""
from collections import Counter, defaultdict
from datetime import timedelta

from enrich import parse_ts
from paths import path
from tables import read_alerts, read_csv, write_csv

WINDOW_DAYS = 7
BASELINE_IMPACT = {"informational": 10, "low": 30, "medium": 60, "high": 90, "critical": 100}
BASELINE_CONFIDENCE = 0.5


def finding_risk(impact_level, p_true_positive):
    """impact_level is Jev's 0-3 Score; returns 0-100 (impact 0-100 times confidence 0-1)."""
    return impact_level / 3 * 100 * p_true_positive


def findings(alerts, decisions, groups):
    """One finding per answered alert. An alert with no user takes the user of its group mates."""
    dec = {d["alert_id"]: d for d in decisions}
    size = Counter(groups.values())
    group_users = defaultdict(Counter)
    for a in alerts:
        if a["user"]:
            group_users[groups[a["alert_id"]]][a["user"]] += 1
    out = []
    for a in alerts:
        d = dec[a["alert_id"]]
        if d["impact"] == "" or d["p_true_positive"] == "":
            continue
        user = a["user"]
        if not user:
            counts = group_users.get(groups[a["alert_id"]])
            if not counts:
                continue
            user = max(sorted(counts), key=counts.get)
        corroboration = 1.0 if size[groups[a["alert_id"]]] >= 3 else 0.5
        out.append({"user": user, "ts": parse_ts(a["timestamp"]), "detection": a["rule_name"],
                    "risk": finding_risk(float(d["impact"]), float(d["p_true_positive"])) * corroboration,
                    "alert_id": a["alert_id"]})
    return out


def baseline_findings(alerts):
    return [{"user": a["user"], "ts": parse_ts(a["timestamp"]), "detection": a["rule_name"],
             "risk": BASELINE_IMPACT[a["source_severity"]] * BASELINE_CONFIDENCE, "alert_id": a["alert_id"]}
            for a in alerts if a["user"]]


def score_window(fs):
    total = sum(f["risk"] for f in fs)
    worst = max(f["risk"] for f in fs)
    serious = sum(1 for f in fs if f["risk"] >= 50)
    kinds = len({f["detection"] for f in fs})
    return 100 * (0.4 * min(total / 150, 1) + 0.3 * min(worst / 100, 1) + 0.2 * min(serious / 3, 1) + 0.1 * min(kinds / 4, 1))


def account_scores(fs, window_days=WINDOW_DAYS):
    by_user = defaultdict(list)
    for f in fs:
        by_user[f["user"]].append(f)
    out = {}
    for user, items in by_user.items():
        items.sort(key=lambda f: f["ts"])
        best, left = 0.0, 0
        for right, end in enumerate(items):
            while items[left]["ts"] <= end["ts"] - timedelta(days=window_days):
                left += 1
            best = max(best, score_window(items[left: right + 1]))
        out[user] = round(best, 2)
    return out


def rank(scores):
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


def _write(filename, scores):
    write_csv(path(filename), [{"rank": i, "user": u, "score": s} for i, (u, s) in enumerate(rank(scores), 1)],
              ["rank", "user", "score"])


def main():
    alerts = read_alerts(path("alerts.csv"))
    decisions = read_csv(path("decisions_alerts.csv"))
    groups = {r["alert_id"]: r["group_id"] for r in read_csv(path("groups_jev.csv"))}
    jev, base = account_scores(findings(alerts, decisions, groups)), account_scores(baseline_findings(alerts))
    _write("output_account_risk.csv", jev)
    _write("output_account_risk_baseline.csv", base)
    print(f"account risk: {len(jev)} accounts scored with Jev, {len(base)} with detector severity")


if __name__ == "__main__":
    main()
