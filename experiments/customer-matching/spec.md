# Customer record matching: spec

Goal: dedupe a messy synthetic customer file, explain every match, pick a master per group.

## Decisions
- Entities: businesses (accounts) and people (contacts), in separate linked files.
- Scale: 1,000 account records and 3,000 contact records, counting duplicate variants (~800 true accounts, ~2,400 true contacts). Synthetic only, no real data, no PII concerns.
- Output: scripts only (terminal report + CSV/JSON files). UI later.
- Language: Python 3.13, `.venv`, `typesafe-sdk`.
- Lives in `experiments/customer-matching/`. Run scripts from the repo root, e.g. `.venv/bin/python experiments/customer-matching/generate.py`.

## Files: accounts and contacts (Salesforce-style)
- `accounts.csv` (businesses): `account_id`, `name`, `website`, `phone`, `address`, `city`, `state`, `zip`, `industry`, `source_system`, `updated_at`.
- `contacts.csv` (people): `contact_id`, `account_id` (nullable), `first_name`, `last_name`, `email`, `phone`, `title`, `address`, `city`, `state`, `zip`, `source_system`, `updated_at`. A contact's address is their own (about a quarter have one), never a copy of the account's, so address is not treated as evidence for colleagues at one company.
- Two steps; the output of the first is an input to the second. Step 1 matches accounts, clusters them, and picks a master account per group (`master.py accounts`). Step 2 gives every contact a `master_account_id` (its account's master) in `contacts_norm.csv`. That id is a match key (`k_name_acct`: swap-proof name plus master account), a signal (`same_account`), and the account context Jev sees for each contact, so two contacts whose accounts were duplicates now count as the same company. Matching contacts on master account alone is too broad (every pair of colleagues), so it is always combined with a name.
- Sole proprietors and contacts with no account are left in as edge cases (`account_id` empty, or an account named after the person).

## Pipeline (one script per stage, files handed along in `data/`)
1. `generate.py` -> `data/accounts.csv`, `data/contacts.csv` + `data/answer_key.csv` (hidden `true_account_id` / `true_contact_id`). Mess: nicknames, typos, swapped names, Inc/LLC/Co, phone/address formats, old addresses, missing fields, plus look-alike non-duplicates (twins, father/son, similar company names).
2. `normalize.py` -> normalized fields + match keys (email, E.164 phone, name+ZIP, phonetic name, normalized company name, address).
3. `block.py` -> candidate pairs. Each pair records `block_keys` (which keys it shared).
4. `match.py ask` then `match.py decide`. `ask` runs hard rules in code (same phone and website for accounts, same email for contacts) and sends every other pair to Jev once: a holistic same-entity Score plus Noul signals for name agreement, conflicting details and lookalikes. Raw answers are saved, so `decide` can apply a policy (and `sweep.py` can tune thresholds) with no new calls.
   - Policy `signals` (main): evidence points added up, each signal named in the trace (Jev's name/conflict/lookalike answers plus code signals: shared phone, website, email, merged account, own address, title). Merge at 4.0 points or more, reject at 0.0 or less, review between.
   - Vetoes: a differing phone never auto-merges; a shared phone, website or email never auto-rejects. Both go to review.
   - Policy `single` (first design): the holistic Score alone. Kept so the two can be compared on the same answers.
5. `cluster.py` -> union-find groups from merged pairs.
6. `master.py` -> Jev scores per record in a group (completeness, recency, trustworthiness); code applies weights to pick the master. Optional field-level survivorship.
7. `evaluate.py` -> precision, recall, false-merge rate, review-queue size vs answer key; also a rules-only/fuzzy baseline for comparison.

## Match explanation (required)
Every pair decision writes: `decision`, `rule` (e.g. `exact_email`, `conflicting_id_block`, `jev_score`), `block_keys` that created the candidate, and for Jev decisions the raw Score, each Noul probability, confidence, and the threshold that fired. Every group merge traces back to the pairs, and each pair to its rule.

## Open defaults (change if wrong)
- 1,000 / 3,000 read as total records per file, not true entities.
- False merges treated as the costly error, so thresholds favor review over auto-merge.

## Run order
`experiments/customer-matching/run_all.sh` runs everything from the repo root (about 2,000 Jev calls). To re-tune, edit `MERGE_POINTS`/`REJECT_POINTS` in match.py and run `match.py decide` for both tables, then `cluster.py`, `evaluate.py`, `report.py` (no new Jev calls).

## Results (seed 7, run 2: accounts and contacts separate, contacts have their own addresses, per-signal policy)
Run 1 (single score, contacts inherited account addresses) is tagged `run-1-single-score`.
- Some true duplicates share only a name, so no method can prove them: 4 of 227 account pairs, 66 of 676 contact pairs. They are reported as "unprovable", not as misses.
- Accounts: precision 100%; recall 91.5% on provable pairs; 98.7% if the review queue (41 pairs, 20 true duplicates) is decided correctly.
- Contacts: precision 100%; recall 98.7% on provable pairs; review queue 19 pairs (after adding the mastered account id).
- Policy comparison on the same Jev answers: the single score gets 92.8% (accounts) and 98.7% (contacts) provable recall, the signals policy 91.5% and 98.4%. No accuracy gain from signals; the gain is the named evidence behind each decision.
- Caution: there were 0 false merges at every threshold tried, under either policy. The synthetic negatives are now too easy to tell the policies apart on precision. Next step is harder look-alikes and a second seed to check the thresholds were not fitted to seed 7.
- Master weights matter: with recency weighted 0.3 the clean original wins about 64% / 48% of groups; recency is random noise in the synthetic data.
