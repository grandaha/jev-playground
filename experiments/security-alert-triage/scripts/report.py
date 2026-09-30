"""Write data/reports/triage_report.html: browse every alert, incident and account with its evidence.

Run from the experiment folder: ../../.venv/bin/python scripts/report.py
Because the data is synthetic, each alert also shows whether the decision was right, from the answer key.
"""
import json

from paths import path
from tables import read_csv


def build(t):
    key = {k["alert_id"]: k for k in t["key"]}
    dec = {d["alert_id"]: d for d in t["decisions"]}
    base = {d["alert_id"]: d for d in t["baseline"]}
    group = {g["alert_id"]: g["group_id"] for g in t["groups"]}
    alerts = []
    for a in t["alerts"]:
        k, d = key[a["alert_id"]], dec[a["alert_id"]]
        real = k["disposition"] == "true_positive"
        if real and d["action"] == "close":
            verdict = "missed"
        elif not real and d["action"] != "close":
            verdict = "queue cost"
        else:
            verdict = "right"
        alerts.append({**a, "scenario": k["scenario"], "disposition": k["disposition"], "incident": k["incident_id"],
                       "action": d["action"], "reason": d["reason"], "p_tp": d["p_true_positive"],
                       "baseline_action": base[a["alert_id"]]["action"], "baseline_reason": base[a["alert_id"]]["reason"],
                       "group": group[a["alert_id"]], "verdict": verdict})
    compromised = {k["compromised_user"] for k in t["key"] if k["compromised_user"]}
    accounts = [{**r, "compromised": r["user"] in compromised} for r in t["risk"]]
    base_rank = {r["user"]: r["rank"] for r in t["risk_baseline"]}
    for a in accounts:
        a["baseline_rank"] = base_rank.get(a["user"], "")
    return {"alerts": alerts, "incidents": t["incidents"], "accounts": accounts}


