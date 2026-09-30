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
- `contacts.csv` (people): `contact_id`, `account_id` (nullable), `first_name`, `last_name`, `email`, `phone`, `title`, `address`, `city`, `state`, `zip`, `source_system`, `updated_at`.
- Dedupe runs twice, accounts against accounts and contacts against contacts. The two passes inform each other: two contacts with the same name at the same account are a stronger candidate pair, two accounts sharing contacts (same email or name) are a stronger account pair, and merging accounts repoints their contacts to the surviving account (which can expose new contact duplicates, so contacts run after accounts).
- Sole proprietors and contacts with no account are left in as edge cases (`account_id` empty, or an account named after the person).

## Pipeline (one script per stage, files handed along in `data/`)
1. `generate.py` -> `data/accounts.csv`, `data/contacts.csv` + `data/answer_key.csv` (hidden `true_account_id` / `true_contact_id`). Mess: nicknames, typos, swapped names, Inc/LLC/Co, phone/address formats, old addresses, missing fields, plus look-alike non-duplicates (twins, father/son, similar company names).
2. `normalize.py` -> normalized fields + match keys (email, E.164 phone, name+ZIP, phonetic name, normalized company name, address).
3. `block.py` -> candidate pairs. Each pair records `block_keys` (which keys it shared).
4. `match.py` -> decision per pair, in this order:
   - Hard rules in code (exact verified email, conflicting unique ID = never merge). Decision `rule` = rule name.
   - Everything else goes to Jev: one Score ("same customer": different / possibly same / same) + Noul companions (same person vs same household/company, conflicting hard identifiers). Thresholds in code, confidence-gated: auto-merge / review / no match.
5. `cluster.py` -> union-find groups from merged pairs.
6. `master.py` -> Jev scores per record in a group (completeness, recency, trustworthiness); code applies weights to pick the master. Optional field-level survivorship.
7. `evaluate.py` -> precision, recall, false-merge rate, review-queue size vs answer key; also a rules-only/fuzzy baseline for comparison.

## Match explanation (required)
Every pair decision writes: `decision`, `rule` (e.g. `exact_email`, `conflicting_id_block`, `jev_score`), `block_keys` that created the candidate, and for Jev decisions the raw Score, each Noul probability, confidence, and the threshold that fired. Every group merge traces back to the pairs, and each pair to its rule.

## Open defaults (change if wrong)
- 1,000 / 3,000 read as total records per file, not true entities.
- False merges treated as the costly error, so thresholds favor review over auto-merge.

## Run order (from repo root, `.venv/bin/python experiments/customer-matching/<script>.py`)
1. `generate`, `normalize`, `block`
2. `match accounts`, `cluster accounts`
3. `normalize`, `block` again (contacts now key on the merged account), then `match contacts`, `cluster contacts`
4. `master accounts`, `master contacts` (`--reuse` re-weights saved Jev answers without new calls)
5. `evaluate`

## Results (seed 7, `run_all.sh`)
- Some true duplicates share only a name (the generator moved the business or person and dropped other fields), so no method can prove them: 4 of 227 account pairs, 42 of 677 contact pairs. `evaluate.py` and the report list them as "unprovable" instead of counting them as misses.
- Accounts: precision 100%, recall 92.8% on provable pairs (98.2% on all if the review queue is resolved correctly).
- Contacts: precision 99.5%, recall 98.7% on provable pairs. 3 false merges left: two are a swapped-name record matching both a clean record and its variant, and one is two different people with an identical gmail address (a generator artifact: no-account contacts all get a gmail address without random digits).
- Hard rules: `same_phone_and_domain` (accounts) and `same_email` (contacts, unless both phones are present and differ). Junior decoys now have their own mailbox.
- Master weights matter: with recency weighted 0.3, the clean original wins about 65% / 53% of groups; with recency 0 it wins about 86% / 91%. Recency is random noise in the synthetic data, so this is a generator artifact until we decide how recency should really count.
