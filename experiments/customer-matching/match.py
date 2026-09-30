"""Decide each candidate pair in two steps, so policy changes never need new Jev calls.

  ask     Hard rules in code first; every other pair goes to Jev once, with all questions in one request.
          Raw answers are saved to data/answers_<table>.csv.
  decide  Apply a policy to the saved answers and write data/decisions_<table>.csv (and ..._single.csv).
          Policies: `signals` (default: weighted evidence from separate signals, each named in the trace)
          and `single` (one holistic Jev score, the first design, kept for comparison).

Run from repo root:
  .venv/bin/python experiments/customer-matching/match.py ask accounts|contacts [--limit N]
  .venv/bin/python experiments/customer-matching/match.py decide accounts|contacts [--merge 5 --reject 1]
"""
import os
import argparse
import csv
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv
from typesafe_sdk import Noul, Score, TypeSafeClient

DATA = Path(__file__).parent / os.environ.get("MATCH_DATA", "data")  # MATCH_DATA=data_seed2 runs on another folder
load_dotenv(DATA.parents[2] / ".env")
WORKERS = 8

# --- policy `single`: one holistic score (Score runs 0 = different .. 2 = same) ---
SINGLE_MERGE, SINGLE_REJECT, LOOKALIKE_P = 1.6, 0.6, 0.5

# --- policy `signals`: evidence points added up, Fellegi-Sunter style. Thresholds are tuned with sweep.py. ---
MERGE_POINTS, REJECT_POINTS = 4.0, 0.0  # from sweep.py on seed 7: 0 false merges down to 3.0; review queue was mostly true duplicates
W = {"name": 3.0, "holistic": 1.5, "details_conflict": 2.0, "lookalike": 3.0,
     "same_account": 2.0, "different_account": 2.0, "phone_equal": 3.0, "phone_differs": 2.0, "email_equal": 4.0,
     "domain_equal": 3.0, "domain_differs": 1.0, "street_equal": 1.5, "title_equal": 0.5}

LEVELS = {
    "accounts": ["The two records describe different businesses, for example a similar name in a different place or a different line of work.",
                 "The two records might describe one business, but details are missing or conflict and it could be two.",
                 "The two records describe one and the same business, allowing for typos, formatting and a changed address or phone."],
    "contacts": ["The two records describe different people, for example a different first name, or relatives who share a name.",
                 "The two records might describe one person, but details are missing or conflict and it could be two people.",
                 "The two records describe one and the same person, allowing for nicknames, typos, swapped names and changed contact details."],
}
QUESTIONS = {
    "accounts": {
        "same_entity": Score(instructions="Do these two account records describe the same business?", criteria=LEVELS["accounts"]),
        "name_same": Noul(instructions="Do the two business names refer to the same business, allowing for a different legal suffix (Inc, LLC), abbreviations, capitalisation and typos?"),
        "details_conflict": Noul(instructions="Do the website, phone or address directly conflict in a way one business would not have? A business can move or get a new number, so blank fields do not count as a conflict."),
        "lookalike": Noul(instructions="Are these two different locations or sibling businesses that share a brand name, rather than one business?"),
    },
    "contacts": {
        "same_entity": Score(instructions="Do these two contact records describe the same person?", criteria=LEVELS["contacts"]),
        "name_same": Noul(instructions="Do the two names refer to the same person, allowing for nicknames (Bob and Robert), initials, typos and first and last names written in swapped order?"),
        "details_conflict": Noul(instructions="Do the email, phone, title or address directly conflict in a way one person would not have? People change jobs and numbers, so blank fields do not count as a conflict."),
        "lookalike": Noul(instructions="Are these two different people who are related or coincidentally share a name, such as a parent and child, twins, or namesakes at different companies?"),
    },
}
ASKED = ["score", "confidence", "p_diff", "p_maybe", "p_same", "name_same", "details_conflict", "lookalike"]
PUBLIC = {"accounts": ["name", "website", "phone", "address", "city", "state", "zip", "industry", "source_system", "updated_at"],
          "contacts": ["first_name", "last_name", "email", "phone", "title", "address", "city", "state", "zip", "source_system", "updated_at"]}


