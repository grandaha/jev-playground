"""Blocking: turn shared match keys into candidate pairs, and report recall vs the answer key.

Run from repo root: .venv/bin/python experiments/customer-matching/block.py
Writes data/candidates_accounts.csv and data/candidates_contacts.csv
(columns: id_a, id_b, block_keys = the k_* keys the two records share).
"""
import os
import csv
from collections import defaultdict
from itertools import combinations
from pathlib import Path

DATA = Path(__file__).parent / os.environ.get("MATCH_DATA", "data")  # MATCH_DATA=data_seed2 runs on another folder
MAX_BLOCK = 50  # ponytail: oversized blocks are skipped (too generic to mean anything); raise or sub-block if recall needs it


def candidates(rows, id_col):
    pairs = defaultdict(list)
    for k in [c for c in rows[0] if c.startswith("k_")]:
        blocks = defaultdict(list)
        for r in rows:
            if r[k]:
                blocks[r[k]].append(r[id_col])
        for ids in blocks.values():
            if len(ids) <= MAX_BLOCK:
                for a, b in combinations(sorted(ids), 2):
                    pairs[(a, b)].append(k)
    return pairs


def report(name, pairs, truth):
    by_true = defaultdict(list)
    for rid, tid in truth.items():
        by_true[tid].append(rid)
    true_pairs = {p for ids in by_true.values() for p in combinations(sorted(ids), 2)}
    hit = true_pairs & pairs.keys()
    n = len(truth)
    print(f"{name}: {len(pairs)} candidates of {n * (n - 1) // 2} possible; "
          f"true dup pairs {len(true_pairs)}, found {len(hit)} ({len(hit) / len(true_pairs):.1%}); "
          f"non-duplicate candidates {len(pairs) - len(hit)}")
    missed = true_pairs - pairs.keys()
    if missed:
        print(f"  missed e.g. {sorted(missed)[:3]}")


if __name__ == "__main__":
    key = list(csv.DictReader(open(DATA / "answer_key.csv")))
    for table, id_col in (("accounts", "account_id"), ("contacts", "contact_id")):
        rows = list(csv.DictReader(open(DATA / f"{table}_norm.csv")))
        pairs = candidates(rows, id_col)
        with open(DATA / f"candidates_{table}.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["id_a", "id_b", "block_keys"])
            for (a, b), ks in sorted(pairs.items()):
                w.writerow([a, b, "+".join(ks)])
        report(table, pairs, {k["record_id"]: k["true_id"] for k in key if k["table"] == table})
