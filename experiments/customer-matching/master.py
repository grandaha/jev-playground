"""Pick a master record per multi-record group: Jev scores each record, code applies weights.

Run from repo root: .venv/bin/python experiments/customer-matching/master.py accounts|contacts
Writes data/masters_<table>.csv (one row per group) and data/master_scores_<table>.csv
(one row per record: raw Jev answers, recency, final score). Re-weighting needs no new Jev calls:
edit WEIGHTS and run with --reuse.
"""
import os
import argparse
import csv
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv
from typesafe_sdk import Noul, Score, TypeSafeClient

from match import PUBLIC, view

DATA = Path(__file__).parent / os.environ.get("MATCH_DATA", "data")  # MATCH_DATA=data_seed2 runs on another folder
load_dotenv(DATA.parents[2] / ".env")

WEIGHTS = {"completeness": 0.4, "clean_format": 0.3, "recency": 0.3}
QUESTIONS = {
    "completeness": Score(
        instructions="How complete is this record as the master copy of this customer?",
        criteria=["Most useful fields are blank; only a name and little else.",
                  "A few useful fields are filled in, but several contact or address fields are blank.",
                  "Most useful fields are filled in, with one or two blank.",
                  "Every useful field is filled in: name, phone, email or website, and a full address."]),
    "clean_format": Noul(instructions="Is the name spelled correctly and written out in full, with no typos, nicknames, initials or all-caps?"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("table", choices=["accounts", "contacts"])
    ap.add_argument("--reuse", action="store_true", help="re-weight saved Jev answers without new calls")
    args = ap.parse_args()
    table = args.table
    idc = f"{table[:-1]}_id"
    scores_file = DATA / f"master_scores_{table}.csv"
    groups = defaultdict(list)
    for r in csv.DictReader(open(DATA / f"groups_{table}.csv")):
        groups[r["group_id"]].append(r["record_id"])
    norm = {r[idc]: r for r in csv.DictReader(open(DATA / f"{table}_norm.csv"))}
    accounts = {r["account_id"]: r for r in csv.DictReader(open(DATA / "accounts_norm.csv"))}
    multi = {g: ids for g, ids in groups.items() if len(ids) > 1}

    if args.reuse:
        raw = {r["record_id"]: r for r in csv.DictReader(open(scores_file))}
    else:
        client = TypeSafeClient()

        def ask(rid):
            for attempt in range(4):  # the API occasionally returns a transient 5xx even after SDK retries
                try:
                    resp = client.system_one(state={"record": view(table, norm[rid], accounts)}, questions=QUESTIONS)
                    break
                except Exception:
                    if attempt == 3:
                        raise
                    time.sleep(2 ** attempt)
            return rid, {"completeness": resp.answers["completeness"].score / 3, "clean_format": resp.answers["clean_format"].noul}

        todo = [i for ids in multi.values() for i in ids]
        with ThreadPoolExecutor(8) as ex:
            raw = {rid: a for rid, a in ex.map(ask, todo)}

    rows, masters = [], []
    for g, ids in multi.items():
        order = sorted(ids, key=lambda i: norm[i]["updated_at"])
        for i in ids:
            a = raw[i]
            rec = order.index(i) / max(len(ids) - 1, 1)  # 0 oldest .. 1 newest within the group
            final = (WEIGHTS["completeness"] * float(a["completeness"]) + WEIGHTS["clean_format"] * float(a["clean_format"])
                     + WEIGHTS["recency"] * rec)
            rows.append({"group_id": g, "record_id": i, "completeness": round(float(a["completeness"]), 3),
                         "clean_format": round(float(a["clean_format"]), 3), "recency": round(rec, 3), "final": round(final, 3)})
        best = max((r for r in rows if r["group_id"] == g), key=lambda r: r["final"])
        masters.append({"group_id": g, "master_id": best["record_id"], "members": " ".join(ids)})
    for path, data in ((scores_file, rows), (DATA / f"masters_{table}.csv", masters)):
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0]))
            w.writeheader()
            w.writerows(data)
    print(f"{table}: {len(masters)} multi-record groups, {len(rows)} records scored{' (reused answers)' if args.reuse else ''}")


if __name__ == "__main__":
    main()