def render(data):
    return PAGE.replace("__DATA__", json.dumps(data).replace("</", "<\\/"))


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Alert triage</title><style>
:root{--bg:#fafaf9;--fg:#1c1917;--mut:#78716c;--card:#fff;--line:#e7e5e4;--ok:#15803d;--bad:#b91c1c;--rev:#b45309}
@media(prefers-color-scheme:dark){:root{--bg:#1c1917;--fg:#fafaf9;--mut:#a8a29e;--card:#292524;--line:#44403c;--ok:#4ade80;--bad:#f87171;--rev:#fbbf24}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 16px}
h1{font-size:16px;margin:0 0 8px}label{margin-right:12px;color:var(--mut)}select,input{font:inherit;color:inherit;background:var(--card);border:1px solid var(--line);border-radius:6px;padding:3px 6px}
main{padding:16px;max-width:1000px;margin:auto}.card{background:var(--card);border:1px solid var(--line);border-radius:8px;margin-bottom:10px;padding:8px 12px}
.mut{color:var(--mut)}.ok{color:var(--ok)}.bad{color:var(--bad)}.rev{color:var(--rev)}b{font-weight:600}
button{font:inherit;padding:6px 12px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:inherit;cursor:pointer}
</style></head><body><header><h1>Alert triage</h1>
<label>View <select id="v"><option value="alerts">alerts</option><option value="incidents">incidents</option><option value="accounts">accounts by risk</option></select></label>
<label>Show <select id="f"></select></label><label>Search <input id="q" size="14"></label></header>
<main><p class="mut">Accounts are ranked by security events, never by who a person is. The ranking is an input for a human to review and never a verdict. "compromised (answer key)" is the label from the synthetic answer key, and the pipeline never sees it.</p><p class="mut" id="sum"></p><div id="list"></div><button id="more">Show more</button></main>
<script>
const D=__DATA__;let shown=0;const PAGE=60,$=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const FILTERS={alerts:[['missed','missed real alerts'],['queue cost','benign alerts that reach a person'],['disagree','Jev and baseline disagree'],['all','all']],incidents:[['all','all']],accounts:[['compromised','compromised (answer key)'],['all','all']]};
const ev=(label,val)=>val?`<br><span class="mut">${label}: ${esc(val)}</span>`:'';
function setFilters(){$('f').innerHTML=FILTERS[$('v').value].map(([v,l])=>`<option value="${v}">${l}</option>`).join('')}
function rows(){const q=$('q').value.trim().toLowerCase(),v=$('v').value,f=$('f').value;
 let r=D[v];if(v=='alerts'){r=r.filter(a=>f=='all'||(f=='disagree'?a.action!=a.baseline_action:a.verdict==f))}
 if(v=='accounts'&&f=='compromised')r=r.filter(a=>a.compromised);
 return r.filter(x=>!q||JSON.stringify(x).toLowerCase().includes(q))}
function card(x){const v=$('v').value;
 if(v=='alerts')return`<div class="card"><b>${esc(x.alert_id)}</b> ${esc(x.rule_name)} <span class="mut">${esc(x.timestamp)} · ${esc(x.detector)} · detector severity ${esc(x.source_severity)}</span><br>${esc(x.description)}<br>
 <span class="mut">${esc(x.user)} ${esc(x.host)} ${esc(x.src_ip)} ${esc(x.dst_ip)}</span><br>
 Jev policy: <b>${esc(x.action)}</b> <span class="mut">${esc(x.reason)}</span> · baseline: <b>${esc(x.baseline_action)}</b> <span class="mut">${esc(x.baseline_reason)}</span><br>
 <span class="${x.verdict=='right'?'ok':x.verdict=='missed'?'bad':'rev'}">${esc(x.verdict)}</span> <span class="mut">truth: ${esc(x.disposition)} · ${esc(x.scenario)} · ${esc(x.incident||'no incident')} · group ${esc(x.group)}</span></div>`;
 if(v=='incidents')return`<div class="card"><b>${esc(x.group_id)}</b> ${esc(x.alerts)} alert(s) · <b>${esc(x.action)}</b> · severity ${esc(x.severity)} <span class="mut">${esc(x.users)} · strongest true-positive probability ${esc(x.max_p_true_positive)}</span></div>`;
 return`<div class="card"><b>#${esc(x.rank)}</b> ${esc(x.user)} score ${esc(x.score)} <span class="mut">(detector-severity rank ${esc(x.baseline_rank||'none')})</span> ${x.compromised?'<span class="bad">compromised (answer key)</span>':''}${ev('alerts',x.alert_ids)}${ev('groups',x.group_ids)}</div>`}
function render(reset){const r=rows();if(reset){shown=0;$('list').innerHTML=''}
 $('sum').textContent=`${r.length} ${$('v').value} shown. The evidence behind every decision is on its card.`;
 $('list').insertAdjacentHTML('beforeend',r.slice(shown,shown+PAGE).map(card).join(''));shown+=PAGE;$('more').style.display=shown<r.length?'':'none'}
$('v').onchange=()=>{setFilters();render(true)};$('f').onchange=()=>render(true);$('q').oninput=()=>render(true);$('more').onclick=()=>render(false);
setFilters();render(true);
</script></body></html>"""


def main():
    t = {"alerts": read_csv(path("alerts.csv")), "key": read_csv(path("answer_key.csv")),
         "decisions": read_csv(path("decisions_alerts.csv")), "baseline": read_csv(path("decisions_alerts_baseline.csv")),
         "groups": read_csv(path("groups_jev.csv")), "incidents": read_csv(path("output_incidents.csv")),
         "risk": read_csv(path("output_account_risk.csv")), "risk_baseline": read_csv(path("output_account_risk_baseline.csv"))}
    data = build(t)
    (path("triage_report.html")).write_text(render(data))
    print("wrote", path("triage_report.html"))


if __name__ == "__main__":
    main()
