#!/bin/sh
# Full pipeline from the repo root. Makes about 2,000 Jev calls.
set -e
P=.venv/bin/python; D=experiments/customer-matching
$P $D/generate.py
$P $D/normalize.py >/dev/null; $P $D/block.py
# step 1: accounts -> groups -> master account for each group
$P $D/match.py ask accounts; $P $D/match.py decide accounts; $P $D/cluster.py accounts; $P $D/master.py accounts
# step 2: every contact gets its master account id (a match key), then contacts are matched
$P $D/normalize.py >/dev/null; $P $D/block.py
$P $D/match.py ask contacts; $P $D/match.py decide contacts; $P $D/cluster.py contacts; $P $D/master.py contacts
$P $D/golden.py accounts; $P $D/golden.py contacts   # golden records + separate email and phone tables
$P $D/sweep.py                                   # to re-tune thresholds: edit MERGE_POINTS/REJECT_POINTS in match.py, then decide again
$P $D/evaluate.py; $P $D/report.py
