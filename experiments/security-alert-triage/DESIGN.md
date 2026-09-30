# Design: security alert triage with Jev

Status: draft for review. Nothing is built yet.

This experiment triages security alerts. For each alert it decides whether the alert is a real threat, how serious it is, and what to do. It groups related alerts into incidents and ranks which employee accounts are most likely compromised or targeted.

Jev (TypeSafe System One) makes the judgment calls. Code makes the decisions and keeps the evidence. The alerts are synthetic, so an answer key can grade every result.

It is defensive only. The alerts describe what a detector saw. They contain no attack steps or tooling.

## What success looks like
1. No missed real attacks. The headline number is how many real alerts and real incidents the pipeline closes or never escalates. The goal is zero, and the result always shows the queue cost next to it.
2. A smaller queue. A person reads far fewer items than the alerts that came in, and noise closes with a reason.
3. Every decision explains itself. Each alert, incident and account score shows the rule and the evidence behind it.
4. A clear view of what Jev adds. Each stage also runs as plain rules, so the two can be compared on the same alerts.
5. A ranking of the accounts most likely compromised or targeted, with the evidence behind each score.

The costly mistake here is the reverse of record matching. A false merge was the worst error there. Here the worst error is closing the alert of a real attack, so the design leans toward escalating.

## Where Jev is used, and why
Jev is called at two points: once for each alert, and once for each pair of alerts that might belong together. Code does everything else. This section lists every question, what goes in, what comes back, and what code does with each answer.

**Why a model at all.** The difference between an attack and its harmless look-alike sits in the words of the alert, not in a field a rule can test. "Sign-in from a country never seen for this user, on an unregistered device, right after a password reset" is an attack. "First sign-in from a new country on the user's registered laptop, and the calendar shows a flight that day" is a trip. Both arrive under the same kind of rule at the same detector severity. A rules-only baseline can use the severity and two lists, so it escalates the trip and misses the quiet attacks. Jev reads the evidence and returns probabilities. Code then decides how cautious to be.

### Call 1: judge one alert
**When it runs.** Once for every alert, except alerts the allowlist already closes. Alerts on the never-suppress list are still asked, because Jev decides whether they escalate or only get investigated.

**What goes in.** The alert's own fields: time, detector, rule name, description, the detector's severity, user, host, source and destination address, and the tactic the detector claims. Two items of context go with it: the asset's criticality and the user's access level. A note says the detector's severity and tactic are its own guesses and are sometimes wrong. No field from the answer key is ever sent.

**The four questions, exactly as they appear in `scripts/ask.py`:**

```
disposition (Choice)
  Is this alert a real attack, a false alarm, or real but authorized activity?
  true_positive          Real malicious activity that needs a response.
  false_positive         Benign activity that only looked suspicious, or a detector misfire.
  benign_true_positive   Real behavior that is authorized or expected, such as an approved admin task, a scheduled job or an authorized security test.

impact (Score)
  If this alert is real, how much damage could it do to the company?
  0  Minimal: no sensitive data or systems are at risk.
  1  Limited: one account or workstation is affected and the damage is easy to contain.
  2  Serious: sensitive data or an important system is at risk, or several accounts are affected.
  3  Severe: customer data, crown-jewel systems or company-wide operations are at risk.

stage (Choice)
  Which attacker goal does this activity serve?
  reconnaissance         Gathering information about the company to plan an attack.
  resource_development   Setting up infrastructure or accounts to support an attack.
  initial_access         Getting a first foothold, for example through phishing or a stolen sign-in.
  execution              Running attacker-controlled code.
  persistence            Keeping access across restarts and password changes.
  privilege_escalation   Gaining higher permissions.
  stealth                Hiding actions so they look normal.
  defense_impairment     Turning off or weakening security tools and logging.
  credential_access      Stealing or guessing account credentials.
  discovery              Mapping the environment to decide where to go next.
  lateral_movement       Moving from one system to another.
  collection             Gathering the data the attacker wants.
  command_and_control    Communicating with compromised systems from outside.
  exfiltration           Stealing data out of the company.
  impact                 Disrupting, encrypting or destroying systems and data.

benign_explanation (Noul)
  Does an ordinary, authorized explanation fit the evidence in this alert?
```

