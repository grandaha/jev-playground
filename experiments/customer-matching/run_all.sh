#!/bin/sh
# Full pipeline from the repo root. Makes about 2,000 Jev calls.
set -e
P=.venv/bin/python; D=experiments/customer-matching
$P $D/generate.py; rm -f $D/data/groups_accounts.csv
$P $D/normalize.py >/dev/null; $P $D/block.py
$P $D/match.py ask accounts; $P $D/match.py decide accounts; $P $D/cluster.py accounts
$P $D/normalize.py >/dev/null; $P $D/block.py   # contacts now key on merged accounts
$P $D/match.py ask contacts; $P $D/match.py decide contacts; $P $D/cluster.py contacts
$P $D/master.py accounts; $P $D/master.py contacts
$P $D/sweep.py                                   # to re-tune thresholds: edit MERGE_POINTS/REJECT_POINTS in match.py, then decide again
$P $D/evaluate.py; $P $D/report.py
