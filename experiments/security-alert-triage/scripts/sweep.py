"""Sweep the policy thresholds over saved answers (no new Jev calls).

Run from the experiment folder: ../../.venv/bin/python scripts/sweep.py
For each setting: real alerts closed, real incidents with no surfaced alert, and how many alerts reach a person.
Pick settings that miss nothing first, then read the queue cost. Check the choice on a fresh seed.
"""
from itertools import product

from decide import Policy, decide_alerts, load_answers
from evaluate import alert_metrics
from paths import path
from tables import read_alerts, read_csv


def main():
    alerts = read_alerts(path("alerts.csv"))
    answers = load_answers(read_csv(path("answers_alerts.csv")))
    key = read_csv(path("answer_key.csv"))
    real = {k["alert_id"] for k in key if k["disposition"] == "true_positive"}
    print(f"{'escalate':>8} {'close':>6} {'explain':>8} | {'missed alerts':>13} {'missed incidents':>16} "
          f"{'no escalated':>12} {'benign escalated':>16} {'reach a person':>14}")
    for esc, close, expl in product((0.4, 0.5, 0.6, 0.7), (0.8, 0.9, 0.95), (0.6, 0.8, 0.9)):
        decisions = decide_alerts(alerts, answers, Policy(escalate_p=esc, close_p=close, benign_explanation_p=expl))
        m = alert_metrics(key, decisions)
        benign_esc = sum(1 for d in decisions if d["action"] == "escalate" and d["alert_id"] not in real)
        print(f"{esc:>8} {close:>6} {expl:>8} | {m['missed_alerts']:>13} {m['missed_incidents']:>16} "
              f"{m['under_prioritized_incidents']:>12} {benign_esc:>16} {m['surfaced']:>14}")


if __name__ == "__main__":
    main()