**What comes back.** The two Choice questions return a probability for each option. The impact Score returns a number from 0 to 3. The Noul question returns a probability of yes.

**What code does with each answer.**
- `disposition`: call the probability of `true_positive` *p*. At *p* of 0.60 or more the alert escalates. A never-suppress alert below that is investigated. At *p* of 0.15 or more the alert is investigated. Below that, the alert closes only if every closing condition holds. The probability of `false_positive` plus `benign_true_positive` must be 0.90 or more. The `benign_explanation` answer must be 0.80 or more. No other alert on the same user or host within 72 hours may doubt it. That means being on the never-suppress list, being unanswered (an alert the allowlist closed does not count as unanswered), or having a *p* of 0.15 or more. If any condition fails, the alert is investigated. An alert with no answer is investigated too.
- `impact`: multiplied by *p* to give the finding's risk (impact divided by 3, times 100, times *p*). That risk feeds the account score, and the impact sets an incident's severity.
- `stage`: not used for any decision in this build. Its answer is compared with the answer key and with the detector's claimed tactic. That measures whether Jev maps alerts to attack stages better than detectors do. A later round may use it for a decision only if that measurement earns it.
- `benign_explanation`: a second, separate check, so that closing an alert never rests on one answer.

The thresholds live in `decide.Policy`. A sweep over the saved answers picks them on one seed, and a fresh seed checks them.

On seed 101 every sweep setting (escalate 0.4 to 0.7, close 0.8 to 0.95, explanation 0.6 to 0.9) missed no real alert, so the sweep could not choose between them. The defaults keep the stricter closing conditions (0.90 and 0.80) because the design leans toward escalating and closing is the risky choice. The queue is 656 of 1,042 alerts at these defaults, against 621 at the loosest setting. The escalate threshold does not change the queue. Real incidents with no escalated alert were 0 at escalate 0.4, 0.5 and 0.6, and 2 at 0.7. Benign alerts escalated were 114 at all four. A lower value reduces neither count below 0.60, so it stays at 0.60. The queue is large because Jev over-calls real attacks on this data: 161 alerts score above 0.60, and only 47 of them are real (the other 114 are false positives). Nothing here is evidence beyond "no real alert missed on one seed"; a fresh seed has to test it.

**Why these questions.** The disposition has three options because security teams treat "real but authorized" differently from "false alarm". The first is closed quietly. The second points at a detector that needs tuning. The impact question exists because detector severity is unreliable and account risk needs an honest measure of damage.

**What the rules-only baseline does instead.** It escalates high and critical detector severities, investigates medium, closes low and informational, and applies the never-suppress list and the allowlist. It cannot read the description.

### Call 2: judge a pair of alerts
**When it runs.** For every candidate pair, meaning two alerts that share a user, host or address within 72 hours. The obvious-link rule (same user and same host within 30 minutes) settles some pairs without a call.

**What goes in.** Both alerts' fields, and the list of entities they share.

**The two questions, exactly as they appear in `scripts/ask.py`:**

```
same_incident (Score)
  Are these two alerts part of the same attack or event?
  0  They are unrelated events that only share a name or address.
  1  They might be related, but the evidence is thin.
  2  They are clearly steps of the same attack or the same event.

shared_entity_is_coincidence (Noul)
  Is the shared user, host or address a coincidence, for example a shared office or guest network address used by many people?
```

**What code does with the answers.** A pair links when the `same_incident` Score is 1.8 or more and the coincidence probability is below 0.5. Linked pairs cluster into incidents. A pair with no answer is not linked, and each of its alerts still gets its own decision.

**Result on seed 101.** We asked Jev about 1,376 of the 1,393 candidate pairs, with 0 errors. Code settled the other 17.

Jev links 279 alert pairs into 917 groups. It gets 216 of the 225 true pairs, so recall is 96% and precision is 77%, against 4% for the baseline. One group holds two different real incidents, down from six. It joins two `benign_pentest` incidents that Jev scored 1.8 to 1.97 as the same event. The `shared_address` strangers are not linked at all. The 9 missed links are all `benign_backup`.

