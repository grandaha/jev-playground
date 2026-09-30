# Security Alert Triage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an experiment that triages synthetic security alerts with Jev: a judgment and action for every alert, alerts grouped into incidents, and a ranking of accounts most likely compromised, each compared with a rules-only baseline and graded against an answer key.

**Architecture:** Same shape as `experiments/customer-matching`. Code settles the clear cases by rule, Jev answers questions about the rest once, and the answers are saved so policies and thresholds change with no new Jev calls. Stages write CSVs to `data/`, evaluation grades them per scenario, and a static HTML report shows every decision with its evidence.

**Tech Stack:** Python 3.13, `typesafe-sdk` (Jev), `python-dotenv`, `pytest`. No other dependencies.

**Spec:** `experiments/security-alert-triage/DESIGN.md`

## Global Constraints

- Defensive only. Alerts describe what a detector saw; they contain no attack steps or tooling.
- Every name, company, host and address is fictional. Addresses come only from 192.0.2.0/24, 198.51.100.0/24 and 203.0.113.0/24. Domains use `example.com`.
- Never edit the data to make a result pass. A failing case means the rules are wrong. New hard cases arrive as a new round with a new seed.
- Severity levels: informational, low, medium, high, critical (detectors use the first four).
- Dispositions: true positive, false positive, benign true positive.
- Attack stages: the 15 MITRE ATT&CK tactics in `schema.TACTICS`.
- Grouping window: 72 hours for ambiguous pairs, 30 minutes for the obvious link (same user and host).
- Account score: rolling 7-day window, 0 to 100. Finding risk is impact times confidence divided by 100.
- Never-suppress list (privilege escalation, data leaving to an unknown destination, command and control) never closes an alert.
- Jev answers are saved; `replay.sh` rebuilds every result with no API key and no network.
- The API key lives in `.env` (gitignored). Never commit or print it.
- All commits stay on branch `worktree-security-alert-triage`, in the worktree at `.claude/worktrees/security-alert-triage`. Do not push. The pull request comes only after every task is done, and only when the user says so.
- Commit messages end with the trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Run commands from the experiment folder `experiments/security-alert-triage/` unless a step says otherwise. The interpreter is `../../.venv/bin/python`.

## Review Focus

Five inputs the spec implies but no happy-path test exercises. Each has a test in the task that owns the code.

1. An alert with every entity empty (no user, host or address). It must not crash any stage, must group alone, and must not reach account risk. (Task 5 grouping test, Task 7 risk test)
2. Jev fails or times out on an alert. The alert must become `investigate` with a reason, never `close`. (Task 4)
3. Two alerts exactly 72 hours apart, or exactly 30 minutes apart. The boundaries are inclusive. (Task 5)
4. One user with hundreds of findings. The account score stays at or below 100 and the run stays fast. (Task 7)
5. An empty `alerts.csv`. Every script stops with a clear message, not a traceback. (Task 1)

## File Structure

All paths are under `experiments/security-alert-triage/`.

| File | Responsibility |
|---|---|
| `pytest.ini` | Puts `scripts/` on the import path for tests |
| `scripts/paths.py` | Data folder and per-stage subfolders |
| `scripts/schema.py` | Shared vocabulary: severities, dispositions, actions, tactics, columns |
| `scripts/tables.py` | CSV read and write helpers, and the empty-file guard |
| `scripts/scenarios.py` | The synthetic world: employees, servers and every scenario's alerts and key rows |
| `scripts/generate.py` | Builds the world, orders it by time, renumbers alert ids, writes the source files |
| `scripts/enrich.py` | Timestamps, entity keys and hours apart |
| `scripts/rules.py` | Never-suppress list, allowlist, and the rules-only baseline triage |
| `scripts/ask.py` | The Jev questions for alerts and for alert pairs, with retries |
| `scripts/decide.py` | The policy that turns answers into close, investigate or escalate |
| `scripts/sweep.py` | Threshold sweep over saved answers |
| `scripts/group.py` | Candidate pairs, baseline grouping, link decisions, clustering, incident table |
| `scripts/risk.py` | Finding risk, account scores, ranking, baseline scores |
| `scripts/evaluate.py` | Every metric, per scenario, Jev against baseline |
| `scripts/report.py` | The static HTML report |
| `tests/` | One test file per script |
| `run_all.sh`, `replay.sh` | Full run and no-key replay |
| `README.md`, `DESIGN.md` | Public documentation |

---

### Task 1: Synthetic alerts and answer key

**Files:**
- Create: `pytest.ini`, `scripts/paths.py`, `scripts/schema.py`, `scripts/tables.py`, `scripts/scenarios.py`, `scripts/generate.py`, `tests/test_generate.py`
- Modify: `requirements.txt` (repo root), `DESIGN.md` (size and scenario text)

**Interfaces:**
- Produces: `schema.{SEVERITIES, SOURCE_SEVERITIES, DISPOSITIONS, ACTIONS, DETECTORS, CRITICALITY, ACCESS_LEVELS, TACTICS, TACTIC_DESCRIPTIONS, ALERT_COLUMNS, KEY_COLUMNS, EMPLOYEE_COLUMNS, is_documentation_ip(ip)}`
- Produces: `paths.{ROOT, REPO, DATA, path(name)}`, `tables.{read_csv(p), write_csv(p, rows, columns=None), read_alerts(p)}`
- Produces: `generate.build(seed) -> (employees, alerts, key)` (three lists of dicts), `generate.write(employees, alerts, key, employees_path, alerts_path, key_path)`, `scenarios.SHARED_NAT_IP`, `scenarios.SERVERS`
- Alert dict keys are `schema.ALERT_COLUMNS`; key dict keys are `schema.KEY_COLUMNS`; timestamps are `YYYY-MM-DDTHH:MM:SSZ`.

- [ ] **Step 1: Set up the environment in the worktree**

The worktree has no `.venv` and no `.env` (both are untracked). From the worktree root `/Users/daveraffaele/Developer/jev-playground/.claude/worktrees/security-alert-triage`:

```bash
python3.13 -m venv .venv
.venv/bin/pip install -q -r requirements.txt pytest
.venv/bin/pip freeze | grep -i "^pytest==" >> requirements.txt
cp /Users/daveraffaele/Developer/jev-playground/.env .env
git check-ignore -q .venv && git check-ignore -q .env && echo "both ignored"
```

Expected: `both ignored`. Do not print `.env`.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_generate.py`:

```python
from collections import defaultdict

import pytest

import generate
import scenarios
from enrich import parse_ts
from schema import (ACCESS_LEVELS, DETECTORS, DISPOSITIONS, SEVERITIES, SOURCE_SEVERITIES,
                    TACTICS, is_documentation_ip)
from tables import read_csv

EXPECTED_SCENARIOS = {
    "phish_to_exfil", "malware_lateral", "mfa_fatigue", "slow_burn", "missing_entity_link",
    "benign_admin_tool", "benign_travel", "benign_pentest", "benign_backup", "fp_scanner",
    "fp_noisy_rule", "high_severity_benign", "low_severity_real", "two_incidents_one_user",
    "shared_address", "background",
}


@pytest.fixture(scope="module")
def world():
    return generate.build(101)


def rows_of(world, scenario):
    _, alerts, key = world
    k = {x["alert_id"]: x for x in key}
    return [(a, k[a["alert_id"]]) for a in alerts if k[a["alert_id"]]["scenario"] == scenario]


def test_build_is_deterministic_and_seed_sensitive():
    assert generate.build(101) == generate.build(101)
    assert generate.build(101)[1] != generate.build(102)[1]


def test_alert_ids_follow_time_order(world):
    _, alerts, _ = world
    ids = [a["alert_id"] for a in alerts]
    times = [a["timestamp"] for a in alerts]
    assert ids == sorted(ids) and times == sorted(times)


def test_every_alert_has_a_key_row_with_valid_labels(world):
    _, alerts, key = world
    assert [k["alert_id"] for k in key] == [a["alert_id"] for a in alerts]
    for k in key:
        assert k["disposition"] in DISPOSITIONS
        assert k["true_severity"] in SEVERITIES
        assert k["true_tactic"] in TACTICS + [""]
    for a in alerts:
        assert a["source_severity"] in SOURCE_SEVERITIES
        assert a["detector"] in DETECTORS
        assert a["claimed_tactic"] in TACTICS + [""]
        assert a["user_access"] in ACCESS_LEVELS + [""]


def test_all_data_is_fictional(world):
    employees, alerts, _ = world
    assert all(e["user"].endswith("@example.com") for e in employees)
    for a in alerts:
        assert a["user"] == "" or a["user"].endswith("@example.com")
        for field in ("src_ip", "dst_ip"):
            assert a[field] == "" or is_documentation_ip(a[field])


def test_size_and_share_of_real_alerts(world):
    _, alerts, key = world
    assert 950 <= len(alerts) <= 1150
    real = [k for k in key if k["disposition"] == "true_positive"]
    assert 0.06 <= len(real) / len(alerts) <= 0.12


def test_twenty_one_real_incidents_each_on_its_own_account(world):
    _, _, key = world
    real = [k for k in key if k["disposition"] == "true_positive"]
    incidents = {k["incident_id"]: k["compromised_user"] for k in real}
    assert len(incidents) == 21
    assert len(set(incidents.values())) == 21


def test_every_scenario_is_present(world):
    _, _, key = world
    assert {k["scenario"] for k in key} == EXPECTED_SCENARIOS


def test_missing_entity_link_alert_shares_an_address_with_its_incident(world):
    by_incident = defaultdict(list)
    for a, k in rows_of(world, "missing_entity_link"):
        by_incident[k["incident_id"]].append(a)
    assert len(by_incident) == 3
    for members in by_incident.values():
        blank = [a for a in members if not a["user"]]
        named = [a for a in members if a["user"]]
        assert len(blank) == 1
        addresses = {a["src_ip"] for a in named} | {a["dst_ip"] for a in named}
        assert blank[0]["src_ip"] in addresses
        local = named[0]["user"].split("@")[0]
        assert f"mailbox of {local}" in blank[0]["description"]


def test_slow_burn_is_quiet_and_slow(world):
    by_incident = defaultdict(list)
    for a, k in rows_of(world, "slow_burn"):
        assert a["source_severity"] in ("informational", "low")
        by_incident[k["incident_id"]].append(parse_ts(a["timestamp"]))
    assert len(by_incident) == 3
    for times in by_incident.values():
        assert (max(times) - min(times)).days >= 4


def test_low_severity_real_is_low_and_true_positive(world):
    rows = rows_of(world, "low_severity_real")
    assert len(rows) == 3
    assert all(a["source_severity"] == "low" and k["disposition"] == "true_positive" for a, k in rows)


def test_high_severity_benign_is_high_and_a_false_positive(world):
    rows = rows_of(world, "high_severity_benign")
    assert len(rows) == 3
    assert all(a["source_severity"] == "high" and k["disposition"] == "false_positive" for a, k in rows)


def test_shared_address_pairs_share_the_nat_address_but_not_the_user(world):
    rows = [a for a, _ in rows_of(world, "shared_address")]
    assert len(rows) == 6
    for a in rows:
        assert a["src_ip"] == scenarios.SHARED_NAT_IP
        partners = [b for b in rows if b is not a and b["user"] != a["user"]
                    and abs((parse_ts(a["timestamp"]) - parse_ts(b["timestamp"])).total_seconds()) <= 3600]
        assert partners


def test_two_incidents_one_user_has_a_benign_then_a_real_incident(world):
    per_user = defaultdict(set)
    for a, k in rows_of(world, "two_incidents_one_user"):
        per_user[a["user"]].add((k["incident_id"], k["disposition"]))
    assert len(per_user) == 3
    for seen in per_user.values():
        assert {d for _, d in seen} == {"true_positive", "benign_true_positive"}
        assert len({i for i, _ in seen}) == 2


def test_write_creates_the_three_source_files(world, tmp_path):
    employees, alerts, key = world
    paths = [tmp_path / n for n in ("employees.csv", "alerts.csv", "answer_key.csv")]
    generate.write(employees, alerts, key, *paths)
    assert len(read_csv(paths[1])) == len(alerts)
    assert len(read_csv(paths[2])) == len(key)
    assert len(read_csv(paths[0])) == 200
```

Also create `tests/test_tables.py`:

```python
import pytest

from tables import read_alerts, read_csv, write_csv


def test_round_trip(tmp_path):
    p = tmp_path / "x.csv"
    write_csv(p, [{"a": "1", "b": "2"}], ["a", "b"])
    assert read_csv(p) == [{"a": "1", "b": "2"}]


def test_empty_alerts_file_stops_with_a_clear_message(tmp_path):
    p = tmp_path / "alerts.csv"
    write_csv(p, [], ["alert_id"])
    with pytest.raises(SystemExit) as stop:
        read_alerts(p)
    assert "no alerts" in str(stop.value)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `../../.venv/bin/python -m pytest -q`
Expected: collection errors, `ModuleNotFoundError: No module named 'generate'` (and `tables`). Create `pytest.ini` first if pytest cannot find the tests folder:

```ini
[pytest]
pythonpath = scripts
testpaths = tests
```

- [ ] **Step 4: Write the shared modules**

`scripts/schema.py`:

```python
"""Shared vocabulary for the alert triage experiment."""
import ipaddress

SEVERITIES = ["informational", "low", "medium", "high", "critical"]
SOURCE_SEVERITIES = ["informational", "low", "medium", "high"]  # what detectors use
DISPOSITIONS = ["true_positive", "false_positive", "benign_true_positive"]
ACTIONS = ["close", "investigate", "escalate"]
DETECTORS = ["email_gateway", "identity_provider", "endpoint_agent", "network_sensor", "cloud_monitor"]
CRITICALITY = ["low", "standard", "high", "crown_jewel"]
ACCESS_LEVELS = ["standard", "elevated", "administrator"]

TACTIC_DESCRIPTIONS = {
    "reconnaissance": "Gathering information about the company to plan an attack.",
    "resource_development": "Setting up infrastructure or accounts to support an attack.",
    "initial_access": "Getting a first foothold, for example through phishing or a stolen sign-in.",
    "execution": "Running attacker-controlled code.",
    "persistence": "Keeping access across restarts and password changes.",
    "privilege_escalation": "Gaining higher permissions.",
    "stealth": "Hiding actions so they look normal.",
    "defense_impairment": "Turning off or weakening security tools and logging.",
    "credential_access": "Stealing or guessing account credentials.",
    "discovery": "Mapping the environment to decide where to go next.",
    "lateral_movement": "Moving from one system to another.",
    "collection": "Gathering the data the attacker wants.",
    "command_and_control": "Communicating with compromised systems from outside.",
    "exfiltration": "Stealing data out of the company.",
    "impact": "Disrupting, encrypting or destroying systems and data.",
}
TACTICS = list(TACTIC_DESCRIPTIONS)

ALERT_COLUMNS = ["alert_id", "timestamp", "detector", "rule_name", "description", "source_severity",
                 "user", "host", "src_ip", "dst_ip", "asset_criticality", "user_access", "claimed_tactic"]
KEY_COLUMNS = ["alert_id", "incident_id", "disposition", "true_severity", "true_tactic", "scenario",
               "compromised_user"]
EMPLOYEE_COLUMNS = ["user", "host", "ip", "access"]

_DOC_NETS = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]


def is_documentation_ip(ip):
    return any(ipaddress.ip_address(ip) in net for net in _DOC_NETS)
```

