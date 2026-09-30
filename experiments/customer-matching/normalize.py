"""Normalize accounts and contacts and build match keys (code only, no Jev).

Run from repo root: .venv/bin/python experiments/customer-matching/normalize.py
Reads data/accounts.csv, data/contacts.csv; writes data/accounts_norm.csv, data/contacts_norm.csv.
Contacts also get master_account_id (from the account cluster + master steps), which feeds k_name_acct.
Each k_* column is a match key. Records sharing a non-empty k_* value become candidates in block.py.
"""
import os
import csv
import re
from pathlib import Path

from generate import NICKS  # nickname table (nickname -> canonical name, inverted below)

DATA = Path(__file__).parent / os.environ.get("MATCH_DATA", "data")  # MATCH_DATA=data_seed2 runs on another folder
CANON = {n.lower(): full.lower() for full, ns in NICKS.items() for n in ns}
COMPANY_NOISE = {"inc", "incorporated", "llc", "co", "corp", "corporation", "ltd", "group", "company"}
STREET = {"street": "st", "avenue": "ave", "road": "rd", "boulevard": "blvd", "drive": "dr"}
ROLE_MAILBOXES = {"info", "sales", "office", "admin", "support", "contact", "billing", "hello", "accounts", "team"}
PERSONAL_DOMAINS = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com"}


def master_accounts():
    """record -> master account id, once accounts are clustered (cluster.py) and mastered (master.py accounts).
    A record in a group of one is its own master. Empty before those steps: raw account ids are used."""
    g = DATA / "groups_accounts.csv"
    if not g.exists():
        return {}
    groups = list(csv.DictReader(open(g)))
    m = DATA / "masters_accounts.csv"
    master = {r["group_id"]: r["master_id"] for r in csv.DictReader(open(m))} if m.exists() else {}
    first = {}
    for r in sorted(groups, key=lambda r: r["record_id"]):
        first.setdefault(r["group_id"], r["record_id"])
    return {r["record_id"]: master.get(r["group_id"], first[r["group_id"]]) for r in groups}


MASTER = master_accounts()


def words(s):
    return re.sub(r"[^a-z0-9 ]", " ", s.lower().replace("&", " and ")).split()


def soundex(w):
    w = re.sub(r"[^a-z]", "", w.lower())
    if not w:
        return ""
    codes = {c: d for d, cs in {"1": "bfpv", "2": "cgjkqsxz", "3": "dt", "4": "l", "5": "mn", "6": "r"}.items() for c in cs}
    out, last = w[0].upper(), codes.get(w[0], "")
    for c in w[1:]:
        d = codes.get(c, "")
        if d and d != last:
            out += d
        if c not in "hw":
            last = d
    return (out + "000")[:4]


def phone(s):
    d = re.sub(r"\D", "", s)
    d = d[1:] if len(d) == 11 and d[0] == "1" else d
    return f"+1{d}" if len(d) == 10 else ""


def address(s):
    return " ".join(STREET.get(w, w) for w in words(s))


def company(s):
    return "".join(w for w in words(s) if w not in COMPANY_NOISE)


def domain(url_or_email):
    d = url_or_email.lower().split("@")[-1].removeprefix("www.")
    return "" if d in PERSONAL_DOMAINS else d


def street_key(addr, zip_):
    """House number + first street word + zip3: survives St/Street, case and zip typos."""
    w = address(addr).split()
    return f"{w[0]}|{w[1]}|{zip_[:3]}" if len(w) > 1 and zip_ else ""


def norm_account(r):
    name = company(r["name"])
    return {**r, "name_norm": name, "phone_norm": phone(r["phone"]), "address_norm": address(r["address"]),
            "k_domain": domain(r["website"]), "k_phone": phone(r["phone"]), "k_name": name,
            "k_name_sound": "".join(soundex(w) for w in words(r["name"]) if w not in COMPANY_NOISE),
            "k_street": street_key(r["address"], r["zip"])}


def norm_contact(r):
    f, l = words(r["first_name"])[0:1], words(r["last_name"])[0:1]
    f, l = (f[0] if f else ""), (l[0] if l else "")
    f = CANON.get(f, f)
    ini = f[:1]
    dom = domain(r["email"])
    master = MASTER.get(r["account_id"], r["account_id"])  # the mastered account this contact belongs to
    names = "".join(sorted([f[:1] + soundex(l), l[:1] + soundex(f)]))  # first/last swap-proof
    return {**r, "first_norm": f, "last_norm": l, "email_norm": r["email"].lower().strip(),
            "phone_norm": phone(r["phone"]), "address_norm": address(r["address"]),
            "k_email": "" if r["email"].split("@")[0].lower() in ROLE_MAILBOXES else r["email"].lower().strip(),  # a shared mailbox is not an identifier
            "k_phone": phone(r["phone"]),
            "k_name_domain": f"{ini}{soundex(l)}|{dom}" if dom and ini and l else "",
            "k_name_street": f"{ini}{soundex(l)}|{street_key(r['address'], r['zip'])}" if ini and l and r["address"] else "",
            "k_name_swap": f"{names}|{dom}" if dom and ini and l else "",
            "master_account_id": master,
            "k_name_acct": f"{names}|{master}" if master and ini and l else "",
            "k_initial_acct": f"{ini}{soundex(l)}|{master}" if master and ini and l else ""}  # catches "R. Smith" vs "Robert Smith"


def run(src, dst, fn):
    rows = [fn(r) for r in csv.DictReader(open(DATA / src))]
    with open(DATA / dst, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return rows


if __name__ == "__main__":
    a = run("accounts.csv", "accounts_norm.csv", norm_account)
    c = run("contacts.csv", "contacts_norm.csv", norm_contact)
    for name, rows in (("accounts", a), ("contacts", c)):
        ks = [k for k in rows[0] if k.startswith("k_")]
        print(name, len(rows), {k: sum(1 for r in rows if r[k]) for k in ks})
