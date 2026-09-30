"""Generate the synthetic alerts and the hidden answer key.

Run from the experiment folder: ../../.venv/bin/python scripts/generate.py
Writes data/source/employees.csv, alerts.csv, answer_key.csv. SEED=202 TRIAGE_DATA=data_holdout for another dataset.
"""
import os

import scenarios
from paths import path
from schema import ALERT_COLUMNS, EMPLOYEE_COLUMNS, KEY_COLUMNS
from tables import write_csv

SEED = int(os.environ.get("SEED", 101))


def build(seed):
    w = scenarios.World(seed)
    scenarios.populate(w)
    order = sorted(range(len(w.alerts)), key=lambda i: (w.alerts[i]["timestamp"], w.alerts[i]["alert_id"]))
    alerts, key = [], []
    for n, i in enumerate(order, 1):  # ids follow time order, so an id never reveals which scenario made it
        new_id = f"ALT-{n:05d}"
        alerts.append({**w.alerts[i], "alert_id": new_id})
        key.append({**w.key[i], "alert_id": new_id})
    employees = [{"user": e.user, "host": e.host, "ip": e.ip, "access": e.access} for e in w.employees]
    return employees, alerts, key


def write(employees, alerts, key, employees_path, alerts_path, key_path):
    write_csv(employees_path, employees, EMPLOYEE_COLUMNS)
    write_csv(alerts_path, alerts, ALERT_COLUMNS)
    write_csv(key_path, key, KEY_COLUMNS)


if __name__ == "__main__":
    employees, alerts, key = build(SEED)
    write(employees, alerts, key, path("employees.csv"), path("alerts.csv"), path("answer_key.csv"))
    real = sum(1 for k in key if k["disposition"] == "true_positive")
    incidents = len({k["incident_id"] for k in key if k["disposition"] == "true_positive"})
    print(f"seed {SEED}: {len(alerts)} alerts, {real} in {incidents} real incidents, {len(employees)} employees")
