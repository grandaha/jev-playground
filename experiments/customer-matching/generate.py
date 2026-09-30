"""Generate messy synthetic accounts + contacts with hidden ground truth.

Run from repo root: .venv/bin/python experiments/customer-matching/generate.py
Writes data/accounts.csv, data/contacts.csv, data/answer_key.csv.
"""
import csv
import random
import re
from datetime import date, timedelta
from pathlib import Path

SEED = 7
N_ACCOUNTS, N_TRUE_ACCOUNTS, N_ACCOUNT_DECOYS = 1000, 800, 40
N_CONTACTS, N_TRUE_CONTACTS, N_CONTACT_DECOYS = 3000, 2400, 90
OUT = Path(__file__).parent / "data"
rng = random.Random(SEED)

NICKS = {"Robert": ["Bob", "Rob"], "William": ["Bill", "Will"], "Elizabeth": ["Liz", "Beth"],
         "James": ["Jim", "Jimmy"], "Michael": ["Mike"], "Katherine": ["Kate", "Katie"],
         "Richard": ["Rick", "Dick"], "Jennifer": ["Jen", "Jenny"], "Christopher": ["Chris"],
         "Margaret": ["Peggy", "Maggie"], "Thomas": ["Tom"], "Patricia": ["Pat", "Trish"],
         "Joseph": ["Joe"], "Susan": ["Sue"], "Daniel": ["Dan", "Danny"], "Deborah": ["Deb"]}
FIRST = list(NICKS) + ["Maria", "David", "Sarah", "Anthony", "Linda", "Kevin", "Priya", "Wei", "Carlos",
                       "Aisha", "Omar", "Hannah", "Luis", "Yuki", "Grace", "Nathan", "Olivia", "Marcus"]
LAST = ["Smith", "Johnson", "Williams", "Brown", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
        "Nguyen", "Patel", "Kim", "Lopez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson",
        "Martin", "Lee", "Thompson", "White", "Harris", "Clark", "Lewis", "Walker", "Hall", "Young", "Allen"]
STEMS = ["Harbor Point", "Summit", "Blue Ridge", "Cedar", "Ironwood", "Bright Path", "Northgate", "Redwood",
         "Silver Creek", "Atlas", "Pioneer", "Lakeside", "Granite", "Evergreen", "Keystone", "Meridian",
         "Copper Hill", "Falcon", "Maple Leaf", "Stonebridge", "Riverbend", "Oakmont", "Sterling", "Beacon"]
TRADES = ["Plumbing", "Dental", "Logistics", "Consulting", "Roofing", "Analytics", "Bakery", "Insurance",
          "Electric", "Landscaping", "Legal Services", "Software", "Staffing", "Auto Repair", "Design"]
SUFFIXES = ["Inc", "LLC", "Co", "Corp", "Ltd", ""]
STREETS = ["Main", "Oak", "Maple", "Cedar", "Elm", "Washington", "Lake", "Hill", "Park", "Sunset", "Church"]
KINDS = {"Street": "St", "Avenue": "Ave", "Road": "Rd", "Boulevard": "Blvd", "Drive": "Dr"}
CITIES = [("Austin", "TX", "787"), ("Denver", "CO", "802"), ("Seattle", "WA", "981"), ("Boston", "MA", "021"),
          ("Atlanta", "GA", "303"), ("Chicago", "IL", "606"), ("Portland", "OR", "972"),
          ("Phoenix", "AZ", "850"), ("Columbus", "OH", "432"), ("Nashville", "TN", "372")]
TITLES = ["Owner", "CFO", "Office Manager", "Director of Operations", "Purchasing Agent", "VP Sales", "Engineer"]
SOURCES = ["crm", "billing", "web_form", "trade_show", "erp"]


def typo(s):
    if len(s) < 4:
        return s
    i = rng.randrange(1, len(s) - 1)
    return rng.choice([s[:i] + s[i + 1] + s[i] + s[i + 2:], s[:i] + s[i + 1:], s[:i] + s[i] + s[i:]])


def fmt_phone(d):
    a, b, c = d[:3], d[3:6], d[6:]
    return rng.choice([f"({a}) {b}-{c}", f"{a}-{b}-{c}", f"{a}.{b}.{c}", f"+1 {a} {b} {c}", d])


