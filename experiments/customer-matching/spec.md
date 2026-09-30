# Customer record matching: spec

Goal: dedupe a messy synthetic customer file, explain every match, pick a master per group.

## Decisions
- Entities: people and businesses (mixed in one file).
- Scale: 6,000 records total (~4,000 true entities, ~2,000 duplicate variants). Synthetic only, no real data, no PII concerns.
- Output: scripts only (terminal report + CSV/JSON files). UI later.
- Language: Python 3.13, `.venv`, `typesafe-sdk`.
- Lives in `experiments/customer-matching/`. Run scripts from the repo root, e.g. `.venv/bin/python experiments/customer-matching/generate.py`.

## File layout: one file, both types
`customers.csv` holds people and businesses together, like a real CRM export. Columns: `record_id`, `record_type` (person/business), `first_name`, `last_name`, `company_name`, `email`, `phone`, `address`, `city`, `state`, `zip`, `source_system`, `updated_at`. Person rows leave `company_name` mostly empty; business rows leave the name fields empty (or hold a contact). Kept together because cross-type matches are real (a sole proprietor as person and business, a contact listed under their company). Normalization and blocking branch on `record_type`, and cross-type candidates are allowed.

## Pipeline (one script per stage, files handed along in `data/`)
1. `generate.py` -> `data/customers.csv` + `data/answer_key.csv` (hidden `true_entity_id`). Mess: nicknames, typos, swapped names, Inc/LLC/Co, phone/address formats, old addresses, missing fields, plus look-alike non-duplicates (twins, father/son, similar company names).
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
- "6,000" read as total records, not true customers.
- False merges treated as the costly error, so thresholds favor review over auto-merge.
