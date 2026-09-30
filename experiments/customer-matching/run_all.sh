#!/bin/sh
# Full pipeline from the repo root. Makes Jev calls (about 2,500).
set -e
P=.venv/bin/python; D=experiments/customer-matching
$P $D/generate.py; rm -f $D/data/groups_accounts.csv
$P $D/normalize.py >/dev/null; $P $D/block.py
$P $D/match.py accounts; $P $D/cluster.py accounts
$P $D/normalize.py >/dev/null; $P $D/block.py   # contacts now key on merged accounts
$P $D/match.py contacts; $P $D/cluster.py contacts
$P $D/master.py accounts; $P $D/master.py contacts
$P $D/evaluate.py; $P $D/report.py