The threshold started at 1.6. At 1.6 the `two_incidents_one_user` pairs (one user's travel alerts and phishing alerts) scored up to 1.78 and merged. We moved it to 1.8 after seeing this data. That is a value tuned on one seed, so a fresh seed has to test it. Recall falls to 77% at 1.9.

**Why Jev here.** Sharing an entity is weak evidence. Many unrelated users sit behind one guest-network address, and unrelated incidents touch the same server. In the other direction, a real incident's alert can lose its user field. Telling these apart means reading the two descriptions together and asking whether one is the next step of the other. The coincidence question exists so that a shared address does not link strangers.

**What the baseline does instead.** It links every candidate pair, which over-links.

### Account risk
Account risk makes no Jev call of its own. It uses the `impact` and the probability *p* from Call 1 and does the arithmetic in code (see Account risk below).

### What Jev never decides
- Whether to close an alert. Code closes, and only when every condition above holds.
- The never-suppress list and the allowlist. They are fixed rules.
- Thresholds and weights. Code sets them and the answer key checks them.
- Obvious links, the clustering of linked pairs, the account score and every metric.
- Anything about a person. No question asks about an employee. Every question is about an alert.

## Standards this design follows
- **Triage outcomes.** Security operations center (SOC) teams sort each alert into one of three outcomes. A true positive is real malicious activity. A false positive is benign activity that looked bad. A benign true positive is real but authorized behavior, such as an admin using a remote tool. The team then closes, investigates or escalates the alert ([CyberDefenders](https://cyberdefenders.org/blog/alert-triage-process/), [Corelight](https://corelight.com/resources/glossary/alert-triage)). Guides also keep a never-suppress list: privilege escalation, data leaving to unknown destinations, and command-and-control traffic ([Blink Ops](https://www.blinkops.com/blog/alert-triage)).
- **Attack stages.** MITRE ATT&CK describes an attacker's goals as tactics. The current page lists 15, from Reconnaissance and Initial Access through Lateral Movement to Exfiltration and Impact ([MITRE ATT&CK](https://attack.mitre.org/tactics/enterprise/)).
- **Alert shape.** The Open Cybersecurity Schema Framework (OCSF) and Elastic Common Schema (ECS) both define alerts. Each alert has a severity, entities, a timestamp and an ATT&CK mapping ([Deepwatch](https://www.deepwatch.com/glossary/open-cybersecurity-schema-framework-ocsf/)). A source's own severity is a judgment the source makes, and ECS leaves it as an uncontrolled number ([Security Data Works](https://securitydataworks.com/writing/ocsf/six-schemas-into-ocsf/)). The design never takes it as the answer.
- **Grouping.** Microsoft Sentinel groups alerts that share mapped entities (account, host, address) inside a time window. The default is 5 hours, and it can be set from 5 minutes to 7 days ([Microsoft](https://learn.microsoft.com/en-us/azure/sentinel/create-incidents-from-alerts)).
- **Risk scores.** Splunk's risk-based alerting scores a finding as impact times confidence divided by 100. It rolls each entity up into a 0 to 100 score over 7 days, weighing frequency, severity and uniqueness ([Splunk](https://help.splunk.com/en/splunk-enterprise-security-8/administer/8.3/risk-based-alerting/entity-risk-scoring-in-splunk-enterprise-security)). This design uses the same ingredients in its own formula.
- **Priority.** NIST SP 800-61 Rev. 3 says to prioritize by business impact, not only technical severity ([Industrial Cyber](https://industrialcyber.co/nist/nist-publishes-sp-800-61-rev-3-overhauling-incident-response-guidance-for-csf-2-0/)). Each alert therefore carries asset and user context.

## Guardrails
- Every name, company, host and address is fictional. Addresses come from the reserved documentation ranges (192.0.2.0/24, 198.51.100.0/24 and 203.0.113.0/24), and domains use `example.com`. No real logs or people appear.
- The account ranking measures security events, never a person. It is an input for a human to review and never a verdict. The only personal context it uses is access level.
- The repo never edits the data to make a result pass. A failing case means the rules are wrong. New hard cases arrive as a new round with a new seed.

## Data
### The alert
A simplified subset of the OCSF and ECS shape:
- `alert_id`, `timestamp`, `detector` (email gateway, identity provider, endpoint agent, network sensor or cloud monitor), `rule_name`, and a short `description` with the evidence.
- `source_severity`: informational, low, medium or high, as the detector set it. It is sometimes wrong.
- Entities: `user`, `host`, `src_ip` and `dst_ip`. Any of them can be missing.
- Context: `asset_criticality` (low, standard, high or crown jewel) and `user_access` (standard, elevated or administrator).
- `claimed_tactic`: the ATT&CK tactic the detector names. It is sometimes missing or wrong.

### The answer key
Hidden, and used only for grading:
- `incident_id`, empty for a lone alert.
- `disposition`: true positive, false positive or benign true positive.
- `true_severity`: informational, low, medium, high or critical.
- `true_tactic`, and which accounts are compromised.

### Scenarios
Real incidents are chains of ATT&CK tactics. Three incidents of each kind:
- `phish_to_exfil`: credential phishing, a login from a new location, a mail forwarding rule, then data sent outside.
- `malware_lateral`: malware on a laptop, privilege escalation, a move to a file server, then a large transfer.
- `mfa_fatigue`: repeated multi-factor authentication (MFA) prompts, a successful login, then a cloud download.
- `slow_burn`: low-severity alerts on one account spread over several days, each ignorable alone.
- `missing_entity_link`: an incident where one alert lost its user field but shares the attacker's address and names the mailbox in its description. Grouping must still attach it, and account risk must still count it for the right user.

Benign look-alikes, each a burst of alerts that forms a benign group:
- Benign true positives: `benign_admin_tool`, `benign_travel` (impossible travel from real travel), `benign_pentest` (an authorized security test) and `benign_backup` (a backup that looks like data leaving).
- False positives: `fp_scanner` and `fp_noisy_rule`.

Traps for the individual stages:
- `high_severity_benign` and `low_severity_real` test the severity field.
- `two_incidents_one_user` and `shared_address` (two unrelated users behind one address) test grouping.

The rest is background: lone benign alerts.

### Size
About 200 employees and 1,050 alerts. About 21 real incidents (about 85 alerts in all), each on a different compromised account, and about 20 benign groups. Roughly 1 in 12 alerts belongs to a real incident. Every scenario has enough copies to grade, with rates reported per scenario as in the matching experiment.

## Pipeline
Each script reads the files the previous stage wrote. Jev answers are saved, so rules and thresholds can change with no new Jev calls.

1. **Generate** the alerts and the answer key.
2. **Enrich** each alert with entity keys, asset context and time windows.
3. **Rules (code).** The never-suppress list never closes an alert. Such an alert is at least investigated, and it escalates when Jev judges it a likely true positive. An allowlist closes known-harmless alerts with a reason, such as a scheduled backup or an approved scanner. The detector's severity is an input, never the answer.
4. **Ask Jev about each alert** (Call 1 in [Where Jev is used, and why](#where-jev-is-used-and-why)). The four questions, their inputs and their use are listed there, and nowhere else.
5. **Decide each alert.** Code closes, investigates or escalates, and leans toward escalating. The exact conditions, and the thresholds, are in Call 1.
6. **Group into incidents.** Alerts that share a user, host or address within 72 hours become candidate pairs. Code settles the obvious links (the same user and host within 30 minutes). Jev (Call 2) judges the ambiguous ones. The linked pairs cluster into incidents. An incident's severity and disposition come from its alerts. Alerts on one user that do not fit together stay separate.
7. **Score accounts.** See the next section.
8. **Explain and report.** Every alert, incident and account records the rule that fired, Jev's answers and the evidence. A browsable report shows them, in the style of the matching reports.

## Account risk
- A finding's risk equals impact times confidence divided by 100. Jev's impact Score supplies the impact, scaled to 0 to 100. Jev's probability of a true positive supplies the confidence.
- An account's score is a rolling 7-day number from 0 to 100. The incidents are spread over two weeks, so each account takes its worst seven-day window. The score combines the total risk, the worst single finding, the count of serious findings and the count of different detections.
- Alerts inside confirmed incidents count in full, and benign alerts count for little.
- The output is a ranked list, and each account shows the incidents and alerts behind its score.

## Baselines
Each stage also runs as plain rules on the same alerts:
- Triage: escalate high and critical detector severities, close low and informational ones, and apply the allowlist and never-suppress list.
- Grouping: shared entity inside a time window.
- Account risk: the same formula, with the detector's severity and a fixed confidence.

The grouping baseline is the floor Jev has to beat. On the current data it finds 1,393 candidate pairs and puts the 1,042 alerts into 363 groups. It links 5,451 alert pairs and gets all 225 true pairs, so recall is 100% and precision is 4%. Six groups each hold two different real incidents. Most of the wrong links join unrelated alerts that share a busy server or address (3,326 across scenarios, 1,760 in background noise).

The account ranking is graded, not tuned. The score weights are this design's own version of the approach and were not adjusted after seeing results. Of the 21 compromised accounts, Jev's ranking puts 10 in the top 10 and 19 in the top 20. Its first hit is at rank 1. The detector-severity ranking puts 6 in the top 10 and 10 in the top 20. Its first hit is at rank 2.

Each scenario has three compromised accounts. The pairs below are accounts in the top 10 and top 20, Jev first, then the baseline:
- `low_severity_real`: 0 and 2, against 0 and 1.
- `malware_lateral`: 3 and 3, against 0 and 2.
- `mfa_fatigue`: 0 and 3, against 1 and 1.
- `missing_entity_link`: 3 and 3, against 2 and 2.
- `phish_to_exfil`: 2 and 3, against 2 and 2.
- `slow_burn`: 1 and 2, against 0 and 0.
- `two_incidents_one_user`: 1 and 3, against 1 and 2.

Jev's weakest spots are `low_severity_real` and `mfa_fatigue`, where no account reaches the top 10.

## Metrics
- Missed attacks: real alerts the pipeline closed, and real incidents with no escalated alert.
- Queue: items a human must read, with an incident counting as one item, against alerts in.
- Benign look-alikes: benign true positives closed with a reason, against ones escalated for no reason.
- Grouping: how many alert pairs from one incident get linked, how many wrong pairs get linked, and whether any incident mixes two real ones.
- Account ranking: how many of the compromised accounts land in the top 10 and top 20.
- Stage accuracy: for real alerts, how often Jev's `stage` answer matches the true tactic, against how often the detector's claimed tactic matches it.
- Every metric comes per scenario, side by side for Jev and the baseline.
- Mean time to detect and mean time to respond need live operations, so the experiment does not claim them.

## Layout
```
experiments/security-alert-triage/
  README.md  DESIGN.md  run_all.sh  replay.sh
  scripts/      generate, enrich, rules, ask, decide, group, risk, evaluate, reports
  data/         source (alerts and answer key), work, output, reports
```
It mirrors the matching experiment. `replay.sh` rebuilds every result from the saved Jev answers with no API key.

## Build order
Each phase is checked before the next starts.
1. Generate the alerts and the answer key. Score the rules-only baseline first, to set the floor.
2. Jev judges each alert. Evaluate per scenario: missed attacks and queue size.
3. Group into incidents: the baseline first, then Jev on the ambiguous links.
4. Score accounts: the baseline against the Jev version. Build the reports.
5. Freeze the rules, then run a fresh seed once. Write the README.

Baseline floor (seed 101): the rules-only baseline misses 30 of 84 real alerts and 6 of 21 real incidents (no alert surfaced). 9 incidents have no escalated alert. 495 of 1042 alerts reach a person (52% fewer), and 517 of 958 benign alerts are closed. The misses are `slow_burn` (all 24 closed), `low_severity_real` (all 3) and `mfa_fatigue` (3 of 9). The benign look-alikes `benign_admin_tool` and `benign_backup` are all escalated.

## Risks
- **Flattering results.** The same person writes the stories and the rules. Hard look-alike scenarios, added in new rounds, and a plain caveat in the README are the answer.
- **Cost.** A full run is about 1,000 requests for Call 1. Call 2 adds one request per ambiguous candidate pair, which is several hundred more. It is cheap, and the results report the measured count.
- **Scope.** The work has three pieces: triage, grouping and account risk. The build order keeps each one small enough to verify.
- **Sensitivity.** The account ranking is about people. The guardrails above apply to the report and to the README.

## Open choices, with the defaults used here
- Grouping window: 72 hours for ambiguous pairs, 30 minutes for the obvious link. Sentinel's default is 5 hours, but the slow-burn story runs over days.
- Severity levels: informational, low, medium, high and critical.
- Account ranking is graded at the top 10 and top 20 of about 200 employees.
