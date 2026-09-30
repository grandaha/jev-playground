"""The synthetic world: employees, servers, and every scenario's alerts with their answer key."""
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

START = datetime(2026, 3, 2, tzinfo=timezone.utc)
DAYS = 14
STORY_COPIES = 3     # copies of each real-incident story and each trap
BENIGN_COPIES = 3    # copies of each benign group
BACKGROUND = 880     # lone benign alerts

FIRST = ["avery", "blake", "casey", "devon", "emery", "finley", "harper", "jordan", "kai", "logan",
         "morgan", "noel", "parker", "quinn", "reese", "riley", "sage", "taylor", "wren", "zion"]
LAST = ["adler", "brooks", "chen", "diaz", "evans", "fox", "grant", "hayes", "ito", "jones",
        "khan", "lopez", "moore", "novak", "ortiz", "patel", "reyes", "silva", "tran", "walsh"]

SERVERS = {  # name: (address, asset criticality)
    "FS-01": ("192.0.2.11", "high"), "FS-02": ("192.0.2.12", "high"),
    "DB-01": ("192.0.2.21", "crown_jewel"), "BK-01": ("192.0.2.31", "high"),
    "SCAN-01": ("192.0.2.200", "standard"), "SEC-TEST-01": ("198.51.100.250", "standard"),
}
SHARED_NAT_IP = "192.0.2.250"  # a guest network address many unrelated people use


@dataclass(frozen=True)
class Employee:
    user: str
    host: str
    ip: str
    access: str


class World:
    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.alerts, self.key = [], []
        self._alerts_n = 0
        self._incidents_n = 0
        names = self.rng.sample([(f, l) for f in FIRST for l in LAST], 200)
        self.employees = []
        for i, (f, l) in enumerate(names, 1):
            r = self.rng.random()
            access = "administrator" if r < 0.03 else "elevated" if r < 0.15 else "standard"
            self.employees.append(Employee(f"{f}.{l}@example.com", f"WS-{i:03d}", f"198.51.100.{i}", access))
        self.access = {e.user: e.access for e in self.employees}
        self._victims = self.rng.sample(self.employees, len(self.employees))  # each victim is used once

    # --- helpers ---
    def victim(self):
        return self._victims.pop()

    def pick(self, access=None):
        pool = [e for e in self.employees if access is None or e.access in access]
        return self.rng.choice(pool)

    def when(self, latest_day=DAYS - 1):
        return START + timedelta(days=self.rng.randrange(0, latest_day), minutes=self.rng.randrange(0, 1440))

    def new_incident(self):
        self._incidents_n += 1
        return f"INC-{self._incidents_n:03d}"

    def resolve_ip(self, kind, victim=None, attacker=None):
        if not kind:
            return ""
        if kind == "victim":
            return victim.ip
        if kind == "attacker":
            return attacker
        if kind == "external":
            return f"203.0.113.{self.rng.randrange(1, 255)}"
        if kind.startswith("server:"):
            return SERVERS[kind.split(":")[1]][0]
        raise ValueError(kind)

    def emit(self, ts, detector, rule, description, severity, *, user=None, host=None, src_ip="", dst_ip="",
             tactic="", incident="", disposition, true_severity, true_tactic="", scenario, compromised=""):
        self._alerts_n += 1
        aid = f"TMP-{self._alerts_n:05d}"
        if host in SERVERS:
            criticality = SERVERS[host][1]
        else:
            criticality = "standard" if host else ""
        self.alerts.append({
            "alert_id": aid, "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"), "detector": detector,
            "rule_name": rule, "description": description, "source_severity": severity,
            "user": user or "", "host": host or "", "src_ip": src_ip, "dst_ip": dst_ip,
            "asset_criticality": criticality, "user_access": self.access.get(user, "") if user else "",
            "claimed_tactic": tactic})
        self.key.append({
            "alert_id": aid, "incident_id": incident, "disposition": disposition,
            "true_severity": true_severity, "true_tactic": true_tactic, "scenario": scenario,
            "compromised_user": compromised})


