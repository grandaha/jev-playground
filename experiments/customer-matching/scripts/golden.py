"""Golden records: one row per final entity, built from every record in its group. No Jev calls.

Run from repo root: .venv/bin/python experiments/customer-matching/golden.py accounts|contacts
A golden record is keyed by its master's own record id (golden_id = master_id), so every id in the output is a real source id.
Writes, in data/:
  golden_<table>.csv         one row per entity (groups of one included): the master's value for each field,
                             with blanks filled from the next-best record; `filled_from` says which fields came from where
  golden_<table[:-1]>_phones.csv, golden_contact_emails.csv
                             one row per distinct phone / email, with every source system and record that had it,
                             and is_primary (the value from the best record) so nothing is thrown away
"Best" is the same order the master uses: most trusted source system, then newest update, then lowest id.
The address is filled as a block (street, city, state, zip from one record) so pieces of two addresses are never mixed.
"""
import csv
import sys
from collections import defaultdict

from master import SOURCE_RANK

from paths import path
FIELDS = {"accounts": ["name", "website", "industry"], "contacts": ["first_name", "last_name", "title"]}
ADDRESS = ["address", "city", "state", "zip"]


def read(name):
    return list(csv.DictReader(open(path(name))))


def write(path, rows, columns):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)


def multi_values(gid, order, norm, raw_col, norm_col):
    """One row per distinct value across the group, primary = the value from the best record that has one."""
    seen = {}
    for i in order:
        v = norm[i][norm_col]
        if not v:
            continue
        s = seen.setdefault(v, {"golden_id": gid, "value": v, "example_as_entered": norm[i][raw_col], "is_primary": not seen,
                                "source_systems": [], "record_ids": [], "latest_update": ""})
        s["source_systems"].append(norm[i]["source_system"])
        s["record_ids"].append(i)
        s["latest_update"] = max(s["latest_update"], norm[i]["updated_at"])
    return [{**s, "source_systems": ";".join(dict.fromkeys(s["source_systems"])), "record_ids": " ".join(s["record_ids"])}
            for s in seen.values()]


def main(table):
    idc = f"{table[:-1]}_id"
    norm = {r[idc]: r for r in read(f"{table}_norm.csv")}
    groups = defaultdict(list)
    for r in read(f"groups_{table}.csv"):
        groups[r["group_id"]].append(r["record_id"])
    rank = lambda i: SOURCE_RANK.index(norm[i]["source_system"]) if norm[i]["source_system"] in SOURCE_RANK else len(SOURCE_RANK)

    golden, phones, emails = [], [], []
    for gid, ids in sorted(groups.items()):
        order = sorted(ids, key=lambda i: (rank(i), -int(norm[i]["updated_at"].replace("-", "")), i))
        master, filled = order[0], []
        # the golden record is keyed by its master's own record id, not a new number
        row = {"golden_id": master, "group_id": gid, "master_id": master, "member_ids": " ".join(order), "member_count": len(ids)}
        for f in FIELDS[table]:
            src = next((i for i in order if norm[i][f]), None)
            row[f] = norm[src][f] if src else ""
            if src and src != master:
                filled.append(f"{f}<-{src}")
        src = next((i for i in order if norm[i]["address"]), None)  # address is one block
        for f in ADDRESS:
            row[f] = norm[src][f] if src else ""
        if src and src != master:
            filled.append(f"address<-{src}")
        if table == "contacts":
            src = next((i for i in order if norm[i]["account_id"]), None)
            row["golden_account_id"] = norm[src]["master_account_id"] if src else ""  # the master account record's own id
            if src and src != master:
                filled.append(f"account<-{src}")
            ev = multi_values(master, order, norm, "email", "email_norm")
            emails += ev
            row["primary_email"] = next((e["value"] for e in ev if e["is_primary"]), "")
            if ev and ev[0]["record_ids"].split()[0] != master:
                filled.append(f"email<-{ev[0]['record_ids'].split()[0]}")
        pv = multi_values(master, order, norm, "phone", "phone_norm")
        phones += pv
        row["primary_phone"] = next((p["value"] for p in pv if p["is_primary"]), "")
        if pv and pv[0]["record_ids"].split()[0] != master:
            filled.append(f"phone<-{pv[0]['record_ids'].split()[0]}")
        row["filled_from"] = "; ".join(filled)
        golden.append(row)

    cols = list(golden[0])
    write(path(f"golden_{table}.csv"), golden, cols)
    mcols = ["golden_id", "value", "example_as_entered", "is_primary", "source_systems", "record_ids", "latest_update"]
    write(path(f"golden_{table[:-1]}_phones.csv"), phones, mcols)
    n_filled = sum(1 for g in golden if g["filled_from"])
    multi_phone = len({p["golden_id"] for p in phones if not p["is_primary"]})
    out = f"{table}: {len(golden)} golden records from {len(norm)} records; {n_filled} had fields filled from another record; {multi_phone} keep more than one phone"
    if table == "contacts":
        write(path("golden_contact_emails.csv"), emails, mcols)
        out += f"; {len({e['golden_id'] for e in emails if not e['is_primary']})} keep more than one email"
    print(out)


if __name__ == "__main__":
    main(sys.argv[1])