`scripts/paths.py`:

```python
"""Where the experiment reads and writes. One dataset lives in data/, sorted by stage."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent       # experiments/security-alert-triage
REPO = ROOT.parents[1]                                # repo root (holds .env)
DATA = ROOT / os.environ.get("TRIAGE_DATA", "data")   # TRIAGE_DATA=data_holdout runs another dataset

SOURCE_FILES = {"employees.csv", "alerts.csv", "answer_key.csv"}


def path(name):
    """data/<stage>/<name>. source: generated inputs and answer key. output: final results.
    reports: html. work: everything in between."""
    if name in SOURCE_FILES:
        stage = "source"
    elif name.endswith(".html"):
        stage = "reports"
    elif name.startswith("output_"):
        stage = "output"
    else:
        stage = "work"
    folder = DATA / stage
    folder.mkdir(parents=True, exist_ok=True)
    return folder / name
```

`scripts/tables.py`:

```python
"""CSV helpers shared by every stage."""
import csv
from pathlib import Path


def read_csv(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def write_csv(p, rows, columns=None):
    cols = columns or (list(rows[0]) if rows else [])
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def read_alerts(p):
    rows = read_csv(p)
    if not rows:
        raise SystemExit(f"{Path(p).name} has no alerts; run generate.py first")
    return rows
```

Create `scripts/enrich.py` now too, because the generator tests import `parse_ts`:

```python
"""Timestamps, entity keys and time gaps."""
from datetime import datetime, timezone


def parse_ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def entities(alert):
    """The things an alert is about, as prefixed keys: user:..., host:..., ip:... (empty fields are skipped)."""
    out = set()
    for field, prefix in (("user", "user"), ("host", "host"), ("src_ip", "ip"), ("dst_ip", "ip")):
        if alert.get(field):
            out.add(f"{prefix}:{alert[field]}")
    return out


def hours_apart(a, b):
    return abs((parse_ts(a["timestamp"]) - parse_ts(b["timestamp"])).total_seconds()) / 3600
```

- [ ] **Step 5: Write the scenarios**

`scripts/scenarios.py`:

```python
"""The synthetic world: employees, servers, and every scenario's alerts with their answer key."""
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

START = datetime(2026, 3, 2, tzinfo=timezone.utc)
DAYS = 14
STORY_COPIES = 3     # copies of each real-incident story and each trap
BENIGN_COPIES = 3    # copies of each benign group
BACKGROUND = 880     # lone benign alerts

FIRST = ["avery", "blake", "casey", "devon", "emery", "finley", "harper", "jordan", "kai", "logan",
         "morgan", "noel", "parker", "quinn", "reese", "riley", "sage", "taylor", "wren", "zion"]
LAST = ["adler", "brooks", "chen", "diaz", "evans", "fox", "grant", "hayes", "ito", "jones",
        "khan", "lopez", "moore", "novak", "ortiz", "patel", "reyes", "silva", "tran", "walsh"]

SERVERS = {  # name: (address, asset criticality)
    "FS-01": ("192.0.2.11", "high"), "FS-02": ("192.0.2.12", "high"),
    "DB-01": ("192.0.2.21", "crown_jewel"), "BK-01": ("192.0.2.31", "high"),
    "SCAN-01": ("192.0.2.200", "standard"), "SEC-TEST-01": ("198.51.100.250", "standard"),
}
SHARED_NAT_IP = "192.0.2.250"  # a guest network address many unrelated people use


@dataclass(frozen=True)
class Employee:
    user: str
    host: str
    ip: str
    access: str


class World:
    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.alerts, self.key = [], []
        self._alerts_n = 0
        self._incidents_n = 0
        names = self.rng.sample([(f, l) for f in FIRST for l in LAST], 200)
        self.employees = []
        for i, (f, l) in enumerate(names, 1):
            r = self.rng.random()
            access = "administrator" if r < 0.03 else "elevated" if r < 0.15 else "standard"
            self.employees.append(Employee(f"{f}.{l}@example.com", f"WS-{i:03d}", f"198.51.100.{i}", access))
        self.access = {e.user: e.access for e in self.employees}
        self._victims = self.rng.sample(self.employees, len(self.employees))  # each victim is used once

    # --- helpers ---
    def victim(self):
        return self._victims.pop()

    def pick(self, access=None):
        pool = [e for e in self.employees if access is None or e.access in access]
        return self.rng.choice(pool)

    def when(self, latest_day=DAYS - 1):
        return START + timedelta(days=self.rng.randrange(0, latest_day), minutes=self.rng.randrange(0, 1440))

    def new_incident(self):
        self._incidents_n += 1
        return f"INC-{self._incidents_n:03d}"

    def resolve_ip(self, kind, victim=None, attacker=None):
        if not kind:
            return ""
        if kind == "victim":
            return victim.ip
        if kind == "attacker":
            return attacker
        if kind == "external":
            return f"203.0.113.{self.rng.randrange(1, 255)}"
        if kind.startswith("server:"):
            return SERVERS[kind.split(":")[1]][0]
        raise ValueError(kind)

    def emit(self, ts, detector, rule, description, severity, *, user=None, host=None, src_ip="", dst_ip="",
             tactic="", incident="", disposition, true_severity, true_tactic="", scenario, compromised=""):
        self._alerts_n += 1
        aid = f"TMP-{self._alerts_n:05d}"
        if host in SERVERS:
            criticality = SERVERS[host][1]
        else:
            criticality = "standard" if host else ""
        self.alerts.append({
            "alert_id": aid, "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"), "detector": detector,
            "rule_name": rule, "description": description, "source_severity": severity,
            "user": user or "", "host": host or "", "src_ip": src_ip, "dst_ip": dst_ip,
            "asset_criticality": criticality, "user_access": self.access.get(user, "") if user else "",
            "claimed_tactic": tactic})
        self.key.append({
            "alert_id": aid, "incident_id": incident, "disposition": disposition,
            "true_severity": true_severity, "true_tactic": true_tactic, "scenario": scenario,
            "compromised_user": compromised})


# --- real incidents: chains of attack stages. "at" is minutes after the start. ---
PHISH = [
    {"at": 0, "det": "email_gateway", "rule": "Credential phishing link clicked",
     "desc": "User clicked a link in a message the gateway classed as credential phishing; the page imitated the company sign-in",
     "sev": "medium", "tactic": "initial_access", "src": "victim"},
    {"at": 25, "det": "identity_provider", "rule": "Sign-in from new country",
     "desc": "Successful sign-in from a country never seen for this user, on an unregistered device, right after a password reset",
     "sev": "high", "tactic": "initial_access", "src": "attacker"},
    {"at": 40, "det": "cloud_monitor", "rule": "Mailbox forwarding rule created",
     "desc": "A new inbox rule forwards all mail to an address outside the company", "sev": "medium",
     "tactic": "collection", "src": "attacker"},
    {"at": 180, "det": "network_sensor", "rule": "Large upload to external address",
     "desc": "Unusually large upload to an address outside the company, well above this user's normal volume",
     "sev": "high", "tactic": "exfiltration", "src": "victim", "dst": "attacker"},
]
MISSING = [dict(s) for s in PHISH]
MISSING[2].update({"user": False, "mention_user": True})  # the forwarding-rule alert lost its user field

MALWARE = [
    {"at": 0, "det": "endpoint_agent", "rule": "Suspicious process started by document",
     "desc": "An office document launched a scripting process that then contacted the internet", "sev": "medium",
     "tactic": "execution", "host": "victim", "src": "victim"},
    {"at": 30, "det": "endpoint_agent", "rule": "Privilege escalation attempt",
     "desc": "A process tried to gain administrator rights using an unpatched driver", "sev": "high",
     "tactic": "privilege_escalation", "host": "victim"},
    {"at": 120, "det": "network_sensor", "rule": "Remote service access to file server",
     "desc": "The workstation opened an administrative session on a file server it has never used",
     "sev": "medium", "tactic": "lateral_movement", "host": "server:FS-01", "src": "victim", "dst": "server:FS-01"},
    {"at": 240, "det": "network_sensor", "rule": "Large outbound transfer",
     "desc": "Hundreds of files sent from the file server to an address outside the company", "sev": "high",
     "tactic": "exfiltration", "host": "server:FS-01", "src": "server:FS-01", "dst": "attacker"},
]

MFA = [
    {"at": 0, "det": "identity_provider", "rule": "Repeated MFA denials",
     "desc": "Nine multi-factor prompts were denied or ignored within ten minutes", "sev": "low",
     "tactic": "credential_access", "src": "attacker"},
    {"at": 14, "det": "identity_provider", "rule": "Sign-in after repeated MFA prompts",
     "desc": "A sign-in succeeded after the prompts, from an address never seen for this user",
     "sev": "medium", "tactic": "initial_access", "src": "attacker"},
    {"at": 90, "det": "cloud_monitor", "rule": "Bulk file download",
     "desc": "Thousands of files downloaded from cloud storage in one session", "sev": "medium",
     "tactic": "collection", "src": "attacker"},
]

_SLOW_MINUTES = [0, 700, 1600, 2900, 4300, 5500, 6500, 7100]  # about five days
_SLOW_ROWS = [
    ("identity_provider", "Unusual sign-in time", "Sign-in at an hour outside this user's normal pattern, from an unfamiliar address", "informational", "initial_access"),
    ("identity_provider", "New device registered", "A new device was registered for multi-factor sign-in without a help-desk ticket", "low", "persistence"),
    ("cloud_monitor", "Rare application accessed", "The user opened an application no one on their team uses", "informational", "discovery"),
    ("identity_provider", "Sign-in from new address", "Sign-in from the same unfamiliar address seen in an earlier unusual sign-in", "low", "initial_access"),
    ("cloud_monitor", "Mailbox accessed by unfamiliar client", "The mailbox was read by a mail client this user has never used", "informational", "collection"),
    ("network_sensor", "Small upload to personal storage", "A small archive was uploaded to a personal storage account", "low", ""),
    ("identity_provider", "Failed sign-ins then success", "Several failed sign-ins followed by a success from the unfamiliar address", "low", "credential_access"),
    ("cloud_monitor", "Unusual access to file share", "The account opened a file share it has not used in the past year", "low", "collection"),
]
SLOW = [{"at": m, "det": d, "rule": r, "desc": t, "sev": s, "tactic": tac or "collection", "claimed": tac, "src": "attacker"}
        for m, (d, r, t, s, tac) in zip(_SLOW_MINUTES, _SLOW_ROWS)]


def run_story(w, scenario, steps, victim, start, true_severity="high"):
    incident = w.new_incident()
    attacker = w.resolve_ip("external")
    local = victim.user.split("@")[0]
    for s in steps:
        host = victim.host if s.get("host") == "victim" else (s["host"].split(":")[1] if s.get("host") else None)
        desc = f"{s['desc']} (mailbox of {local})" if s.get("mention_user") else s["desc"]
        w.emit(start + timedelta(minutes=s["at"]), s["det"], s["rule"], desc, s["sev"],
               user=victim.user if s.get("user", True) else None, host=host,
               src_ip=w.resolve_ip(s.get("src"), victim, attacker), dst_ip=w.resolve_ip(s.get("dst"), victim, attacker),
               tactic=s.get("claimed", s["tactic"]), incident=incident, disposition="true_positive",
               true_severity=true_severity, true_tactic=s["tactic"], scenario=scenario, compromised=victim.user)
    return incident


# --- benign groups. Each returns nothing; the answer key says what they are. ---
def benign_admin_tool(w, start):
    admin = w.pick(("administrator", "elevated"))
    incident = w.new_incident()
    for server, at in (("FS-01", 0), ("FS-02", 6), ("DB-01", 15), ("BK-01", 22)):
        w.emit(start + timedelta(minutes=at), "endpoint_agent", "Remote administration tool executed",
               "An administrator ran a remote administration tool during the approved maintenance window (change ticket CHG-2041)",
               "high", user=admin.user, host=server, src_ip=admin.ip, dst_ip=SERVERS[server][0],
               tactic="lateral_movement", incident=incident, disposition="benign_true_positive",
               true_severity="informational", scenario="benign_admin_tool")


def benign_travel(w, start, user, scenario="benign_travel"):
    incident = w.new_incident()
    w.emit(start, "identity_provider", "Impossible travel",
           "Two sign-ins from distant countries within two hours; both used the user's registered laptop and passed multi-factor sign-in; the user's calendar shows a flight that day",
           "high", user=user.user, src_ip=w.resolve_ip("external"), tactic="initial_access", incident=incident,
           disposition="benign_true_positive", true_severity="low", scenario=scenario)
    w.emit(start + timedelta(minutes=40), "identity_provider", "Sign-in from new country",
           "First sign-in from a new country using the user's registered laptop; multi-factor sign-in passed",
           "medium", user=user.user, src_ip=w.resolve_ip("external"), tactic="initial_access", incident=incident,
           disposition="benign_true_positive", true_severity="low", scenario=scenario)


def benign_pentest(w, start):
    incident = w.new_incident()
    tester = SERVERS["SEC-TEST-01"][0]
    for at, rule, desc, sev, tactic, target in (
            (0, "Port scan", "Sequential connection attempts across many ports from the approved security test host", "low", "reconnaissance", "FS-01"),
            (10, "Port scan", "Sequential connection attempts across many ports from the approved security test host", "low", "reconnaissance", "FS-02"),
            (30, "Credential guessing pattern", "Repeated failed sign-ins from the approved test host during the authorized test window (ticket SEC-2026-014)", "high", "credential_access", "DB-01"),
            (45, "Credential guessing pattern", "Repeated failed sign-ins from the approved test host during the authorized test window (ticket SEC-2026-014)", "high", "credential_access", "BK-01")):
        w.emit(start + timedelta(minutes=at), "network_sensor", rule, desc, sev, host="SEC-TEST-01", src_ip=tester,
               dst_ip=SERVERS[target][0], tactic=tactic, incident=incident, disposition="benign_true_positive",
               true_severity="informational", scenario="benign_pentest")


def benign_backup(w, start):
    incident = w.new_incident()
    night = start.replace(hour=2, minute=0)
    for at in (0, 10, 20):
        w.emit(night + timedelta(minutes=at), "cloud_monitor", "Large transfer to external address",
               "Scheduled nightly backup job to the approved storage provider; same volume as previous nights",
               "high", host="BK-01", src_ip=SERVERS["BK-01"][0], dst_ip=w.resolve_ip("external"),
               tactic="exfiltration", incident=incident, disposition="benign_true_positive",
               true_severity="informational", scenario="benign_backup")


def fp_scanner(w, start):
    incident = w.new_incident()
    scanner = w.resolve_ip("external")
    for at in (0, 4, 9):
        w.emit(start + timedelta(minutes=at), "network_sensor", "Port scan from external address",
               "Sequential connection attempts from a public address with no follow-up activity; consistent with internet-wide scanning",
               "low", host="FS-01", src_ip=scanner, dst_ip=SERVERS["FS-01"][0], tactic="reconnaissance",
               incident=incident, disposition="false_positive", true_severity="informational", scenario="fp_scanner")


def fp_noisy_rule(w, start):
    for at in range(5):
        u = w.pick(None)
        w.emit(start + timedelta(minutes=15 * at), "endpoint_agent", "Suspicious PowerShell",
               "Matched on a script signed by the software vendor and run by the update service",
               "medium", user=u.user, host=u.host, src_ip=u.ip, tactic="execution",
               disposition="false_positive", true_severity="informational", scenario="fp_noisy_rule")


# --- traps for individual stages ---
def high_severity_benign(w, start):
    u = w.pick(None)
    w.emit(start, "endpoint_agent", "Malware signature match",
           "Match on the standard antivirus test file the IT team uses to check the agent",
           "high", user=u.user, host=u.host, src_ip=u.ip, tactic="execution", disposition="false_positive",
           true_severity="informational", scenario="high_severity_benign")


def low_severity_real(w, start):
    victim = w.victim()
    incident = w.new_incident()
    w.emit(start, "cloud_monitor", "Unusual admin action",
           "An administrator role was granted to a standard account outside any change ticket, on the database host that holds customer records",
           "low", user=victim.user, host="DB-01", src_ip=w.resolve_ip("external"), tactic="persistence",
           incident=incident, disposition="true_positive", true_severity="high",
           true_tactic="privilege_escalation", scenario="low_severity_real", compromised=victim.user)


def two_incidents_one_user(w):
    user = w.victim()
    start = w.when(10)
    benign_travel(w, start, user, scenario="two_incidents_one_user")
    run_story(w, "two_incidents_one_user", PHISH, user, start + timedelta(days=2))


def shared_address(w, start):
    a, b = w.rng.sample(w.employees, 2)
    for u, at in ((a, 0), (b, 25)):
        w.emit(start + timedelta(minutes=at), "identity_provider", "Sign-in from unfamiliar address",
               "Sign-in from the office guest network address that many visitors use; the device is registered and multi-factor sign-in passed",
               "low", user=u.user, src_ip=SHARED_NAT_IP, tactic="initial_access", disposition="false_positive",
               true_severity="informational", scenario="shared_address")


_BACKGROUND = [
    ("identity_provider", "Sign-in from unfamiliar device", "First sign-in on a laptop issued by IT last week; multi-factor sign-in passed", "low", "benign_true_positive"),
    ("identity_provider", "Failed sign-in attempts", "Three failed sign-ins followed by a success within two minutes; a typing-error pattern", "low", "false_positive"),
    ("endpoint_agent", "Unapproved software installed", "An approved design tool installed from the company software catalog", "low", "benign_true_positive"),
    ("network_sensor", "Connection to rare domain", "One connection to a rarely seen domain that hosts a public font service", "medium", "false_positive"),
    ("cloud_monitor", "Large file download", "Download of the user's own project folder before a planned laptop refresh", "medium", "benign_true_positive"),
    ("email_gateway", "Suspicious attachment quarantined", "Attachment quarantined and never opened; the sender is a known vendor using a new template", "low", "false_positive"),
    ("endpoint_agent", "USB storage device connected", "Company-issued encrypted USB drive used for a scheduled presentation", "low", "benign_true_positive"),
    ("identity_provider", "Password spray pattern", "Low-rate failed sign-ins across many accounts from one public address with no successes", "medium", "false_positive"),
    ("network_sensor", "Large upload to external address", "Upload of a video to the company's marketing account on an approved platform", "high", "benign_true_positive"),
]


def background(w, n):
    for _ in range(n):
        det, rule, desc, sev, disposition = w.rng.choice(_BACKGROUND)
        u = w.pick(None)
        w.emit(w.when(), det, rule, desc, sev, user=u.user, host=u.host, src_ip=u.ip,
               disposition=disposition, true_severity="informational", scenario="background")


def populate(w):
    for _ in range(STORY_COPIES):
        run_story(w, "phish_to_exfil", PHISH, w.victim(), w.when())
        run_story(w, "malware_lateral", MALWARE, w.victim(), w.when())
        run_story(w, "mfa_fatigue", MFA, w.victim(), w.when())
        run_story(w, "slow_burn", SLOW, w.victim(), w.when(8))
        run_story(w, "missing_entity_link", MISSING, w.victim(), w.when())
        low_severity_real(w, w.when())
        two_incidents_one_user(w)
    for _ in range(BENIGN_COPIES):
        benign_admin_tool(w, w.when())
        benign_travel(w, w.when(), w.pick(None))
        benign_pentest(w, w.when())
        benign_backup(w, w.when())
        fp_scanner(w, w.when())
        fp_noisy_rule(w, w.when())
        high_severity_benign(w, w.when())
        shared_address(w, w.when())
    background(w, BACKGROUND)
```

