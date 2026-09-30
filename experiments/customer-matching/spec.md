# Customer record matching

Takes two messy, linked customer files (accounts and contacts), finds the duplicates, explains every decision, picks a master record for each group, and builds one golden record per real-world entity. Jev (TypeSafe System One) makes the judgment calls that code cannot; everything else is plain Python. The data is synthetic, so an answer key can grade the result.

## Run it
From the repo root:

```
experiments/customer-matching/run_all.sh     # builds data/ from scratch, about 120 Jev requests (one per ambiguous pair)
```

Then open `data/reports/report.html` (every pair decision) and `data/reports/golden_report.html` (golden records and their lineage). Another dataset: `SEED=23 ROUND=1 MATCH_DATA=data_other experiments/customer-matching/run_all.sh`.

## Layout
```
experiments/customer-matching/
  spec.md            this file
  run_all.sh         runs every script in order
  scripts/           generate, normalize, block, match, cluster, master, golden, evaluate, sweep, report, golden_report, paths
  data/
    source/          generated inputs: accounts.csv, contacts.csv, answer_key.csv (hidden truth, used only for grading)
    work/            in-between files: normalized records and match keys, candidate pairs, Jev answers, decisions, groups, masters
    golden/          the output: golden_accounts.csv, golden_contacts.csv, and separate phone and email tables
    reports/         report.html, golden_report.html
```

## Data
- `accounts.csv` (businesses): `account_id`, `name`, `website`, `phone`, `address`, `city`, `state`, `zip`, `industry`, `source_system`, `updated_at`.
- `contacts.csv` (people): `contact_id`, `account_id` (nullable), `first_name`, `last_name`, `email`, `phone`, `title`, `address`, `city`, `state`, `zip`, `source_system`, `updated_at`. A contact's address is their own (about a quarter have one), never a copy of the account's, so a shared address is not evidence that two colleagues are the same person.
- The sample dataset (seed 67): 169 account records (126 real accounts) and 344 contact records (276 real contacts), built from named scenarios, one per hard case, plus unrelated single records as background.

### Scenarios
`DUP` = the same entity appearing more than once, which must merge. `DISTINCT` = look-alikes, which must not.

| Table | Scenario | Kind | What it tests |
|---|---|---|---|
| accounts | exact_formatting | DUP | only case, St/Street and phone format differ |
| accounts | typo_suffix | DUP | name typo and different legal suffix; phone or website kept |
| accounts | moved_keeps_ids | DUP | new address, same phone and website |
| accounts | three_way | DUP | three records of one business |
| accounts | moved_lost_ids | DUP, unprovable | moved, and phone and website gone: nothing left to match on |
| accounts | sibling_locations | DISTINCT | same brand, two cities, different phones |
| accounts | shared_brand_website | DISTINCT | franchises sharing one website |
| accounts | same_name_other_trade | DISTINCT | "Summit Dental" vs "Summit Logistics" |
| contacts | nickname | DUP | Robert / Bob |
| contacts | swapped_typo | DUP | first and last swapped, plus a typo |
| contacts | initial_only | DUP | "R." vs "Robert" |
| contacts | email_changed | DUP | work email vs personal gmail, same phone |
| contacts | same_email_details_changed | DUP | same name, company and email; new phone and title |
| contacts | dup_account | DUP | one person attached to two duplicate variants of an account |
| contacts | account_vs_no_account | DUP | one record has its account, the other has none |
| contacts | no_account_email | DUP | no account, same personal email |
| contacts | jr_both_same | DUP | "Johnson Jr" on both records |
| contacts | no_account_name_only | DUP, unprovable | no account, only the name in common |
| contacts | junior_senior | DISTINCT | same name, company and address; own emails and phones |
| contacts | twins | DISTINCT | same last name, company and address; first names share an initial |
| contacts | namesakes_other_company | DISTINCT | same name at different companies |
| contacts | same_name_same_company | DISTINCT | two people, same name and company, different emails |
| contacts | shared_mailbox | DISTINCT | two people on `info@company` |
| contacts | shared_personal_email | DISTINCT | spouses sharing one gmail |
| contacts | phone_only_shared | DISTINCT | two people sharing one phone, no account |
| contacts | jr_sr_marked | DISTINCT | "Johnson Sr" and "Johnson Jr", own emails and phones |
| contacts | jr_marker_one_side | DISTINCT | "Johnson Jr" and plain "Johnson" |
| contacts | jr_sr_shared_details | DISTINCT | Sr and Jr sharing one email and one phone |

"Unprovable" pairs share nothing but a name, so no method could prove them. They are reported separately and are not counted as misses.

## Pipeline
Each script reads the previous stage's files. Accounts run first, and their result feeds the contact step.

