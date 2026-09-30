#!/bin/sh
# Builds the dataset in data/ from scratch. Run from the repo root. About 2,400 Jev requests: one per alert
# (1,036) plus one per candidate pair the obvious-link rule does not settle (about 1,400).
# Another dataset: SEED=202 TRIAGE_DATA=data_holdout experiments/security-alert-triage/run_all.sh
set -e
P=.venv/bin/python; D=experiments/security-alert-triage/scripts
$P $D/generate.py
$P $D/rules.py
$P $D/ask.py alerts
$P $D/decide.py
$P $D/group.py baseline
$P $D/ask.py links
$P $D/group.py jev
$P $D/risk.py
$P $D/evaluate.py
$P $D/report.py
