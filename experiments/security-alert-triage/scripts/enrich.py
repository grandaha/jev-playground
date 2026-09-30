"""Timestamps, entity keys and time gaps."""
from datetime import datetime, timezone


def parse_ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def entities(alert):
    """The things an alert is about, as prefixed keys: user:..., host:..., ip:... (empty fields are skipped)."""
    out = set()
    for field, prefix in (("user", "user"), ("host", "host"), ("src_ip", "ip"), ("dst_ip", "ip")):
        if alert.get(field):
            out.add(f"{prefix}:{alert[field]}")
    return out


def hours_apart(a, b):
    return abs((parse_ts(a["timestamp"]) - parse_ts(b["timestamp"])).total_seconds()) / 3600