- [ ] **Step 6: Write the generator**

`scripts/generate.py`:

```python
"""Generate the synthetic alerts and the hidden answer key.

Run from the experiment folder: ../../.venv/bin/python scripts/generate.py
Writes data/source/employees.csv, alerts.csv, answer_key.csv. SEED=202 TRIAGE_DATA=data_holdout for another dataset.
"""
import os

import scenarios
from paths import path
from schema import ALERT_COLUMNS, EMPLOYEE_COLUMNS, KEY_COLUMNS
from tables import write_csv

SEED = int(os.environ.get("SEED", 101))


def build(seed):
    w = scenarios.World(seed)
    scenarios.populate(w)
    order = sorted(range(len(w.alerts)), key=lambda i: (w.alerts[i]["timestamp"], w.alerts[i]["alert_id"]))
    alerts, key = [], []
    for n, i in enumerate(order, 1):  # ids follow time order, so an id never reveals which scenario made it
        new_id = f"ALT-{n:05d}"
        alerts.append({**w.alerts[i], "alert_id": new_id})
        key.append({**w.key[i], "alert_id": new_id})
    employees = [{"user": e.user, "host": e.host, "ip": e.ip, "access": e.access} for e in w.employees]
    return employees, alerts, key


def write(employees, alerts, key, employees_path, alerts_path, key_path):
    write_csv(employees_path, employees, EMPLOYEE_COLUMNS)
    write_csv(alerts_path, alerts, ALERT_COLUMNS)
    write_csv(key_path, key, KEY_COLUMNS)


if __name__ == "__main__":
    employees, alerts, key = build(SEED)
    write(employees, alerts, key, path("employees.csv"), path("alerts.csv"), path("answer_key.csv"))
    real = sum(1 for k in key if k["disposition"] == "true_positive")
    incidents = len({k["incident_id"] for k in key if k["disposition"] == "true_positive"})
    print(f"seed {SEED}: {len(alerts)} alerts, {real} in {incidents} real incidents, {len(employees)} employees")
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `../../.venv/bin/python -m pytest -q`
Expected: all tests pass. If a size or share assertion fails, print `len(alerts)` and the real share, and fix the scenario counts (not the assertion) only if the counts contradict the spec; otherwise adjust the spec text in Step 9.

- [ ] **Step 8: Generate the dataset and look at it**

```bash
../../.venv/bin/python scripts/generate.py
head -4 data/source/alerts.csv
```

Expected: one line like `seed 101: 1042 alerts, 84 in 21 real incidents, 200 employees`, then a header and three alert rows.

- [ ] **Step 9: Update DESIGN.md to match what was built**

In the `Size` paragraph, replace the numbers with the printed ones: about 1,050 alerts, about 21 real incidents (about 85 alerts), about 1 in 12. In the `missing_entity_link` line, replace "an incident where one alert lacks its user, so only context links it" with "an incident where one alert lost its user field but shares the attacker's address and names the mailbox in its description, so grouping must still attach it and account risk must still count it for the right user".

- [ ] **Step 10: Commit**

```bash
cd ../..
git add experiments/security-alert-triage requirements.txt
git commit -m "Add synthetic alert generator and answer key" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Rules-only baseline triage and the alert metrics

**Files:**
- Create: `scripts/rules.py`, `scripts/evaluate.py`, `tests/test_rules.py`, `tests/test_evaluate.py`

**Interfaces:**
- Consumes: `schema.ACTIONS`, `tables.{read_alerts, read_csv, write_csv}`, `paths.path`
- Produces: `rules.never_suppress(alert) -> str | None` (the reason), `rules.allowlisted(alert) -> str | None` (the entry name), `rules.baseline_action(alert) -> (action, reason)`
- Produces: `evaluate.alert_metrics(key, decisions) -> dict` with keys `alerts, tp_alerts, missed_alerts, real_incidents, missed_incidents, under_prioritized_incidents, surfaced, queue_reduction, benign_total, benign_closed, benign_surfaced`
- Produces: `evaluate.scenario_table(key, decisions) -> {scenario: {(disposition, action): count}}`
- Output file: `data/work/decisions_alerts_baseline.csv` with columns `alert_id, action, reason`.

- [ ] **Step 1: Write the failing tests**

`tests/test_rules.py`:

```python
import rules


def alert(**over):
    base = {"alert_id": "A1", "rule_name": "Something", "source_severity": "low", "claimed_tactic": "", "src_ip": ""}
    return {**base, **over}


def test_never_suppress_by_claimed_tactic_and_by_rule_name():
    assert "privilege_escalation" in rules.never_suppress(alert(claimed_tactic="privilege_escalation"))
    assert "large upload" in rules.never_suppress(alert(rule_name="Large upload to external address"))
    assert rules.never_suppress(alert()) is None


def test_allowlist_matches_the_approved_scanner_only():
    scan = alert(rule_name="Port scan", src_ip="192.0.2.200")
    assert rules.allowlisted(scan) == "approved internal scanner"
    assert rules.allowlisted(alert(rule_name="Port scan", src_ip="203.0.113.9")) is None


def test_allowlist_never_overrides_the_never_suppress_list():
    a = alert(rule_name="Port scan", src_ip="192.0.2.200", claimed_tactic="exfiltration")
    assert rules.allowlisted(a) is None


def test_baseline_action_follows_detector_severity():
    assert rules.baseline_action(alert(source_severity="high"))[0] == "escalate"
    assert rules.baseline_action(alert(source_severity="critical"))[0] == "escalate"
    assert rules.baseline_action(alert(source_severity="medium"))[0] == "investigate"
    assert rules.baseline_action(alert(source_severity="low"))[0] == "close"
    assert rules.baseline_action(alert(source_severity="informational"))[0] == "close"


def test_baseline_never_closes_a_never_suppress_alert():
    action, reason = rules.baseline_action(alert(source_severity="low", claimed_tactic="exfiltration"))
    assert action == "investigate" and "never-suppress" in reason


def test_baseline_closes_allowlisted_alerts_with_a_reason():
    action, reason = rules.baseline_action(alert(rule_name="Port scan", src_ip="192.0.2.200"))
    assert action == "close" and "allowlist" in reason
```

`tests/test_evaluate.py`:

```python
import evaluate


def k(aid, inc, disp, scenario="s"):
    return {"alert_id": aid, "incident_id": inc, "disposition": disp, "scenario": scenario}


def d(aid, action):
    return {"alert_id": aid, "action": action}


KEY = [k("A1", "I1", "true_positive"), k("A2", "I1", "true_positive"), k("A3", "I2", "true_positive"),
       k("A4", "", "false_positive"), k("A5", "", "benign_true_positive")]
DEC = [d("A1", "close"), d("A2", "escalate"), d("A3", "close"), d("A4", "close"), d("A5", "investigate")]


def test_alert_metrics_on_a_small_example():
    m = evaluate.alert_metrics(KEY, DEC)
    assert m["alerts"] == 5 and m["tp_alerts"] == 3
    assert m["missed_alerts"] == 2            # A1 and A3 were real and closed
    assert m["real_incidents"] == 2
    assert m["missed_incidents"] == 1         # I2 has no surfaced alert
    assert m["under_prioritized_incidents"] == 1   # I2 has no escalated alert; I1 does
    assert m["surfaced"] == 2
    assert m["queue_reduction"] == 0.6
    assert m["benign_total"] == 2 and m["benign_closed"] == 1 and m["benign_surfaced"] == 1


def test_scenario_table_counts_actions_by_disposition():
    t = evaluate.scenario_table(KEY, DEC)
    assert t["s"][("true_positive", "close")] == 2
    assert t["s"][("true_positive", "escalate")] == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `../../.venv/bin/python -m pytest tests/test_rules.py tests/test_evaluate.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'rules'`.

- [ ] **Step 3: Write the rules**

`scripts/rules.py`:

```python
"""Code-only triage: the never-suppress list, the allowlist, and the rules-only baseline.

Run from the experiment folder: ../../.venv/bin/python scripts/rules.py
Writes data/work/decisions_alerts_baseline.csv.
"""
from paths import path
from tables import read_alerts, write_csv

NEVER_SUPPRESS_TACTICS = {"privilege_escalation", "exfiltration", "command_and_control"}
NEVER_SUPPRESS_PHRASES = ("privilege escalation", "large upload", "large outbound", "large transfer",
                          "beacon", "command and control")
ALLOWLIST = [
    {"name": "approved internal scanner", "rule": "port scan", "src_ip": "192.0.2.200"},
    {"name": "authorized test host scans", "rule": "port scan", "src_ip": "198.51.100.250"},
]


def never_suppress(alert):
    """The reason this alert must never be closed, or None."""
    tactic = alert.get("claimed_tactic", "")
    if tactic in NEVER_SUPPRESS_TACTICS:
        return f"claimed tactic {tactic}"
    name = alert.get("rule_name", "").lower()
    for phrase in NEVER_SUPPRESS_PHRASES:
        if phrase in name:
            return f"rule name mentions '{phrase}'"
    return None


def allowlisted(alert):
    """The allowlist entry that makes this alert known-harmless, or None. Never applies to never-suppress alerts."""
    if never_suppress(alert):
        return None
    name = alert.get("rule_name", "").lower()
    for entry in ALLOWLIST:
        if entry["rule"] in name and alert.get("src_ip") == entry["src_ip"]:
            return entry["name"]
    return None


def baseline_action(alert):
    """The rules-only decision: detector severity plus the two lists. Returns (action, reason)."""
    ns, sev = never_suppress(alert), alert.get("source_severity", "")
    if sev in ("high", "critical"):
        return "escalate", f"detector severity {sev}" + (f"; never-suppress: {ns}" if ns else "")
    if ns:
        return "investigate", f"never-suppress: {ns}"
    entry = allowlisted(alert)
    if entry:
        return "close", f"allowlist: {entry}"
    if sev == "medium":
        return "investigate", "detector severity medium"
    return "close", f"detector severity {sev or 'unknown'}"


def main():
    rows = []
    for a in read_alerts(path("alerts.csv")):
        action, reason = baseline_action(a)
        rows.append({"alert_id": a["alert_id"], "action": action, "reason": reason})
    write_csv(path("decisions_alerts_baseline.csv"), rows, ["alert_id", "action", "reason"])
    counts = {x: sum(1 for r in rows if r["action"] == x) for x in ("close", "investigate", "escalate")}
    print("baseline:", counts)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Write the alert metrics and the command-line report**

`scripts/evaluate.py`:

