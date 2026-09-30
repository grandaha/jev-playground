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
