# Customer record matching with Jev

This project finds duplicate customers in two messy, linked files: accounts (businesses) and contacts (people). It explains every decision, picks a master record for each group, and builds one golden record for each real-world entity.

Jev (TypeSafe System One) makes the judgment calls that code cannot. Everything else is plain Python. The data is synthetic, so an answer key can grade the result.

## What you get

- A reason for every decision. Each pair records the rule or the evidence that decided it, for example `+8.2 points: phone_equal +3.0, name_same +2.6, holistic_score +1.5, street_equal +1.5, lookalike -0.3, details_conflict -0.2`.
- A test for each hard case. 28 scenarios cover the duplicates that must merge, such as a nickname, a moved business or a swapped name. They also cover the look-alikes that must stay apart: twins, franchises, a father and son, and two people on one `info@` mailbox.
- Golden records with lineage. Every field shows which source record supplied it. Every email and phone number stays, with its source system.

## See the result without an API key

The saved Jev answers are in the repo, so you can rebuild every result with no key and no network calls. From the repo root:

```
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
experiments/customer-matching/replay.sh
```

Then open two files in `experiments/customer-matching/data/reports/`:

- `report.html` shows every pair decision, with both records side by side, the rule that fired and whether the answer key agrees.
- `golden_report.html` shows each golden record, where every value came from, and which rules joined its records.

## Run it yourself

Create a key at [console.typesafe.ai](https://console.typesafe.ai/) and put it in a `.env` file in the repo root:

```
TYPESAFE_API_KEY=your-key
```

Then run `experiments/customer-matching/run_all.sh`. It builds the dataset from scratch and sends Jev about 120 requests, one per ambiguous pair.

## How it works

1. Normalize names, phones, emails, addresses and company names, and build match keys.
2. Turn shared keys into candidate pairs.
3. Decide each pair. Hard rules in code settle the clear cases, such as the same email with a compatible name. Jev answers four questions about every other pair. Is it the same entity? Do the names agree? Do the details conflict? Is it a look-alike? Code adds up the evidence and decides to merge, reject or send the pair to review.
4. Match the accounts first and pick a master account for each group. Each contact then gets its master account as a match key, so two contacts at duplicate accounts count as the same company.
5. Pick a master record for each group: the most trusted source system, then the most recent update. Fill its blanks from the other records to make the golden record.

## Results

| | Precision | Recall on provable pairs | Review queue |
|---|---|---|---|
| Accounts | 100% | 100% (43 of 43) | 6 pairs |
| Contacts | 100% | 98.4% (62 of 63) | 20 pairs |

No false merges. The sample set has 169 account records (126 real accounts) and 344 contact records (276 real contacts). They become 131 golden accounts and 282 golden contacts. Five duplicate pairs in each file share only a name, so nothing in the records can prove them. The results list them apart from the misses.

## What the tests found

Three rule gaps turned up, and each got a fix in the rules:

- "R. Smith" never became a candidate for "Robert Smith". Contacts now also match on first initial, last-name sound and master account.
- Two people on one `info@` mailbox merged. Role mailboxes no longer count as identifiers.
- A father and son sharing one mailbox merged. Generational suffixes such as Jr and Sr now mark different people.

## Limits

- The author wrote both the scenarios and the rules. The results show the method works on these cases. No test covers accuracy on your data.
- The test set is small: 48 duplicate pairs in the accounts and 68 in the contacts. The two designs (Jev's score alone, and Jev plus the evidence rules) give identical results here, so the set cannot rank them.

Start with [spec.md](spec.md) for the full design: the scenarios, the rules and the decisions behind them.
