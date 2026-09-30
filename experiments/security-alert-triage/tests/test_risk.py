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


def test_evidence_is_the_alert_ids_of_the_worst_window():
    def f(aid, day, detection):
        return {"user": "v", "ts": risk.parse_ts(f"2026-03-{day:02d}T00:00:00Z"), "detection": detection,
                "risk": 100.0, "alert_id": aid}
    fs = [f("1", 1, "a"), f("2", 4, "b"), f("3", 5, "c"), f("4", 20, "d")]
    assert risk.account_evidence(fs) == {"v": ["1", "2", "3"]}


def test_written_rows_carry_alert_and_group_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(risk, "path", lambda name: str(tmp_path / name))
    risk._write("r.csv", {"u": 50.0}, {"u": ["A", "B"]}, {"A": "G1", "B": "G1"})
    row = risk.read_csv(str(tmp_path / "r.csv"))[0]
    assert row["alert_ids"] == "A B" and row["group_ids"] == "G1" and row["rank"] == "1"


def test_rank_orders_by_score_then_name():
    assert risk.rank({"b": 50.0, "a": 50.0, "c": 70.0}) == [("c", 70.0), ("a", 50.0), ("b", 50.0)]


def test_baseline_findings_use_detector_severity_and_a_fixed_confidence():
    fs = risk.baseline_findings([alert("A")])
    assert fs[0]["risk"] == 45.0     # high severity 90 x confidence 0.5