def slug(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def when():
    return (date(2022, 1, 1) + timedelta(days=rng.randrange(1700))).isoformat()


def new_address():
    city, st, z3 = rng.choice(CITIES)
    kind = rng.choice(list(KINDS))
    return {"address": f"{rng.randrange(10, 9900)} {rng.choice(STREETS)} {kind}", "city": city,
            "state": st, "zip": z3 + f"{rng.randrange(100):02d}"}


def mess_address(r):
    r = dict(r)
    if rng.random() < 0.6:
        for long, short in KINDS.items():
            r["address"] = r["address"].replace(long, short)
    if rng.random() < 0.15:
        r["address"] = typo(r["address"])
    if rng.random() < 0.15:
        r["address"] = r["address"].upper()
    if rng.random() < 0.15:
        r["zip"] = r["zip"][:3] + f"{rng.randrange(100):02d}"  # wrong last digits
    if rng.random() < 0.1:
        r.update(new_address())  # moved: old address on record
    return r


# ---- accounts ----
def new_account(i):
    stem, trade = rng.choice(STEMS), rng.choice(TRADES)
    name = f"{stem} {trade}"
    a = {"true_id": f"TA{i:04d}", "name": name, "suffix": rng.choice(SUFFIXES),
         "website": f"www.{slug(name)}.com", "phone": f"{rng.randrange(200, 999)}{rng.randrange(200, 999)}{rng.randrange(10000):04d}",
         "industry": trade, "source_system": rng.choice(SOURCES), "updated_at": when(), **new_address()}
    return a


def account_row(a, variant):
    r = dict(a)
    name = r["name"]
    if variant:
        if rng.random() < 0.5:
            r["suffix"] = rng.choice(SUFFIXES)
        if rng.random() < 0.3:
            name = name.replace(" ", "") if rng.random() < 0.3 else name.upper()
        if rng.random() < 0.25:
            name = typo(name)
        if rng.random() < 0.2:
            name = name.replace(" Services", "") + " Group"
        if rng.random() < 0.3:
            r["website"] = ""
        if rng.random() < 0.3:
            r["phone"] = ""
        r = mess_address(r)
        r["source_system"], r["updated_at"] = rng.choice(SOURCES), when()
    full = f"{name} {r['suffix']}".strip()
    return {"name": full, "website": r["website"], "phone": fmt_phone(r["phone"]) if r["phone"] else "",
            "address": r["address"], "city": r["city"], "state": r["state"], "zip": r["zip"],
            "industry": r["industry"], "source_system": r["source_system"], "updated_at": r["updated_at"]}


def make_accounts():
    base = [new_account(i) for i in range(N_TRUE_ACCOUNTS - N_ACCOUNT_DECOYS)]
    # decoys: look like an existing business but are a different one (other city, other trade or same-brand sibling)
    for j in range(N_ACCOUNT_DECOYS):
        d = dict(rng.choice(base))
        d.update(new_address())
        d["true_id"] = f"TA{len(base):04d}"
        d["phone"] = f"{rng.randrange(200, 999)}{rng.randrange(200, 999)}{rng.randrange(10000):04d}"
        if rng.random() < 0.5:
            d["name"] = d["name"].split()[0] + " " + rng.choice([t for t in TRADES if t != d["industry"]])
            d["industry"] = d["name"].split(" ", 1)[1]
        d["website"] = f"www.{slug(d['name'])}.com" if rng.random() < 0.5 else ""
        base.append(d)
    rows = [(a["true_id"], account_row(a, False), "clean") for a in base]
    for _ in range(N_ACCOUNTS - len(rows)):
        a = rng.choice(base)
        rows.append((a["true_id"], account_row(a, True), "variant"))
    rng.shuffle(rows)
    return base, rows


# ---- contacts ----
def new_contact(i, acct, first=None, last=None):
    first, last = first or rng.choice(FIRST), last or rng.choice(LAST)
    return {"true_id": f"TC{i:04d}", "first": first, "last": last, "acct": acct, "title": rng.choice(TITLES),
            "phone": f"{rng.randrange(200, 999)}{rng.randrange(200, 999)}{rng.randrange(10000):04d}",
            "source_system": rng.choice(SOURCES), "updated_at": when()}


def email_for(c, domain, variant):
    f, l = slug(c["first"]), slug(c["last"])
    style = rng.choice(["f.l", "fl", "first", "gmail"]) if variant else "f.l"
    return {"f.l": f"{f}.{l}@{domain}", "fl": f"{f[0]}{l}@{domain}", "first": f"{f}@{domain}",
            "gmail": f"{f}{l}{rng.randrange(100)}@gmail.com"}[style]


def make_contacts(accts, acct_ids):
    by_true = {a["true_id"]: a for a in accts}
    true_ids = list(by_true)
    base = []
    for i in range(N_TRUE_CONTACTS - N_CONTACT_DECOYS):
        acct = rng.choice(true_ids) if rng.random() < 0.94 else None  # no-account edge case
        base.append(new_contact(i, acct))
    # decoys: father/son, twins, same name at different company
    for _ in range(N_CONTACT_DECOYS):
        o = rng.choice([c for c in base if c["acct"]])
        kind = rng.choice(["junior", "twin", "namesake"])
        d = new_contact(len(base), o["acct"] if kind != "namesake" else rng.choice(true_ids), o["first"], o["last"])
        if kind == "twin":
            d["first"] = rng.choice([n for n in FIRST if n[0] == o["first"][0]] or FIRST)
        d["decoy"], d["sibling"] = kind, o["true_id"]
        base.append(d)
    by_c = {c["true_id"]: c for c in base}

    def row(c, variant):
        acct = by_true.get(c["acct"])
        domain = acct["website"][4:] if acct and acct["website"] else "gmail.com"
        first, last, phone = c["first"], c["last"], c["phone"]
        r = dict(address="", city="", state="", zip="", title=c["title"])
        if acct:
            r.update({k: acct[k] for k in ("address", "city", "state", "zip")})
        if variant:
            if rng.random() < 0.4 and first in NICKS:
                first = rng.choice(NICKS[first])
            if rng.random() < 0.2:
                first, last = last, first  # swapped
            if rng.random() < 0.2:
                last = typo(last)
            if rng.random() < 0.15:
                first = first[0] + "."
            r = mess_address(r) if r["address"] else r
            r["title"] = r["title"] if rng.random() < 0.6 else ""
            phone = phone if rng.random() < 0.6 else ""
        e = email_for(c, domain, variant)
        if variant and rng.random() < 0.25:
            e = ""
        src, upd = (rng.choice(SOURCES), when()) if variant else (c["source_system"], c["updated_at"])
        return {"first_name": first, "last_name": last, "email": e, "phone": fmt_phone(phone) if phone else "",
                "title": r["title"], "address": r["address"], "city": r["city"], "state": r["state"],
                "zip": r["zip"], "source_system": src, "updated_at": upd}

    rows = [(c["true_id"], c["acct"], row(c, False), c.get("decoy", "clean")) for c in base]
    for _ in range(N_CONTACTS - len(rows)):
        c = rng.choice(base)
        rows.append((c["true_id"], c["acct"], row(c, True), "variant"))
    rng.shuffle(rows)
    return rows


def main():
    OUT.mkdir(exist_ok=True)
    accts, arows = make_accounts()
    a_records = {}  # true account id -> record ids
    a_out, key = [], []
    for n, (tid, r, kind) in enumerate(arows, 1):
        rid = f"A{n:05d}"
        a_records.setdefault(tid, []).append(rid)
        a_out.append({"account_id": rid, **r})
        key.append({"table": "accounts", "record_id": rid, "true_id": tid, "kind": kind})
    c_out = []
    for n, (tid, acct, r, kind) in enumerate(make_contacts(accts, None), 1):
        rid = f"C{n:05d}"
        # contact points at one of its true account's records (possibly a duplicate variant)
        c_out.append({"contact_id": rid, "account_id": rng.choice(a_records[acct]) if acct else "", **r})
        key.append({"table": "contacts", "record_id": rid, "true_id": tid, "kind": kind})
    for name, rows in (("accounts", a_out), ("contacts", c_out), ("answer_key", key)):
        with open(OUT / f"{name}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    print(f"accounts={len(a_out)} contacts={len(c_out)} true_accounts={len(a_records)} "
          f"true_contacts={len({k['true_id'] for k in key if k['table'] == 'contacts'})}")


if __name__ == "__main__":
    main()
