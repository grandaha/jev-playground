#!/bin/sh
# Rebuilds every result in data/ from the saved Jev answers. Needs no API key and makes no network calls.
# Run from the repo root. (run_all.sh is the version that asks Jev again.)
set -e
P=.venv/bin/python; D=experiments/customer-matching/scripts
$P $D/normalize.py >/dev/null; $P $D/block.py >/dev/null
$P $D/match.py decide accounts; $P $D/cluster.py accounts; $P $D/master.py accounts
$P $D/normalize.py >/dev/null; $P $D/block.py >/dev/null
$P $D/match.py decide contacts; $P $D/cluster.py contacts; $P $D/master.py contacts
$P $D/golden.py accounts; $P $D/golden.py contacts
$P $D/evaluate.py; $P $D/report.py >/dev/null; $P $D/golden_report.py >/dev/null
