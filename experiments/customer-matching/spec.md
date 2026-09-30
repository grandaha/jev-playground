# Customer record matching: spec

Goal: dedupe a messy synthetic customer file, explain every match, pick a master per group.

## Decisions
- Entities: businesses (accounts) and people (contacts), in separate linked files.
- Scale: a small targeted set, 169 account records (126 true accounts) and 244 contact records (196 true contacts), built from named scenarios (see below). Synthetic only, no real data, no PII concerns.
- Output: scripts only (terminal report + CSV/JSON files). UI later.
- Language: Python 3.13, `.venv`, `typesafe-sdk`.
- Lives in `experiments/customer-matching/`. Run scripts from the repo root, e.g. `.venv/bin/python experiments/customer-matching/generate.py`.

## Files: accounts and contacts (Salesforce-style)
- `accounts.csv` (businesses): `account_id`, `name`, `website`, `phone`, `address`, `city`, `state`, `zip`, `industry`, `source_system`, `updated_at`.
- `contacts.csv` (people): `contact_id`, `account_id` (nullable), `first_name`, `last_name`, `email`, `phone`, `title`, `address`, `city`, `state`, `zip`, `source_system`, `updated_at`. A contact's address is their own (about a quarter have one), never a copy of the account's, so address is not treated as evidence for colleagues at one company.
- Two steps; the output of the first is an input to the second. Step 1 matches accounts, clusters them, and picks a master account per group (`master.py accounts`). Step 2 gives every contact a `master_account_id` (its account's master) in `contacts_norm.csv`. That id is a match key (`k_name_acct`: swap-proof name plus master account), a signal (`same_account`), and the account context Jev sees for each contact, so two contacts whose accounts were duplicates now count as the same company. Matching contacts on master account alone is too broad (every pair of colleagues), so it is always combined with a name.
- Sole proprietors and contacts with no account are left in as edge cases (`account_id` empty, or an account named after the person).

## Pipeline (one script per stage, files handed along in `data/`)
1. `generate.py` -> `data/accounts.csv`, `data/contacts.csv` + `data/answer_key.csv` (hidden `true_id`, `kind`, `scenario`). One named scenario per hard case; the counts are in `ACCOUNT_SCENARIOS` / `CONTACT_SCENARIOS` at the top of the file.
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

## Scenarios
Duplicates the pipeline should merge (DUP) and look-alikes it must not (DISTINCT). `evaluate.py` and the report break results down by scenario.
- Accounts DUP: exact_formatting, typo_suffix, moved_keeps_ids, three_way, and moved_lost_ids (unprovable: moved with no phone or website left).
- Accounts DISTINCT: sibling_locations (same brand, two cities), shared_brand_website (franchise), same_name_other_trade.
- Contacts DUP: nickname, swapped_typo, initial_only, email_changed, dup_account (person attached to two duplicate variants of an account), no_account_email, and no_account_name_only (unprovable).
- Contacts DISTINCT: junior_senior, twins, namesakes_other_company, same_name_same_company, shared_mailbox (two people on info@company).
- Plus single unrelated records as background (40 accounts, 80 contacts).

## Results (seed 11, targeted set)
Run 1 (random 1,000/3,000 set, single score) is tagged `run-1-single-score`; run 2 (random set, signals policy) is tagged `run-2-signals`.
- Accounts and contacts: 0 false merges and 100% recall on provable pairs (43 of 48 duplicate pairs each; the other 5 share only a name). The unprovable ones are never merged, as intended.
- Look-alikes: siblings and twins are rejected; franchise accounts sharing a website (6 pairs), junior/senior (3) and same-name-same-company (1) go to a review queue rather than merging.
- Two real bugs the scenarios found, both fixed: (1) "R. Smith" vs "Robert Smith" was never proposed as a pair, so contacts now also block on first initial + last-name sound + master account (`k_initial_acct`); (2) the same-email hard rule merged three different people sharing `info@`, so role mailboxes (info, sales, office, admin, support, contact, billing, hello, accounts, team) are no longer treated as identifiers.
- Both policies (signals and single score) score the same on this set, so it cannot yet say which is better. The set is small (about 50 duplicate pairs per table) and was shaped while reading results, so a second seed is still needed before trusting it.
- One contact in `dup_account` is never proposed: its account's two records were never merged (an unprovable moved account), so the contacts do not share a master account. That is the two-step flow working as designed, and a consequence of the account miss.

## Holdout runs (same code, same thresholds)
`MATCH_DATA=data_seed2 SEED=23 experiments/customer-matching/run_all.sh`, and `data_seed3` with `SEED=37`. The sets are never mixed.
Fixed after reading the seed 23 results (so seed 23 stopped being a clean holdout and seed 37 was generated afterwards as a fresh one):
- Generator: two random people could be given the same name at the same company, and their emails (built from the name) then collided. Random names are now redrawn so one name and company means one person; same-name scenarios stay intentional.
- Rule: an identical non-role email with a compatible name (nickname, initial, swapped order) is a hard merge even when the phones differ. The old phone exemption only protected junior decoys, which now have their own emails.

| Seed | False merges | Accounts recall (provable) | Contacts recall (provable) | Contacts in review that are true duplicates |
|---|---|---|---|---|
| 11 (tuned on) | 0 | 100% | 95.3% | 2 |
| 23 (used to find the two fixes) | 0 | 100% | 95.3% | 2 |
| 37 (fresh) | 0 | 100% | 100% | 0 |

Open finding: the 2 contact true duplicates in review (seeds 11 and 23) are people whose accounts were never merged (an account pair left unmerged, e.g. a moved business), so the `different_account` penalty (-2) applies to two records that share a company email domain and often a phone. A company-domain signal would fix them, but adding it now would be tuning on these sets again, so it is left for a decision.
- The master-record proxy is still low (recency 0.3 on random dates). Still open.

## Round 2: new scenarios, fresh seed 41 (`data_round2/`)
`ROUND=2 MATCH_DATA=data_round2 SEED=41 experiments/customer-matching/run_all.sh`. `ROUND=2` only adds scenarios; the seed 11, 23 and 37 data are byte-identical to before (checked with cmp). Rule: never edit data to make a result pass, so fixes are to rules.
New contact scenarios: `shared_personal_email` (spouses sharing one gmail, DISTINCT), `phone_only_shared` (two people, one phone, no account, DISTINCT), `account_vs_no_account` (one record lacks its account, DUP), and `same_email_details_changed` (same name, company and work email, second record has a new phone and title, DUP).
- `account_vs_no_account` 8 of 8 and `same_email_details_changed` 6 of 6 merged. `phone_only_shared` and `shared_personal_email`: all pairs go to review, none merged.
- `shared_personal_email` first merged 1 of 6 spouse pairs: the same-email rule's name check accepted "same first initial and last-name sound" (Maria Lopez and Marcus Lopez). Fixed in the rule: an initial only matches when one side is a bare initial; otherwise first names must sound alike or be swapped.
- This scenario was first written as `namesake_identical_email` (two different people with identical name, company and email). Dave's judgment: identical work email, name and company is one person, and a work email belongs to one person; real namesakes get different addresses (covered by `same_name_same_company`). The scenario was replaced with `same_email_details_changed` and round 2 was regenerated. The earlier version is in git history.
- Result: 0 false merges; contacts recall on provable pairs 94.7% (3 true duplicates in review: one `dup_account`, one `initial_only`, one `swapped_typo`).
