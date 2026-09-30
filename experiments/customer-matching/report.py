"""Write data/report.html: a static, self-contained page to browse every pair decision.

Run from repo root: .venv/bin/python experiments/customer-matching/report.py
Open data/report.html in a browser. Shows both records side by side, what Jev and the rules said,
and (because the data is synthetic) whether the decision was right, from the answer key.
"""
import os
import csv
import json
from itertools import combinations
from collections import defaultdict
from pathlib import Path

from evaluate import corroborated

DATA = Path(__file__).parent / os.environ.get("MATCH_DATA", "data")  # MATCH_DATA=data_seed2 runs on another folder
FIELDS = {"accounts": ["name", "website", "phone", "address", "city", "state", "zip", "industry", "source_system", "updated_at"],
          "contacts": ["first_name", "last_name", "email", "phone", "title", "address", "city", "state", "zip", "account_id", "source_system", "updated_at"]}
NORM = {"accounts": ["name_norm", "phone_norm", "address_norm"],
        "contacts": ["first_norm", "last_norm", "email_norm", "phone_norm", "address_norm", "master_account_id"]}


def read(name):
    return list(csv.DictReader(open(DATA / name)))


def build(table):
    idc = f"{table[:-1]}_id"
    recs = {r[idc]: r for r in read(f"{table}.csv")}
    key = {k["record_id"]: k for k in read("answer_key.csv") if k["table"] == table}
    by_true = defaultdict(list)
    for rid, k in key.items():
        by_true[k["true_id"]].append(rid)
    true_pairs = {p for ids in by_true.values() for p in combinations(sorted(ids), 2)}
    norm = {x[idc]: x for x in read(f"{table}_norm.csv")}
    seen, pairs = set(), []

    def add(a, b, decision, rule, detail, score, look, keys):
        dup = (a, b) in true_pairs
        if decision == "merge":
            verdict = "right" if dup else "wrong"
        elif decision in ("no_match", "missed"):
            # a true duplicate with nothing but the name in common can't be proven from the data
            verdict = "right" if not dup else "wrong" if corroborated(table, norm[a], norm[b]) else "unprovable"
        else:
            verdict = "review"
        pairs.append({"a": a, "b": b, "decision": decision, "rule": rule, "detail": detail, "score": score,
                      "look": look, "keys": keys, "dup": dup, "verdict": verdict,
                      "kinds": f"{key[a]['kind']} / {key[b]['kind']}", "scenario": key[a]["scenario"]})

    for d in read(f"decisions_{table}.csv"):
        seen.add((d["id_a"], d["id_b"]))
        ans = ""
        if d["score"]:
            ans = f"Jev: same-{table[:-1]} score {float(d['score']):.2f} of 2, name same {float(d['name_same']):.2f}, details conflict {float(d['details_conflict']):.2f}, lookalike {float(d['lookalike']):.2f}"
        add(d["id_a"], d["id_b"], d["decision"], d["rule"], d["detail"], ans, d["lookalike"], d["block_keys"])
    for a, b in sorted(true_pairs - seen):  # true duplicates that blocking never proposed
        add(a, b, "missed", "not_a_candidate", "no shared match key, never sent to a rule or Jev", "", "", "")
    used = {i for p in pairs for i in (p["a"], p["b"])}
    def rec(i):
        n = norm[i]
        return {"raw": {f: recs[i][f] for f in FIELDS[table]}, "norm": {f: n[f] for f in NORM[table]},
                "keys": {k: v for k, v in n.items() if k.startswith("k_") and v}}
    return {"fields": FIELDS[table], "norm_fields": NORM[table], "records": {i: rec(i) for i in used}, "pairs": pairs}


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Match review</title><style>
:root{--bg:#fafaf9;--fg:#1c1917;--mut:#78716c;--card:#fff;--line:#e7e5e4;--ok:#15803d;--bad:#b91c1c;--rev:#b45309;--diff:#fef3c7;--same:#dcfce7}
@media(prefers-color-scheme:dark){:root{--bg:#1c1917;--fg:#fafaf9;--mut:#a8a29e;--card:#292524;--line:#44403c;--ok:#4ade80;--bad:#f87171;--rev:#fbbf24;--diff:#4a3b12;--same:#14532d}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 16px;z-index:1}
h1{font-size:16px;margin:0 0 8px}label{margin-right:12px;color:var(--mut)}select,input{font:inherit;color:inherit;background:var(--card);border:1px solid var(--line);border-radius:6px;padding:3px 6px}
main{padding:16px;max-width:980px;margin:auto}.sum{color:var(--mut);margin:0 0 12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;margin-bottom:12px;overflow:hidden}
.top{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:baseline;padding:8px 12px;border-bottom:1px solid var(--line)}
.tag{font-weight:600}.right{color:var(--ok)}.wrong{color:var(--bad)}.review,.unprovable{color:var(--rev)}.mut{color:var(--mut)}
table{width:100%;border-collapse:collapse}td,th{padding:3px 12px;text-align:left;vertical-align:top;word-break:break-word}
th{width:16%;color:var(--mut);font-weight:400}td.d{background:var(--diff)}td.s{background:var(--same)}tr.sec th{padding-top:10px;font-size:12px;text-transform:uppercase;letter-spacing:.04em}.note{padding:6px 12px;color:var(--mut);border-top:1px solid var(--line);font-size:13px}
button{font:inherit;padding:6px 12px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:inherit;cursor:pointer}
</style></head><body><header><h1>Match review</h1>
<label>Table <select id="t"><option>accounts</option><option>contacts</option></select></label>
<label>Show <select id="v"><option value="all">all</option><option value="wrong" selected>wrong only</option><option value="review">review queue</option><option value="right">right only</option><option value="unprovable">unprovable (no shared evidence)</option></select></label>
<label>Rule <select id="r"></select></label><label>Scenario <select id="s"></select></label><label>Search id <input id="q" size="8"></label></header>
<main><p class="sum" id="sum"></p><div id="list"></div><button id="more">Show more</button></main>
<script>
const D=__DATA__;let shown=0;const PAGE=100;
const $=id=>document.getElementById(id),esc=s=>String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const LABEL={merge:'merged',no_match:'not a match',review:'sent to review',missed:'missed (never a candidate)'};
function filtered(){const d=D[$('t').value],v=$('v').value,r=$('r').value,s=$('s').value,q=$('q').value.trim().toUpperCase();
 return d.pairs.filter(p=>(v=='all'||p.verdict==v)&&(r=='all'||p.rule==r)&&(s=='all'||p.scenario==s)&&(!q||p.a.includes(q)||p.b.includes(q)))}
function card(p,d){const A=d.records[p.a],B=d.records[p.b];
 const row=(f,x,y,cls)=>{const diff=x!==y;return`<tr><th>${f}</th><td class="${cls||(diff?'d':'')}">${esc(x)}</td><td class="${cls||(diff?'d':'')}">${esc(y)}</td></tr>`};
 const rows=d.fields.map(f=>row(f,A.raw[f],B.raw[f])).join('')
  +`<tr class="sec"><th colspan="3">normalized</th></tr>`+d.norm_fields.map(f=>row(f,A.norm[f],B.norm[f])).join('')
  +`<tr class="sec"><th colspan="3">match keys (green = shared, what made them candidates)</th></tr>`
  +[...new Set([...Object.keys(A.keys),...Object.keys(B.keys)])].sort().map(k=>{const x=A.keys[k]||'',y=B.keys[k]||'';return row(k,x,y,x&&x===y?'s':'')}).join('');
 const truth=p.dup?'same entity':'different entities';
 const vtxt=p.verdict=='review'?`review: truth is ${truth}`:p.verdict=='unprovable'?'unprovable: same entity, but only the name matches':p.verdict=='right'?'right':p.decision=='merge'?'wrong: merged, but the answer key says different entities':'wrong: not merged, but the answer key says the same entity';
 return`<div class="card"><div class="top"><span class="tag ${p.verdict}">${vtxt}</span><span>${LABEL[p.decision]}</span>
 <span class="mut">rule: ${p.rule}</span>${p.score?`<span class="mut">${esc(p.score)}</span>`:''}
 <span class="mut">truth: ${truth} (${p.kinds})</span><span class="mut">scenario: ${p.scenario}</span></div>
 <table><tr><th>record</th><td><b>${p.a}</b></td><td><b>${p.b}</b></td></tr>${rows}</table>
 <div class="note">${esc(p.detail)}${p.keys?` · candidate because of: ${p.keys.split('+').join(', ')}`:''}</div></div>`}
function render(reset){const d=D[$('t').value],f=filtered();if(reset){shown=0;$('list').innerHTML=''}
 const c={right:0,wrong:0,review:0,unprovable:0};d.pairs.forEach(p=>c[p.verdict]++);
 $('sum').textContent=`${d.pairs.length} pairs: ${c.right} right, ${c.wrong} wrong, ${c.unprovable} unprovable (true duplicates sharing only a name), ${c.review} in the review queue. Showing ${Math.min(shown+PAGE,f.length)} of ${f.length} matching.`;
 $('list').insertAdjacentHTML('beforeend',f.slice(shown,shown+PAGE).map(p=>card(p,d)).join(''));shown+=PAGE;$('more').style.display=shown<f.length?'':'none'}
function scenarios(){const d=D[$('t').value];$('s').innerHTML='<option value="all">all</option>'+[...new Set(d.pairs.map(p=>p.scenario))].sort().map(x=>`<option>${x}</option>`).join('')}
function rules(){const d=D[$('t').value];$('r').innerHTML='<option value="all">all</option>'+[...new Set(d.pairs.map(p=>p.rule))].sort().map(x=>`<option>${x}</option>`).join('')}
$('t').onchange=()=>{rules();scenarios();render(true)};['v','r','s'].forEach(i=>$(i).onchange=()=>render(true));$('q').oninput=()=>render(true);$('more').onclick=()=>render(false);
rules();scenarios();render(true);
</script></body></html>"""

if __name__ == "__main__":
    data = {t: build(t) for t in ("accounts", "contacts")}
    html = PAGE.replace("__DATA__", json.dumps(data).replace("</", "<\\/"))
    (DATA / "report.html").write_text(html)
    for t, d in data.items():
        print(t, len(d["pairs"]), "pairs,", sum(p["verdict"] == "wrong" for p in d["pairs"]), "wrong,", sum(p["verdict"] == "unprovable" for p in d["pairs"]), "unprovable")
    print("wrote", DATA / "report.html")