# --- real incidents: chains of attack stages. "at" is minutes after the start. ---
PHISH = [
    {"at": 0, "det": "email_gateway", "rule": "Credential phishing link clicked",
     "desc": "User clicked a link in a message the gateway classed as credential phishing; the page imitated the company sign-in",
     "sev": "medium", "tactic": "initial_access", "src": "victim"},
    {"at": 25, "det": "identity_provider", "rule": "Sign-in from new country",
     "desc": "Successful sign-in from a country never seen for this user, on an unregistered device, right after a password reset",
     "sev": "high", "tactic": "initial_access", "src": "attacker"},
    {"at": 40, "det": "cloud_monitor", "rule": "Mailbox forwarding rule created",
     "desc": "A new inbox rule forwards all mail to an address outside the company", "sev": "medium",
     "tactic": "collection", "src": "attacker"},
    {"at": 180, "det": "network_sensor", "rule": "Large upload to external address",
     "desc": "Unusually large upload to an address outside the company, well above this user's normal volume",
     "sev": "high", "tactic": "exfiltration", "src": "victim", "dst": "attacker"},
]
MISSING = [dict(s) for s in PHISH]
MISSING[2].update({"user": False, "mention_user": True})  # the forwarding-rule alert lost its user field

MALWARE = [
    {"at": 0, "det": "endpoint_agent", "rule": "Suspicious process started by document",
     "desc": "An office document launched a scripting process that then contacted the internet", "sev": "medium",
     "tactic": "execution", "host": "victim", "src": "victim"},
    {"at": 30, "det": "endpoint_agent", "rule": "Privilege escalation attempt",
     "desc": "A process tried to gain administrator rights using an unpatched driver", "sev": "high",
     "tactic": "privilege_escalation", "host": "victim"},
    {"at": 120, "det": "network_sensor", "rule": "Remote service access to file server",
     "desc": "The workstation opened an administrative session on a file server it has never used",
     "sev": "medium", "tactic": "lateral_movement", "host": "server:FS-01", "src": "victim", "dst": "server:FS-01"},
    {"at": 240, "det": "network_sensor", "rule": "Large outbound transfer",
     "desc": "Hundreds of files sent from the file server to an address outside the company", "sev": "high",
     "tactic": "exfiltration", "host": "server:FS-01", "src": "server:FS-01", "dst": "attacker"},
]

MFA = [
    {"at": 0, "det": "identity_provider", "rule": "Repeated MFA denials",
     "desc": "Nine multi-factor prompts were denied or ignored within ten minutes", "sev": "low",
     "tactic": "credential_access", "src": "attacker"},
    {"at": 14, "det": "identity_provider", "rule": "Sign-in after repeated MFA prompts",
     "desc": "A sign-in succeeded after the prompts, from an address never seen for this user",
     "sev": "medium", "tactic": "initial_access", "src": "attacker"},
    {"at": 90, "det": "cloud_monitor", "rule": "Bulk file download",
     "desc": "Thousands of files downloaded from cloud storage in one session", "sev": "medium",
     "tactic": "collection", "src": "attacker"},
]

_SLOW_MINUTES = [0, 700, 1600, 2900, 4300, 5500, 6500, 7100]  # about five days
_SLOW_ROWS = [
    ("identity_provider", "Unusual sign-in time", "Sign-in at an hour outside this user's normal pattern, from an unfamiliar address", "informational", "initial_access"),
    ("identity_provider", "New device registered", "A new device was registered for multi-factor sign-in without a help-desk ticket", "low", "persistence"),
    ("cloud_monitor", "Rare application accessed", "The user opened an application no one on their team uses", "informational", "discovery"),
    ("identity_provider", "Sign-in from new address", "Sign-in from the same unfamiliar address seen in an earlier unusual sign-in", "low", "initial_access"),
    ("cloud_monitor", "Mailbox accessed by unfamiliar client", "The mailbox was read by a mail client this user has never used", "informational", "collection"),
    ("network_sensor", "Small upload to personal storage", "A small archive was uploaded to a personal storage account", "low", ""),
    ("identity_provider", "Failed sign-ins then success", "Several failed sign-ins followed by a success from the unfamiliar address", "low", "credential_access"),
    ("cloud_monitor", "Unusual access to file share", "The account opened a file share it has not used in the past year", "low", "collection"),
]
SLOW = [{"at": m, "det": d, "rule": r, "desc": t, "sev": s, "tactic": tac or "collection", "claimed": tac, "src": "attacker"}
        for m, (d, r, t, s, tac) in zip(_SLOW_MINUTES, _SLOW_ROWS)]


