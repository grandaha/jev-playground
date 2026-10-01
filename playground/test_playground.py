"""Checks for the playground. Run from the repo root: .venv/bin/python playground/test_playground.py

The example presets must be exactly what the experiment pipelines send, so the tests rebuild
them from the pipelines' own code and data and compare.
"""
import csv
import importlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import server

HERE = Path(__file__).resolve().parent
EXP = HERE.parent / "experiments"


def presets():
    html = (HERE / "index.html").read_text()
    block = re.search(r'<script type="application/json" id="presets">(.*?)</script>', html, re.S).group(1)
    return {p["name"]: p for p in json.loads(block)}


def load_from(experiment, module):
    """Import a script module from one experiment, dropping same-named modules from the other one."""
    scripts = str(EXP / experiment / "scripts")
    for name in [m for m, mod in sys.modules.items() if getattr(mod, "__file__", None) and "/experiments/" in mod.__file__]:
        del sys.modules[name]
    sys.path.insert(0, scripts)
    try:
        return importlib.import_module(module)
    finally:
        sys.path.remove(scripts)


def dump(questions):
    return {k: q.model_dump(mode="json", exclude_none=True, by_alias=True) for k, q in questions.items()}


def test_alert_preset_matches_ask_py():
    ask = load_from("security-alert-triage", "ask")
    alert = next(r for r in csv.DictReader(open(EXP / "security-alert-triage/data/source/alerts.csv")) if r["alert_id"] == "ALT-00062")
    p = presets()["Security alert ALT-00062 (security-alert-triage)"]
    assert not ask.rules.allowlisted(alert)  # the pipeline really asks Jev about this alert
    assert p["state"] == ask.alert_state(alert)
    assert p["questions"] == dump(ask.ALERT_QUESTIONS)


def test_account_pair_preset_matches_match_py():
    match = load_from("customer-matching", "match")
    norm = {r["account_id"]: r for r in csv.DictReader(open(match.path("accounts_norm.csv")))}
    a, b = norm["A00002"], norm["A00146"]
    p = presets()["Account pair A00002 / A00146 (customer-matching)"]
    assert match.hard_rule("accounts", a, b) is None  # not settled by a rule, so the pipeline asks Jev
    assert p["state"] == {"record_a": match.view("accounts", a, norm), "record_b": match.view("accounts", b, norm)}
    assert p["questions"] == dump(match.QUESTIONS["accounts"])


def test_load_key_reads_env_file_then_environment():
    saved = os.environ.pop("TYPESAFE_API_KEY", None)
    try:
        with tempfile.TemporaryDirectory() as d:
            env, missing = Path(d) / ".env", Path(d) / "missing.env"
            env.write_text('# comment\nOTHER=1\nexport TYPESAFE_API_KEY="fake-key-123"\n')
            assert server.load_key(missing) == ""
            os.environ["TYPESAFE_API_KEY"] = "from-env"
            assert server.load_key(env) == "fake-key-123"
            assert server.load_key(missing) == "from-env"
    finally:
        os.environ.pop("TYPESAFE_API_KEY", None)
        if saved is not None:
            os.environ["TYPESAFE_API_KEY"] = saved


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for t in tests:
        t()
    print(f"{len(tests)} passed")
