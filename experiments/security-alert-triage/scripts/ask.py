"""Ask Jev about each alert once, and save the raw answers.

Run from the experiment folder:
  ../../.venv/bin/python scripts/ask.py alerts [--limit N]
  ../../.venv/bin/python scripts/ask.py links [--limit N]
Writes data/work/answers_alerts.csv and answers_links.csv. Rules and thresholds can change later with no new Jev calls.
"""
import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

import rules
from group import candidate_pairs, obvious_link
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


LINK_QUESTIONS = {
    "same_incident": Score(
        instructions="Are these two alerts part of the same attack or event?",
        criteria=["They are unrelated events that only share a name or address.",
                  "They might be related, but the evidence is thin.",
                  "They are clearly steps of the same attack or the same event."]),
    "shared_entity_is_coincidence": Noul(
        instructions="Is the shared user, host or address a coincidence, for example a shared office or guest network address used by many people?"),
}
LINK_COLUMNS = ["alert_a", "alert_b", "asked", "score", "p_coincidence", "error"]


def link_state(a, b, shared):
    return {"alert_a": {k: a[k] for k in ALERT_FIELDS if a.get(k)},
            "alert_b": {k: b[k] for k in ALERT_FIELDS if b.get(k)},
            "shared_entities": list(shared)}


def parse_link(resp):
    """Turn a Jev response into (score, p_coincidence). Raises on a malformed response."""
    score = resp.answers["same_incident"].score
    coincidence = resp.answers["shared_entity_is_coincidence"].noul
    if score is None or coincidence is None:
        raise ValueError("response has an empty same_incident score or shared_entity_is_coincidence")
    return score, coincidence


def ask_link(a, b, shared, client, attempts=4):
    row = {"alert_a": a["alert_id"], "alert_b": b["alert_id"], "asked": "yes", "score": "", "p_coincidence": "", "error": ""}
    for attempt in range(attempts):
        try:
            row["score"], row["p_coincidence"] = parse_link(client.system_one(state=link_state(a, b, shared), questions=LINK_QUESTIONS))
            return row
        except Exception as e:
            if attempt == attempts - 1:
                return {**row, "score": "", "p_coincidence": "", "error": f"{type(e).__name__}: {e}"[:200]}
            time.sleep(2 ** attempt)


def ask_links(pairs, alerts_by_id, client, workers=8):
    """Ask about every candidate pair that the obvious-link rule does not already settle."""
    todo = [(a, b, s) for (a, b), s in pairs.items() if not obvious_link(alerts_by_id[a], alerts_by_id[b])]
    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(lambda t: ask_link(alerts_by_id[t[0]], alerts_by_id[t[1]], t[2], client), todo))


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["alerts", "links"])
    ap.add_argument("--limit", type=int)
    args = ap.parse_args(argv)
    alerts = read_alerts(path("alerts.csv"))
    if args.what == "alerts":
        rows = ask_alerts(alerts[: args.limit], make_client())
        write_csv(path("answers_alerts.csv"), rows, ANSWER_COLUMNS)
        asked = [r for r in rows if r["asked"] == "yes"]
        print(f"{len(rows)} alerts, {len(asked)} asked Jev, {sum(1 for r in asked if r['error'])} errors")
    else:
        pairs = dict(list(candidate_pairs(alerts).items())[: args.limit])
        rows = ask_links(pairs, {a["alert_id"]: a for a in alerts}, make_client())
        write_csv(path("answers_links.csv"), rows, LINK_COLUMNS)
        print(f"{len(pairs)} candidate pairs, {len(rows)} asked Jev, {sum(1 for r in rows if r['error'])} errors")


if __name__ == "__main__":
    main(sys.argv[1:])
