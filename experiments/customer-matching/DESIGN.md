# Design: customer record matching

This document describes how the project works and what it found. The [README](README.md) is the short introduction.

The project finds duplicates in two messy, linked customer files (accounts and contacts). It explains every decision, picks a master record for each group, and builds one golden record for each real-world entity. Jev (TypeSafe System One) makes the judgment calls that code cannot, and plain Python does everything else. Jev returns typed answers with probabilities, not text. The data is synthetic, so an answer key can grade the result.

## Run it
From the repo root:

```
experiments/customer-matching/run_all.sh     # builds data/ from scratch, about 120 Jev requests (one per ambiguous pair)
experiments/customer-matching/replay.sh      # rebuilds every result from the saved Jev answers: no API key, no network
```

Then open `data/reports/report.html` (every pair decision) and `data/reports/golden_report.html` (golden records and their lineage). To build another dataset, run `SEED=23 ROUND=1 MATCH_DATA=data_other experiments/customer-matching/run_all.sh`.

## Layout
```
experiments/customer-matching/
  README.md          the short introduction
  DESIGN.md          this file: the full design
  run_all.sh         runs every script in order, asking Jev
  replay.sh          runs the same steps from the saved Jev answers, with no API key
  scripts/           generate, normalize, block, match, cluster, master, golden, evaluate, sweep, report, golden_report, paths
  data/
    source/          generated inputs: accounts.csv, contacts.csv, answer_key.csv (hidden truth, used only for grading)
    work/            in-between files: normalized records and match keys, candidate pairs, Jev answers, decisions, groups, masters
    golden/          the output: golden_accounts.csv, golden_contacts.csv, and separate phone and email tables
    reports/         report.html, golden_report.html
```

## Data
- `accounts.csv` (businesses): `account_id`, `name`, `website`, `phone`, `address`, `city`, `state`, `zip`, `industry`, `source_system`, `updated_at`.
- `contacts.csv` (people): `contact_id`, `account_id` (nullable), `first_name`, `last_name`, `email`, `phone`, `title`, `address`, `city`, `state`, `zip`, `source_system`, `updated_at`. A contact's address is their own, and about a quarter of contacts have one. It is never a copy of the account's address, so a shared address is no evidence that two colleagues are the same person.
- The sample dataset (seed 67) has 169 account records (126 real accounts) and 344 contact records (276 real contacts). The author built it from named scenarios, one per hard case, plus unrelated single records as background.

### Scenarios
"Merge" means the same entity appears more than once and the pipeline must merge the records. "Keep apart" means look-alikes that must stay separate.

| Table | Scenario | Expected | What it tests |
|---|---|---|---|
| accounts | exact_formatting | merge | only case, St/Street and phone format differ |
| accounts | typo_suffix | merge | name typo and different legal suffix; phone or website kept |
| accounts | moved_keeps_ids | merge | new address, same phone and website |
| accounts | three_way | merge | three records of one business |
| accounts | moved_lost_ids | merge (unprovable) | moved, and phone and website gone: nothing left to match on |
| accounts | sibling_locations | keep apart | same brand, two cities, different phones |
| accounts | shared_brand_website | keep apart | franchises sharing one website |
| accounts | same_name_other_trade | keep apart | "Summit Dental" vs "Summit Logistics" |
| contacts | nickname | merge | Robert / Bob |
| contacts | swapped_typo | merge | first and last swapped, plus a typo |
| contacts | initial_only | merge | "R." vs "Robert" |
| contacts | email_changed | merge | work email vs personal gmail, same phone |
| contacts | same_email_details_changed | merge | same name, company and email; new phone and title |
| contacts | dup_account | merge | one person attached to two duplicate variants of an account |
| contacts | account_vs_no_account | merge | one record has its account, the other has none |
| contacts | no_account_email | merge | no account, same personal email |
| contacts | jr_both_same | merge | "Johnson Jr" on both records |
| contacts | no_account_name_only | merge (unprovable) | no account, only the name in common |
| contacts | junior_senior | keep apart | same name, company and address; own emails and phones |
| contacts | twins | keep apart | same last name, company and address; first names share an initial |
| contacts | namesakes_other_company | keep apart | same name at different companies |
| contacts | same_name_same_company | keep apart | two people, same name and company, different emails |
| contacts | shared_mailbox | keep apart | two people on `info@company` |
| contacts | shared_personal_email | keep apart | spouses sharing one gmail |
| contacts | phone_only_shared | keep apart | two people sharing one phone, no account |
| contacts | jr_sr_marked | keep apart | "Johnson Sr" and "Johnson Jr", own emails and phones |
| contacts | jr_marker_one_side | keep apart | "Johnson Jr" and plain "Johnson" |
| contacts | jr_sr_shared_details | keep apart | Sr and Jr sharing one email and one phone |

"Unprovable" pairs share nothing but a name, so nothing in the records can prove them. The results list them apart from the misses.

## Pipeline
Each script reads the files the previous stage wrote. Accounts run first, and their result feeds the contact step.

1. `generate.py` writes the source files and the answer key. The scenario counts sit at the top of the file.
2. `normalize.py` cleans names, phones, emails, addresses and company names, and builds match keys (the `k_*` columns).
3. `block.py` turns shared keys into candidate pairs, and records which keys made each pair a candidate.
4. `match.py ask` applies the hard rules, then sends every other pair to Jev once with all its questions. `match.py decide` applies a policy to the saved answers, so rules and thresholds can change with no new Jev calls.
5. `cluster.py` groups merged pairs (union-find) and flags any group that holds a pair the rules did not merge.
6. `master.py` picks a master record for each group.
7. The account steps end here. Running `normalize.py` and `block.py` again gives every contact a `master_account_id`, the record id of its account's master. That id is a match key (`k_name_acct` and `k_initial_acct`: name plus master account), a signal (same company), and the account context Jev sees. Master account alone is too broad a key, because it pairs every two colleagues, so it always comes with a name.
8. `golden.py` builds the golden records.
9. `evaluate.py`, `sweep.py`, `report.py` and `golden_report.py` grade the result and show it.