1. `generate.py` writes the source files and the answer key. The scenario counts are at the top of the file.
2. `normalize.py` cleans names, phones, emails, addresses and company names, and builds match keys (`k_*` columns).
3. `block.py` turns shared keys into candidate pairs, and records which keys made each pair a candidate.
4. `match.py ask` applies the hard rules, then sends every other pair to Jev once with all questions. `match.py decide` applies a policy to the saved answers, so rules and thresholds can change with no new Jev calls.
5. `cluster.py` groups merged pairs (union-find) and flags any group that contains a pair that was not merged.
6. `master.py` picks a master record per group.
7. Step 1 of accounts ends here. Re-running `normalize.py` and `block.py` then gives every contact a `master_account_id` (its account's master record id). That id is a match key (`k_name_acct`, `k_initial_acct`: name plus master account), a signal (same company), and the account context Jev sees. Matching on master account alone is too broad (every pair of colleagues), so it is always combined with a name.
8. `golden.py` builds the golden records.
9. `evaluate.py`, `sweep.py`, `report.py`, `golden_report.py` grade and show the result.

## Decision rules
**Hard rules (code, no Jev call)**
- Accounts: same phone and same website merge (`same_phone_and_domain`).
- Contacts: the same email (not a role mailbox: info, sales, office, admin, support, contact, billing, hello, accounts, team) with a compatible name merges (`same_email`). Compatible means sound-alike first and last names (nicknames and typos), swapped order, or a bare initial against a full first name. Phone and title do not veto it, because people change both.
- Contacts: different generational suffixes (Jr and Sr, II and III) are a hard no-match (`generational_suffix_differs`).

**Jev questions per pair:** a same-entity Score (different / maybe / same), and Noul answers for name agreement, conflicting details, and look-alike.

**Policy `signals` (main):** evidence points are added up, and every signal is named in the trace. Jev's name, conflict and look-alike answers and its Score combine with code signals (shared phone, website, email, same master account, own address, title). Merge at 4.0 points or more, reject at 0.0 or less, review in between. The thresholds came from `sweep.py`. The alternative policy `single` (Jev's Score alone) is kept for comparison.

**Vetoes**
- A differing phone never auto-merges, and a merge where only one record has a Jr/Sr suffix goes to review.
- A shared phone, website or email never auto-rejects; it goes to review.

**Explanation:** every decision records `decision`, `rule`, `detail` (the signals and points, or the rule that fired), `block_keys`, and the raw Jev answers. Each group traces back to its merged pairs.

## Master and golden records
- **Master:** the record from the most trusted source system (`SOURCE_RANK` in `master.py`: erp, billing, crm, web_form, trade_show), and among those the most recently updated. Code only.
- **Golden record:** one per final entity, singles included. Each field starts from the master; blanks are filled from the next-best record in the same order. The address is filled as one block, so two addresses are never mixed.
- **Keys:** a golden record is keyed by its master's own record id (`golden_id` = `master_id`), so every id in the output is a real source id. A contact's `golden_account_id` is its master account's id. If records arrived over time, a better record joining a group would change the golden id, and a persistent surrogate id would be needed then.
- **Phones and emails** keep every distinct value in their own tables (`golden_*_phones.csv`, `golden_contact_emails.csv`) with source systems, record ids, latest update and a primary flag. `filled_from` on a golden row says which fields came from a record other than the master.

## Results (sample dataset)
| | Precision | Recall on provable pairs | Review queue |
|---|---|---|---|
| Accounts | 100% | 100% (43 of 43) | 6 pairs, all true non-duplicates |
| Contacts | 100% | 98.4% (62 of 63) | 20 pairs (1 true duplicate) |

- 0 false merges and 0 golden records that mix two real entities. Golden records: 131 accounts (126 real) and 282 contacts (276 real). The leftover splits are the unprovable pairs plus one email_changed pair in review.
- Every look-alike scenario ends in rejection or the review queue; none merges.
- On this data the `signals` policy and the `single` policy give identical results (100% and 98.4% recall on provable pairs, no false merges), so the dataset cannot rank them. The value of `signals` is that every decision names its evidence.
- Every master follows the source-then-recency rule (checked in `evaluate.py`).

## How it got here, and what it found
- Tests are the point: each scenario was added to find a rule gap, and the gap was fixed in the rules. Rule: never edit data to make a result pass; add scenarios as a new round.
- Found and fixed by scenarios: "R. Smith" never becoming a candidate (added `k_initial_acct`); shared `info@` mailboxes merging strangers (role mailboxes are not identifiers); a same-email rule that accepted "same initial, same last-name sound" for different first names (now stricter); a same-email rule exempted by differing phones; a father and son sharing one mailbox merging (generational suffix rules).
- Judgment calls by Dave: identical work email, name and company is one person (so the scenario became `same_email_details_changed`); source system before recency for masters; email and phone keep multiple values; contacts whose accounts were never merged stay in review for a data steward; Jr/Sr means different people; no review UI, because an HTML file cannot send decisions back.
- Tried and dropped: Jev-scored master selection (completeness, name cleanliness, recency weights); a company-domain signal; a local Nimble decision model via Ollama (9.5 GB, too slow and memory-hungry on a 16 GB Mac); a pure-Python replacement for the Jev questions was proposed, not built.

## Earlier datasets
Six earlier dataset folders were removed to leave one sample. They are all in git under the tag `before-cleanup`, and every one regenerates exactly from its seed: seeds 11, 23 and 37 with `ROUND=1`, seed 41 with `ROUND=2`, seed 53 with `ROUND=3`. Tags `run-1-single-score` and `run-2-signals` hold the first two designs (random 1,000 and 3,000 record sets).
