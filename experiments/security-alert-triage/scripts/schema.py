"""Shared vocabulary for the alert triage experiment."""
import ipaddress

SEVERITIES = ["informational", "low", "medium", "high", "critical"]
SOURCE_SEVERITIES = ["informational", "low", "medium", "high"]  # what detectors use
DISPOSITIONS = ["true_positive", "false_positive", "benign_true_positive"]
ACTIONS = ["close", "investigate", "escalate"]
DETECTORS = ["email_gateway", "identity_provider", "endpoint_agent", "network_sensor", "cloud_monitor"]
CRITICALITY = ["low", "standard", "high", "crown_jewel"]
ACCESS_LEVELS = ["standard", "elevated", "administrator"]

TACTIC_DESCRIPTIONS = {
    "reconnaissance": "Gathering information about the company to plan an attack.",
    "resource_development": "Setting up infrastructure or accounts to support an attack.",
    "initial_access": "Getting a first foothold, for example through phishing or a stolen sign-in.",
    "execution": "Running attacker-controlled code.",
    "persistence": "Keeping access across restarts and password changes.",
    "privilege_escalation": "Gaining higher permissions.",
    "stealth": "Hiding actions so they look normal.",
    "defense_impairment": "Turning off or weakening security tools and logging.",
    "credential_access": "Stealing or guessing account credentials.",
    "discovery": "Mapping the environment to decide where to go next.",
    "lateral_movement": "Moving from one system to another.",
    "collection": "Gathering the data the attacker wants.",
    "command_and_control": "Communicating with compromised systems from outside.",
    "exfiltration": "Stealing data out of the company.",
    "impact": "Disrupting, encrypting or destroying systems and data.",
}
TACTICS = list(TACTIC_DESCRIPTIONS)

ALERT_COLUMNS = ["alert_id", "timestamp", "detector", "rule_name", "description", "source_severity",
                 "user", "host", "src_ip", "dst_ip", "asset_criticality", "user_access", "claimed_tactic"]
KEY_COLUMNS = ["alert_id", "incident_id", "disposition", "true_severity", "true_tactic", "scenario",
               "compromised_user"]
EMPLOYEE_COLUMNS = ["user", "host", "ip", "access"]

_DOC_NETS = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]


def is_documentation_ip(ip):
    return any(ipaddress.ip_address(ip) in net for net in _DOC_NETS)
