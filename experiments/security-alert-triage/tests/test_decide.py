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