```python
"""Grade every stage against the hidden answer key, per scenario, Jev against the baseline.

Run from the experiment folder: ../../.venv/bin/python scripts/evaluate.py
"""
import os
from collections import Counter, defaultdict

from paths import path
from tables import read_csv


def alert_metrics(key, decisions):
    act = {d["alert_id"]: d["action"] for d in decisions}
    tp = [k for k in key if k["disposition"] == "true_positive"]
    incidents = defaultdict(list)
    for k in tp:
        incidents[k["incident_id"]].append(act[k["alert_id"]])
    benign = [k for k in key if k["disposition"] != "true_positive"]
    surfaced = sum(1 for a in act.values() if a != "close")
    return {
        "alerts": len(key),
        "tp_alerts": len(tp),
        "missed_alerts": sum(1 for k in tp if act[k["alert_id"]] == "close"),
        "real_incidents": len(incidents),
        "missed_incidents": sum(1 for acts in incidents.values() if all(a == "close" for a in acts)),
        "under_prioritized_incidents": sum(1 for acts in incidents.values() if "escalate" not in acts),
        "surfaced": surfaced,
        "queue_reduction": round(1 - surfaced / len(key), 4) if key else 0.0,
        "benign_total": len(benign),
        "benign_closed": sum(1 for k in benign if act[k["alert_id"]] == "close"),
        "benign_surfaced": sum(1 for k in benign if act[k["alert_id"]] != "close"),
    }


def scenario_table(key, decisions):
    act = {d["alert_id"]: d["action"] for d in decisions}
    table = defaultdict(Counter)
    for k in key:
        table[k["scenario"]][(k["disposition"], act[k["alert_id"]])] += 1
    return {s: dict(c) for s, c in table.items()}


def _print_alert_section(name, key, decisions):
    m = alert_metrics(key, decisions)
    print(f"\n{name}")
    print(f"  missed real alerts: {m['missed_alerts']} of {m['tp_alerts']}; "
          f"real incidents with no surfaced alert: {m['missed_incidents']} of {m['real_incidents']}; "
          f"incidents with no escalated alert: {m['under_prioritized_incidents']}")
    print(f"  queue: {m['surfaced']} of {m['alerts']} alerts reach a person ({m['queue_reduction']:.0%} fewer); "
          f"benign alerts closed {m['benign_closed']} of {m['benign_total']}")
    return scenario_table(key, decisions)


def main():
    key = read_csv(path("answer_key.csv"))
    sections = {}
    for name, file in (("Rules-only baseline", "decisions_alerts_baseline.csv"), ("Jev policy", "decisions_alerts.csv")):
        if os.path.exists(path(file)):
            sections[name] = _print_alert_section(name, key, read_csv(path(file)))
    for name, table in sections.items():
        print(f"\nBy scenario, {name}: disposition/action counts")
        for scenario in sorted(table):
            cells = ", ".join(f"{d[:2]}:{a[:3]}={n}" for (d, a), n in sorted(table[scenario].items()))
            print(f"  {scenario:<26} {cells}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `../../.venv/bin/python -m pytest -q`
Expected: all tests pass (Task 1 and Task 2).

- [ ] **Step 6: Run the baseline on the generated data**

```bash
../../.venv/bin/python scripts/rules.py
../../.venv/bin/python scripts/evaluate.py
```

Expected: the baseline misses real alerts (for example `low_severity_real` and `slow_burn`), escalates the noisy benign look-alikes, and prints the per-scenario table. Write the printed numbers into the `Build order` note of `DESIGN.md` as "Baseline floor (seed 101)". Do not change any rule to improve these numbers.

- [ ] **Step 7: Commit**

```bash
cd ../..
git add experiments/security-alert-triage
git commit -m "Add rules-only baseline triage and alert metrics" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Ask Jev about each alert

**Files:**
- Create: `scripts/ask.py`, `tests/test_ask.py`

**Interfaces:**
- Consumes: `rules.allowlisted`, `schema.{TACTIC_DESCRIPTIONS, DISPOSITIONS}`, `paths.{REPO, path}`, `tables`
- Produces: `ask.ALERT_QUESTIONS`, `ask.alert_state(alert) -> dict`, `ask.choice_probs(answer, options) -> {option: float}`, `ask.ask_one(alert, client, attempts=4) -> dict`, `ask.ask_alerts(alerts, client, workers=8) -> list[dict]`, `ask.make_client()`, `ask.ANSWER_COLUMNS`
- Output file: `data/work/answers_alerts.csv` with columns `alert_id, asked, p_true_positive, p_false_positive, p_benign_true_positive, impact, impact_confidence, stage, stage_confidence, p_benign_explanation, error`. `asked` is `yes` or `no` (allowlisted alerts are not asked).

- [ ] **Step 1: Write the failing tests**

`tests/test_ask.py`:

```python
from types import SimpleNamespace as NS

import ask
from schema import DISPOSITIONS, TACTICS

ALERT = {"alert_id": "A1", "timestamp": "2026-03-02T10:00:00Z", "detector": "identity_provider",
         "rule_name": "Sign-in from new country", "description": "desc", "source_severity": "high",
         "user": "a.b@example.com", "host": "", "src_ip": "203.0.113.5", "dst_ip": "",
         "asset_criticality": "", "user_access": "standard", "claimed_tactic": "initial_access"}
SCAN = {**ALERT, "alert_id": "A2", "rule_name": "Port scan", "src_ip": "192.0.2.200", "claimed_tactic": ""}


def fake_response(tp=0.8):
    rest = (1 - tp) / 2
    return NS(answers={
        "disposition": NS(choice="true_positive", confidence=0.7,
                          probabilities={"true_positive": tp, "false_positive": rest, "benign_true_positive": rest}),
        "impact": NS(score=2.4, confidence=0.6, probabilities={0: 0.0, 1: 0.1, 2: 0.5, 3: 0.4}),
        "stage": NS(choice="exfiltration", confidence=0.5, probabilities={t: 1 / 15 for t in TACTICS}),
        "benign_explanation": NS(noul=0.1)})


class FakeClient:
    def __init__(self, response=None, fail=0):
        self.calls, self.response, self.fail = [], response or fake_response(), fail

    def system_one(self, state, questions):
        self.calls.append((state, questions))
        if self.fail:
            self.fail -= 1
            raise RuntimeError("transient")
        return self.response


def test_questions_cover_all_dispositions_and_tactics():
    assert list(ask.ALERT_QUESTIONS["disposition"].criteria) == DISPOSITIONS
    assert list(ask.ALERT_QUESTIONS["stage"].criteria) == TACTICS
    assert set(ask.ALERT_QUESTIONS) == {"disposition", "impact", "stage", "benign_explanation"}


def test_alert_state_hides_empty_fields_and_labels_context():
    state = ask.alert_state(ALERT)
    assert "host" not in state["alert"] and state["alert"]["user"] == "a.b@example.com"
    assert state["context"] == {"asset_criticality": "unknown", "user_access": "standard"}


def test_choice_probs_accepts_option_names_or_positions():
    by_name = NS(probabilities={"a": 0.6, "b": 0.4})
    by_index = NS(probabilities={0: 0.6, 1: 0.4})
    assert ask.choice_probs(by_name, ["a", "b"]) == {"a": 0.6, "b": 0.4}
    assert ask.choice_probs(by_index, ["a", "b"]) == {"a": 0.6, "b": 0.4}


def test_ask_one_returns_the_saved_columns():
    row = ask.ask_one(ALERT, FakeClient())
    assert set(row) == set(ask.ANSWER_COLUMNS)
    assert row["asked"] == "yes" and row["error"] == ""
    assert row["p_true_positive"] == 0.8 and row["impact"] == 2.4
    assert row["stage"] == "exfiltration" and row["p_benign_explanation"] == 0.1


def test_ask_one_retries_then_records_the_error(monkeypatch):
    monkeypatch.setattr(ask.time, "sleep", lambda s: None)
    ok = ask.ask_one(ALERT, FakeClient(fail=2))
    assert ok["error"] == "" and ok["p_true_positive"] == 0.8
    bad = ask.ask_one(ALERT, FakeClient(fail=10))
    assert "transient" in bad["error"] and bad["asked"] == "yes"


def test_ask_alerts_skips_allowlisted_alerts():
    client = FakeClient()
    rows = ask.ask_alerts([ALERT, SCAN], client, workers=1)
    assert len(client.calls) == 1
    assert [r["asked"] for r in rows] == ["yes", "no"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `../../.venv/bin/python -m pytest tests/test_ask.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'ask'`.

- [ ] **Step 3: Write the alert questions**

`scripts/ask.py`:

```python
"""Ask Jev about each alert once, and save the raw answers.

Run from the experiment folder:
  ../../.venv/bin/python scripts/ask.py alerts [--limit N]
Writes data/work/answers_alerts.csv. Rules and thresholds can change later with no new Jev calls.
"""
import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

import rules
from paths import REPO, path
from schema import DISPOSITIONS, TACTIC_DESCRIPTIONS
from tables import read_alerts, write_csv

load_dotenv(REPO / ".env")

IMPACT_LEVELS = [
    "Minimal: no sensitive data or systems are at risk.",
    "Limited: one account or workstation is affected and the damage is easy to contain.",
    "Serious: sensitive data or an important system is at risk, or several accounts are affected.",
    "Severe: customer data, crown-jewel systems or company-wide operations are at risk.",
]

ALERT_QUESTIONS = {
    "disposition": Choice(
        instructions="Is this alert a real attack, a false alarm, or real but authorized activity?",
        criteria={
            "true_positive": "Real malicious activity that needs a response.",
            "false_positive": "Benign activity that only looked suspicious, or a detector misfire.",
            "benign_true_positive": "Real behavior that is authorized or expected, such as an approved admin task, a scheduled job or an authorized security test.",
        }),
    "impact": Score(
        instructions="If this alert is real, how much damage could it do to the company?",
        criteria=IMPACT_LEVELS),
    "stage": Choice(
        instructions="Which attacker goal does this activity serve?",
        criteria=dict(TACTIC_DESCRIPTIONS)),
    "benign_explanation": Noul(
        instructions="Does an ordinary, authorized explanation fit the evidence in this alert?"),
}

ANSWER_COLUMNS = ["alert_id", "asked", "p_true_positive", "p_false_positive", "p_benign_true_positive",
                  "impact", "impact_confidence", "stage", "stage_confidence", "p_benign_explanation", "error"]
ALERT_FIELDS = ["timestamp", "detector", "rule_name", "description", "source_severity", "user", "host",
                "src_ip", "dst_ip", "claimed_tactic"]


def make_client():
    return TypeSafeClient()


def alert_state(alert):
    return {
        "alert": {k: alert[k] for k in ALERT_FIELDS if alert.get(k)},
        "context": {"asset_criticality": alert.get("asset_criticality") or "unknown",
                    "user_access": alert.get("user_access") or "unknown"},
        "note": "The detector's severity and tactic are its own guesses and are sometimes wrong.",
    }


def choice_probs(answer, options):
    """Probability of each option, whether the SDK keys them by option name or by position."""
    p = dict(answer.probabilities)
    return {o: float(p.get(o, p.get(i, p.get(str(i), 0.0)))) for i, o in enumerate(options)}


def ask_one(alert, client, attempts=4):
    row = {c: "" for c in ANSWER_COLUMNS}
    row.update(alert_id=alert["alert_id"], asked="yes")
    for attempt in range(attempts):  # the API occasionally returns a transient error even after SDK retries
        try:
            resp = client.system_one(state=alert_state(alert), questions=ALERT_QUESTIONS)
            break
        except Exception as e:
            if attempt == attempts - 1:
                row["error"] = str(e)[:200]
                return row
            time.sleep(2 ** attempt)
    disp = choice_probs(resp.answers["disposition"], DISPOSITIONS)
    stage = resp.answers["stage"]
    impact = resp.answers["impact"]
    row.update(p_true_positive=disp["true_positive"], p_false_positive=disp["false_positive"],
               p_benign_true_positive=disp["benign_true_positive"], impact=impact.score,
               impact_confidence=impact.confidence, stage=stage.choice, stage_confidence=stage.confidence,
               p_benign_explanation=resp.answers["benign_explanation"].noul)
    return row


def ask_alerts(alerts, client, workers=8):
    def one(alert):
        if rules.allowlisted(alert):  # known-harmless by rule: no question needed
            return {**{c: "" for c in ANSWER_COLUMNS}, "alert_id": alert["alert_id"], "asked": "no"}
        return ask_one(alert, client)

    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(one, alerts))


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["alerts"])
    ap.add_argument("--limit", type=int)
    args = ap.parse_args(argv)
    alerts = read_alerts(path("alerts.csv"))[: args.limit]
    rows = ask_alerts(alerts, make_client())
    write_csv(path("answers_alerts.csv"), rows, ANSWER_COLUMNS)
    asked = [r for r in rows if r["asked"] == "yes"]
    print(f"{len(rows)} alerts, {len(asked)} asked Jev, {sum(1 for r in asked if r['error'])} errors")


if __name__ == "__main__":
    main(sys.argv[1:])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `../../.venv/bin/python -m pytest tests/test_ask.py -q`
Expected: 6 passed.

- [ ] **Step 5: Probe the real API on five alerts**

```bash
../../.venv/bin/python scripts/ask.py alerts --limit 5
head -3 data/work/answers_alerts.csv
```

Expected: `5 alerts, N asked Jev, 0 errors`, and answer rows whose `p_true_positive`, `p_false_positive` and `p_benign_true_positive` are numbers that sum to about 1. If they are all `0.0`, the SDK keys Choice probabilities in a form `choice_probs` does not handle: print `resp.answers["disposition"].probabilities` for one alert, extend `choice_probs` to that shape, and add a test for it in `test_ask.py`.

- [ ] **Step 6: Ask about every alert**

```bash
../../.venv/bin/python scripts/ask.py alerts
```

Expected: about 1,040 alerts, all but a few dozen asked, 0 errors (retry once if a few errors appear, then investigate any that remain). This takes a few minutes and costs about 1,000 requests.

- [ ] **Step 7: Commit**

The answers are saved data, so commit them with the code.

```bash
cd ../..
git add experiments/security-alert-triage
git commit -m "Ask Jev about each alert and save the answers" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Decide each alert, and sweep the thresholds

**Files:**
- Create: `scripts/decide.py`, `scripts/sweep.py`, `tests/test_decide.py`
- Modify: `scripts/evaluate.py` (none needed; it already prints the Jev section when `decisions_alerts.csv` exists)

**Interfaces:**
- Consumes: `rules.{never_suppress, allowlisted}`, `enrich.hours_apart`, `evaluate.alert_metrics`, the answers CSV from Task 3
- Produces: `decide.Policy` (frozen dataclass: `escalate_p=0.60, investigate_p=0.15, close_p=0.90, benign_explanation_p=0.80, neighbor_hours=72`), `decide.decide_alerts(alerts, answers, policy=Policy()) -> list[dict]`, `decide.load_answers(rows) -> {alert_id: row}`
- Output file: `data/work/decisions_alerts.csv` with columns `alert_id, action, reason, p_true_positive, p_benign, p_benign_explanation, impact, neighbor_doubt`.

- [ ] **Step 1: Write the failing tests**

`tests/test_decide.py`:

```python
import decide

BASE = {"asked": "yes", "error": "", "p_true_positive": "0.02", "p_false_positive": "0.6",
        "p_benign_true_positive": "0.38", "impact": "0.5", "p_benign_explanation": "0.95"}


def alert(aid, ts="2026-03-02T10:00:00Z", user="u@example.com", host="", **over):
    return {"alert_id": aid, "timestamp": ts, "user": user, "host": host, "src_ip": "", "dst_ip": "",
            "rule_name": "Some rule", "claimed_tactic": "", **over}


def answer(aid, **over):
    return {"alert_id": aid, **BASE, **over}


def run(alerts, answers, policy=decide.Policy()):
    return {d["alert_id"]: d for d in decide.decide_alerts(alerts, {a["alert_id"]: a for a in answers}, policy)}


