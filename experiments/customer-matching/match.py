"""Decide each candidate pair: hard rules in code first, then Jev for the ambiguous rest.

Run from repo root:
  .venv/bin/python experiments/customer-matching/match.py accounts [--limit 50]
  .venv/bin/python experiments/customer-matching/match.py contacts [--limit 50]
Writes data/decisions_<table>.csv. Every row says which rule decided it (the `rule` column)
and, for Jev decisions, the raw answers and the threshold that fired (`detail`).
"""
import argparse
import csv
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv
from typesafe_sdk import Noul, Score, TypeSafeClient

DATA = Path(__file__).parent / "data"
load_dotenv(DATA.parents[2] / ".env")

# Thresholds live in code so they can be tuned without re-asking Jev (raw answers are saved).
MERGE_SCORE = 1.6   # Score is 0 (different) .. 2 (same); at/above this = auto-merge candidate
REJECT_SCORE = 0.6  # at/below this = not a match
LOOKALIKE_P = 0.5   # companion Noul at/above this blocks auto-merge and sends the pair to review
WORKERS = 8

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
        "lookalike": Noul(instructions="Are these two different locations or sibling businesses that share a brand name, rather than one business?"),
    },
    "contacts": {
        "same_entity": Score(instructions="Do these two contact records describe the same person?", criteria=LEVELS["contacts"]),
        "lookalike": Noul(instructions="Are these two different people who are related or coincidentally share a name, such as a parent and child, twins, or namesakes at different companies?"),
    },
}
PUBLIC = {"accounts": ["name", "website", "phone", "address", "city", "state", "zip", "industry", "source_system", "updated_at"],
          "contacts": ["first_name", "last_name", "email", "phone", "title", "address", "city", "state", "zip", "source_system", "updated_at"]}


def hard_rule(table, a, b):
    """Returns (decision, rule) or None. Kept to cases that are safe without judgment."""
    if table == "accounts" and a["k_phone"] and a["k_phone"] == b["k_phone"] and a["k_domain"] and a["k_domain"] == b["k_domain"]:
        return "merge", "same_phone_and_domain"
    if table == "contacts" and a["k_email"] and a["k_email"] == b["k_email"] and a["k_phone"] and a["k_phone"] == b["k_phone"]:
        return "merge", "same_email_and_phone"  # email alone is unsafe: a junior/senior pair can share one
    return None


def view(table, r, accounts):
    v = {k: r[k] for k in PUBLIC[table] if r.get(k)}
    if table == "contacts" and r["account_id"]:
        acct = accounts[r["account_id"]]
        v["account"] = {k: acct[k] for k in ("name", "website", "address", "city", "state") if acct.get(k)}
    return v


def jev_decision(table, client, a, b, accounts):
    resp = client.system_one(state={"record_a": view(table, a, accounts), "record_b": view(table, b, accounts)},
                             questions=QUESTIONS[table])
    s, look = resp.answers["same_entity"], resp.answers["lookalike"].noul
    p = [s.probabilities.get(i, 0) for i in range(3)]
    base = {"score": s.score, "confidence": s.confidence, "p_diff": p[0], "p_maybe": p[1], "p_same": p[2], "p_lookalike": look}
    if s.score >= MERGE_SCORE and look < LOOKALIKE_P:
        return "merge", "jev_score_high", f"score {s.score:.2f} >= {MERGE_SCORE} and lookalike {look:.2f} < {LOOKALIKE_P}", base
    if s.score >= MERGE_SCORE:
        return "review", "jev_lookalike_flag", f"score {s.score:.2f} >= {MERGE_SCORE} but lookalike {look:.2f} >= {LOOKALIKE_P}", base
    if s.score <= REJECT_SCORE:
        return "no_match", "jev_score_low", f"score {s.score:.2f} <= {REJECT_SCORE}", base
    return "review", "jev_score_mid", f"{REJECT_SCORE} < score {s.score:.2f} < {MERGE_SCORE}", base


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("table", choices=["accounts", "contacts"])
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    table = args.table
    norm = {r[f"{table[:-1]}_id"]: r for r in csv.DictReader(open(DATA / f"{table}_norm.csv"))}
    accounts = {r["account_id"]: r for r in csv.DictReader(open(DATA / "accounts_norm.csv"))}
    cands = list(csv.DictReader(open(DATA / f"candidates_{table}.csv")))[: args.limit]
    client = TypeSafeClient()

    def decide(c):
        a, b = norm[c["id_a"]], norm[c["id_b"]]
        out = {**c, "decision": "", "rule": "", "detail": "", "score": "", "confidence": "", "p_diff": "", "p_maybe": "",
               "p_same": "", "p_lookalike": ""}
        hit = hard_rule(table, a, b)
        if hit:
            out.update(decision=hit[0], rule=hit[1], detail=f"hard rule {hit[1]}")
            return out
        try:
            d, rule, detail, raw = jev_decision(table, client, a, b, accounts)
            if d == "merge" and a["k_phone"] and b["k_phone"] and a["k_phone"] != b["k_phone"]:
                d, rule, detail = "review", "phone_conflict", f"Jev said merge ({rule}) but phones differ: {a['k_phone']} vs {b['k_phone']}"
            out.update(decision=d, rule=rule, detail=detail, **raw)
        except Exception as e:  # keep the run going; errors are visible in the output
            out.update(decision="error", rule="jev_error", detail=str(e)[:200])
        return out

    with ThreadPoolExecutor(WORKERS) as ex:
        rows = list(ex.map(decide, cands))
    with open(DATA / f"decisions_{table}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    from collections import Counter
    print(table, len(rows), "pairs;", dict(Counter((r["decision"], r["rule"]) for r in rows)))


if __name__ == "__main__":
    main()
