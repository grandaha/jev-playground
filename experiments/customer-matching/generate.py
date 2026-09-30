"""Generate a small, targeted synthetic dataset: one named scenario per hard case.

Run from repo root: .venv/bin/python experiments/customer-matching/generate.py
Writes data/accounts.csv, data/contacts.csv, data/answer_key.csv (table, record_id, true_id, kind, scenario).
Scenarios marked DUP are the same entity appearing more than once; DISTINCT are look-alikes that must NOT merge.
"""
import os
import csv
import random
import re
from datetime import date, timedelta
from pathlib import Path

SEED = int(os.environ.get("SEED", 11))
OUT = Path(__file__).parent / os.environ.get("MATCH_DATA", "data")
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
ROLE_MAILBOXES = ["info", "sales", "office", "admin", "support"]
ADDR = ("address", "city", "state", "zip")

# scenario -> number of groups. Each group is a true entity (DUP) or a pair of look-alike entities (DISTINCT).
ACCOUNT_SCENARIOS = {
    "exact_formatting": 10,      # DUP: same business, only case / St-vs-Street / phone format differ
    "typo_suffix": 10,           # DUP: name typo + different legal suffix; one of phone/website kept
    "moved_keeps_ids": 8,        # DUP: new address, same phone and website
    "moved_lost_ids": 5,         # DUP but unprovable: new address, phone and website dropped
    "three_way": 5,              # DUP: three records of one business
    "sibling_locations": 10,     # DISTINCT: same brand name, two cities, different phones, no website
    "shared_brand_website": 6,   # DISTINCT: franchise, same website, different city and phone
    "same_name_other_trade": 8,  # DISTINCT: "Summit Dental" vs "Summit Logistics"
    "unrelated": 40,             # single records, no duplicates
}
CONTACT_SCENARIOS = {
    "nickname": 10,              # DUP: Robert / Bob, different email style, same phone
    "swapped_typo": 8,           # DUP: names swapped + typo, no email, same phone
    "initial_only": 6,           # DUP: "R." vs "Robert", no email, phone sometimes kept
    "email_changed": 6,          # DUP: work email vs personal gmail, same phone
    "dup_account": 10,           # DUP: one person attached to two duplicate variants of an account; only name + master account link them
    "no_account_email": 4,       # DUP: no account, same personal email
    "no_account_name_only": 4,   # DUP but unprovable: no account, only the name in common
    "junior_senior": 8,          # DISTINCT: same name, account, address; own emails and phones
    "twins": 6,                  # DISTINCT: same last name, account, address; first names share an initial
    "namesakes_other_company": 10,   # DISTINCT: same name at different companies
    "same_name_same_company": 4,     # DISTINCT: two different people, same name, same company
    "shared_mailbox": 6,         # DISTINCT: two different people sharing info@company
    "unrelated": 80,             # single records
}

if os.environ.get("ROUND") == "2":  # round 2 adds scenarios; earlier rounds are left exactly as they were
    CONTACT_SCENARIOS.update({
        "shared_personal_email": 6,     # DISTINCT: two different people (spouses) sharing one gmail, no account
        "same_email_details_changed": 6,  # DUP: same name, company and work email; the second record has a new phone and title
        "phone_only_shared": 6,         # DISTINCT: two different people sharing a phone number, no account
        "account_vs_no_account": 8,     # DUP: one record has its account, the other has none (personal email, same phone)
    })


def typo(s):
    i = rng.randrange(1, len(s) - 1)
    return rng.choice([s[:i] + s[i + 1] + s[i] + s[i + 2:], s[:i] + s[i + 1:], s[:i] + s[i] + s[i:]])


def digits10():
    return f"{rng.randrange(200, 999)}{rng.randrange(200, 999)}{rng.randrange(10000):04d}"


def fmt_phone(d):
    a, b, c = d[:3], d[3:6], d[6:]
    return rng.choice([f"({a}) {b}-{c}", f"{a}-{b}-{c}", f"{a}.{b}.{c}", f"+1 {a} {b} {c}", d])


