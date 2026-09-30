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


def test_account_keeps_its_alert_and_group_evidence():
    t = tables()
    t["risk"][0].update({"alert_ids": "A1 A9", "group_ids": "GRP-0001"})
    data = report.build(t)
    assert data["accounts"][0]["alert_ids"] == "A1 A9" and data["accounts"][0]["group_ids"] == "GRP-0001"
    assert "A9" in report.render(data)
