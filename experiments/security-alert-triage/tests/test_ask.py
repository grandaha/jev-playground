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
