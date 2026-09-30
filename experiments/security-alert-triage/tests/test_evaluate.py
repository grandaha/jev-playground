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


def test_stage_accuracy_compares_jev_and_the_detector_on_real_alerts():
    key = [{"alert_id": "A1", "disposition": "true_positive", "true_tactic": "exfiltration"},
           {"alert_id": "A2", "disposition": "true_positive", "true_tactic": "collection"},
           {"alert_id": "A3", "disposition": "false_positive", "true_tactic": ""}]
    alerts = [{"alert_id": "A1", "claimed_tactic": "exfiltration"}, {"alert_id": "A2", "claimed_tactic": ""},
              {"alert_id": "A3", "claimed_tactic": "execution"}]
    answers = {"A1": {"asked": "yes", "stage": "exfiltration"}, "A2": {"asked": "yes", "stage": "collection"},
               "A3": {"asked": "yes", "stage": "execution"}}
    assert evaluate.stage_accuracy(key, alerts, answers) == {"real_alerts": 2, "jev_correct": 2, "detector_correct": 1}


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
