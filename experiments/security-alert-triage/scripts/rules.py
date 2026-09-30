"""Code-only triage: the never-suppress list, the allowlist, and the rules-only baseline.

Run from the experiment folder: ../../.venv/bin/python scripts/rules.py
Writes data/work/decisions_alerts_baseline.csv.
"""
from paths import path
from tables import read_alerts, write_csv

NEVER_SUPPRESS_TACTICS = {"privilege_escalation", "exfiltration", "command_and_control"}
NEVER_SUPPRESS_PHRASES = ("privilege escalation", "large upload", "large outbound", "large transfer",
                          "beacon", "command and control")
ALLOWLIST = [
    {"name": "approved internal scanner", "rule": "port scan", "src_ip": "192.0.2.200"},
    {"name": "authorized test host scans", "rule": "port scan", "src_ip": "198.51.100.250"},
]


def never_suppress(alert):
    """The reason this alert must never be closed, or None."""
    tactic = alert.get("claimed_tactic", "")
    if tactic in NEVER_SUPPRESS_TACTICS:
        return f"claimed tactic {tactic}"
    name = alert.get("rule_name", "").lower()
    for phrase in NEVER_SUPPRESS_PHRASES:
        if phrase in name:
            return f"rule name mentions '{phrase}'"
    return None


def allowlisted(alert):
    """The allowlist entry that makes this alert known-harmless, or None. Never applies to never-suppress alerts."""
    if never_suppress(alert):
        return None
    name = alert.get("rule_name", "").lower()
    for entry in ALLOWLIST:
        if entry["rule"] in name and alert.get("src_ip") == entry["src_ip"]:
            return entry["name"]
    return None


def baseline_action(alert):
    """The rules-only decision: detector severity plus the two lists. Returns (action, reason)."""
    ns, sev = never_suppress(alert), alert.get("source_severity", "")
    if sev in ("high", "critical"):
        return "escalate", f"detector severity {sev}" + (f"; never-suppress: {ns}" if ns else "")
    if ns:
        return "investigate", f"never-suppress: {ns}"
    entry = allowlisted(alert)
    if entry:
        return "close", f"allowlist: {entry}"
    if sev == "medium":
        return "investigate", "detector severity medium"
    return "close", f"detector severity {sev or 'unknown'}"


def main():
    rows = []
    for a in read_alerts(path("alerts.csv")):
        action, reason = baseline_action(a)
        rows.append({"alert_id": a["alert_id"], "action": action, "reason": reason})
    write_csv(path("decisions_alerts_baseline.csv"), rows, ["alert_id", "action", "reason"])
    counts = {x: sum(1 for r in rows if r["action"] == x) for x in ("close", "investigate", "escalate")}
    print("baseline:", counts)


if __name__ == "__main__":
    main()