def hard_rule(table, a, b):
    """(decision, rule) for pairs that need no judgment, else None."""
    if table == "accounts" and a["k_phone"] and a["k_phone"] == b["k_phone"] and a["k_domain"] and a["k_domain"] == b["k_domain"]:
        return "merge", "same_phone_and_domain"
    if table == "contacts" and a["k_email"] and a["k_email"] == b["k_email"]:
        # one mailbox and a compatible name (nickname, initial or swapped order): phones and titles change, so they do not veto
        if {a["name_a"], a["name_b"]} & {b["name_a"], b["name_b"]}:
            return "merge", "same_email"
    return None


def view(table, r, accounts):
    v = {k: r[k] for k in PUBLIC[table] if r.get(k)}
    acct_id = r.get("master_account_id") or r.get("account_id")  # show the master account, not a messy duplicate
    if table == "contacts" and acct_id:
        acct = accounts[acct_id]
        v["account"] = {k: acct[k] for k in ("name", "website", "address", "city", "state") if acct.get(k)}
    return v


def write(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def ask(table, limit):
    idc = f"{table[:-1]}_id"
    norm = {r[idc]: r for r in csv.DictReader(open(DATA / f"{table}_norm.csv"))}
    accounts = {r["account_id"]: r for r in csv.DictReader(open(DATA / "accounts_norm.csv"))}
    cands = list(csv.DictReader(open(DATA / f"candidates_{table}.csv")))[:limit]
    client = TypeSafeClient()

    def one(c):
        a, b = norm[c["id_a"]], norm[c["id_b"]]
        out = {**c, "hard_decision": "", "hard_rule": "", "error": "", **{k: "" for k in ASKED}}
        hit = hard_rule(table, a, b)
        if hit:
            out.update(hard_decision=hit[0], hard_rule=hit[1])
            return out
        for attempt in range(4):  # the API occasionally returns a transient 5xx even after SDK retries
            try:
                resp = client.system_one(state={"record_a": view(table, a, accounts), "record_b": view(table, b, accounts)},
                                         questions=QUESTIONS[table])
                break
            except Exception as e:
                if attempt == 3:
                    out["error"] = str(e)[:200]
                    return out
                time.sleep(2 ** attempt)
        s = resp.answers["same_entity"]
        p = [s.probabilities.get(i, 0) for i in range(3)]
        out.update(score=s.score, confidence=s.confidence, p_diff=p[0], p_maybe=p[1], p_same=p[2],
                   **{k: resp.answers[k].noul for k in ("name_same", "details_conflict", "lookalike")})
        return out

    with ThreadPoolExecutor(WORKERS) as ex:
        rows = list(ex.map(one, cands))
    write(DATA / f"answers_{table}.csv", rows)
    jev = [r for r in rows if not r["hard_rule"]]
    print(f"{table}: {len(rows)} pairs, {len(rows) - len(jev)} by hard rule, {len(jev)} asked Jev, {sum(1 for r in jev if r['error'])} errors")


def evidence(table, a, b, r):
    """Named evidence points for the `signals` policy: [(signal, points)]."""
    f = lambda k: float(r[k])
    pts = [("name_same", W["name"] * (2 * f("name_same") - 1)),
           ("holistic_score", W["holistic"] * (f("score") - 1)),
           ("details_conflict", -W["details_conflict"] * f("details_conflict")),
           ("lookalike", -W["lookalike"] * f("lookalike"))]
    both = lambda k: a[k] and b[k]
    if both("k_phone"):
        pts.append(("phone_equal", W["phone_equal"]) if a["k_phone"] == b["k_phone"] else ("phone_differs", -W["phone_differs"]))
    if table == "accounts":
        if both("k_domain"):
            pts.append(("domain_equal", W["domain_equal"]) if a["k_domain"] == b["k_domain"] else ("domain_differs", -W["domain_differs"]))
        if both("k_street") and a["k_street"] == b["k_street"]:
            pts.append(("street_equal", W["street_equal"]))
    else:
        ga, gb = a["master_account_id"], b["master_account_id"]
        if ga and gb:
            pts.append(("same_account", W["same_account"]) if ga == gb else ("different_account", -W["different_account"]))
        if both("k_email") and a["k_email"] == b["k_email"]:
            pts.append(("email_equal", W["email_equal"]))
        if a["k_name_street"] and a["k_name_street"] == b["k_name_street"]:
            pts.append(("own_address_equal", W["street_equal"]))
        if both("title") and a["title"].lower() == b["title"].lower():
            pts.append(("title_equal", W["title_equal"]))
    return pts


def decide_one(table, policy, a, b, r, merge_t, reject_t):
    """Returns (decision, rule, detail) for one answered pair."""
    if r["hard_rule"]:
        return r["hard_decision"], r["hard_rule"], f"hard rule {r['hard_rule']}"
    if r["error"]:
        return "error", "jev_error", r["error"]
    s, look = float(r["score"]), float(r["lookalike"])
    if policy == "single":
        if s >= SINGLE_MERGE and look < LOOKALIKE_P:
            d, rule, detail = "merge", "single_high", f"score {s:.2f} >= {SINGLE_MERGE}, lookalike {look:.2f} < {LOOKALIKE_P}"
        elif s >= SINGLE_MERGE:
            d, rule, detail = "review", "single_lookalike", f"score {s:.2f} >= {SINGLE_MERGE} but lookalike {look:.2f} >= {LOOKALIKE_P}"
        elif s <= SINGLE_REJECT:
            d, rule, detail = "no_match", "single_low", f"score {s:.2f} <= {SINGLE_REJECT}"
        else:
            d, rule, detail = "review", "single_mid", f"{SINGLE_REJECT} < score {s:.2f} < {SINGLE_MERGE}"
    else:
        pts = evidence(table, a, b, r)
        total = sum(p for _, p in pts)
        detail = f"{total:+.1f} points: " + ", ".join(f"{n} {p:+.1f}" for n, p in sorted(pts, key=lambda x: -abs(x[1])) if abs(p) >= 0.05)
        d, rule = ("merge", "signals_high") if total >= merge_t else ("no_match", "signals_low") if total <= reject_t else ("review", "signals_mid")
    shared = [k for k in ("k_phone", "k_domain", "k_email") if a.get(k) and a.get(k) == b.get(k)]
    if d == "no_match" and shared:
        # veto: sharing a phone, website or email is too strong to reject outright
        d, detail, rule = "review", f"would reject ({rule}) but they share {', '.join(shared)}. {detail}", "shared_identifier"
    if d == "merge" and a["k_phone"] and b["k_phone"] and a["k_phone"] != b["k_phone"]:
        # veto: a differing phone never auto-merges
        d, detail, rule = "review", f"would merge ({rule}) but phones differ. {detail}", "phone_conflict"
    return d, rule, detail


def decide(table, merge_t, reject_t):
    idc = f"{table[:-1]}_id"
    norm = {r[idc]: r for r in csv.DictReader(open(DATA / f"{table}_norm.csv"))}
    answers = list(csv.DictReader(open(DATA / f"answers_{table}.csv")))
    for policy, name in (("signals", f"decisions_{table}.csv"), ("single", f"decisions_{table}_single.csv")):
        rows = []
        for r in answers:
            d, rule, detail = decide_one(table, policy, norm[r["id_a"]], norm[r["id_b"]], r, merge_t, reject_t)
            rows.append({**r, "decision": d, "rule": rule, "detail": detail})
        write(DATA / name, rows)
        print(f"{table} [{policy}]:", dict(Counter((x["decision"], x["rule"]) for x in rows)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["ask", "decide"])
    ap.add_argument("table", choices=["accounts", "contacts"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--merge", type=float, default=MERGE_POINTS)
    ap.add_argument("--reject", type=float, default=REJECT_POINTS)
    args = ap.parse_args()
    ask(args.table, args.limit) if args.step == "ask" else decide(args.table, args.merge, args.reject)
