"""Sweep the `signals` policy thresholds over saved Jev answers (no new calls).

Run from repo root: .venv/bin/python experiments/customer-matching/sweep.py
For each table: merge threshold vs precision/recall, and reject threshold vs review-queue size.
Recall is measured on provable pairs (true duplicates that share evidence beyond the name).
"""
import csv
from collections import defaultdict
from itertools import combinations

from evaluate import corroborated
from match import decide_one

from paths import path
MERGES = [3, 3.5, 4, 4.5, 5, 5.5, 6, 6.5, 7]
REJECTS = [-1, 0, 0.5, 1, 1.5, 2, 3]


def main():
    key = list(csv.DictReader(open(path("answer_key.csv"))))
    for table in ("accounts", "contacts"):
        idc = f"{table[:-1]}_id"
        norm = {r[idc]: r for r in csv.DictReader(open(path(f"{table}_norm.csv")))}
        answers = list(csv.DictReader(open(path(f"answers_{table}.csv"))))
        by_true = defaultdict(list)
        for k in key:
            if k["table"] == table:
                by_true[k["true_id"]].append(k["record_id"])
        truth = {p for ids in by_true.values() for p in combinations(sorted(ids), 2)}
        provable = {p for p in truth if corroborated(table, norm[p[0]], norm[p[1]])}

        def run(m, r):
            out = defaultdict(set)
            for ans in answers:
                a, b = ans["id_a"], ans["id_b"]
                d = decide_one(table, "signals", norm[a], norm[b], ans, m, r)[0]
                out[d].add((a, b))
            return out

        print(f"\n=== {table}: {len(provable)} provable duplicate pairs ===")
        print("merge threshold (reject fixed at 1.0): merges, false merges, precision, recall, review queue")
        for m in MERGES:
            o = run(m, 1.0)
            tp, fp = len(o["merge"] & truth), len(o["merge"] - truth)
            print(f"  merge >= {m:<4} {len(o['merge']):>4} merges  {fp:>3} false  precision {tp / max(tp + fp, 1):6.1%}  "
                  f"recall {len(o['merge'] & provable) / len(provable):6.1%}  review {len(o['review']):>3}")
        print("reject threshold (merge fixed at 5.0): review queue, true duplicates in it, true duplicates rejected outright")
        for r in REJECTS:
            o = run(5.0, r)
            print(f"  reject <= {r:<4} review {len(o['review']):>3} ({len(o['review'] & truth):>2} true dups)  "
                  f"rejected {len(o['no_match']):>3} ({len(o['no_match'] & provable):>2} provable dups lost)")


if __name__ == "__main__":
    main()
