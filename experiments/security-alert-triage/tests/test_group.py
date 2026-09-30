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


def test_an_errored_pair_is_not_linked():
    bad = {("A", "B"): {"score": "", "p_coincidence": "", "error": "boom"}}
    assert group.decide_links({("A", "B"): ["ip:x"]}, pair_alerts(), bad)[0]["rule"] == "no_jev_answer"


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


def sev(impact, p_benign="0.1"):
    return group._severity({"impact": impact, "p_benign": p_benign})


def test_severity_bands_are_even_at_each_boundary():
    assert [sev(x) for x in ("0.49", "0.5", "1.49", "1.5", "2.49", "2.5")] == [
        "low", "medium", "medium", "high", "high", "critical"]


def test_likely_benign_is_informational_and_empty_p_benign_counts_as_zero():
    assert sev("2.8", "0.5") == "informational"
    assert sev("2.8", "") == "critical"