def slug(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def when():
    return (date(2022, 1, 1) + timedelta(days=rng.randrange(1700))).isoformat()


def new_address(city=None):
    c, st, z3 = city or rng.choice(CITIES)
    return {"address": f"{rng.randrange(10, 9900)} {rng.choice(STREETS)} {rng.choice(list(KINDS))}", "city": c,
            "state": st, "zip": z3 + f"{rng.randrange(100):02d}"}


def other_city(a):
    return new_address(rng.choice([c for c in CITIES if c[0] != a["city"]]))


def abbreviate(addr):
    for long, short in KINDS.items():
        addr = addr.replace(long, short)
    return addr


# ---------------- accounts ----------------
_names = [(s, t) for s in STEMS for t in TRADES]
rng.shuffle(_names)
_ids = {"A": 0, "C": 0}


def new_tid(prefix):
    _ids[prefix] += 1
    return f"T{prefix}{_ids[prefix]:04d}"


def base_account(stem=None, trade=None, **over):
    s, t = (stem, trade) if stem else _names.pop()
    name = f"{s} {t}"
    a = {"true_id": new_tid("A"), "stem": s, "name": name, "suffix": rng.choice(SUFFIXES), "website": f"www.{slug(name)}.com",
         "phone": digits10(), "industry": t, "source_system": rng.choice(SOURCES), "updated_at": when(), **new_address()}
    a.update(over)
    return a


def acct_row(a, variant=False, **o):
    name = a["name"]
    if o.get("typo"):
        name = typo(name)
    if o.get("upper"):
        name = name.upper()
    addr = o.get("addr") or {k: a[k] for k in ADDR}
    if o.get("abbrev"):
        addr = {**addr, "address": abbreviate(addr["address"])}
    return {"name": f"{name} {o.get('suffix', a['suffix'])}".strip(),
            "website": "" if o.get("drop_website") else a["website"],
            "phone": "" if o.get("drop_phone") else fmt_phone(a["phone"]),
            **addr, "industry": a["industry"],
            "source_system": rng.choice(SOURCES) if variant else a["source_system"],
            "updated_at": when() if variant else a["updated_at"]}


def make_accounts():
    rows, entities = [], {}  # rows: (true_id, scenario, kind, row)
    n = ACCOUNT_SCENARIOS

    def emit(scn, a, kind="clean", **o):
        entities[a["true_id"]] = a
        rows.append((a["true_id"], scn, kind, acct_row(a, variant=(kind == "variant"), **o)))

    def other_suffix(a):
        return rng.choice([s for s in SUFFIXES if s != a["suffix"]])

    for _ in range(n["exact_formatting"]):
        a = base_account(); emit("exact_formatting", a); emit("exact_formatting", a, "variant", abbrev=True, upper=rng.random() < 0.5)
    for _ in range(n["typo_suffix"]):
        a = base_account(); emit("typo_suffix", a)
        emit("typo_suffix", a, "variant", typo=True, suffix=other_suffix(a), **{rng.choice(["drop_phone", "drop_website"]): True})
    for _ in range(n["moved_keeps_ids"]):
        a = base_account(); emit("moved_keeps_ids", a); emit("moved_keeps_ids", a, "variant", addr=other_city(a))
    for _ in range(n["moved_lost_ids"]):
        a = base_account(); emit("moved_lost_ids", a)
        emit("moved_lost_ids", a, "variant", addr=other_city(a), drop_phone=True, drop_website=True, upper=True)
    for _ in range(n["three_way"]):
        a = base_account(); emit("three_way", a); emit("three_way", a, "variant", typo=True)
        emit("three_way", a, "variant", abbrev=True, suffix=other_suffix(a))
    for _ in range(n["sibling_locations"]):
        a = base_account(website=""); b = {**a, "true_id": new_tid("A"), "phone": digits10(), **other_city(a)}
        emit("sibling_locations", a); emit("sibling_locations", b)
    for _ in range(n["shared_brand_website"]):
        a = base_account(); b = {**a, "true_id": new_tid("A"), "phone": digits10(), **other_city(a)}
        emit("shared_brand_website", a); emit("shared_brand_website", b)
    for _ in range(n["same_name_other_trade"]):
        a = base_account(); b = base_account(a["stem"], rng.choice([t for t in TRADES if t != a["industry"]]))
        emit("same_name_other_trade", a); emit("same_name_other_trade", b)
    for _ in range(n["unrelated"]):
        emit("unrelated", base_account())
    return rows, entities


# ---------------- contacts ----------------
def domain(acct):
    return acct["website"].removeprefix("www.")


def personal_email(c):
    return f"{slug(c['first'])}{slug(c['last'])}{c['true_id'][2:]}@gmail.com"


def corp_email(c, acct, style="f.l"):
    if not acct:
        return personal_email(c)
    f, l = slug(c["first"]), slug(c["last"])
    return {"f.l": f"{f}.{l}@{domain(acct)}", "fl": f"{f[0]}{l}@{domain(acct)}"}[style]


_used_names = set()  # (first, last, account): random people never collide, so two records with one name and company are one person


def base_contact(accounts, first=None, last=None, acct="any", **over):
    acct = rng.choice(list(accounts)) if acct == "any" else acct
    while True:  # name parts left open are redrawn until (first, last, account) is new; fully specified names are intentional
        f, l = first or rng.choice(FIRST), last or rng.choice(LAST)
        if (first and last) or (f, l, acct) not in _used_names:
            break
    _used_names.add((f, l, acct))
    c = {"true_id": new_tid("C"), "first": f, "last": l,
         "acct": acct,
         "title": rng.choice(TITLES), "phone": digits10(), "addr": new_address() if rng.random() < 0.25 else None,
         "source_system": rng.choice(SOURCES), "updated_at": when()}
    c.update(over)
    return c


def make_contacts(accounts, dup_accounts):
    rows = []  # (true_id, scenario, kind, acct_true, pick, row)
    n = CONTACT_SCENARIOS

    def emit(scn, c, kind="clean", pick="any", **o):
        acct = accounts.get(c["acct"])
        variant = kind == "variant"
        addr = c["addr"] or {k: "" for k in ADDR}
        if variant and c["addr"] and rng.random() < 0.5:
            addr = {**addr, "address": abbreviate(addr["address"]).upper()}
        rows.append((c["true_id"], scn, kind, None if o.get("no_account") else c["acct"], pick, {
            "first_name": o.get("first", c["first"]), "last_name": o.get("last", c["last"]),
            "email": o["email"] if "email" in o else corp_email(c, acct),
            "phone": "" if o.get("drop_phone") else fmt_phone(o.get("phone", c["phone"])),
            "title": o.get("title", c["title"]), **addr,
            "source_system": rng.choice(SOURCES) if variant else c["source_system"],
            "updated_at": when() if variant else c["updated_at"]}))

    for _ in range(n["nickname"]):
        full = rng.choice(list(NICKS)); c = base_contact(accounts, first=full); nick = rng.choice(NICKS[full])
        emit("nickname", c)
        emit("nickname", c, "variant", first=nick, email=f"{slug(nick)}.{slug(c['last'])}@{domain(accounts[c['acct']])}")
    for _ in range(n["swapped_typo"]):
        c = base_contact(accounts); emit("swapped_typo", c)
        emit("swapped_typo", c, "variant", first=c["last"], last=typo(c["first"]), email="")
    for _ in range(n["initial_only"]):
        c = base_contact(accounts); emit("initial_only", c)
        emit("initial_only", c, "variant", first=c["first"][0] + ".", email="", drop_phone=rng.random() < 0.5)
    for _ in range(n["email_changed"]):
        c = base_contact(accounts); emit("email_changed", c); emit("email_changed", c, "variant", email=personal_email(c))
    for _ in range(n["dup_account"]):
        c = base_contact(accounts, acct=rng.choice(dup_accounts))
        emit("dup_account", c, pick=0); emit("dup_account", c, "variant", pick=1, email="", drop_phone=True)
    for _ in range(n["no_account_email"]):
        c = base_contact(accounts, acct=None, addr=None)
        emit("no_account_email", c); emit("no_account_email", c, "variant", drop_phone=True)
    for _ in range(n["no_account_name_only"]):
        c = base_contact(accounts, acct=None, addr=None)
        emit("no_account_name_only", c, email=""); emit("no_account_name_only", c, "variant", email="", drop_phone=True)
    for _ in range(n["junior_senior"]):
        s = base_contact(accounts, addr=new_address()); j = {**s, "true_id": new_tid("C"), "phone": digits10(), "title": rng.choice(TITLES)}
        emit("junior_senior", s); emit("junior_senior", j, email=corp_email(j, accounts[j["acct"]]).replace("@", ".jr@"))
    for _ in range(n["twins"]):
        a = base_contact(accounts, addr=new_address())
        t = {**a, "true_id": new_tid("C"), "phone": digits10(),
             "first": rng.choice([x for x in FIRST if x[0] == a["first"][0] and x != a["first"]] or [x for x in FIRST if x != a["first"]])}
        emit("twins", a); emit("twins", t)
    for _ in range(n["namesakes_other_company"]):
        a = base_contact(accounts)
        b = base_contact(accounts, first=a["first"], last=a["last"], acct=rng.choice([x for x in accounts if x != a["acct"]]))
        emit("namesakes_other_company", a); emit("namesakes_other_company", b)
    for _ in range(n["same_name_same_company"]):
        a = base_contact(accounts); b = base_contact(accounts, first=a["first"], last=a["last"], acct=a["acct"])
        emit("same_name_same_company", a); emit("same_name_same_company", b, email=corp_email(b, accounts[b["acct"]], "fl"))
    for _ in range(n["shared_mailbox"]):
        acct = rng.choice(list(accounts)); box = f"{rng.choice(ROLE_MAILBOXES)}@{domain(accounts[acct])}"
        for i in range(2):  # one of the pair often has no phone on file, so the phone check can't save us
            emit("shared_mailbox", base_contact(accounts, acct=acct), email=box, drop_phone=(i == 1 and rng.random() < 0.6))
    for _ in range(n["unrelated"]):
        emit("unrelated", base_contact(accounts, acct="any" if rng.random() > 0.05 else None))
    # round 2 scenarios (zero groups unless ROUND=2), drawn after everything else so earlier rounds are unchanged
    for _ in range(n.get("shared_personal_email", 0)):
        a = base_contact(accounts, acct=None, addr=None); b = base_contact(accounts, last=a["last"], acct=None, addr=None)
        while b["first"] == a["first"]:
            b = base_contact(accounts, last=a["last"], acct=None, addr=None)
        emit("shared_personal_email", a, email=personal_email(a)); emit("shared_personal_email", b, email=personal_email(a))
    for _ in range(n.get("same_email_details_changed", 0)):
        c = base_contact(accounts); emit("same_email_details_changed", c)
        emit("same_email_details_changed", c, "variant", phone=digits10(), title=rng.choice([t for t in TITLES if t != c["title"]]))
    for _ in range(n.get("phone_only_shared", 0)):
        a = base_contact(accounts, acct=None, addr=None); b = base_contact(accounts, acct=None, addr=None, phone=a["phone"])
        emit("phone_only_shared", a, email=personal_email(a)); emit("phone_only_shared", b, email=personal_email(b))
    for _ in range(n.get("account_vs_no_account", 0)):
        c = base_contact(accounts); emit("account_vs_no_account", c)
        emit("account_vs_no_account", c, "variant", email=personal_email(c), no_account=True)
    return rows


def write(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    OUT.mkdir(exist_ok=True)
    for stale in ("groups_accounts.csv", "masters_accounts.csv"):  # derived files from an earlier run must not leak into this one
        (OUT / stale).unlink(missing_ok=True)
    arows, accounts = make_accounts()
    rng.shuffle(arows)
    a_records, a_out, key = {}, [], []
    for n, (tid, scn, kind, r) in enumerate(arows, 1):
        rid = f"A{n:05d}"
        a_records.setdefault(tid, []).append(rid)
        a_out.append({"account_id": rid, **r})
        key.append({"table": "accounts", "record_id": rid, "true_id": tid, "kind": kind, "scenario": scn})
    pool = {t: a for t, a in accounts.items() if a["website"]}  # contacts get work emails, so their account needs a website
    dup_accounts = [t for t, ids in a_records.items() if len(ids) > 1 and t in pool]
    crows = make_contacts(pool, dup_accounts)
    rng.shuffle(crows)
    c_out = []
    for n, (tid, scn, kind, acct, pick, r) in enumerate(crows, 1):
        rid = f"C{n:05d}"
        recs = a_records.get(acct, [])
        acct_rid = "" if not acct else rng.choice(recs) if pick == "any" else recs[pick % len(recs)]
        c_out.append({"contact_id": rid, "account_id": acct_rid, **r})
        key.append({"table": "contacts", "record_id": rid, "true_id": tid, "kind": kind, "scenario": scn})
    write(OUT / "accounts.csv", a_out)
    write(OUT / "contacts.csv", c_out)
    write(OUT / "answer_key.csv", key)
    print(f"accounts={len(a_out)} ({len(a_records)} true) contacts={len(c_out)} "
          f"({len({k['true_id'] for k in key if k['table'] == 'contacts'})} true)")


if __name__ == "__main__":
    main()