def test_confident_benign_alert_closes_with_a_reason():
    out = run([alert("A1")], [answer("A1")])
    assert out["A1"]["action"] == "close" and "benign" in out["A1"]["reason"]


def test_likely_real_alert_escalates():
    out = run([alert("A1")], [answer("A1", p_true_positive="0.8", p_false_positive="0.1", p_benign_true_positive="0.1")])
    assert out["A1"]["action"] == "escalate"


def test_uncertain_alert_is_investigated_not_closed():
    out = run([alert("A1")], [answer("A1", p_true_positive="0.3", p_false_positive="0.4", p_benign_true_positive="0.3")])
    assert out["A1"]["action"] == "investigate"


def test_never_suppress_alert_is_never_closed():
    a = alert("A1", rule_name="Large upload to external address")
    assert run([a], [answer("A1")])["A1"]["action"] == "investigate"


def test_low_confidence_in_the_benign_explanation_blocks_closing():
    out = run([alert("A1")], [answer("A1", p_benign_explanation="0.4")])
    assert out["A1"]["action"] == "investigate"


def test_a_suspicious_neighbor_blocks_closing():
    alerts = [alert("A1"), alert("A2", ts="2026-03-03T10:00:00Z")]
    answers = [answer("A1"), answer("A2", p_true_positive="0.4", p_false_positive="0.3", p_benign_true_positive="0.3")]
    out = run(alerts, answers)
    assert out["A1"]["action"] == "investigate" and out["A1"]["neighbor_doubt"] is True


def test_a_neighbor_outside_the_window_does_not_block_closing():
    alerts = [alert("A1"), alert("A2", ts="2026-03-09T10:00:00Z")]
    answers = [answer("A1"), answer("A2", p_true_positive="0.9", p_false_positive="0.05", p_benign_true_positive="0.05")]
    assert run(alerts, answers)["A1"]["action"] == "close"


def test_allowlisted_alert_closes_without_an_answer():
    a = alert("A1", rule_name="Port scan", src_ip="192.0.2.200")
    out = run([a], [{"alert_id": "A1", "asked": "no", "error": ""}])
    assert out["A1"]["action"] == "close" and "allowlist" in out["A1"]["reason"]


def test_a_missing_or_failed_jev_answer_is_investigated_never_closed():
    out = run([alert("A1"), alert("A2", user="other@example.com")], [answer("A1", error="timeout")])
    assert out["A1"]["action"] == "investigate" and "no Jev answer" in out["A1"]["reason"]
    assert out["A2"]["action"] == "investigate"


def test_an_alert_with_no_entities_is_decided_alone():
    a = alert("A1", user="", host="")
    assert run([a], [answer("A1")])["A1"]["action"] == "close"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `../../.venv/bin/python -m pytest tests/test_decide.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'decide'`.

- [ ] **Step 3: Write the policy**

`scripts/decide.py`:

```python
"""Turn saved Jev answers into an action for each alert: close, investigate or escalate.

Run from the experiment folder: ../../.venv/bin/python scripts/decide.py
Reads data/source/alerts.csv and data/work/answers_alerts.csv; writes data/work/decisions_alerts.csv.
Closing is the risky choice, so every doubt resolves toward investigating.
"""
from collections import defaultdict
from dataclasses import dataclass

import rules
from enrich import hours_apart
from paths import path
from tables import read_alerts, read_csv, write_csv


@dataclass(frozen=True)
class Policy:
    escalate_p: float = 0.60          # probability of a true positive at or above this escalates
    investigate_p: float = 0.15       # at or above this, the alert is at least investigated
    close_p: float = 0.90             # probability of benign needed to close
    benign_explanation_p: float = 0.80  # and an ordinary explanation must fit this well
    neighbor_hours: float = 72        # nearby alerts on the same user or host can block a close


COLUMNS = ["alert_id", "action", "reason", "p_true_positive", "p_benign", "p_benign_explanation", "impact",
           "neighbor_doubt"]


def load_answers(rows):
    return {r["alert_id"]: r for r in rows}


def _view(row):
    if not row or row.get("asked") != "yes" or row.get("error"):
        return None
    return {"p_tp": float(row["p_true_positive"]),
            "p_benign": float(row["p_false_positive"]) + float(row["p_benign_true_positive"]),
            "expl": float(row["p_benign_explanation"]), "impact": float(row["impact"])}


def decide_alerts(alerts, answers, policy=Policy()):
    views = {a["alert_id"]: _view(answers.get(a["alert_id"])) for a in alerts}
    by_entity = defaultdict(list)
    for a in alerts:
        for field in ("user", "host"):
            if a[field]:
                by_entity[(field, a[field])].append(a)

    def casts_doubt(b):
        v = views[b["alert_id"]]
        if rules.never_suppress(b):
            return True
        if v is None:
            return not rules.allowlisted(b)
        return v["p_tp"] >= policy.investigate_p

    def neighbor_doubt(a):
        for field in ("user", "host"):
            if not a[field]:
                continue
            for b in by_entity[(field, a[field])]:
                if b["alert_id"] != a["alert_id"] and hours_apart(a, b) <= policy.neighbor_hours and casts_doubt(b):
                    return True
        return False

    out = []
    for a in alerts:
        v, ns, entry = views[a["alert_id"]], rules.never_suppress(a), rules.allowlisted(a)
        d = {c: "" for c in COLUMNS}
        d["alert_id"] = a["alert_id"]
        if entry:
            action, reason = "close", f"allowlist: {entry}"
        elif v is None:
            action, reason = "investigate", "no Jev answer; an unanswered alert is never closed" + (f" ({ns})" if ns else "")
        else:
            d.update(p_true_positive=round(v["p_tp"], 3), p_benign=round(v["p_benign"], 3),
                     p_benign_explanation=round(v["expl"], 3), impact=round(v["impact"], 2))
            if v["p_tp"] >= policy.escalate_p:
                action, reason = "escalate", f"Jev: true positive {v['p_tp']:.2f} >= {policy.escalate_p}"
            elif ns:
                action, reason = "investigate", f"never-suppress ({ns}); Jev true positive {v['p_tp']:.2f}"
            elif v["p_tp"] >= policy.investigate_p:
                action, reason = "investigate", f"Jev: true positive {v['p_tp']:.2f} >= {policy.investigate_p}"
            elif v["p_benign"] < policy.close_p or v["expl"] < policy.benign_explanation_p:
                action, reason = "investigate", (f"not confident enough to close: benign {v['p_benign']:.2f}, "
                                                 f"ordinary explanation {v['expl']:.2f}")
            else:
                doubt = neighbor_doubt(a)
                d["neighbor_doubt"] = doubt
                if doubt:
                    action, reason = "investigate", "nearby alerts on the same user or host cast doubt"
                else:
                    action, reason = "close", (f"Jev: benign {v['p_benign']:.2f} and an ordinary explanation "
                                               f"fits {v['expl']:.2f}")
        d.update(action=action, reason=reason)
        out.append(d)
    return out


def main():
    alerts = read_alerts(path("alerts.csv"))
    rows = decide_alerts(alerts, load_answers(read_csv(path("answers_alerts.csv"))))
    write_csv(path("decisions_alerts.csv"), rows, COLUMNS)
    print("Jev policy:", {x: sum(1 for r in rows if r["action"] == x) for x in ("close", "investigate", "escalate")})


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `../../.venv/bin/python -m pytest tests/test_decide.py -q`
Expected: 10 passed. Note that `test_a_suspicious_neighbor_blocks_closing` expects `neighbor_doubt` to be `True` (a Python bool), which the code stores; once written to CSV it becomes the string `True`.

- [ ] **Step 5: Write the sweep**

`scripts/sweep.py`:

```python
"""Sweep the policy thresholds over saved answers (no new Jev calls).

Run from the experiment folder: ../../.venv/bin/python scripts/sweep.py
For each setting: real alerts closed, real incidents with no surfaced alert, and how many alerts reach a person.
Pick settings that miss nothing first, then read the queue cost. Check the choice on a fresh seed.
"""
from itertools import product

from decide import Policy, decide_alerts, load_answers
from evaluate import alert_metrics
from paths import path
from tables import read_alerts, read_csv