def run_story(w, scenario, steps, victim, start, true_severity="high"):
    incident = w.new_incident()
    attacker = w.resolve_ip("external")
    local = victim.user.split("@")[0]
    for s in steps:
        host = victim.host if s.get("host") == "victim" else (s["host"].split(":")[1] if s.get("host") else None)
        desc = f"{s['desc']} (mailbox of {local})" if s.get("mention_user") else s["desc"]
        w.emit(start + timedelta(minutes=s["at"]), s["det"], s["rule"], desc, s["sev"],
               user=victim.user if s.get("user", True) else None, host=host,
               src_ip=w.resolve_ip(s.get("src"), victim, attacker), dst_ip=w.resolve_ip(s.get("dst"), victim, attacker),
               tactic=s.get("claimed", s["tactic"]), incident=incident, disposition="true_positive",
               true_severity=true_severity, true_tactic=s["tactic"], scenario=scenario, compromised=victim.user)
    return incident


# --- benign groups. Each returns nothing; the answer key says what they are. ---
def benign_admin_tool(w, start):
    admin = w.pick(("administrator", "elevated"))
    incident = w.new_incident()
    for server, at in (("FS-01", 0), ("FS-02", 6), ("DB-01", 15), ("BK-01", 22)):
        w.emit(start + timedelta(minutes=at), "endpoint_agent", "Remote administration tool executed",
               "An administrator ran a remote administration tool during the approved maintenance window (change ticket CHG-2041)",
               "high", user=admin.user, host=server, src_ip=admin.ip, dst_ip=SERVERS[server][0],
               tactic="lateral_movement", incident=incident, disposition="benign_true_positive",
               true_severity="informational", scenario="benign_admin_tool")


def benign_travel(w, start, user, scenario="benign_travel"):
    incident = w.new_incident()
    w.emit(start, "identity_provider", "Impossible travel",
           "Two sign-ins from distant countries within two hours; both used the user's registered laptop and passed multi-factor sign-in; the user's calendar shows a flight that day",
           "high", user=user.user, src_ip=w.resolve_ip("external"), tactic="initial_access", incident=incident,
           disposition="benign_true_positive", true_severity="low", scenario=scenario)
    w.emit(start + timedelta(minutes=40), "identity_provider", "Sign-in from new country",
           "First sign-in from a new country using the user's registered laptop; multi-factor sign-in passed",
           "medium", user=user.user, src_ip=w.resolve_ip("external"), tactic="initial_access", incident=incident,
           disposition="benign_true_positive", true_severity="low", scenario=scenario)


def benign_pentest(w, start):
    incident = w.new_incident()
    tester = SERVERS["SEC-TEST-01"][0]
    for at, rule, desc, sev, tactic, target in (
            (0, "Port scan", "Sequential connection attempts across many ports from the approved security test host", "low", "reconnaissance", "FS-01"),
            (10, "Port scan", "Sequential connection attempts across many ports from the approved security test host", "low", "reconnaissance", "FS-02"),
            (30, "Credential guessing pattern", "Repeated failed sign-ins from the approved test host during the authorized test window (ticket SEC-2026-014)", "high", "credential_access", "DB-01"),
            (45, "Credential guessing pattern", "Repeated failed sign-ins from the approved test host during the authorized test window (ticket SEC-2026-014)", "high", "credential_access", "BK-01")):
        w.emit(start + timedelta(minutes=at), "network_sensor", rule, desc, sev, host="SEC-TEST-01", src_ip=tester,
               dst_ip=SERVERS[target][0], tactic=tactic, incident=incident, disposition="benign_true_positive",
               true_severity="informational", scenario="benign_pentest")


def benign_backup(w, start):
    incident = w.new_incident()
    night = start.replace(hour=2, minute=0)
    for at in (0, 10, 20):
        w.emit(night + timedelta(minutes=at), "cloud_monitor", "Large transfer to external address",
               "Scheduled nightly backup job to the approved storage provider; same volume as previous nights",
               "high", host="BK-01", src_ip=SERVERS["BK-01"][0], dst_ip=w.resolve_ip("external"),
               tactic="exfiltration", incident=incident, disposition="benign_true_positive",
               true_severity="informational", scenario="benign_backup")


def fp_scanner(w, start):
    incident = w.new_incident()
    scanner = w.resolve_ip("external")
    for at in (0, 4, 9):
        w.emit(start + timedelta(minutes=at), "network_sensor", "Port scan from external address",
               "Sequential connection attempts from a public address with no follow-up activity; consistent with internet-wide scanning",
               "low", host="FS-01", src_ip=scanner, dst_ip=SERVERS["FS-01"][0], tactic="reconnaissance",
               incident=incident, disposition="false_positive", true_severity="informational", scenario="fp_scanner")


