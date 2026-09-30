import pytest

from tables import read_alerts, read_csv, write_csv


def test_round_trip(tmp_path):
    p = tmp_path / "x.csv"
    write_csv(p, [{"a": "1", "b": "2"}], ["a", "b"])
    assert read_csv(p) == [{"a": "1", "b": "2"}]


def test_empty_alerts_file_stops_with_a_clear_message(tmp_path):
    p = tmp_path / "alerts.csv"
    write_csv(p, [], ["alert_id"])
    with pytest.raises(SystemExit) as stop:
        read_alerts(p)
    assert "no alerts" in str(stop.value)


def test_require_returns_an_existing_path_and_stops_on_a_missing_one(tmp_path):
    from tables import require
    p = tmp_path / "answers_links.csv"
    with pytest.raises(SystemExit) as stop:
        require(p, "run ask.py links first")
    assert "answers_links.csv is missing; run ask.py links first" in str(stop.value)
    p.write_text("x")
    assert require(p, "unused") == p