def main():
    alerts = read_alerts(path("alerts.csv"))
    answers = load_answers(read_csv(path("answers_alerts.csv")))
    key = read_csv(path("answer_key.csv"))
    print(f"{'escalate':>8} {'close':>6} {'explain':>8} | {'missed alerts':>13} {'missed incidents':>16} {'reach a person':>14}")
    for esc, close, expl in product((0.4, 0.5, 0.6, 0.7), (0.8, 0.9, 0.95), (0.6, 0.8, 0.9)):
        m = alert_metrics(key, decide_alerts(alerts, answers, Policy(escalate_p=esc, close_p=close, benign_explanation_p=expl)))
        print(f"{esc:>8} {close:>6} {expl:>8} | {m['missed_alerts']:>13} {m['missed_incidents']:>16} {m['surfaced']:>14}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Decide, evaluate and sweep on the real answers**

```bash
../../.venv/bin/python scripts/decide.py
../../.venv/bin/python scripts/evaluate.py
../../.venv/bin/python scripts/sweep.py
```

Expected: a Jev policy section next to the baseline with the per-scenario tables, and a sweep table. Choose defaults only by the rule "no missed real alerts on seed 101, then the smallest queue". If that differs from the defaults in `Policy`, change the defaults, rerun `decide.py` and `evaluate.py`, and record the choice and the reason in `DESIGN.md`. Do not change data or add scenario-specific rules.

- [ ] **Step 7: Commit**

```bash
cd ../..
git add experiments/security-alert-triage
git commit -m "Decide each alert from saved Jev answers; add threshold sweep" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Group alerts into incidents, baseline first

**Files:**
- Create: `scripts/group.py`, `tests/test_group.py`
- Modify: `scripts/evaluate.py` (add `grouping_metrics` and print it)

**Interfaces:**
- Consumes: `enrich.{entities, hours_apart}`, `tables`, `paths`
- Produces: `group.WINDOW_HOURS = 72`, `group.OBVIOUS_MINUTES = 30`, `group.candidate_pairs(alerts, window_hours=WINDOW_HOURS) -> {(id_a, id_b): [shared entity keys]}` (ids sorted within a pair), `group.obvious_link(a, b) -> bool`, `group.cluster(ids, links) -> {alert_id: group_id}` (group ids `GRP-0001`...), `group.baseline_groups(alerts) -> {alert_id: group_id}`
- Produces: `evaluate.grouping_metrics(key, groups) -> {"pairs_linked", "true_pairs", "correct_pairs", "precision", "recall", "merged_incidents"}`
- Output files: `data/work/candidate_pairs.csv` (`alert_a, alert_b, shared`), `data/work/groups_baseline.csv` (`alert_id, group_id`).

- [ ] **Step 1: Write the failing tests**

`tests/test_group.py`:

```python
import group


def alert(i, ts, user="", host="", src="", dst=""):
    return {"alert_id": i, "timestamp": ts, "user": user, "host": host, "src_ip": src, "dst_ip": dst}


def test_candidate_pairs_share_an_entity_inside_the_window():
    a = alert("A", "2026-03-02T00:00:00Z", user="u@example.com")
    b = alert("B", "2026-03-04T23:00:00Z", user="u@example.com")  # 71 hours after A
    c = alert("C", "2026-03-05T01:00:00Z", user="u@example.com")  # 73 hours after A
    pairs = group.candidate_pairs([a, b, c])
    assert ("A", "B") in pairs and ("B", "C") in pairs and ("A", "C") not in pairs
    assert pairs[("A", "B")] == ["user:u@example.com"]


def test_window_boundary_is_inclusive():
    a = alert("A", "2026-03-02T00:00:00Z", host="H")
    b = alert("B", "2026-03-05T00:00:00Z", host="H")  # exactly 72 hours
    assert ("A", "B") in group.candidate_pairs([a, b])


def test_a_shared_address_links_unrelated_users():
    a = alert("A", "2026-03-02T00:00:00Z", user="x@example.com", src="192.0.2.250")
    b = alert("B", "2026-03-02T00:20:00Z", user="y@example.com", src="192.0.2.250")
    assert group.candidate_pairs([a, b])[("A", "B")] == ["ip:192.0.2.250"]


def test_an_alert_with_no_entities_pairs_with_nothing_and_groups_alone():
    lone = alert("X", "2026-03-02T00:00:00Z")
    other = alert("Y", "2026-03-02T00:05:00Z", user="u@example.com")
    assert group.candidate_pairs([lone, other]) == {}
    assert group.baseline_groups([lone, other]) == {"X": "GRP-0001", "Y": "GRP-0002"}


def test_obvious_link_needs_same_user_and_host_within_thirty_minutes():
    a = alert("A", "2026-03-02T00:00:00Z", user="u@example.com", host="H")
    at30 = alert("B", "2026-03-02T00:30:00Z", user="u@example.com", host="H")
    at31 = alert("C", "2026-03-02T00:31:00Z", user="u@example.com", host="H")
    other_host = alert("D", "2026-03-02T00:05:00Z", user="u@example.com", host="K")
    no_host = alert("E", "2026-03-02T00:05:00Z", user="u@example.com")
    assert group.obvious_link(a, at30)
    assert not group.obvious_link(a, at31)
    assert not group.obvious_link(a, other_host)
    assert not group.obvious_link(a, no_host)


def test_cluster_joins_chains_and_numbers_groups_in_order():
    groups = group.cluster(["A", "B", "C", "D"], [("A", "B"), ("B", "C")])
    assert groups == {"A": "GRP-0001", "B": "GRP-0001", "C": "GRP-0001", "D": "GRP-0002"}
```

Add to `tests/test_evaluate.py`:

```python
def test_grouping_metrics_precision_recall_and_merged_incidents():
    key = [{"alert_id": "A", "incident_id": "I1", "scenario": "s1"}, {"alert_id": "B", "incident_id": "I1", "scenario": "s1"},
           {"alert_id": "C", "incident_id": "", "scenario": "s1"}, {"alert_id": "D", "incident_id": "I2", "scenario": "s2"}]
    perfect = evaluate.grouping_metrics(key, {"A": "G1", "B": "G1", "C": "G2", "D": "G3"})
    assert perfect["precision"] == 1.0 and perfect["recall"] == 1.0 and perfect["merged_incidents"] == 0
    assert perfect["by_scenario"] == {}
    lumped = evaluate.grouping_metrics(key, {"A": "G1", "B": "G1", "C": "G1", "D": "G1"})
    assert lumped["recall"] == 1.0 and lumped["precision"] == 1 / 6
    assert lumped["merged_incidents"] == 1   # one group holds two different real incidents
    assert lumped["by_scenario"]["s1"] == {"wrong_links": 2, "missed_links": 0}
    assert lumped["by_scenario"]["cross-scenario"] == {"wrong_links": 3, "missed_links": 0}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `../../.venv/bin/python -m pytest tests/test_group.py tests/test_evaluate.py -q`
Expected: FAIL (`No module named 'group'`, and `grouping_metrics` missing).

- [ ] **Step 3: Write the grouping**

`scripts/group.py`:

```python
"""Group alerts into incidents: candidate pairs, the baseline, and (Task 6) Jev's link judgments.

Run from the experiment folder: ../../.venv/bin/python scripts/group.py baseline
Writes data/work/candidate_pairs.csv and data/work/groups_baseline.csv.
"""
import sys
from collections import defaultdict
from itertools import combinations

from enrich import entities, hours_apart
from paths import path
from tables import read_alerts, write_csv

WINDOW_HOURS = 72
OBVIOUS_MINUTES = 30


def candidate_pairs(alerts, window_hours=WINDOW_HOURS):
    """Alert pairs that share a user, host or address within the window, with the entities they share."""
    by_entity = defaultdict(list)
    for a in alerts:
        for e in entities(a):
            by_entity[e].append(a)
    shared = defaultdict(set)
    for e, members in by_entity.items():
        for a, b in combinations(members, 2):
            if hours_apart(a, b) <= window_hours:
                shared[tuple(sorted((a["alert_id"], b["alert_id"])))].add(e)
    return {pair: sorted(es) for pair, es in shared.items()}


def obvious_link(a, b):
    """Same user and same host within 30 minutes: no question needed."""
    return (bool(a["user"]) and a["user"] == b["user"] and bool(a["host"]) and a["host"] == b["host"]
            and hours_apart(a, b) * 60 <= OBVIOUS_MINUTES)


def cluster(ids, links):
    """Union-find. Returns {alert_id: group_id}, with groups numbered in order of their first member."""
    parent = {i: i for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in links:
        parent[find(a)] = find(b)
    names, out = {}, {}
    for i in sorted(ids):
        root = find(i)
        names.setdefault(root, f"GRP-{len(names) + 1:04d}")
        out[i] = names[root]
    return out


def baseline_groups(alerts):
    """The rules-only baseline: every candidate pair is linked."""
    return cluster([a["alert_id"] for a in alerts], candidate_pairs(alerts).keys())


def write_groups(groups, filename):
    write_csv(path(filename), [{"alert_id": i, "group_id": g} for i, g in sorted(groups.items())], ["alert_id", "group_id"])


def main(argv):
    alerts = read_alerts(path("alerts.csv"))
    if argv == ["baseline"]:
        pairs = candidate_pairs(alerts)
        write_csv(path("candidate_pairs.csv"),
                  [{"alert_a": a, "alert_b": b, "shared": " ".join(s)} for (a, b), s in sorted(pairs.items())],
                  ["alert_a", "alert_b", "shared"])
        groups = baseline_groups(alerts)
        write_groups(groups, "groups_baseline.csv")
        print(f"baseline: {len(pairs)} candidate pairs, {len(set(groups.values()))} groups from {len(alerts)} alerts")
    else:
        raise SystemExit("usage: group.py baseline")


if __name__ == "__main__":
    main(sys.argv[1:])
```

- [ ] **Step 4: Add the grouping metrics to evaluate.py**

Add this function above `main` in `scripts/evaluate.py`, add `from itertools import combinations` to the imports, and call it from `main` (Step 5):

```python
def grouping_metrics(key, groups):
    incident = {k["alert_id"]: k["incident_id"] for k in key}
    by_group, by_incident = defaultdict(list), defaultdict(list)
    for aid, g in groups.items():
        by_group[g].append(aid)
    for aid, inc in incident.items():
        if inc:
            by_incident[inc].append(aid)
    linked = {pair for members in by_group.values() for pair in combinations(sorted(members), 2)}
    truth = {pair for members in by_incident.values() for pair in combinations(sorted(members), 2)}
    correct = linked & truth
    merged = sum(1 for members in by_group.values() if len({incident[a] for a in members if incident[a]}) > 1)
    scenario = {k["alert_id"]: k.get("scenario", "") for k in key}
    by_scenario = defaultdict(lambda: {"wrong_links": 0, "missed_links": 0})
    for label, pairs in (("wrong_links", linked - truth), ("missed_links", truth - linked)):
        for a, b in pairs:
            owner = scenario[a] if scenario[a] == scenario[b] else "cross-scenario"
            by_scenario[owner][label] += 1
    return {"pairs_linked": len(linked), "true_pairs": len(truth), "correct_pairs": len(correct),
            "precision": len(correct) / len(linked) if linked else 1.0,
            "recall": len(correct) / len(truth) if truth else 1.0, "merged_incidents": merged,
            "by_scenario": {s: dict(v) for s, v in by_scenario.items()}}
```

- [ ] **Step 5: Print grouping in the evaluation**

In `main()` of `scripts/evaluate.py`, after the alert sections, add:

```python
    for name, file in (("Baseline grouping (shared entity, 72 hours)", "groups_baseline.csv"),
                       ("Jev grouping", "groups_jev.csv")):
        if os.path.exists(path(file)):
            groups = {r["alert_id"]: r["group_id"] for r in read_csv(path(file))}
            g = grouping_metrics(key, groups)
            print(f"\n{name}: {len(set(groups.values()))} groups; linked pairs {g['pairs_linked']}, "
                  f"correct {g['correct_pairs']} of {g['true_pairs']} true pairs "
                  f"(precision {g['precision']:.0%}, recall {g['recall']:.0%}); "
                  f"groups that hold two different real incidents: {g['merged_incidents']}")
            for s, v in sorted(g["by_scenario"].items()):
                print(f"    {s:<26} wrong links {v['wrong_links']}, missed links {v['missed_links']}")
```

- [ ] **Step 6: Run the tests, then the baseline grouping**

```bash
../../.venv/bin/python -m pytest -q
../../.venv/bin/python scripts/group.py baseline
../../.venv/bin/python scripts/evaluate.py
```

Expected: all tests pass; the baseline line shows recall near 100% and low precision (shared servers and the shared address over-link). Record the numbers in `DESIGN.md` as the grouping floor.

- [ ] **Step 7: Commit**

```bash
cd ../..
git add experiments/security-alert-triage
git commit -m "Add candidate pairs, baseline grouping and grouping metrics" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Jev judges the ambiguous links

**Files:**
- Modify: `scripts/ask.py` (add link questions and `links` command), `scripts/group.py` (add link decisions and Jev groups, plus the incident table), `tests/test_ask.py`, `tests/test_group.py`

**Interfaces:**
- Consumes: `group.{candidate_pairs, obvious_link, cluster}`, `decide` decisions for severity and action
- Produces: `ask.LINK_QUESTIONS`, `ask.link_state(a, b, shared) -> dict`, `ask.ask_link(a, b, shared, client, attempts=4) -> dict`, `ask.ask_links(pairs, alerts_by_id, client, workers=8) -> list[dict]`, `ask.LINK_COLUMNS = ["alert_a", "alert_b", "asked", "score", "p_coincidence", "error"]`
- Produces: `group.LinkPolicy(link_score=1.6, coincidence_p=0.5)`, `group.decide_links(pairs, alerts_by_id, answers, policy=LinkPolicy()) -> list[dict]` (columns `alert_a, alert_b, link, rule, detail`), `group.jev_groups(alerts, link_rows) -> {alert_id: group_id}`, `group.incident_table(alerts, groups, decisions) -> list[dict]`
- Output files: `data/work/answers_links.csv`, `data/work/decisions_links.csv`, `data/work/groups_jev.csv`, `data/output_incidents.csv` (under `data/output/`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ask.py`:

```python
def link_response(score=2.0, coincidence=0.1):
    return NS(answers={"same_incident": NS(score=score, confidence=0.6, probabilities={0: 0.0, 1: 0.0, 2: 1.0}),
                       "shared_entity_is_coincidence": NS(noul=coincidence)})


def test_link_state_names_both_alerts_and_the_shared_entities():
    state = ask.link_state(ALERT, SCAN, ["ip:192.0.2.250"])
    assert state["alert_a"]["rule_name"] == "Sign-in from new country"
    assert state["shared_entities"] == ["ip:192.0.2.250"]


def test_ask_links_saves_score_and_coincidence():
    client = FakeClient(response=link_response(1.8, 0.2))
    rows = ask.ask_links({("A1", "A2"): ["user:a"]}, {"A1": ALERT, "A2": SCAN}, client, workers=1)
    assert rows == [{"alert_a": "A1", "alert_b": "A2", "asked": "yes", "score": 1.8, "p_coincidence": 0.2, "error": ""}]
```

Append to `tests/test_group.py`:

```python
def pair_alerts():
    a = alert("A", "2026-03-02T00:00:00Z", user="u@example.com", host="H", src="203.0.113.5")
    b = alert("B", "2026-03-02T05:00:00Z", user="u@example.com", host="K", src="203.0.113.5")
    return {"A": a, "B": b}


def test_decide_links_uses_the_obvious_rule_without_an_answer():
    a = alert("A", "2026-03-02T00:00:00Z", user="u@example.com", host="H")
    b = alert("B", "2026-03-02T00:10:00Z", user="u@example.com", host="H")
    rows = group.decide_links({("A", "B"): ["host:H"]}, {"A": a, "B": b}, {})
    assert rows[0]["link"] == "yes" and rows[0]["rule"] == "obvious_link"


def test_decide_links_follows_jev_and_rejects_coincidences():
    alerts = pair_alerts()
    pairs = {("A", "B"): ["ip:203.0.113.5"]}
    yes = group.decide_links(pairs, alerts, {("A", "B"): {"score": "1.9", "p_coincidence": "0.1", "error": ""}})
    no = group.decide_links(pairs, alerts, {("A", "B"): {"score": "1.9", "p_coincidence": "0.8", "error": ""}})
    unrelated = group.decide_links(pairs, alerts, {("A", "B"): {"score": "0.3", "p_coincidence": "0.1", "error": ""}})
    assert yes[0]["link"] == "yes" and yes[0]["rule"] == "jev_link"
    assert no[0]["link"] == "no" and unrelated[0]["link"] == "no"


def test_an_unanswered_pair_is_not_linked_and_says_so():
    rows = group.decide_links({("A", "B"): ["ip:x"]}, pair_alerts(), {})
    assert rows[0]["link"] == "no" and rows[0]["rule"] == "no_jev_answer"


def test_jev_groups_follow_the_linked_pairs():
    alerts = list(pair_alerts().values())
    linked = [{"alert_a": "A", "alert_b": "B", "link": "yes"}]
    assert group.jev_groups(alerts, linked) == {"A": "GRP-0001", "B": "GRP-0001"}
    assert group.jev_groups(alerts, [{"alert_a": "A", "alert_b": "B", "link": "no"}]) == {"A": "GRP-0001", "B": "GRP-0002"}


def test_incident_table_takes_the_strongest_action_and_severity_in_a_group():
    alerts = [alert("A", "2026-03-02T00:00:00Z", user="u@example.com"), alert("B", "2026-03-02T01:00:00Z", user="u@example.com")]
    decisions = [
        {"alert_id": "A", "action": "close", "p_true_positive": "0.02", "p_benign": "0.98", "impact": "0.4"},
        {"alert_id": "B", "action": "escalate", "p_true_positive": "0.9", "p_benign": "0.1", "impact": "2.8"}]
    rows = group.incident_table(alerts, {"A": "GRP-0001", "B": "GRP-0001"}, decisions)
    assert rows == [{"group_id": "GRP-0001", "alerts": 2, "action": "escalate", "severity": "critical",
                     "users": "u@example.com", "max_p_true_positive": 0.9}]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `../../.venv/bin/python -m pytest tests/test_ask.py tests/test_group.py -q`
Expected: FAIL with `AttributeError: module 'ask' has no attribute 'link_state'` and similar.

- [ ] **Step 3: Add the link questions to ask.py**

Add below `ask_alerts` in `scripts/ask.py`:

```python
LINK_QUESTIONS = {
    "same_incident": Score(
        instructions="Are these two alerts part of the same attack or event?",
        criteria=["They are unrelated events that only share a name or address.",
                  "They might be related, but the evidence is thin.",
                  "They are clearly steps of the same attack or the same event."]),
    "shared_entity_is_coincidence": Noul(
        instructions="Is the shared user, host or address a coincidence, for example a shared office or guest network address used by many people?"),
}
LINK_COLUMNS = ["alert_a", "alert_b", "asked", "score", "p_coincidence", "error"]


def link_state(a, b, shared):
    return {"alert_a": {k: a[k] for k in ALERT_FIELDS if a.get(k)},
            "alert_b": {k: b[k] for k in ALERT_FIELDS if b.get(k)},
            "shared_entities": list(shared)}


def ask_link(a, b, shared, client, attempts=4):
    row = {"alert_a": a["alert_id"], "alert_b": b["alert_id"], "asked": "yes", "score": "", "p_coincidence": "", "error": ""}
    for attempt in range(attempts):
        try:
            resp = client.system_one(state=link_state(a, b, shared), questions=LINK_QUESTIONS)
            break
        except Exception as e:
            if attempt == attempts - 1:
                row["error"] = str(e)[:200]
                return row
            time.sleep(2 ** attempt)
    row.update(score=resp.answers["same_incident"].score,
               p_coincidence=resp.answers["shared_entity_is_coincidence"].noul)
    return row


def ask_links(pairs, alerts_by_id, client, workers=8):
    """Ask about every candidate pair that the obvious-link rule does not already settle."""
    from group import obvious_link  # imported here: group.py imports nothing from ask.py, but this keeps ask.py light

    todo = [(a, b, s) for (a, b), s in pairs.items() if not obvious_link(alerts_by_id[a], alerts_by_id[b])]
    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(lambda t: ask_link(alerts_by_id[t[0]], alerts_by_id[t[1]], t[2], client), todo))
```

And extend `main()`:

```python
def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["alerts", "links"])
    ap.add_argument("--limit", type=int)
    args = ap.parse_args(argv)
    alerts = read_alerts(path("alerts.csv"))
    if args.what == "alerts":
        rows = ask_alerts(alerts[: args.limit], make_client())
        write_csv(path("answers_alerts.csv"), rows, ANSWER_COLUMNS)
        asked = [r for r in rows if r["asked"] == "yes"]
        print(f"{len(rows)} alerts, {len(asked)} asked Jev, {sum(1 for r in asked if r['error'])} errors")
    else:
        from group import candidate_pairs
        pairs = candidate_pairs(alerts)
        pairs = dict(list(pairs.items())[: args.limit])
        rows = ask_links(pairs, {a["alert_id"]: a for a in alerts}, make_client())
        write_csv(path("answers_links.csv"), rows, LINK_COLUMNS)
        print(f"{len(pairs)} candidate pairs, {len(rows)} asked Jev, {sum(1 for r in rows if r['error'])} errors")
```

Also change the `choices=["alerts"]` argument in the existing parser accordingly (the code above replaces it).

- [ ] **Step 4: Add the link decisions, Jev groups and incident table to group.py**

Add `from dataclasses import dataclass` and `from schema import ACTIONS` to the imports, then below `write_groups`:

```python
@dataclass(frozen=True)
class LinkPolicy:
    link_score: float = 1.6      # Jev's same-incident Score runs 0 to 2
    coincidence_p: float = 0.5   # a shared entity judged a coincidence at or above this does not link


def decide_links(pairs, alerts_by_id, answers, policy=LinkPolicy()):
    rows = []
    for (a, b), shared in pairs.items():
        row = {"alert_a": a, "alert_b": b}
        if obvious_link(alerts_by_id[a], alerts_by_id[b]):
            rows.append({**row, "link": "yes", "rule": "obvious_link", "detail": "same user and host within 30 minutes"})
            continue
        ans = answers.get((a, b))
        if not ans or ans.get("error") or ans.get("score", "") == "":
            rows.append({**row, "link": "no", "rule": "no_jev_answer",
                         "detail": "unanswered pairs are not linked; each alert still gets its own decision"})
            continue
        score, coincidence = float(ans["score"]), float(ans["p_coincidence"])
        if score >= policy.link_score and coincidence < policy.coincidence_p:
            rows.append({**row, "link": "yes", "rule": "jev_link",
                         "detail": f"same-incident {score:.2f} >= {policy.link_score}, coincidence {coincidence:.2f}"})
        else:
            rows.append({**row, "link": "no", "rule": "jev_no_link",
                         "detail": f"same-incident {score:.2f}, coincidence {coincidence:.2f}; shared {' '.join(shared)}"})
    return rows


