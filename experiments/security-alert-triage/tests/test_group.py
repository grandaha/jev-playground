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
