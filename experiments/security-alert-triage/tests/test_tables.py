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
