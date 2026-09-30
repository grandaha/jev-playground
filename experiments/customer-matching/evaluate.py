"""Score the pipeline against the hidden answer key and compare with a fuzzy-name baseline.

Run from repo root: .venv/bin/python experiments/customer-matching/evaluate.py
Reads the decisions/groups/masters files written by the earlier stages. No Jev calls.
"""
import csv
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path

DATA = Path(__file__).parent / "data"
BASELINE_NAME_SIM = 0.88  # fuzzy-name baseline: merge any candidate pair whose names are at least this similar


# Identifiers beyond the name. A true duplicate pair sharing none of these can't be proven from the records.
EVIDENCE = {"accounts": ["k_domain", "k_phone", "k_street"], "contacts": ["k_email", "k_phone", "k_name_street", "k_name_acct"]}


def corroborated(table, a, b):
    return any(a[k] and a[k] == b[k] for k in EVIDENCE[table])


def read(name):
    return list(csv.DictReader(open(DATA / name)))


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0
    r = tp / (tp + fn) if tp + fn else 0
    return f"precision {p:.1%}  recall {r:.1%}  (tp {tp}, fp {fp}, fn {fn})"


def main():
    key = read("answer_key.csv")
    for table in ("accounts", "contacts"):
        truth = {k["record_id"]: k["true_id"] for k in key if k["table"] == table}
        kind = {k["record_id"]: k["kind"] for k in key if k["table"] == table}
        by_true = defaultdict(list)
        for rid, t in truth.items():
            by_true[t].append(rid)
        true_pairs = {p for ids in by_true.values() for p in combinations(sorted(ids), 2)}
        norm = {r[f"{table[:-1]}_id"]: r for r in read(f"{table}_norm.csv")}
        dec = read(f"decisions_{table}.csv")
        print(f"\n=== {table} ({len(truth)} records, {len(by_true)} true entities, {len(true_pairs)} true duplicate pairs) ===")

        merged = {(d["id_a"], d["id_b"]) for d in dec if d["decision"] == "merge"}
        provable = {p for p in true_pairs if corroborated(table, norm[p[0]], norm[p[1]])}
        print(f"True duplicate pairs with shared evidence (phone, email, website or address): {len(provable)} of {len(true_pairs)}; "
              f"the other {len(true_pairs) - len(provable)} share only a name, so no method could prove them.")
        print("Pipeline on provable pairs only:", prf(len(merged & provable), len(merged - true_pairs), len(provable - merged)))
        print("Pipeline (hard rules + Jev):   ", prf(len(merged & true_pairs), len(merged - true_pairs), len(true_pairs - merged)))
        review = [d for d in dec if d["decision"] == "review"]
        rdup = sum(1 for d in review if (d["id_a"], d["id_b"]) in true_pairs)
        print(f"Review queue: {len(review)} pairs ({rdup} true duplicates, {len(review) - rdup} not). If reviewers decide them correctly: "
              + prf(len(merged & true_pairs) + rdup, len(merged - true_pairs), len(true_pairs - merged) - rdup))

        def name(r):
            return r["name_norm"] if table == "accounts" else f"{r['first_norm']} {r['last_norm']}"
        base = {(d["id_a"], d["id_b"]) for d in dec
                if SequenceMatcher(None, name(norm[d["id_a"]]), name(norm[d["id_b"]])).ratio() >= BASELINE_NAME_SIM}
        print(f"Baseline (name similarity >= {BASELINE_NAME_SIM}, same candidates):", prf(len(base & true_pairs), len(base - true_pairs), len(true_pairs - base)))

        print("Merge precision by rule:")
        by_rule = defaultdict(lambda: [0, 0])
        for d in dec:
            if d["decision"] == "merge":
                by_rule[d["rule"]][(d["id_a"], d["id_b"]) in true_pairs] += 1
        for rule, (bad, good) in sorted(by_rule.items()):
            print(f"  {rule}: {good + bad} merges, {good / (good + bad):.1%} correct")
        fm = Counter()
        for d in dec:
            if d["decision"] == "merge" and (d["id_a"], d["id_b"]) not in true_pairs:
                fm[f"{kind[d['id_a']]}/{kind[d['id_b']]}"] += 1
        if fm:
            print("  false merges by record kind:", dict(fm))

        groups = defaultdict(list)
        for g in read(f"groups_{table}.csv"):
            groups[g["group_id"]].append(g["record_id"])
        impure = sum(1 for ids in groups.values() if len({truth[i] for i in ids}) > 1)
        gid = {i: g for g, ids in groups.items() for i in ids}
        split = sum(1 for ids in by_true.values() if len({gid[i] for i in ids}) > 1)
        print(f"Groups: {len(groups)} (truth {len(by_true)}); {impure} contain more than one true entity; {split} true entities split across groups")

        m = read(f"masters_{table}.csv")
        with_clean = [r for r in m if any(kind[i] == "clean" for i in r["members"].split())]
        ok = sum(1 for r in with_clean if kind[r["master_id"]] == "clean")
        print(f"Master = the original clean record: {ok}/{len(with_clean)} groups (a proxy: a variant can be a fine master)")


if __name__ == "__main__":
    main()
