"""Checks for the playground. Run from experiments/playground: ../../.venv/bin/python -m pytest -q

The example presets must be exactly what the experiment pipelines send, so these tests rebuild
them from the pipelines' own code and data and compare. DESIGN.md must name the same presets,
port and run command as the code.
"""
import csv
import importlib
import json
import re
import sys
from pathlib import Path

import server

PLAYGROUND = Path(__file__).resolve().parents[1]
EXP = PLAYGROUND.parent
REPO = EXP.parent
RUN_COMMAND = ".venv/bin/python experiments/playground/scripts/server.py"


def presets():
    html = (PLAYGROUND / "scripts" / "index.html").read_text()
    block = re.search(r'<script type="application/json" id="presets">(.*?)</script>', html, re.S).group(1)
    return {p["name"]: p for p in json.loads(block)}


def load_from(experiment, module):
    """Import a script module from one pipeline, dropping same-named modules (paths, tables) of the other one."""
    scripts = EXP / experiment / "scripts"
    others = [str(EXP / e / "scripts") for e in ("security-alert-triage", "customer-matching")]
    for name, mod in list(sys.modules.items()):
        if any(str(getattr(mod, "__file__", "") or "").startswith(o) for o in others):
            del sys.modules[name]
    sys.path.insert(0, str(scripts))
    try:
        return importlib.import_module(module)
    finally:
        sys.path.remove(str(scripts))


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


def test_env_file_is_repo_root():
    assert server.ENV_FILE == REPO / ".env"


def test_load_key_reads_env_file_then_environment(tmp_path, monkeypatch):
    env, missing = tmp_path / ".env", tmp_path / "missing.env"
    env.write_text('# comment\nOTHER=1\nexport TYPESAFE_API_KEY="fake-key-123"\n')
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert server.load_key(missing) == ""
    monkeypatch.setenv("TYPESAFE_API_KEY", "from-env")
    assert server.load_key(env) == "fake-key-123"
    assert server.load_key(missing) == "from-env"


def test_design_names_every_preset():
    design = (PLAYGROUND / "DESIGN.md").read_text()
    for name in presets():
        assert name in design, f"DESIGN.md does not name preset {name!r}"


def test_design_port_and_run_command_match_server():
    design = (PLAYGROUND / "DESIGN.md").read_text()
    assert f"{server.HOST}:{server.PORT}" in design
    assert RUN_COMMAND in design
    assert RUN_COMMAND in (PLAYGROUND / "scripts" / "server.py").read_text()
    assert RUN_COMMAND in (PLAYGROUND / "README.md").read_text()