## Decision rules

### Hard rules (code, no Jev call)
- Accounts: the same phone and the same website merge (`same_phone_and_domain`).
- Contacts: the same email with a compatible name merges (`same_email`). Role mailboxes do not count as identifiers: info, sales, office, admin, support, contact, billing, hello, accounts and team. A compatible name means sound-alike first and last names (nicknames and typos), swapped order, or a bare initial against a full first name. Phone and title do not veto the merge, because people change both.
- Contacts: different generational suffixes, such as Jr and Sr, are a hard no-match (`generational_suffix_differs`).

### Jev questions
Jev answers four questions about each remaining pair. A Score asks whether it is the same entity (different, possibly the same, or the same). Three Noul questions, each a yes-or-no with a probability, ask whether the names agree, whether the details conflict, and whether the pair is a look-alike.

### Policy `signals` (main)
- Code adds up evidence points. Jev's answers combine with code signals: a shared phone, website or email, the same master account, the same own address, and the same title.
- Code merges a pair at 4.0 points or more, rejects it at 0.0 or less, and sends it to review in between. `sweep.py` produced these thresholds.
- Every signal appears by name in the decision trace.
- The alternative policy `single` (Jev's Score alone) stays in for comparison.

### Vetoes
- A pair with different phone numbers never auto-merges. A merge where only one record has a Jr or Sr suffix goes to review.
- A pair that shares a phone, website or email never auto-rejects. It goes to review.

### Explanation
Every decision records its `decision` and its `rule`. It also records `detail` (the signals and points, or the rule that fired), the `block_keys` that made it a candidate, and the raw Jev answers. Each group traces back to its merged pairs.

## Master and golden records
- The master is the record from the most trusted source system, then the most recently updated (`SOURCE_RANK` in `master.py`: erp, billing, crm, web_form, trade_show). Code decides this, with no Jev call.
- A golden record exists for every final entity, singles included. Each field starts from the master, and the next-best record fills any blank, in the same order. The address fills as one block, so two addresses never mix.
- A golden record takes its master's own record id (`golden_id` equals `master_id`), so every id in the output is a real source id. A contact's `golden_account_id` is its master account's id. If records arrived over time, a better record joining a group would change the golden id, and you would need a persistent surrogate id.
- Phones and emails keep every distinct value in their own tables (`golden_*_phones.csv` and `golden_contact_emails.csv`). Each row shows the source systems, the record ids, the latest update and a primary flag. `filled_from` on a golden row lists the fields that came from a record other than the master.

## Results (sample dataset)
| | Precision | Recall on provable pairs | Review queue |
|---|---|---|---|
| Accounts | 100% | 100% (43 of 43) | 6 pairs, all true non-duplicates |
| Contacts | 100% | 98.4% (62 of 63) | 20 pairs (1 true duplicate) |

- There are no false merges, and no golden record mixes two real entities. The 131 golden accounts come from 126 real accounts, and the 282 golden contacts from 276 real contacts. The leftover splits are the unprovable pairs plus one `email_changed` pair in review.
- Every look-alike scenario ends in rejection or the review queue, and none merges.
- The `signals` policy and the `single` policy give identical results here: 100% and 98.4% recall on provable pairs, and no false merges. The dataset cannot rank them. The value of `signals` is that every decision names its evidence.
- Every master follows the source-then-recency rule, and `evaluate.py` checks it.

## What the tests found
Each scenario exists to find a rule gap, and the author fixed every gap in the rules, never in the data. To add a scenario, add a new round with a new seed.

- "R. Smith" never became a candidate for "Robert Smith". The fix is the `k_initial_acct` key.
- Two people on one `info@` mailbox merged. Role mailboxes no longer count as identifiers.
- The same-email rule accepted "same first initial, same last-name sound" for different first names, so Maria Lopez and Marcus Lopez merged. The rule now needs a bare initial on one side, or first names that sound alike.
- An old exemption let the same-email rule ignore different phones. That exemption protected a case the data no longer had, so the author removed it.
- A father and son sharing one mailbox merged. Generational suffix rules now keep them apart.

## Choices the author made
- Identical work email, name and company means one person. A work email belongs to one person, and real namesakes get different addresses.
- The master comes from the source system first, then recency.
- Email and phone keep every value, in separate tables.
- Contacts at accounts the pipeline never merged stay in the review queue for a data steward.
- Jr and Sr mean different people.
- There is no review interface, because an HTML file cannot send decisions back.

## Tried and dropped
- Jev-scored master selection, which weighed completeness, name cleanliness and recency.
- A company email-domain signal for contacts at unmerged accounts.
- A local Nimble decision model through Ollama. The 9.5-gigabyte model swapped heavily on a 16-gigabyte Mac, and requests took minutes.
- A pure-Python replacement for the Jev questions. The author proposed it and did not build it.

## Earlier datasets
The repo's first runs used random sets of 1,000 account records and 3,000 contact records. The design then moved to scenario-built sets.

Five earlier scenario datasets came and went, and the sample in `data/` is the last one, the full set. They regenerate exactly from their seeds: seeds 11, 23 and 37 with `ROUND=1`, seed 41 with `ROUND=2`, and seed 53 with `ROUND=3`. The tag `before-cleanup` holds their saved files. The tags `run-1-single-score` and `run-2-signals` hold the first two designs.
