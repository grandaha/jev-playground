"""Write data/golden_report.html: browse golden records and see how each was built (lineage).

Run from repo root: .venv/bin/python experiments/customer-matching/golden_report.py
For each golden record: the value of every field and which source record supplied it, the phones and
emails kept with their source systems, every record that went into it, and the pair decisions (rule and
evidence) that joined those records. Because the data is synthetic, the answer key adds a check on each group.
"""
import csv
import json
from collections import defaultdict

from paths import path
FIELDS = {"accounts": ["name", "website", "industry"], "contacts": ["first_name", "last_name", "title"]}
ADDRESS = ["address", "city", "state", "zip"]
SHOW = {"accounts": ["name", "website", "phone", "address", "city", "state", "zip", "source_system", "updated_at"],
        "contacts": ["first_name", "last_name", "email", "phone", "title", "address", "city", "state", "zip", "account_id",
                     "master_account_id", "source_system", "updated_at"]}


def read(name):
    return list(csv.DictReader(open(path(name))))


def build(table):
    idc = f"{table[:-1]}_id"
    raw = {r[idc]: r for r in read(f"{table}.csv")}
    if table == "contacts":  # the master account each contact was keyed to, from normalization
        for r in read("contacts_norm.csv"):
            raw[r["contact_id"]]["master_account_id"] = r["master_account_id"]
    golden = read(f"golden_{table}.csv")
    decisions = read(f"decisions_{table}.csv")
    masters = {m["group_id"]: m["reason"] for m in read(f"masters_{table}.csv")}
    status = {}
    for g in read(f"groups_{table}.csv"):
        status[g["group_id"]] = g["status"]
    truth = {k["record_id"]: k for k in read("answer_key.csv") if k["table"] == table}
    where = {i: g["golden_id"] for g in golden for i in g["member_ids"].split()}
    true_in = defaultdict(set)
    for i, gid in where.items():
        true_in[truth[i]["true_id"]].add(gid)
    acct_name = {g["golden_id"]: g["name"] for g in read("golden_accounts.csv")}
    phones = defaultdict(list)
    for p in read(f"golden_{table[:-1]}_phones.csv"):
        phones[p["golden_id"]].append(p)
    emails = defaultdict(list)
    if table == "contacts":
        for e in read("golden_contact_emails.csv"):
            emails[e["golden_id"]].append(e)
    merges, dissent = defaultdict(list), defaultdict(list)
    for d in decisions:
        ga, gb = where[d["id_a"]], where[d["id_b"]]
        if ga == gb and d["decision"] == "merge":
            merges[ga].append(d)
        elif ga == gb:
            dissent[ga].append(d)
    cards = []
    for g in golden:
        ids = g["member_ids"].split()
        order = ids  # golden.py already wrote these best-first
        fields = []
        for f in FIELDS[table]:
            src = next((i for i in order if raw[i][f]), None)
            fields.append({"field": f, "value": g[f], "from": src, "source": raw[src]["source_system"] if src else ""})
        src = next((i for i in order if raw[i]["address"]), None)
        fields.append({"field": "address", "value": ", ".join(x for x in (g[f] for f in ADDRESS) if x), "from": src,
                       "source": raw[src]["source_system"] if src else ""})
        if table == "contacts":
            fields.append({"field": "account", "value": (g["golden_account_id"] + " " + acct_name.get(g["golden_account_id"], "")).strip(),
                           "from": next((i for i in order if raw[i]["account_id"]), None), "source": ""})
        true_ids = {truth[i]["true_id"] for i in ids}
        incomplete = any(len(true_in[t]) > 1 for t in true_ids)
        check = "MIXED: more than one real entity (false merge)" if len(true_ids) > 1 else \
            "incomplete: true duplicates are in another golden record" if incomplete else "correct"
        cards.append({
            "id": g["golden_id"], "title": " ".join(x for x in (g.get("name"), g.get("first_name"), g.get("last_name")) if x),
            "master": g["master_id"], "reason": masters.get(g["group_id"], "single record, nothing to merge"),
            "filled": g["filled_from"], "status": status[g["group_id"]], "check": check,
            "scenarios": sorted({truth[i]["scenario"] for i in ids}),
            "fields": fields,
            "phones": [{k: p[k] for k in ("value", "is_primary", "source_systems", "record_ids")} for p in phones[g["golden_id"]]],
            "emails": [{k: e[k] for k in ("value", "is_primary", "source_systems", "record_ids")} for e in emails[g["golden_id"]]],
            "members": [{"id": i, **{f: raw[i][f] for f in SHOW[table]}} for i in ids],
            "merges": [{"a": d["id_a"], "b": d["id_b"], "rule": d["rule"], "detail": d["detail"]} for d in merges[g["golden_id"]]],
            "dissent": [{"a": d["id_a"], "b": d["id_b"], "decision": d["decision"], "rule": d["rule"], "detail": d["detail"]}
                        for d in dissent[g["golden_id"]]],
        })
    return {"show": SHOW[table], "cards": cards}


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Golden records</title><style>
:root{--bg:#fafaf9;--fg:#1c1917;--mut:#78716c;--card:#fff;--line:#e7e5e4;--ok:#15803d;--bad:#b91c1c;--rev:#b45309;--hl:#dcfce7;--m:#e0f2fe}
@media(prefers-color-scheme:dark){:root{--bg:#1c1917;--fg:#fafaf9;--mut:#a8a29e;--card:#292524;--line:#44403c;--ok:#4ade80;--bad:#f87171;--rev:#fbbf24;--hl:#14532d;--m:#0c4a6e}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 16px;z-index:1}
h1{font-size:16px;margin:0 0 8px}label{margin-right:12px;color:var(--mut)}select,input{font:inherit;color:inherit;background:var(--card);border:1px solid var(--line);border-radius:6px;padding:3px 6px}
main{padding:16px;max-width:1040px;margin:auto}.sum{color:var(--mut);margin:0 0 12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;margin-bottom:14px;overflow:hidden}
.top{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:baseline;padding:8px 12px;border-bottom:1px solid var(--line)}
.top b{font-size:15px}.mut{color:var(--mut)}.ok{color:var(--ok)}.bad{color:var(--bad)}.rev{color:var(--rev)}
h3{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--mut);margin:0;padding:10px 12px 4px;font-weight:600}
table{width:100%;border-collapse:collapse}td,th{padding:3px 12px;text-align:left;vertical-align:top;word-break:break-word}
th{color:var(--mut);font-weight:400}.g{background:var(--hl)}.mast td{background:var(--m)}
table.mem td,table.mem th{padding:3px 6px;font-size:12.5px}ul{margin:0;padding:2px 12px 8px 30px}li{margin:2px 0}.sm{font-size:13px}
button{font:inherit;padding:6px 12px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:inherit;cursor:pointer}
</style></head><body><header><h1>Golden records</h1>
<label>Table <select id="t"><option>accounts</option><option>contacts</option></select></label>
<label>Show <select id="v"><option value="merged" selected>merged from 2+ records</option><option value="filled">fields filled from another record</option><option value="multi">more than one phone or email</option><option value="flag">group needs review</option><option value="bad">problems: falsely merged or incomplete</option><option value="all">all</option></select></label>
<label>Search <input id="q" size="14" placeholder="name or id"></label></header>
<main><p class="sum" id="sum"></p><div id="list"></div><button id="more">Show more</button></main>
<script>
const D=__DATA__;let shown=0;const PAGE=40;
const $=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const vals=(L)=>L.length?'<ul>'+L.map(x=>`<li class="sm"><b>${esc(x.value)}</b> ${x.is_primary==='True'||x.is_primary===true?'<span class="ok">primary</span>':'<span class="rev">alternate</span>'} <span class="mut">from ${esc(x.source_systems)} (records ${esc(x.record_ids)})</span></li>`).join('')+'</ul>':'<ul><li class="mut">none on any record</li></ul>';
function match(c){const v=$('v').value,q=$('q').value.trim().toLowerCase();
 const ok=v=='all'||(v=='merged'&&c.members.length>1)||(v=='filled'&&c.filled)||(v=='multi'&&(c.phones.length>1||c.emails.length>1))||(v=='flag'&&c.status!='auto')||(v=='bad'&&c.check!='correct');
 return ok&&(!q||(c.id+' '+c.title+' '+c.members.map(m=>m.id).join(' ')).toLowerCase().includes(q))}
function card(c,d){
 const from=new Map();c.fields.forEach(f=>{if(f.from)from.set(f.field,f.from)});
 const fr=c.fields.map(f=>`<tr><th>${f.field}</th><td class="${f.from&&f.from!==c.master?'g':''}"><b>${esc(f.value)||'<span class="mut">blank</span>'}</b></td><td class="mut">${f.from?`from ${esc(f.from)}${f.source?' ('+esc(f.source)+')':''}${f.from!==c.master?' <span class="rev">not the master</span>':''}`:'no record had a value'}</td></tr>`).join('');
 const head='<tr><th>record</th>'+d.show.map(f=>`<th>${f}</th>`).join('')+'</tr>';
 const mem=c.members.map(m=>`<tr class="${m.id===c.master?'mast':''}"><td><b>${m.id}</b>${m.id===c.master?' <span class="mut">master</span>':''}</td>${d.show.map(f=>`<td>${esc(m[f])}</td>`).join('')}</tr>`).join('');
 const mg=c.merges.length?'<ul>'+c.merges.map(e=>`<li class="sm"><b>${e.a} + ${e.b}</b> merged by <b>${esc(e.rule)}</b> <span class="mut">${esc(e.detail)}</span></li>`).join('')+'</ul>':'<ul><li class="mut">one record, nothing to join</li></ul>';
 const ds=c.dissent.length?'<h3>Pairs inside this group that were not merged</h3><ul>'+c.dissent.map(e=>`<li class="sm rev"><b>${e.a} / ${e.b}</b> ${esc(e.decision)} by ${esc(e.rule)} <span class="mut">${esc(e.detail)}</span></li>`).join('')+'</ul>':'';
 return`<div class="card"><div class="top"><b>${esc(c.id)} ${esc(c.title)}</b><span class="mut">${c.members.length} record${c.members.length>1?'s':''}</span><span class="${c.check=='correct'?'ok':c.check.startsWith('MIXED')?'bad':'rev'}">${esc(c.check)}</span>${c.status!='auto'?'<span class="rev">group needs review</span>':''}<span class="mut">${esc(c.scenarios.join(', '))}</span></div>
 <h3>Golden record: value and where it came from</h3><table>${fr}</table>
 <h3>Phones kept</h3>${vals(c.phones)}${c.emails.length?'<h3>Emails kept</h3>'+vals(c.emails):''}
 <h3>Master chosen: ${esc(c.master)}</h3><ul><li class="sm mut">${esc(c.reason)}${c.filled?'. Filled from other records: '+esc(c.filled):''}</li></ul>
 <h3>Source records (master highlighted)</h3><table class="mem">${head}${mem}</table>
 <h3>How the records were joined</h3>${mg}${ds}</div>`}
function render(reset){const d=D[$('t').value],f=d.cards.filter(match);if(reset){shown=0;$('list').innerHTML=''}
 $('sum').textContent=`${d.cards.length} golden records, ${d.cards.filter(c=>c.members.length>1).length} built from 2+ records, ${d.cards.filter(c=>c.check.startsWith('MIXED')).length} falsely merged, ${d.cards.filter(c=>c.check.startsWith('incomplete')).length} incomplete (their true duplicates are in another golden record). Showing ${Math.min(shown+PAGE,f.length)} of ${f.length}.`;
 $('list').insertAdjacentHTML('beforeend',f.slice(shown,shown+PAGE).map(c=>card(c,d)).join(''));shown+=PAGE;$('more').style.display=shown<f.length?'':'none'}
['t','v'].forEach(i=>$(i).onchange=()=>render(true));$('q').oninput=()=>render(true);$('more').onclick=()=>render(false);render(true);
</script></body></html>"""

if __name__ == "__main__":
    data = {t: build(t) for t in ("accounts", "contacts")}
    (path("golden_report.html")).write_text(PAGE.replace("__DATA__", json.dumps(data).replace("</", "<\\/")))
    for t, d in data.items():
        print(t, len(d["cards"]), "golden records,", sum(c["check"].startswith("MIXED") for c in d["cards"]), "falsely merged,",
              sum(c["check"].startswith("incomplete") for c in d["cards"]), "incomplete")
    print("wrote", path("golden_report.html"))
