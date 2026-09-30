#!/bin/sh
# Rebuilds every result from the saved Jev answers. Needs no API key and makes no network calls.
# Run from the repo root. (run_all.sh is the version that asks Jev again.)
set -e
P=.venv/bin/python; D=experiments/security-alert-triage/scripts
$P $D/rules.py
$P $D/decide.py
$P $D/group.py baseline
$P $D/group.py jev
$P $D/risk.py
$P $D/evaluate.py
$P $D/report.py
