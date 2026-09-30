"""Ask Jev about each alert once, and save the raw answers.

Run from the experiment folder:
  ../../.venv/bin/python scripts/ask.py alerts [--limit N]
Writes data/work/answers_alerts.csv. Rules and thresholds can change later with no new Jev calls.
"""
import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

import rules
from paths import REPO, path
from schema import DISPOSITIONS, TACTIC_DESCRIPTIONS
from tables import read_alerts, write_csv

load_dotenv(REPO / ".env")

IMPACT_LEVELS = [
    "Minimal: no sensitive data or systems are at risk.",
    "Limited: one account or workstation is affected and the damage is easy to contain.",
    "Serious: sensitive data or an important system is at risk, or several accounts are affected.",
    "Severe: customer data, crown-jewel systems or company-wide operations are at risk.",
]

ALERT_QUESTIONS = {
    "disposition": Choice(
        instructions="Is this alert a real attack, a false alarm, or real but authorized activity?",
        criteria={
            "true_positive": "Real malicious activity that needs a response.",
            "false_positive": "Benign activity that only looked suspicious, or a detector misfire.",
            "benign_true_positive": "Real behavior that is authorized or expected, such as an approved admin task, a scheduled job or an authorized security test.",
        }),
    "impact": Score(
        instructions="If this alert is real, how much damage could it do to the company?",
        criteria=IMPACT_LEVELS),
    "stage": Choice(
        instructions="Which attacker goal does this activity serve?",
        criteria=dict(TACTIC_DESCRIPTIONS)),
    "benign_explanation": Noul(
        instructions="Does an ordinary, authorized explanation fit the evidence in this alert?"),
}

ANSWER_COLUMNS = ["alert_id", "asked", "p_true_positive", "p_false_positive", "p_benign_true_positive",
                  "impact", "impact_confidence", "stage", "stage_confidence", "p_benign_explanation", "error"]
ALERT_FIELDS = ["timestamp", "detector", "rule_name", "description", "source_severity", "user", "host",
                "src_ip", "dst_ip", "claimed_tactic"]


def make_client():
    return TypeSafeClient()


def alert_state(alert):
    return {
        "alert": {k: alert[k] for k in ALERT_FIELDS if alert.get(k)},
        "context": {"asset_criticality": alert.get("asset_criticality") or "unknown",
                    "user_access": alert.get("user_access") or "unknown"},
        "note": "The detector's severity and tactic are its own guesses and are sometimes wrong.",
    }


def choice_probs(answer, options):
    """Probability of each option, whether the SDK keys them by option name or by position."""
    p = dict(answer.probabilities)
    return {o: float(p.get(o, p.get(i, p.get(str(i), 0.0)))) for i, o in enumerate(options)}


def parse_answers(resp):
    """Turn a Jev response into the answer columns. Raises on a malformed response."""
    disp = choice_probs(resp.answers["disposition"], DISPOSITIONS)
    stage = resp.answers["stage"]
    impact = resp.answers["impact"]
    noul = resp.answers["benign_explanation"].noul
    if impact.score is None or noul is None:
        raise ValueError("response has an empty impact score or benign_explanation")
    return dict(p_true_positive=disp["true_positive"], p_false_positive=disp["false_positive"],
                p_benign_true_positive=disp["benign_true_positive"], impact=impact.score,
                impact_confidence=impact.confidence, stage=stage.choice, stage_confidence=stage.confidence,
                p_benign_explanation=noul)


def ask_one(alert, client, attempts=4):
    row = {c: "" for c in ANSWER_COLUMNS}
    row.update(alert_id=alert["alert_id"], asked="yes")
    for attempt in range(attempts):  # the API occasionally errors, or returns a malformed answer
        try:
            resp = client.system_one(state=alert_state(alert), questions=ALERT_QUESTIONS)
            row.update(parse_answers(resp))
            return row
        except Exception as e:
            if attempt == attempts - 1:
                return {**{c: "" for c in ANSWER_COLUMNS}, "alert_id": alert["alert_id"], "asked": "yes",
                        "error": f"{type(e).__name__}: {e}"[:200]}
            time.sleep(2 ** attempt)


def ask_alerts(alerts, client, workers=8):
    def one(alert):
        if rules.allowlisted(alert):  # known-harmless by rule: no question needed
            return {**{c: "" for c in ANSWER_COLUMNS}, "alert_id": alert["alert_id"], "asked": "no"}
        return ask_one(alert, client)

    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(one, alerts))


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["alerts"])
    ap.add_argument("--limit", type=int)
    args = ap.parse_args(argv)
    alerts = read_alerts(path("alerts.csv"))[: args.limit]
    rows = ask_alerts(alerts, make_client())
    write_csv(path("answers_alerts.csv"), rows, ANSWER_COLUMNS)
    asked = [r for r in rows if r["asked"] == "yes"]
    print(f"{len(rows)} alerts, {len(asked)} asked Jev, {sum(1 for r in asked if r['error'])} errors")


if __name__ == "__main__":
    main(sys.argv[1:])
