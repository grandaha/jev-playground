# Security alert triage with Jev

This project triages security alerts. For each alert it decides whether the threat is real and how serious it is. Then it closes, investigates or escalates the alert. It groups related alerts into incidents and ranks the employee accounts most likely to be compromised or targeted.

Jev (TypeSafe System One) makes the judgment calls that code cannot. Code makes every decision and keeps the evidence. The data is synthetic, so an answer key can grade the result. The alerts describe what a detector saw. They contain no attack steps or tooling.

## What you get

- A decision and a reason for every alert. The design leans toward escalating, because the costly mistake is closing the alert of a real attack.
- Incidents built from related alerts, each with its severity and the alerts inside it.
- A ranked list of accounts with a 0 to 100 score for the worst seven-day window, and the alert ids behind each score.
- A browsable report. Each alert shows the rule that fired, Jev's answers and, in a labeled badge, whether the answer key agrees.
- A rules-only baseline for every stage, scored on the same alerts, so you can see what Jev adds.

## See the result without an API key

The saved Jev answers are in the repo, so you can rebuild every result with no key and no network calls. From the repo root:

```
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
experiments/security-alert-triage/replay.sh
```

Then open `experiments/security-alert-triage/data/reports/triage_report.html`.

## Run it yourself

Create a key at [console.typesafe.ai](https://console.typesafe.ai/) and put it in a `.env` file in the repo root:

```
TYPESAFE_API_KEY=your-key
```

Then run `experiments/security-alert-triage/run_all.sh`. It builds the dataset from scratch and sends Jev about 2,400 requests: one per alert and one per ambiguous pair of alerts. The repo keeps only the seed 101 data. Seeds 202 and 303 were each run once after the freeze, and their results are in the table below. To reproduce one, run `SEED=<n> TRIAGE_DATA=data_holdout_<n> experiments/security-alert-triage/run_all.sh`. It needs a key and spends about 2,400 real requests.

## How it works

1. Generate about 1,050 alerts for 200 employees, with 21 real incidents among them, plus an answer key.
2. Apply the fixed rules. A never-suppress list (privilege escalation, data leaving to an unknown destination, command and control) never closes an alert. An allowlist closes known-harmless alerts with a reason.
3. Ask Jev about each alert. Four questions come back as probabilities and a score. Code escalates, investigates or closes, and closes only when several conditions hold at once.
4. Group alerts into incidents. Alerts that share a user, host or address within 72 hours form candidate pairs. Code settles the obvious links (same user and host within 30 minutes). Jev judges the rest.
5. Score accounts in code from Jev's probabilities and impact, then rank them.

Jev is used in two places, and nowhere else:

- Once per alert: is it a real threat, how bad would it be, which attack stage is it, and does an ordinary explanation fit.
- Once per ambiguous pair of alerts: are they part of the same attack, and is the shared user, host or address a coincidence.

The exact questions, what goes in, what code does with each answer, why a model is needed, and what Jev never decides are in [DESIGN.md](DESIGN.md#where-jev-is-used-and-why).

## Results

Seed 101 is the tuning seed: the thresholds were chosen while looking at it. Seeds 202 and 303 were generated after the rules were frozen and each ran once. They are the clean checks.

| | Seed 101 baseline | Seed 101 Jev | Seed 202 baseline | Seed 202 Jev | Seed 303 baseline | Seed 303 Jev |
|---|---|---|---|---|---|---|
| Missed real alerts (of 84) | 30 | 0 | 30 | 0 | 30 | 0 |
| Real incidents with no surfaced alert (of 21) | 6 | 0 | 6 | 0 | 6 | 0 |
| Alerts that reach a person (of 1,042) | 495 | 656 | 502 | 674 | 484 | 647 |
| Grouping precision / recall | 4% / 100% | 77% / 96% | 5% / 100% | 67% / 96% | 3% / 100% | 82% / 96% |
| Groups with more than one real incident | 1 | 0 | 2 | 1 | 1 | 0 |
| Compromised accounts in top 10 / top 20 (of 21) | 6 / 10 | 10 / 19 | 4 / 8 | 10 / 19 | 3 / 8 | 10 / 17 |

On both fresh seeds Jev closed no real alert and every real incident got an escalated alert. The price is a bigger queue. On seed 202, 674 alerts reach a person against 502 for the rules. On seed 303 it is 647 against 484. Grouping precision was 67% on seed 202 and 82% on seed 303, against 77% on seed 101. The baseline is far lower at 3% to 5%. On seed 303 Jev places 17 of 21 compromised accounts in the top 20, where it placed 19 on the other two.

Jev's attack-stage answer matched the true stage on 60 of 84 real alerts, and the detector's own claim matched on 78. The data generator sets the claimed tactic. It copies the true tactic for every real alert except the low-severity ones and one blank per `slow_burn` copy. So 78 is a stated baseline, not a measured detector. Seed 101 took 2,412 requests, seed 202 took 2,486 and seed 303 took 2,444, with no errors. [DESIGN.md](DESIGN.md#results) has the full tables and every scenario where Jev did worse than the baseline.

## What the tests found

- The rules-only baseline closes every `slow_burn` alert and every `low_severity_real` alert, because each looks ignorable alone. That is where Jev's gain is largest.
- Jev's first link threshold (1.6) merged one user's travel alerts with that user's phishing alerts. The threshold moved to 1.8 on seed 101. Seed 202 still shows one group that holds two real incidents, which is worth a look. Seed 303 shows none. Jev also joins `benign_pentest` incidents to each other, which are benign.
- Jev over-calls real attacks on noise: many false positives in the background score as likely true. That is why the queue stays large.
- Five odd inputs each have a test. They are an alert with no entities, a failed Jev call, and alerts exactly at the 72-hour and 30-minute limits. The other two are one user with hundreds of findings and an empty `alerts.csv`. A failed Jev call becomes "investigate", never "close".

## Limits

- The author wrote both the scenarios and the rules, so the results flatter the design. A real alert stream has cases nobody thought of.
- The set is small: 21 real incidents per seed, three of each scenario kind. One missed incident would change the headline.
- Thresholds were tuned on seed 101. Seeds 202 and 303 check them, once each.
- The account ranking is an input for a human and never a verdict. It is about people, and a high score means "look here first", not "this person is compromised".

The full write-up is in [DESIGN.md](DESIGN.md).