def fp_noisy_rule(w, start):
    for at in range(5):
        u = w.pick(None)
        w.emit(start + timedelta(minutes=15 * at), "endpoint_agent", "Suspicious PowerShell",
               "Matched on a script signed by the software vendor and run by the update service",
               "medium", user=u.user, host=u.host, src_ip=u.ip, tactic="execution",
               disposition="false_positive", true_severity="informational", scenario="fp_noisy_rule")


# --- traps for individual stages ---
def high_severity_benign(w, start):
    u = w.pick(None)
    w.emit(start, "endpoint_agent", "Malware signature match",
           "Match on the standard antivirus test file the IT team uses to check the agent",
           "high", user=u.user, host=u.host, src_ip=u.ip, tactic="execution", disposition="false_positive",
           true_severity="informational", scenario="high_severity_benign")


def low_severity_real(w, start):
    victim = w.victim()
    incident = w.new_incident()
    w.emit(start, "cloud_monitor", "Unusual admin action",
           "An administrator role was granted to a standard account outside any change ticket, on the database host that holds customer records",
           "low", user=victim.user, host="DB-01", src_ip=w.resolve_ip("external"), tactic="persistence",
           incident=incident, disposition="true_positive", true_severity="high",
           true_tactic="privilege_escalation", scenario="low_severity_real", compromised=victim.user)


def two_incidents_one_user(w):
    user = w.victim()
    start = w.when(10)
    benign_travel(w, start, user, scenario="two_incidents_one_user")
    run_story(w, "two_incidents_one_user", PHISH, user, start + timedelta(days=2))


def shared_address(w, start):
    a, b = w.rng.sample(w.employees, 2)
    for u, at in ((a, 0), (b, 25)):
        w.emit(start + timedelta(minutes=at), "identity_provider", "Sign-in from unfamiliar address",
               "Sign-in from the office guest network address that many visitors use; the device is registered and multi-factor sign-in passed",
               "low", user=u.user, src_ip=SHARED_NAT_IP, tactic="initial_access", disposition="false_positive",
               true_severity="informational", scenario="shared_address")


_BACKGROUND = [
    ("identity_provider", "Sign-in from unfamiliar device", "First sign-in on a laptop issued by IT last week; multi-factor sign-in passed", "low", "benign_true_positive"),
    ("identity_provider", "Failed sign-in attempts", "Three failed sign-ins followed by a success within two minutes; a typing-error pattern", "low", "false_positive"),
    ("endpoint_agent", "Unapproved software installed", "An approved design tool installed from the company software catalog", "low", "benign_true_positive"),
    ("network_sensor", "Connection to rare domain", "One connection to a rarely seen domain that hosts a public font service", "medium", "false_positive"),
    ("cloud_monitor", "Large file download", "Download of the user's own project folder before a planned laptop refresh", "medium", "benign_true_positive"),
    ("email_gateway", "Suspicious attachment quarantined", "Attachment quarantined and never opened; the sender is a known vendor using a new template", "low", "false_positive"),
    ("endpoint_agent", "USB storage device connected", "Company-issued encrypted USB drive used for a scheduled presentation", "low", "benign_true_positive"),
    ("identity_provider", "Password spray pattern", "Low-rate failed sign-ins across many accounts from one public address with no successes", "medium", "false_positive"),
    ("network_sensor", "Large upload to external address", "Upload of a video to the company's marketing account on an approved platform", "high", "benign_true_positive"),
]


def background(w, n):
    for _ in range(n):
        det, rule, desc, sev, disposition = w.rng.choice(_BACKGROUND)
        u = w.pick(None)
        w.emit(w.when(), det, rule, desc, sev, user=u.user, host=u.host, src_ip=u.ip,
               disposition=disposition, true_severity="informational", scenario="background")


def populate(w):
    for _ in range(STORY_COPIES):
        run_story(w, "phish_to_exfil", PHISH, w.victim(), w.when())
        run_story(w, "malware_lateral", MALWARE, w.victim(), w.when())
        run_story(w, "mfa_fatigue", MFA, w.victim(), w.when())
        run_story(w, "slow_burn", SLOW, w.victim(), w.when(8))
        run_story(w, "missing_entity_link", MISSING, w.victim(), w.when())
        low_severity_real(w, w.when())
        two_incidents_one_user(w)
    for _ in range(BENIGN_COPIES):
        benign_admin_tool(w, w.when())
        benign_travel(w, w.when(), w.pick(None))
        benign_pentest(w, w.when())
        benign_backup(w, w.when())
        fp_scanner(w, w.when())
        fp_noisy_rule(w, w.when())
        high_severity_benign(w, w.when())
        shared_address(w, w.when())
    background(w, BACKGROUND)