def jev_groups(alerts, link_rows):
    return cluster([a["alert_id"] for a in alerts], [(r["alert_a"], r["alert_b"]) for r in link_rows if r["link"] == "yes"])


_SEVERITY_BY_IMPACT = ["low", "medium", "high", "critical"]   # Jev's impact Score 0-3 rounded to a level
_SEVERITY_RANK = {"informational": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def _severity(decision):
    if decision["impact"] == "":
        return "informational"
    if float(decision["p_benign"]) >= 0.5:
        return "informational"
    return _SEVERITY_BY_IMPACT[min(3, max(0, round(float(decision["impact"]))))]


def incident_table(alerts, groups, decisions):
    dec = {d["alert_id"]: d for d in decisions}
    members = defaultdict(list)
    for a in alerts:
        members[groups[a["alert_id"]]].append(a)
    rows = []
    for g in sorted(members):
        ds = [dec[a["alert_id"]] for a in members[g]]
        rows.append({
            "group_id": g, "alerts": len(ds),
            "action": max((d["action"] for d in ds), key=ACTIONS.index),
            "severity": max((_severity(d) for d in ds), key=_SEVERITY_RANK.get),
            "users": " ".join(sorted({a["user"] for a in members[g] if a["user"]})),
            "max_p_true_positive": max((float(d["p_true_positive"]) for d in ds if d["p_true_positive"] != ""), default=0.0)})
    return rows
```

And extend `main()` in `scripts/group.py`:

```python
    elif argv == ["jev"]:
        from tables import read_csv
        by_id = {a["alert_id"]: a for a in alerts}
        pairs = candidate_pairs(alerts)
        answers = {(r["alert_a"], r["alert_b"]): r for r in read_csv(path("answers_links.csv"))}
        link_rows = decide_links(pairs, by_id, answers)
        write_csv(path("decisions_links.csv"), link_rows, ["alert_a", "alert_b", "link", "rule", "detail"])
        groups = jev_groups(alerts, link_rows)
        write_groups(groups, "groups_jev.csv")
        write_csv(path("output_incidents.csv"), incident_table(alerts, groups, read_csv(path("decisions_alerts.csv"))),
                  ["group_id", "alerts", "action", "severity", "users", "max_p_true_positive"])
        print(f"Jev grouping: {sum(1 for r in link_rows if r['link'] == 'yes')} of {len(link_rows)} pairs linked, "
              f"{len(set(groups.values()))} groups")
```

Change the usage line to `usage: group.py baseline|jev` and move the `if argv == ["baseline"]` so the structure is `if ... elif ... else`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `../../.venv/bin/python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 6: Probe ten pairs, then ask about all of them**

```bash
../../.venv/bin/python scripts/ask.py links --limit 10
head -3 data/work/answers_links.csv
../../.venv/bin/python scripts/ask.py links
../../.venv/bin/python scripts/group.py jev
../../.venv/bin/python scripts/evaluate.py
```

Expected: 0 errors; the evaluation shows the Jev grouping next to the baseline, with higher precision and similar recall, and no groups holding two different real incidents (the `two_incidents_one_user` and `shared_address` traps). Write the numbers into `DESIGN.md`. If the traps merge, the rule is wrong, not the data: adjust `LinkPolicy` or the link questions' wording, rerun `group.py jev` (no new Jev calls for policy changes), and record what changed.

- [ ] **Step 7: Commit**

```bash
cd ../..
git add experiments/security-alert-triage
git commit -m "Jev judges ambiguous links; build incidents" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Account risk

**Files:**
- Create: `scripts/risk.py`, `tests/test_risk.py`
- Modify: `scripts/evaluate.py` (ranking metrics and printout)

**Interfaces:**
- Consumes: alerts, `decisions_alerts.csv` rows (`impact`, `p_true_positive` as strings), groups `{alert_id: group_id}`, `enrich.parse_ts`
- Produces: `risk.finding_risk(impact_level, p_true_positive) -> float` (0 to 100), `risk.findings(alerts, decisions, groups) -> list[dict]` (keys `user, ts, detection, risk, alert_id`), `risk.baseline_findings(alerts) -> list[dict]`, `risk.score_window(findings) -> float`, `risk.account_scores(findings, window_days=7) -> {user: peak score}`, `risk.rank(scores) -> [(user, score)]`
- Produces: `evaluate.ranking_metrics(ranked, key, ks=(10, 20)) -> {"compromised", "top_k": {k: hits}, "first_hit_rank"}`
- Output files: `data/output/output_account_risk.csv` and `output_account_risk_baseline.csv` with columns `rank, user, score, compromised` (the last only filled by `evaluate`, so leave it out of these files; the report joins the key).

- [ ] **Step 1: Write the failing tests**

`tests/test_risk.py`:

```python
import risk

T0 = "2026-03-02T00:00:00Z"


def alert(aid, user="u@example.com", ts=T0, rule="Rule A"):
    return {"alert_id": aid, "user": user, "timestamp": ts, "rule_name": rule, "source_severity": "high"}


def decision(aid, impact="3", p_tp="1.0"):
    return {"alert_id": aid, "impact": impact, "p_true_positive": p_tp}


def test_finding_risk_is_impact_times_confidence():
    assert risk.finding_risk(3, 1.0) == 100
    assert risk.finding_risk(0, 1.0) == 0
    assert risk.finding_risk(1.5, 0.5) == 25.0


def test_findings_use_corroboration_and_skip_unanswered_alerts():
    alerts = [alert("A"), alert("B"), alert("C"), alert("D", user="v@example.com")]
    decisions = [decision("A"), decision("B"), decision("C"), {"alert_id": "D", "impact": "", "p_true_positive": ""}]
    groups = {"A": "G1", "B": "G1", "C": "G1", "D": "G2"}
    fs = risk.findings(alerts, decisions, groups)
    assert [f["alert_id"] for f in fs] == ["A", "B", "C"]
    assert all(f["risk"] == 100 for f in fs)             # group of three counts in full


def test_a_lone_alert_counts_for_half():
    fs = risk.findings([alert("A")], [decision("A")], {"A": "G1"})
    assert fs[0]["risk"] == 50.0


def test_a_missing_user_is_attributed_through_the_group():
    alerts = [alert("A"), alert("B"), alert("C", user="")]
    decisions = [decision("A"), decision("B"), decision("C")]
    fs = risk.findings(alerts, decisions, {"A": "G1", "B": "G1", "C": "G1"})
    assert {f["user"] for f in fs} == {"u@example.com"} and len(fs) == 3


def test_an_alert_with_no_user_and_no_group_mates_is_ignored():
    fs = risk.findings([alert("A", user="")], [decision("A")], {"A": "G1"})
    assert fs == []


def test_account_score_is_bounded_and_uses_a_seven_day_window():
    many = [{"user": "u", "ts": risk.parse_ts(T0), "detection": f"r{i}", "risk": 100.0, "alert_id": str(i)} for i in range(400)]
    assert risk.account_scores(many)["u"] <= 100
    old = {"user": "v", "ts": risk.parse_ts("2026-03-01T00:00:00Z"), "detection": "a", "risk": 100.0, "alert_id": "1"}
    new = {"user": "v", "ts": risk.parse_ts("2026-03-09T00:00:00Z"), "detection": "b", "risk": 100.0, "alert_id": "2"}
    together = risk.account_scores([old, {**new, "ts": risk.parse_ts("2026-03-05T00:00:00Z")}])["v"]
    apart = risk.account_scores([old, new])["v"]
    assert together > apart                                  # eight days apart do not add up


def test_many_findings_for_one_user_stay_fast():
    import time
    many = [{"user": "u", "ts": risk.parse_ts(T0), "detection": "r", "risk": 10.0, "alert_id": str(i)} for i in range(300)]
    start = time.time()
    risk.account_scores(many)
    assert time.time() - start < 2


def test_rank_orders_by_score_then_name():
    assert risk.rank({"b": 50.0, "a": 50.0, "c": 70.0}) == [("c", 70.0), ("a", 50.0), ("b", 50.0)]


def test_baseline_findings_use_detector_severity_and_a_fixed_confidence():
    fs = risk.baseline_findings([alert("A")])
    assert fs[0]["risk"] == 45.0     # high severity 90 x confidence 0.5
```

Add to `tests/test_evaluate.py`:

```python
def test_ranking_metrics_counts_compromised_accounts_in_the_top_k():
    key = [{"compromised_user": "a", "scenario": "s1"}, {"compromised_user": "b", "scenario": "s2"},
           {"compromised_user": "", "scenario": "s3"}]
    ranked = [("x", 90.0), ("a", 80.0), ("y", 70.0), ("b", 60.0)]
    m = evaluate.ranking_metrics(ranked, key, ks=(2, 4))
    assert m["compromised"] == 2 and m["top_k"] == {2: 1, 4: 2} and m["first_hit_rank"] == 2
    assert m["by_scenario"] == {"s1": {"compromised": 1, "top_2": 1, "top_4": 1},
                                "s2": {"compromised": 1, "top_2": 0, "top_4": 1}}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `../../.venv/bin/python -m pytest tests/test_risk.py tests/test_evaluate.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'risk'`.

- [ ] **Step 3: Write the risk module**

`scripts/risk.py`:

```python
"""Account risk: impact times confidence per finding, rolled up per account over seven days.

Run from the experiment folder: ../../.venv/bin/python scripts/risk.py
Writes data/output/output_account_risk.csv (Jev) and output_account_risk_baseline.csv (detector severity).
Every account is scored at its worst seven-day window, because the incidents are spread over two weeks.
"""
from collections import Counter, defaultdict
from datetime import timedelta

from enrich import parse_ts
from paths import path
from tables import read_alerts, read_csv, write_csv

WINDOW_DAYS = 7
BASELINE_IMPACT = {"informational": 10, "low": 30, "medium": 60, "high": 90, "critical": 100}
BASELINE_CONFIDENCE = 0.5


def finding_risk(impact_level, p_true_positive):
    """impact_level is Jev's 0-3 Score; returns 0-100 (impact 0-100 times confidence 0-1)."""
    return impact_level / 3 * 100 * p_true_positive


def findings(alerts, decisions, groups):
    """One finding per answered alert. An alert with no user takes the user of its group mates."""
    dec = {d["alert_id"]: d for d in decisions}
    size = Counter(groups.values())
    group_users = defaultdict(Counter)
    for a in alerts:
        if a["user"]:
            group_users[groups[a["alert_id"]]][a["user"]] += 1
    out = []
    for a in alerts:
        d = dec[a["alert_id"]]
        if d["impact"] == "" or d["p_true_positive"] == "":
            continue
        user = a["user"]
        if not user:
            counts = group_users.get(groups[a["alert_id"]])
            if not counts:
                continue
            user = max(sorted(counts), key=counts.get)
        corroboration = 1.0 if size[groups[a["alert_id"]]] >= 3 else 0.5
        out.append({"user": user, "ts": parse_ts(a["timestamp"]), "detection": a["rule_name"],
                    "risk": finding_risk(float(d["impact"]), float(d["p_true_positive"])) * corroboration,
                    "alert_id": a["alert_id"]})
    return out


def baseline_findings(alerts):
    return [{"user": a["user"], "ts": parse_ts(a["timestamp"]), "detection": a["rule_name"],
             "risk": BASELINE_IMPACT[a["source_severity"]] * BASELINE_CONFIDENCE, "alert_id": a["alert_id"]}
            for a in alerts if a["user"]]


def score_window(fs):
    total = sum(f["risk"] for f in fs)
    worst = max(f["risk"] for f in fs)
    serious = sum(1 for f in fs if f["risk"] >= 50)
    kinds = len({f["detection"] for f in fs})
    return 100 * (0.4 * min(total / 150, 1) + 0.3 * min(worst / 100, 1) + 0.2 * min(serious / 3, 1) + 0.1 * min(kinds / 4, 1))


def account_scores(fs, window_days=WINDOW_DAYS):
    by_user = defaultdict(list)
    for f in fs:
        by_user[f["user"]].append(f)
    out = {}
    for user, items in by_user.items():
        items.sort(key=lambda f: f["ts"])
        best, left = 0.0, 0
        for right, end in enumerate(items):
            while items[left]["ts"] <= end["ts"] - timedelta(days=window_days):
                left += 1
            best = max(best, score_window(items[left: right + 1]))
        out[user] = round(best, 2)
    return out


def rank(scores):
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


def _write(filename, scores):
    write_csv(path(filename), [{"rank": i, "user": u, "score": s} for i, (u, s) in enumerate(rank(scores), 1)],
              ["rank", "user", "score"])


def main():
    alerts = read_alerts(path("alerts.csv"))
    decisions = read_csv(path("decisions_alerts.csv"))
    groups = {r["alert_id"]: r["group_id"] for r in read_csv(path("groups_jev.csv"))}
    jev, base = account_scores(findings(alerts, decisions, groups)), account_scores(baseline_findings(alerts))
    _write("output_account_risk.csv", jev)
    _write("output_account_risk_baseline.csv", base)
    print(f"account risk: {len(jev)} accounts scored with Jev, {len(base)} with detector severity")


if __name__ == "__main__":
    main()
```

The window uses two pointers, so the cost per user is linear in its findings.

- [ ] **Step 4: Add the ranking metrics to evaluate.py**

Add above `main` in `scripts/evaluate.py`:

```python
def ranking_metrics(ranked, key, ks=(10, 20)):
    scenario_of = {k["compromised_user"]: k["scenario"] for k in key if k["compromised_user"]}
    compromised = set(scenario_of)
    users = [u for u, _ in ranked]
    hits = {k: sum(1 for u in users[:k] if u in compromised) for k in ks}
    first = next((i for i, u in enumerate(users, 1) if u in compromised), None)
    by_scenario = {}
    for user, scenario in scenario_of.items():
        row = by_scenario.setdefault(scenario, {"compromised": 0, **{f"top_{k}": 0 for k in ks}})
        row["compromised"] += 1
        for k in ks:
            row[f"top_{k}"] += 1 if user in users[:k] else 0
    return {"compromised": len(compromised), "top_k": hits, "first_hit_rank": first, "by_scenario": by_scenario}
```

and in `main()` after the grouping block:

```python
    for name, file in (("Account risk with Jev", "output_account_risk.csv"),
                       ("Account risk, detector severity only", "output_account_risk_baseline.csv")):
        if os.path.exists(path(file)):
            ranked = [(r["user"], float(r["score"])) for r in read_csv(path(file))]
            m = ranking_metrics(ranked, key)
            print(f"\n{name}: {m['compromised']} compromised accounts; "
                  + ", ".join(f"top {k}: {n}" for k, n in m["top_k"].items()) + f"; first hit at rank {m['first_hit_rank']}")
            for s, v in sorted(m["by_scenario"].items()):
                print(f"    {s:<26} " + ", ".join(f"{label} {n}" for label, n in v.items()))
```

- [ ] **Step 5: Run the tests, then the real ranking**

```bash
../../.venv/bin/python -m pytest -q
../../.venv/bin/python scripts/risk.py
../../.venv/bin/python scripts/evaluate.py
```

Expected: all tests pass; the evaluation shows how many of the 21 compromised accounts land in the top 10 and top 20 for Jev and for the baseline. Record both in `DESIGN.md`.

- [ ] **Step 6: Commit**

```bash
cd ../..
git add experiments/security-alert-triage
git commit -m "Add account risk scoring and ranking metrics" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Report and run scripts

**Files:**
- Create: `scripts/report.py`, `tests/test_report.py`, `run_all.sh`, `replay.sh`

**Interfaces:**
- Consumes: every CSV the earlier tasks wrote, and `evaluate.{alert_metrics}`
- Produces: `report.build(data) -> dict` where `data` is a dict of already-read tables (see the test), and `data/reports/triage_report.html`

- [ ] **Step 1: Write the failing test**

`tests/test_report.py`:

```python
import report


def tables():
    return {
        "alerts": [{"alert_id": "A1", "timestamp": "2026-03-02T00:00:00Z", "rule_name": "R", "description": "d",
                    "source_severity": "high", "user": "u@example.com", "host": "", "src_ip": "", "dst_ip": "",
                    "detector": "identity_provider", "claimed_tactic": "", "asset_criticality": "", "user_access": ""}],
        "key": [{"alert_id": "A1", "incident_id": "INC-001", "disposition": "true_positive", "true_severity": "high",
                 "true_tactic": "initial_access", "scenario": "phish_to_exfil", "compromised_user": "u@example.com"}],
        "decisions": [{"alert_id": "A1", "action": "escalate", "reason": "Jev", "p_true_positive": "0.9",
                       "p_benign": "0.1", "p_benign_explanation": "0.1", "impact": "2.5", "neighbor_doubt": ""}],
        "baseline": [{"alert_id": "A1", "action": "close", "reason": "detector severity low"}],
        "groups": [{"alert_id": "A1", "group_id": "GRP-0001"}],
        "incidents": [{"group_id": "GRP-0001", "alerts": "1", "action": "escalate", "severity": "high",
                       "users": "u@example.com", "max_p_true_positive": "0.9"}],
        "risk": [{"rank": "1", "user": "u@example.com", "score": "80"}],
        "risk_baseline": [{"rank": "1", "user": "u@example.com", "score": "45"}],
    }


def test_build_joins_decisions_truth_and_baseline():
    data = report.build(tables())
    alert = data["alerts"][0]
    assert alert["action"] == "escalate" and alert["baseline_action"] == "close"
    assert alert["verdict"] == "right" and alert["scenario"] == "phish_to_exfil"
    assert data["accounts"][0]["compromised"] is True
    assert data["incidents"][0]["group_id"] == "GRP-0001"


def test_a_closed_real_alert_is_marked_missed():
    t = tables()
    t["decisions"][0]["action"] = "close"
    assert report.build(t)["alerts"][0]["verdict"] == "missed"


def test_page_embeds_the_data():
    html = report.render(report.build(tables()))
    assert "phish_to_exfil" in html and "<script>" in html
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `../../.venv/bin/python -m pytest tests/test_report.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'report'`.

- [ ] **Step 3: Write the report**

`scripts/report.py`:

```python
"""Write data/reports/triage_report.html: browse every alert, incident and account with its evidence.

Run from the experiment folder: ../../.venv/bin/python scripts/report.py
Because the data is synthetic, each alert also shows whether the decision was right, from the answer key.
"""
import json

from paths import path
from tables import read_csv


def build(t):
    key = {k["alert_id"]: k for k in t["key"]}
    dec = {d["alert_id"]: d for d in t["decisions"]}
    base = {d["alert_id"]: d for d in t["baseline"]}
    group = {g["alert_id"]: g["group_id"] for g in t["groups"]}
    alerts = []
    for a in t["alerts"]:
        k, d = key[a["alert_id"]], dec[a["alert_id"]]
        real = k["disposition"] == "true_positive"
        if real and d["action"] == "close":
            verdict = "missed"
        elif not real and d["action"] != "close":
            verdict = "queue cost"
        else:
            verdict = "right"
        alerts.append({**a, "scenario": k["scenario"], "disposition": k["disposition"], "incident": k["incident_id"],
                       "action": d["action"], "reason": d["reason"], "p_tp": d["p_true_positive"],
                       "baseline_action": base[a["alert_id"]]["action"], "baseline_reason": base[a["alert_id"]]["reason"],
                       "group": group[a["alert_id"]], "verdict": verdict})
    compromised = {k["compromised_user"] for k in t["key"] if k["compromised_user"]}
    accounts = [{**r, "compromised": r["user"] in compromised} for r in t["risk"]]
    base_rank = {r["user"]: r["rank"] for r in t["risk_baseline"]}
    for a in accounts:
        a["baseline_rank"] = base_rank.get(a["user"], "")
    return {"alerts": alerts, "incidents": t["incidents"], "accounts": accounts}


def render(data):
    return PAGE.replace("__DATA__", json.dumps(data).replace("</", "<\\/"))


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Alert triage</title><style>
:root{--bg:#fafaf9;--fg:#1c1917;--mut:#78716c;--card:#fff;--line:#e7e5e4;--ok:#15803d;--bad:#b91c1c;--rev:#b45309}
@media(prefers-color-scheme:dark){:root{--bg:#1c1917;--fg:#fafaf9;--mut:#a8a29e;--card:#292524;--line:#44403c;--ok:#4ade80;--bad:#f87171;--rev:#fbbf24}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 16px}
h1{font-size:16px;margin:0 0 8px}label{margin-right:12px;color:var(--mut)}select,input{font:inherit;color:inherit;background:var(--card);border:1px solid var(--line);border-radius:6px;padding:3px 6px}
main{padding:16px;max-width:1000px;margin:auto}.card{background:var(--card);border:1px solid var(--line);border-radius:8px;margin-bottom:10px;padding:8px 12px}
.mut{color:var(--mut)}.ok{color:var(--ok)}.bad{color:var(--bad)}.rev{color:var(--rev)}b{font-weight:600}
button{font:inherit;padding:6px 12px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:inherit;cursor:pointer}
</style></head><body><header><h1>Alert triage</h1>
<label>View <select id="v"><option value="alerts">alerts</option><option value="incidents">incidents</option><option value="accounts">accounts by risk</option></select></label>
<label>Show <select id="f"></select></label><label>Search <input id="q" size="14"></label></header>
<main><p class="mut" id="sum"></p><div id="list"></div><button id="more">Show more</button></main>
<script>
const D=__DATA__;let shown=0;const PAGE=60,$=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const FILTERS={alerts:[['missed','missed real alerts'],['queue cost','benign alerts that reach a person'],['disagree','Jev and baseline disagree'],['all','all']],incidents:[['all','all']],accounts:[['compromised','compromised accounts'],['all','all']]};
function setFilters(){$('f').innerHTML=FILTERS[$('v').value].map(([v,l])=>`<option value="${v}">${l}</option>`).join('')}
function rows(){const q=$('q').value.trim().toLowerCase(),v=$('v').value,f=$('f').value;
 let r=D[v];if(v=='alerts'){r=r.filter(a=>f=='all'||(f=='disagree'?a.action!=a.baseline_action:a.verdict==f))}
 if(v=='accounts'&&f=='compromised')r=r.filter(a=>a.compromised);
 return r.filter(x=>!q||JSON.stringify(x).toLowerCase().includes(q))}
function card(x){const v=$('v').value;
 if(v=='alerts')return`<div class="card"><b>${x.alert_id}</b> ${esc(x.rule_name)} <span class="mut">${x.timestamp} · ${x.detector} · detector severity ${x.source_severity}</span><br>${esc(x.description)}<br>
 <span class="mut">${esc(x.user)} ${esc(x.host)} ${esc(x.src_ip)} ${esc(x.dst_ip)}</span><br>
 Jev policy: <b>${x.action}</b> <span class="mut">${esc(x.reason)}</span> · baseline: <b>${x.baseline_action}</b> <span class="mut">${esc(x.baseline_reason)}</span><br>
 <span class="${x.verdict=='right'?'ok':x.verdict=='missed'?'bad':'rev'}">${x.verdict}</span> <span class="mut">truth: ${x.disposition} · ${x.scenario} · ${x.incident||'no incident'} · group ${x.group}</span></div>`;
 if(v=='incidents')return`<div class="card"><b>${x.group_id}</b> ${x.alerts} alert(s) · <b>${x.action}</b> · severity ${x.severity} <span class="mut">${esc(x.users)} · strongest true-positive probability ${x.max_p_true_positive}</span></div>`;
 return`<div class="card"><b>#${x.rank}</b> ${esc(x.user)} score ${x.score} <span class="mut">(detector-severity rank ${x.baseline_rank||'none'})</span> ${x.compromised?'<span class="bad">compromised</span>':''}</div>`}
function render(reset){const r=rows();if(reset){shown=0;$('list').innerHTML=''}
 $('sum').textContent=`${r.length} ${$('v').value} shown. The evidence behind every decision is on its card.`;
 $('list').insertAdjacentHTML('beforeend',r.slice(shown,shown+PAGE).map(card).join(''));shown+=PAGE;$('more').style.display=shown<r.length?'':'none'}
$('v').onchange=()=>{setFilters();render(true)};$('f').onchange=()=>render(true);$('q').oninput=()=>render(true);$('more').onclick=()=>render(false);
setFilters();render(true);
</script></body></html>"""


def main():
    t = {"alerts": read_csv(path("alerts.csv")), "key": read_csv(path("answer_key.csv")),
         "decisions": read_csv(path("decisions_alerts.csv")), "baseline": read_csv(path("decisions_alerts_baseline.csv")),
         "groups": read_csv(path("groups_jev.csv")), "incidents": read_csv(path("output_incidents.csv")),
         "risk": read_csv(path("output_account_risk.csv")), "risk_baseline": read_csv(path("output_account_risk_baseline.csv"))}
    data = build(t)
    (path("triage_report.html")).write_text(render(data))
    print("wrote", path("triage_report.html"))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Write the run scripts**

`run_all.sh`:

```sh
#!/bin/sh
# Builds the dataset in data/ from scratch. Run from the repo root. About 1,000 Jev requests for alerts
# plus the candidate pairs the obvious-link rule does not settle.
# Another dataset: SEED=202 TRIAGE_DATA=data_holdout experiments/security-alert-triage/run_all.sh
set -e
P=.venv/bin/python; D=experiments/security-alert-triage/scripts
$P $D/generate.py
$P $D/rules.py
$P $D/ask.py alerts
$P $D/decide.py
$P $D/group.py baseline
$P $D/ask.py links
$P $D/group.py jev
$P $D/risk.py
$P $D/evaluate.py
$P $D/report.py
```

`replay.sh`:

```sh
#!/bin/sh
# Rebuilds every result from the saved Jev answers. Needs no API key and makes no network calls.
# Run from the repo root. (run_all.sh is the version that asks Jev again.)
set -e
P=.venv/bin/python; D=experiments/security-alert-triage/scripts
$P $D/rules.py
$P $D/decide.py
$P $D/group.py baseline
$P $D/group.py jev
$P $D/risk.py
$P $D/evaluate.py
$P $D/report.py
```

```bash
chmod +x run_all.sh replay.sh
sh -n run_all.sh && sh -n replay.sh && echo "scripts parse"
```

- [ ] **Step 5: Run the tests, then the replay with no key**

```bash
../../.venv/bin/python -m pytest -q
cd ../..
env -u TYPESAFE_API_KEY experiments/security-alert-triage/replay.sh > /dev/null && echo "replay ok"
git status --short
```

Expected: all tests pass, `replay ok`, and `git status` shows only the regenerated outputs (run the replay twice and compare `git status`; a second run must change nothing, so if the report differs between runs, sort any set or dict before writing it). Open `data/reports/triage_report.html` and check each view renders.

- [ ] **Step 6: Commit**

```bash
git add experiments/security-alert-triage
git commit -m "Add the triage report and the run and replay scripts" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Freeze, run a fresh seed once, and write the README

**Files:**
- Modify: `DESIGN.md` (results), `README.md` (create)
- Generate: `data_holdout/` (seed 202)

**Interfaces:**
- Consumes: everything above. No rule, threshold or question may change in this task.

- [ ] **Step 1: Freeze the rules**

```bash
cd ../..   # repo root of the worktree
git status --short          # must be empty
git tag triage-rules-frozen
```

Expected: no output from `git status`. From here, edit only `README.md` and `DESIGN.md`.

- [ ] **Step 2: Run the fresh seed once**

```bash
SEED=202 TRIAGE_DATA=data_holdout experiments/security-alert-triage/run_all.sh 2>&1 | tail -40
```

Expected: a full run into `experiments/security-alert-triage/data_holdout/`, ending with the evaluation for both the baseline and Jev. Run it once. If a stage errors for a reason that is not the rules (for example a transient API error), rerun only that stage and say so in `DESIGN.md`.

- [ ] **Step 3: Record the results honestly**

In `DESIGN.md`, add a `Results` section with two tables (seed 101 and seed 202): missed real alerts, real incidents with no surfaced alert, alerts that reach a person, grouping precision and recall, merged incidents, and compromised accounts in the top 10 and top 20, each for the baseline and for Jev. Name the scenarios where Jev did worse than the baseline or missed something. The thresholds were chosen on seed 101, so say that seed 202 is the only clean check. If the rules missed a real incident on seed 202, record that as a finding and do not edit the rules to fix it. Also replace the `Cost` line under Risks with the real request counts from the two runs: one request per asked alert plus one per candidate pair the obvious-link rule did not settle.

- [ ] **Step 4: Write the README**

Load the `writing-standards:writing-standards` skill, profile `deliverable`. `README.md` covers, in this order: what the project does; what you get; how to see the result with no key (`replay.sh`, then the report); how to run it with a key; how it works in five steps; the results table; what the tests found; limits (the author wrote both the scenarios and the rules, the set is small, the account ranking is an input for a human and never a verdict); a link to `DESIGN.md`. Run `python3 tools/style_check.py` from the skill folder on `README.md` and `DESIGN.md` and fix every `fix`.

- [ ] **Step 5: Scan before anything leaves the machine**

```bash
KEY=$(grep '^TYPESAFE_API_KEY=' .env | cut -d= -f2-)
git ls-files -z | xargs -0 grep -lF -- "$KEY" | wc -l
git ls-files -z | xargs -0 grep -lIE "(^|[^0-9.])([0-9]{1,3}\.){3}[0-9]{1,3}" experiments/security-alert-triage/scripts | head
```

Expected: `0` for the key. The second command lists any script containing an address; every address must be in `192.0.2.`, `198.51.100.` or `203.0.113.` (check each by eye).

- [ ] **Step 6: Final checks and commit**

```bash
cd experiments/security-alert-triage && ../../.venv/bin/python -m pytest -q && cd ../..
env -u TYPESAFE_API_KEY experiments/security-alert-triage/replay.sh > /dev/null && git status --short
git add experiments/security-alert-triage
git commit -m "Record holdout results and write the README" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

Expected: tests pass, the replay changes nothing, and the commit succeeds.

- [ ] **Step 7: Hand back for review. Do not push.**

Report the final numbers and the branch name. The pull request is created only when the user says so, after a whole-branch review.
