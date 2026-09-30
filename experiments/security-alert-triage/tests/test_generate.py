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
