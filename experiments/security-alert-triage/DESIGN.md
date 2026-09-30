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
Real incidents are chains of ATT&CK tactics. Four incidents of each kind:
- `phish_to_exfil`: credential phishing, a login from a new location, a mail forwarding rule, then data sent outside.
- `malware_lateral`: malware on a laptop, privilege escalation, a move to a file server, then a large transfer.
- `mfa_fatigue`: repeated multi-factor authentication (MFA) prompts, a successful login, then a cloud download.
- `slow_burn`: low-severity alerts on one account spread over several days, each ignorable alone.
- `missing_entity_link`: an incident where one alert lacks its user, so only context links it.

Benign look-alikes, each a burst of alerts that forms a benign group:
- Benign true positives: `benign_admin_tool`, `benign_travel` (impossible travel from real travel), `benign_pentest` (an authorized security test) and `benign_backup` (a backup that looks like data leaving).
- False positives: `fp_scanner` and `fp_noisy_rule`.

Traps for the individual stages:
- `high_severity_benign` and `low_severity_real` test the severity field.
- `two_incidents_one_user` and `shared_address` (two unrelated users behind one address) test grouping.

The rest is background: lone benign alerts.

### Size
About 200 employees and 1,200 alerts. About 20 real incidents (80 to 150 alerts in all), each on a different compromised account, and about 20 benign groups. Roughly 1 in 8 alerts belongs to a real incident. Every scenario has enough copies to grade, with rates reported per scenario as in the matching experiment.

## Pipeline
Each script reads the files the previous stage wrote. Jev answers are saved, so rules and thresholds can change with no new Jev calls.

1. **Generate** the alerts and the answer key.
2. **Enrich** each alert with entity keys, asset context and time windows.
3. **Rules (code).** The never-suppress list never closes an alert. Such an alert is at least investigated, and it escalates when Jev judges it a likely true positive. An allowlist closes known-harmless alerts with a reason, such as a scheduled backup or an approved scanner. The detector's severity is an input, never the answer.
4. **Ask Jev** once per remaining alert. It gets the alert with its asset and user context and answers:
   - Disposition (Choice): true positive, false positive or benign true positive.
   - Impact (Score): minimal, limited, serious or severe.
   - Stage (Choice): one of the 15 ATT&CK tactics.
   - Benign explanation (Noul): does an ordinary explanation fit?
5. **Decide each alert.** Code closes, investigates or escalates, and leans toward escalating. An alert closes only when three things hold. Jev is confident it is benign. It is not on the never-suppress list. No other alert in its story casts doubt. The thresholds come from a sweep on one seed, and a fresh seed checks them.
6. **Group into incidents.** Alerts that share a user, host or address within 72 hours become candidate pairs. Code settles the obvious links (the same user and host within 30 minutes). Jev judges the ambiguous ones: is this the same incident? The pairs cluster into incidents. An incident's severity and disposition come from its alerts. Alerts on one user that do not fit together stay separate.
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

## Metrics
- Missed attacks: real alerts the pipeline closed, and real incidents with no escalated alert.
- Queue: items a human must read, with an incident counting as one item, against alerts in.
- Benign look-alikes: benign true positives closed with a reason, against ones escalated for no reason.
- Grouping: how many alert pairs from one incident get linked, how many wrong pairs get linked, and whether any incident mixes two real ones.
- Account ranking: how many of the compromised accounts land in the top 10 and top 20.
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

## Risks
- **Flattering results.** The same person writes the stories and the rules. Hard look-alike scenarios, added in new rounds, and a plain caveat in the README are the answer.
- **Cost.** A full run is roughly 600 to 900 Jev requests, so it is cheap.
- **Scope.** The work has three pieces: triage, grouping and account risk. The build order keeps each one small enough to verify.
- **Sensitivity.** The account ranking is about people. The guardrails above apply to the report and to the README.

## Open choices, with the defaults used here
- Grouping window: 72 hours for ambiguous pairs, 30 minutes for the obvious link. Sentinel's default is 5 hours, but the slow-burn story runs over days.
- Severity levels: informational, low, medium, high and critical.
- Account ranking is graded at the top 10 and top 20 of about 200 employees.
