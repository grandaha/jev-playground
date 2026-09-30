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
