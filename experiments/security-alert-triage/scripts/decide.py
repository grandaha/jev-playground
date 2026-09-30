"""Turn saved Jev answers into an action for each alert: close, investigate or escalate.

Run from the experiment folder: ../../.venv/bin/python scripts/decide.py
Reads data/source/alerts.csv and data/work/answers_alerts.csv; writes data/work/decisions_alerts.csv.
Closing is the risky choice, so every doubt resolves toward investigating.
"""
import math
from collections import defaultdict
from dataclasses import dataclass

import rules
from enrich import hours_apart
from paths import path
from tables import read_alerts, read_csv, require, write_csv


@dataclass(frozen=True)
class Policy:
    escalate_p: float = 0.60          # probability of a true positive at or above this escalates
    investigate_p: float = 0.15       # at or above this, the alert is at least investigated
    close_p: float = 0.90             # probability of benign needed to close
    benign_explanation_p: float = 0.80  # and an ordinary explanation must fit this well
    neighbor_hours: float = 72        # nearby alerts on the same user or host can block a close


COLUMNS = ["alert_id", "action", "reason", "p_true_positive", "p_benign", "p_benign_explanation", "impact",
           "neighbor_doubt"]


def load_answers(rows):
    return {r["alert_id"]: r for r in rows}


def _view(row):
    if not row or row.get("asked") != "yes" or row.get("error"):
        return None
    try:
        p_tp, p_fp, p_btp = (float(row[k]) for k in ("p_true_positive", "p_false_positive", "p_benign_true_positive"))
        expl, impact = float(row["p_benign_explanation"]), float(row["impact"])
    except (ValueError, TypeError):  # a malformed answer counts as no answer
        return None
    if not all(math.isfinite(x) and 0 <= x <= 1 for x in (p_tp, p_fp, p_btp, expl)):
        return None
    if not (math.isfinite(impact) and 0 <= impact <= 3):   # impact is a 0 to 3 Score
        return None
    return {"p_tp": p_tp, "p_benign": p_fp + p_btp, "expl": expl, "impact": impact}


def decide_alerts(alerts, answers, policy=Policy()):
    views = {a["alert_id"]: _view(answers.get(a["alert_id"])) for a in alerts}
    by_entity = defaultdict(list)
    for a in alerts:
        for field in ("user", "host"):
            if a[field]:
                by_entity[(field, a[field])].append(a)

    def casts_doubt(b):
        v = views[b["alert_id"]]
        if rules.never_suppress(b):
            return True
        if v is None:
            return not rules.allowlisted(b)
        return v["p_tp"] >= policy.investigate_p

    def neighbor_doubt(a):
        for field in ("user", "host"):
            if not a[field]:
                continue
            for b in by_entity[(field, a[field])]:
                if b["alert_id"] != a["alert_id"] and hours_apart(a, b) <= policy.neighbor_hours and casts_doubt(b):
                    return True
        return False

    out = []
    for a in alerts:
        v, ns, entry = views[a["alert_id"]], rules.never_suppress(a), rules.allowlisted(a)
        d = {c: "" for c in COLUMNS}
        d["alert_id"] = a["alert_id"]
        if entry:
            action, reason = "close", f"allowlist: {entry}"
        elif v is None:
            action, reason = "investigate", "no Jev answer; an unanswered alert is never closed" + (f" ({ns})" if ns else "")
        else:
            d.update(p_true_positive=round(v["p_tp"], 3), p_benign=round(v["p_benign"], 3),
                     p_benign_explanation=round(v["expl"], 3), impact=round(v["impact"], 2))
            if v["p_tp"] >= policy.escalate_p:
                action, reason = "escalate", f"Jev: true positive {v['p_tp']:.2f} >= {policy.escalate_p}"
            elif ns:
                action, reason = "investigate", f"never-suppress ({ns}); Jev true positive {v['p_tp']:.2f}"
            elif v["p_tp"] >= policy.investigate_p:
                action, reason = "investigate", f"Jev: true positive {v['p_tp']:.2f} >= {policy.investigate_p}"
            elif v["p_benign"] < policy.close_p or v["expl"] < policy.benign_explanation_p:
                action, reason = "investigate", (f"not confident enough to close: benign {v['p_benign']:.2f}, "
                                                 f"ordinary explanation {v['expl']:.2f}")
            else:
                doubt = neighbor_doubt(a)
                d["neighbor_doubt"] = doubt
                if doubt:
                    action, reason = "investigate", "nearby alerts on the same user or host cast doubt"
                else:
                    action, reason = "close", (f"Jev: benign {v['p_benign']:.2f} and an ordinary explanation "
                                               f"fits {v['expl']:.2f}")
        d.update(action=action, reason=reason)
        out.append(d)
    return out


def main():
    alerts = read_alerts(path("alerts.csv"))
    rows = decide_alerts(alerts, load_answers(read_csv(require(path("answers_alerts.csv"), "run ask.py alerts first"))))
    write_csv(path("decisions_alerts.csv"), rows, COLUMNS)
    print("Jev policy:", {x: sum(1 for r in rows if r["action"] == x) for x in ("close", "investigate", "escalate")})


if __name__ == "__main__":
    main()
