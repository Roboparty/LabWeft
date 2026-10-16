"""One self-contained HTML page per traced source, in the LabWeft workspace look (same stylesheet, top bar,
sidebar navigation, stat cards, list + inspector layout as `labweft serve`).

Views: overview (coverage, layout, the authors' key documents), research decomposition (questions -> factors ->
conditions with mean +/- SD and error-bar charts), validity (studies the authors flagged, divergent copies),
audit leads and the review worklist. Clicking an item opens it in the inspector on the right.

Collecting is read-only over the index and can take minutes on a large tree, so the collected data is cached as
JSON next to the index; rendering is instant. No network, no external assets."""
from __future__ import annotations

import html
import json
import time
from collections import Counter
from pathlib import Path

from . import analyze, audit, index, navigate, review

STATIC = Path(__file__).resolve().parent.parent / "static"

BRAND = """<span class="brandmark brandmark-weft"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96" aria-hidden="true">
<rect width="96" height="96" rx="23" fill="#123e32"/><g fill="none" stroke-linecap="round">
<path d="M28 20v56M48 20v56M68 20v56" stroke="#efc779" stroke-width="8"/>
<path d="M20 28h56M20 48h56M20 68h56" stroke="#b6dac5" stroke-width="8"/>
<path d="M28 22v12M68 22v12M48 42v12M28 62v12M68 62v12" stroke="#123e32" stroke-width="14"/>
<path d="M28 22v12M68 22v12M48 42v12M28 62v12M68 62v12" stroke="#efc779" stroke-width="8"/></g></svg></span>"""

EXTRA_CSS = """
.project-switcher a{color:#e6f4e9;text-decoration:none;border:1px solid #2f5b4e;border-radius:5px;padding:5px 9px;font-size:11px}
.project-switcher a.current{background:#e6f4e9;color:#143c32;font-weight:650}
.list{padding:8px 16px 22px}.row{display:flex;align-items:flex-start;gap:10px;border:1px solid transparent;border-radius:7px;background:#fafbf8;padding:10px 12px;margin:6px 0;cursor:pointer}
.row:hover{background:#f0f5ed}.row.selected{border-color:#9dbda8;background:#eef5ed}
.row .node-label b{font-weight:600}.row .tags{margin-top:5px;display:flex;flex-wrap:wrap;gap:4px}
.group-title{font-size:10px;letter-spacing:1.4px;color:var(--muted);margin:18px 4px 4px;font-weight:600;text-transform:uppercase}
.kind-dot{width:9px;height:9px;border-radius:50%;margin-top:5px;flex-shrink:0;background:#98aca2}
.kind-dot.q{background:#566d96}.kind-dot.warn{background:#c78074}.kind-dot.flag{background:#b99b60}.kind-dot.ok{background:#5c9478}
.mini{width:100%;display:block;margin:6px 0 2px}
.cells{width:100%;border-collapse:collapse;font-size:11px;margin:8px 0}.cells th,.cells td{border-bottom:1px solid var(--line);padding:6px 5px;text-align:left;vertical-align:top}
.cells td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.cells th{color:var(--muted);font-weight:500}
code.p{font:11px/1.5 ui-monospace,Consolas,monospace;overflow-wrap:anywhere;color:#41544e}
.detail ul{padding-left:16px;margin:6px 0;font-size:11px;line-height:1.75}.detail li{margin:3px 0}
.chip{display:inline-block;max-width:100%;overflow-wrap:anywhere;font-size:10px;border:1px solid #dce6da;background:#f4f8f0;color:#5d7466;border-radius:4px;padding:2px 6px;margin:0 4px 4px 0}
.chip.warn{color:#9a4b3c;border-color:#ecd2c9;background:#fbf2ee}.chip.flag{color:var(--amber);border-color:#ecdfbe;background:#fff9eb}
.bars{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;padding:6px 22px 18px}
.bar{border:1px solid var(--line);border-radius:8px;padding:10px 12px;background:#fff;font-size:11px}.bar b{font-size:18px;display:block;font-weight:550}
.track{height:6px;border-radius:3px;background:#edf2ec;margin-top:7px;overflow:hidden}.track i{display:block;height:100%;background:#7fae96}
"""

JS = r"""
const D=JSON.parse(document.getElementById('data').textContent);
const $=id=>document.getElementById(id);const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let view='overview',query='';
const VIEWS={overview:['概览','从文件到研究：覆盖范围、目录结构与作者的关键文档'],decompose:['研究拆解','改了什么因子 × 测了什么指标 × 在哪些任务上评测 × 几个独立 seed'],
validity:['有效性','作者标记为无效 / 不完整 / 已取代的研究，以及内容不同的副本'],audit:['审计线索','自动规则找到的疑点：每一条都需要打开所引文件核实'],worklist:['核对清单','逐份报告人工核对：找不到来源的行、算术不符、引用缺失']};
function stats(){const s=D.stats;$('stats').innerHTML=[['文件',s.files,'▧'],['报告',s.reports,'◇'],['结果文件',s.results,'▤'],['研究问题',s.questions,'◉']].map(([k,n,i])=>`<div class="stat"><div><div class="stat-number">${Number(n).toLocaleString()}</div><div class="stat-label">${k}</div></div><div class="stat-icon">${i}</div></div>`).join('');}
function chips(a,cls=''){return (a||[]).map(x=>`<span class="chip ${cls}">${esc(x)}</span>`).join('')}
function match(t){return !query||t.toLowerCase().includes(query)}
function errbars(cells){ // horizontal mean ± SD chart
 const c=cells.filter(x=>x.mean!=null).slice(0,14);if(!c.length)return'';
 const lo=Math.min(...c.map(x=>x.mean-(x.sd||0))),hi=Math.max(...c.map(x=>x.mean+(x.sd||0)));const span=(hi-lo)||1,W=270,H=c.length*20+18,L=4;
 const X=v=>L+(v-lo)/span*(W-L-8);
 let g=`<svg class="mini" viewBox="0 0 ${W} ${H}" role="img">`;
 c.forEach((x,i)=>{const y=12+i*20;g+=`<line x1="${X(x.mean-(x.sd||0))}" x2="${X(x.mean+(x.sd||0))}" y1="${y}" y2="${y}" stroke="#9db8a6" stroke-width="2"/><circle cx="${X(x.mean)}" cy="${y}" r="3.6" fill="#267b65"><title>${esc(x.label)}: ${x.mean.toFixed(2)} ± ${(x.sd||0).toFixed(2)}</title></circle>`});
 g+=`<text x="${L}" y="${H-2}" font-size="9" fill="#758382">${lo.toFixed(1)}</text><text x="${W-8}" y="${H-2}" font-size="9" fill="#758382" text-anchor="end">${hi.toFixed(1)}</text></svg>`;return g;}
function render(){
 const [t,sub]=VIEWS[view];$('page-title').textContent=t;$('page-subtitle').textContent=sub;
 document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('active',b.dataset.view===view));
 let h='',rows=[];
 if(view==='overview'){
  h+=`<div class="panel-head"><div><h2>目录结构</h2><small>顶层文件夹，按文件类型计数；作者标记过的文件夹带标签</small></div></div><div class="list">`;
  D.layout.forEach((e,i)=>{const txt=e.name+' '+Object.keys(e.roles||{}).join(' ');if(!match(txt))return;
   h+=`<div class="row" data-k="layout" data-i="${i}"><span class="kind-dot ${e.flag?'flag':''}"></span><div class="node-label"><b>${esc(e.name)}</b><span class="node-sub">${e.files!=null?Number(e.files).toLocaleString()+' 个文件':''}</span><div class="tags">${chips(Object.entries(e.roles||{}).slice(0,5).map(([k,v])=>k+' '+v))}${e.flag?'<span class="chip flag">作者标记</span>':''}</div></div></div>`});
  h+=`</div><div class="panel-head"><div><h2>作者的关键文档</h2><small>README / FINAL / STATUS 一类，浅层与最新优先</small></div></div><div class="list">`;
  D.docs.forEach((d,i)=>{if(!match(d.path+d.title))return;h+=`<div class="row" data-k="doc" data-i="${i}"><span class="kind-dot ok"></span><div class="node-label"><b>${esc(d.title||d.path.split('/').pop())}</b><span class="node-sub">${esc(d.path)}</span></div></div>`});
  h+='</div>';
 } else if(view==='decompose'){
  h+=`<div class="panel-head"><div><h2>${D.questions.length} 个研究问题</h2><small>由配置、表格列和 run 名中的超参自动恢复；点击查看各条件的均值 ± 样本 SD</small></div></div><div class="list">`;
  D.questions.forEach((q,i)=>{if(!match(q.title+' '+q.factors.join(' ')+' '+q.locations.map(l=>l.source).join(' ')))return;
   h+=`<div class="row" data-k="q" data-i="${i}"><span class="kind-dot q"></span><div class="node-label"><b>${esc(q.title)}</b><span class="node-sub">${q.units} 个单元 · ${q.n_locations} 处证据 · 指标 ${esc(q.metric)}</span><div class="tags">${chips(q.factors)}${chips(q.context.map(x=>'评测于 '+x))}</div></div></div>`});
  h+='</div>';
 } else if(view==='validity'){
  h+=`<div class="panel-head"><div><h2>被标记的研究（${D.flagged.length}）</h2><small>文件夹名或报告原文中的“无效 / 不完整 / 已取代”</small></div></div><div class="list">`;
  D.flagged.forEach((a,i)=>{if(!match(a.area+a.marker+(a.text||'')))return;h+=`<div class="row" data-k="flag" data-i="${i}"><span class="kind-dot flag"></span><div class="node-label"><b>${esc(a.area)}</b><span class="node-sub">${esc(a.text||'')}</span><div class="tags"><span class="chip flag">${esc(a.marker)}</span>${chips(a.contradictions,'warn')}</div></div></div>`});
  h+=`</div><div class="panel-head"><div><h2>内容不同的副本（${D.copies.length}）</h2><small>同名同标题的文档保存在多处且内容不同：引用时要用最新的那份</small></div></div><div class="list">`;
  D.copies.forEach((g,i)=>{if(!match(g.document))return;h+=`<div class="row" data-k="copy" data-i="${i}"><span class="kind-dot"></span><div class="node-label"><b>${esc(g.document)}</b><span class="node-sub">${g.versions} 个版本 · ${g.copies.length} 处</span></div></div>`});
  h+='</div>';
 } else if(view==='audit'){
  const kinds={};D.findings.forEach(f=>kinds[f.kind]=(kinds[f.kind]||0)+1);
  h+=`<div class="panel-head"><div><h2>${D.findings.length} 条审计线索</h2><small>${esc(D.manual)}</small></div></div><div class="bars">`+Object.entries(kinds).map(([k,n])=>`<div class="bar"><b>${n}</b>${esc(k)}<div class="track"><i style="width:${Math.min(100,n/Math.max(...Object.values(kinds))*100)}%"></i></div></div>`).join('')+`</div><div class="list">`;
  D.findings.forEach((f,i)=>{if(!match(f.kind+f.file+f.evidence))return;h+=`<div class="row" data-k="finding" data-i="${i}"><span class="kind-dot warn"></span><div class="node-label"><b>${esc(f.evidence)}</b><span class="node-sub">${esc(f.file)}</span><div class="tags"><span class="chip warn">${esc(f.kind)}</span>${f.confidence?`<span class="chip">${esc(f.confidence)}</span>`:''}</div></div></div>`});
  h+='</div>';
 } else if(view==='worklist'){
  h+=`<div class="panel-head"><div><h2>按研究分组</h2><small>大项目可以把每个研究交给一个人或一个 agent 逐份核对</small></div></div><div class="bars">`+D.studies.map(s=>`<div class="bar"><b>${s.reports}</b>${esc(s.study)}<span class="node-sub">${s.result_files} 个结果文件</span></div>`).join('')+`</div><div class="panel-head"><div><h2>需要核对的报告（${D.work.length}）</h2><small>按报告中的数字多少排序</small></div></div><div class="list">`;
  D.work.forEach((w,i)=>{if(!match(w.report))return;const n=(w.arith||[]).length+(w.missing||[]).length;h+=`<div class="row" data-k="work" data-i="${i}"><span class="kind-dot ${n?'warn':''}"></span><div class="node-label"><b>${esc(w.report.split('/').pop())}</b><span class="node-sub">${esc(w.report)}</span><div class="tags"><span class="chip">${w.numbers} 行数字</span>${(w.unsourced||[]).length?`<span class="chip flag">${w.unsourced.length} 行无来源</span>`:''}${(w.arith||[]).length?`<span class="chip warn">${w.arith.length} 处算术不符</span>`:''}${(w.missing||[]).length?`<span class="chip warn">${w.missing.length} 个引用缺失</span>`:''}</div></div></div>`});
  h+='</div>';
 }
 $('content').innerHTML=`<div class="search-wrap"><input class="search" id="q" placeholder="筛选当前列表…" value="${esc(query)}"></div>`+h;
 $('q').oninput=e=>{query=e.target.value.toLowerCase();const p=e.target.selectionStart;render();$('q').focus();$('q').setSelectionRange(p,p)};
 document.querySelectorAll('.row').forEach(r=>r.onclick=()=>{document.querySelectorAll('.row').forEach(x=>x.classList.remove('selected'));r.classList.add('selected');detail(r.dataset.k,+r.dataset.i)});
 if(!document.querySelector('.row.selected'))defaultDetail();
}
function kv(o){return `<dl class="kv">${Object.entries(o).filter(([k,v])=>v!==undefined&&v!==null&&v!=='').map(([k,v])=>`<dt>${esc(k)}</dt><dd>${v}</dd>`).join('')}</dl>`}
function defaultDetail(){$('detail').innerHTML=`<div class="eyebrow">项目</div><h2>${esc(D.name)}</h2><p class="description"><code class="p">${esc(D.root)}</code></p>${kv({'文件':Number(D.stats.files).toLocaleString(),'压缩包成员':Number(D.stats.members).toLocaleString(),'报告':D.stats.reports,'结果文件':D.stats.results,'日志':D.stats.logs,'配置':D.stats.configs,'被标记研究':D.flagged.length,'审计线索':D.findings.length,'索引':esc(D.coverage),'生成时间':esc(D.generated)})}<div class="detail-section"><div class="note">只读生成：没有改动项目里的任何文件。数字都来自索引中的原始文件；“审计线索”是待核实的疑点，不是结论。</div></div>`}
function detail(k,i){let h='';
 if(k==='q'){const q=D.questions[i];h=`<div class="eyebrow">研究问题</div><h2>${esc(q.title)}</h2>${kv({'处理因子':chips(q.factors),'评测语境':chips(q.context),'指标':esc(q.metric),'单元':q.units})}`;
  Object.entries(q.levels).forEach(([f,v])=>h+=`<div class="detail-section"><h3>${esc(f)} 的取值</h3>${chips(v)}</div>`);
  q.locations.forEach(l=>{h+=`<div class="detail-section"><h3>证据：${esc(l.role)} · ${l.cells} 个条件 · ${l.units} 个单元</h3><code class="p">${esc(l.source)}</code>${errbars(l.cells_list)}<table class="cells"><thead><tr><th>条件</th><th>${esc(l.metric)}</th></tr></thead><tbody>${l.cells_list.map(c=>`<tr><td>${esc(c.label)}</td><td class="n">${c.mean!=null?c.mean.toFixed(2):''}${c.sd!=null?' ± '+c.sd.toFixed(2):''} <span class="muted">n=${c.n}</span></td></tr>`).join('')}</tbody></table></div>`});
 } else if(k==='layout'){const e=D.layout[i];h=`<div class="eyebrow">文件夹</div><h2>${esc(e.name)}</h2>${kv({'文件数':e.files,'类型':chips(Object.entries(e.roles||{}).map(([a,b])=>a+' '+b))})}`;
 } else if(k==='doc'){const d=D.docs[i];h=`<div class="eyebrow">关键文档</div><h2>${esc(d.title)}</h2><p class="description"><code class="p">${esc(d.path)}</code></p><div class="note">用 <code>labweft trace read --path</code> 阅读全文（来自哈希固定的快照）。</div>`;
 } else if(k==='flag'){const a=D.flagged[i];h=`<div class="eyebrow">被标记的研究</div><h2>${esc(a.area)}</h2>${kv({'标记':`<span class="chip flag">${esc(a.marker)}</span>`,'矛盾':chips(a.contradictions,'warn')})}${a.text?`<div class="detail-section"><h3>作者原话</h3><div class="note">${esc(a.text)}</div></div>`:''}${(a.alternatives||[]).length?`<div class="detail-section"><h3>未被标记的同主题研究</h3><ul>${a.alternatives.map(x=>`<li><code class="p">${esc(x)}</code></li>`).join('')}</ul></div>`:''}`;
 } else if(k==='copy'){const g=D.copies[i];h=`<div class="eyebrow">内容不同的副本</div><h2>${esc(g.document)}</h2><ul>${g.copies.map(c=>`<li><code class="p">${esc(c.path)}</code> <span class="chip">版本 ${esc(c.version)}</span>${c.newest?'<span class="chip">最新</span>':''}</li>`).join('')}</ul>`;
 } else if(k==='finding'){const f=D.findings[i];h=`<div class="eyebrow">审计线索 · ${esc(f.kind)}</div><h2>${esc(f.evidence)}</h2>${kv({'可信度':esc(f.confidence),'位置':esc(f.locator)})}<div class="detail-section"><h3>相关文件</h3><ul>${f.files.map(x=>`<li><code class="p">${esc(x)}</code></li>`).join('')}</ul></div><div class="detail-section"><div class="note">打开上面的文件核实后再下结论；作者自己已说明的情况不算问题。</div></div>`;
 } else if(k==='work'){const w=D.work[i];h=`<div class="eyebrow">核对清单</div><h2>${esc(w.report.split('/').pop())}</h2><p class="description"><code class="p">${esc(w.report)}</code></p>${kv({'研究':esc(w.study),'数字行':w.numbers,'追溯结果':esc(JSON.stringify(w.by_state||{}))})}`;
  if((w.arith||[]).length)h+=`<div class="detail-section"><h3>表格算术不符</h3><ul>${w.arith.map(x=>`<li class="warn">${esc(x)}</li>`).join('')}</ul></div>`;
  if((w.missing||[]).length)h+=`<div class="detail-section"><h3>引用但缺失的文件</h3><ul>${w.missing.map(x=>`<li><code class="p">${esc(x)}</code></li>`).join('')}</ul></div>`;
  if((w.unsourced||[]).length)h+=`<div class="detail-section"><h3>文件夹里找不到来源的行</h3><ul>${w.unsourced.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`;
  if((w.raw||[]).length)h+=`<div class="detail-section"><h3>报告引用的原始文件</h3><ul>${w.raw.map(x=>`<li><code class="p">${esc(x)}</code></li>`).join('')}</ul></div>`;
  h+=`<div class="detail-section"><div class="note">逐表核对：均值是否按声明的集合计算、差值与相对变化的基数、SD 口径、由计数推出的 p 值、n 与列出的项目、单位。</div></div>`;}
 $('detail').innerHTML=h;}
document.querySelectorAll('#nav button').forEach(b=>b.onclick=()=>{view=b.dataset.view;query='';render()});
stats();
const hp=new URLSearchParams(location.hash.slice(1));if(hp.get('view')&&VIEWS[hp.get('view')])view=hp.get('view');render();
if(hp.get('sel')){const r=document.querySelectorAll('.row')[+hp.get('sel')];if(r)r.click();}
"""


def _fname(f: str) -> str:
    """Factor keys recovered from unnamed run-name tokens look like `s#2`: say so in words."""
    import re
    m = re.match(r"^(\w*)#(\d+)$", str(f))
    return f"run 名第 {m.group(2)} 段（{m.group(1) or '无前缀'}）" if m else str(f)


def _short(v) -> str:
    v = str(v).strip('"')
    return ("…/" + "/".join(v.split("/")[-2:])) if "/" in v and len(v) > 48 else v


def _cells(loc, limit=40):
    out = []
    for c in loc.get("top_cells", [])[:limit]:
        st = c.get("stats") or {}
        out.append({"label": ", ".join(f"{_fname(k)}={_short(v)}" for k, v in (c.get("levels") or {}).items()),
                    "mean": st.get("mean"), "sd": st.get("sd_sample"), "n": st.get("n")})
    return out


def collect(ws: Path, name: str, outline_limit: int = 60, audit_limit: int = 400, log=print) -> dict:
    con = index.connect(ws, name)
    meta = index.meta(con)
    n_files = con.execute("SELECT COUNT(*) FROM files WHERE path NOT LIKE '%::%'").fetchone()[0]
    n_members = con.execute("SELECT COUNT(*) FROM files WHERE path LIKE '%::%'").fetchone()[0]
    roles = Counter(dict(con.execute("SELECT COALESCE(role, kind, '?'), COUNT(*) FROM files WHERE path NOT LIKE '%::%' GROUP BY 1").fetchall()))
    log(f"{name}: brief");
    br = navigate.brief(con, limit=40)
    log(f"{name}: outline")
    ol = analyze.outline(con, limit=outline_limit)
    log(f"{name}: validity")
    va = navigate.validity(con, limit=80)
    log(f"{name}: audit")
    au = audit.audit(con, limit=audit_limit)
    log(f"{name}: worklist")
    wl = review.worklist(con, limit=40)
    con.close()
    src = {}
    try:
        from . import source
        src = source.load(ws, name)
    except Exception:
        pass
    questions = []
    for ex in ol.get("experiments", {}).get("items", []):
        fac = [_fname(f) for f in ex.get("treatment_factors", [])]
        title = f"{'、'.join(fac[:4])} 对 {ex.get('metric')} 的影响" + (f"（在 {'、'.join(ex.get('evaluated_across', []))} 上评测）" if ex.get("evaluated_across") else "")
        questions.append({"title": title, "raw_title": ex.get("experiment"), "factors": fac, "context": ex.get("evaluated_across", []),
                          "metric": ex.get("metric"), "units": ex.get("units"), "n_locations": ex.get("evidence_locations"),
                          "levels": {_fname(k): [_short(v) for v in vals[:16]] for k, vals in (ex.get("levels") or {}).items()},
                          "locations": [{"source": l.get("source"), "role": l.get("role"), "cells": l.get("cells"), "units": l.get("units"),
                                         "metric": l.get("primary_metric"), "cells_list": _cells(l)} for l in ex.get("locations", [])[:6]]})
    layout = []
    for e in br.get("layout", [])[:80]:
        if "dir" in e:
            layout.append({"name": e["dir"], "files": e.get("files"), "roles": e.get("roles") or {}, "flag": bool(e.get("flag"))})
        else:
            layout.append({"name": e.get("name"), "files": None, "roles": {str(e.get("role") or e.get("kind")): 1}, "flag": False})
    flagged = [{"area": a.get("area"), "marker": a.get("path_marker"),
                "text": "; ".join(str(t.get("text", ""))[:220] for t in (a.get("text_evidence") or [])[:2]),
                "contradictions": [c.get("kind") for c in a.get("contradictions", [])],
                "alternatives": [x.get("study") for x in a.get("unflagged_alternatives", [])[:4]]}
               for a in va.get("flagged_areas", {}).get("items", [])]
    copies = va.get("divergent_copies", {}).get("items", [])
    findings = [{"kind": f["kind"], "file": f["files"][0], "files": f["files"], "evidence": f.get("evidence", ""),
                 "locator": f.get("locator"), "confidence": f.get("confidence")} for f in au.get("findings", {}).get("items", [])]
    work = [{"report": e["report"], "numbers": e["numbers"], "study": e.get("study"), "by_state": e.get("by_state"),
             "unsourced": e.get("check_rows_without_source", []), "arith": e.get("table_arithmetic_fails", []),
             "missing": e.get("cited_files_not_found", []), "raw": e.get("raw_files_cited", [])}
            for e in wl.get("worklist", {}).get("items", [])]
    return {"name": name, "root": f"{src.get('host') + ':' if src.get('host') else ''}{src.get('root', '')}",
            "generated": time.strftime("%Y-%m-%d %H:%M"), "coverage": str(meta.get("coverage") or meta.get("complete") or ""),
            "stats": {"files": n_files, "members": n_members, "reports": roles.get("report", 0),
                      "results": roles.get("result", 0) + roles.get("result_table", 0), "logs": roles.get("log", 0),
                      "configs": roles.get("config", 0), "questions": len(questions)},
            "layout": layout, "docs": br.get("key_documents", []), "questions": questions, "flagged": flagged, "copies": copies,
            "findings": findings, "manual": (au.get("manual_review_still_needed") or {}).get("next", ""),
            "studies": wl.get("studies", []), "work": work}


def render(data: dict, out: Path, siblings: list[tuple[str, str]] | None = None) -> Path:
    css = (STATIC / "app.css").read_text(encoding="utf-8") + EXTRA_CSS
    sw = ""
    if siblings:
        sw = ('<div class="project-switcher"><strong>切换项目</strong><div>' + " ".join(
            f'<a href="{html.escape(href)}" class="{"current" if n == data["name"] else ""}">{html.escape(n)}</a>' for n, href in siblings)
              + "</div></div>")
    nav = "".join(f'<button data-view="{v}"{" class=active" if v == "overview" else ""}><span>{i}</span><span>{t}</span></button>'
                  for v, i, t in [("overview", "⌘", "概览"), ("decompose", "◉", "研究拆解"), ("validity", "◇", "有效性"),
                                  ("audit", "△", "审计线索"), ("worklist", "▤", "核对清单")])
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    doc = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>LabWeft trace · {html.escape(data['name'])}</title><style>{css}</style></head><body>
<header class="topbar"><div class="brand">{BRAND}<div>LabWeft<small>TRACE · 项目调查报告</small></div></div>
<div class="topright"><span class="pill">只读 · 本地</span><span class="muted">{html.escape(data['generated'])}</span></div></header>
{sw}<div class="shell"><aside class="sidebar"><div class="eyebrow">项目</div><div class="project-name">{html.escape(data['name'])}</div>
<nav id="nav">{nav}</nav><div class="sidebar-note"><span class="status-dot"></span> 由 trace 索引生成<p>按“因子 × 指标 × 任务 × seed”拆解研究；数字都能追到原始文件。</p></div>
<div class="sidebar-foot"><span>{html.escape(data['root'])}</span></div></aside>
<main><section class="heading"><div><div class="eyebrow">从文件到研究</div><h1 id="page-title"></h1><p id="page-subtitle"></p></div></section>
<section id="stats" class="stats"></section><div class="workspace-body"><section id="content" class="content"></section><aside id="detail" class="detail"></aside></div>
<footer><span>LabWeft trace · 只读生成，未改动项目文件</span><span>审计线索是待核实的疑点，不是结论</span></footer></main></div>
<script id="data" type="application/json">{payload}</script><script>{JS}</script></body></html>"""
    out = Path(out)
    out.write_text(doc, encoding="utf-8")
    return out


def build(ws: Path, name: str, out: Path, siblings=None, log=print, refresh: bool = False) -> Path:
    cache = index.trace_dir(Path(ws), name) / "report-data.json"
    if cache.exists() and not refresh:
        data = json.loads(cache.read_text(encoding="utf-8"))
    else:
        t0 = time.time()
        data = collect(Path(ws), name, log=log)
        cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        log(f"{name}: collected in {time.time() - t0:.0f} s")
    p = render(data, out, siblings)
    log(f"{name}: wrote {p} ({p.stat().st_size // 1024} KB)")
    return p


SEM_JS = r"""
const S=JSON.parse(document.getElementById('sem').textContent);const D=JSON.parse(document.getElementById('data').textContent);
const $=id=>document.getElementById(id);const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let view='summary',query='';
const VIEWS={summary:['研究概要','这个项目在研究什么、用什么方法、最重要的结论'],claims:['结论','论文式结论：每条都带数字与证据，并标明是否仍然成立'],
experiments:['实验','按研究问题组织：主实验、消融、对照、机制分析、重评'],timeline:['研究历程','各阶段做了什么、得到什么、为什么转向'],
invalid:['作废与取代','被作者撤回、作废或取代的研究与数字，以及替代者'],open:['待解决','尚未完成的实验与开放问题'],audit:['审计线索','自动规则找到的、待核实的疑点']};
const ST={'成立':'ok','部分成立':'flag','已被取代':'warn','已撤回':'warn','待验证':'flag','有效':'ok','已被取代 ':'warn','作废':'warn','进行中':'flag'};
const CK={verified:['✓ 工具已核验',''],partly:['◐ 部分核验','flag'],problem:['⚠ 证据不符','warn'],unchecked:['未核验','flag']};
const NC={ok:['✓',''],ok_derived:['✓ 复算一致',''],number_not_at_source:['⚠ 引用处找不到此数','warn'],path_missing:['⚠ 文件不存在','warn'],line_out_of_range:['⚠ 行号越界','warn'],unreadable:['未能读取','flag'],no_source:['无出处','flag']};
function ck(x){const c=CK[x];return c?chip(c[0],c[1]):''}function nc(x){const c=NC[x];return c?chip(c[0],c[1]):''}
function chip(t,c=''){return `<span class="chip ${c}">${esc(t)}</span>`}
function ev(a){return (a||[]).length?`<div class="detail-section"><h3>证据</h3><ul>${a.map(x=>`<li><code class="p">${esc(x)}</code></li>`).join('')}</ul></div>`:''}
function match(t){return !query||t.toLowerCase().includes(query)}
function stats(){const cs=S._check_summary;$('stats').innerHTML=[['结论',(S.claims||[]).length,'✓'],['实验',(S.experiments||[]).length,'▤'],['研究阶段',(S.phases||[]).length,'↺'],cs?['证据核验通过',Math.round(100*((cs.ok||0)+(cs.ok_derived||0))/cs.checked)+'%','⚖']:['作废/取代',(S.invalidated||[]).length,'◇']].map(([k,n,i])=>`<div class="stat"><div><div class="stat-number">${n}</div><div class="stat-label">${k}</div></div><div class="stat-icon">${i}</div></div>`).join('')}
function bars(rs){const c=(rs||[]).filter(r=>typeof r.value==='number').slice(0,16);if(c.length<2)return'';
 const lo=Math.min(...c.map(x=>x.value-(x.sd||0))),hi=Math.max(...c.map(x=>x.value+(x.sd||0)));const sp=(hi-lo)||1,W=280,H=c.length*22+18,X=v=>110+(v-lo)/sp*(W-120);
 let g=`<svg class="mini" viewBox="0 0 ${W} ${H}">`;c.forEach((r,i)=>{const y=13+i*22;g+=`<text x="0" y="${y+3}" font-size="9" fill="#596e62">${esc(String(r.condition).slice(0,22))}</text><line x1="${X(r.value-(r.sd||0))}" x2="${X(r.value+(r.sd||0))}" y1="${y}" y2="${y}" stroke="#9db8a6" stroke-width="2"/><circle cx="${X(r.value)}" cy="${y}" r="3.8" fill="#267b65"><title>${esc(r.condition)}: ${r.value}${r.sd!=null?' ± '+r.sd:''}</title></circle>`});
 return g+`<text x="110" y="${H-2}" font-size="9" fill="#758382">${lo.toFixed(1)}</text><text x="${W-10}" y="${H-2}" font-size="9" fill="#758382" text-anchor="end">${hi.toFixed(1)}</text></svg>`}
function list(items,fn){return `<div class="list">${items.map((x,i)=>fn(x,i)).filter(Boolean).join('')}</div>`}
function render(){const [t,sub]=VIEWS[view];$('page-title').textContent=t;$('page-subtitle').textContent=sub;
 document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('active',b.dataset.view===view));let h='';
 if(view==='summary'){
  h+=`<div class="panel-head"><div><h2>一句话</h2></div></div><div class="list"><div class="note" style="font-size:13px">${esc(S.one_line)}</div></div>`;
  h+=`<div class="panel-head"><div><h2>研究背景</h2></div></div><div class="list"><p class="description" style="font-size:13px;line-height:1.9">${esc(S.background)}</p></div>`;
  const m=S.method||{};h+=`<div class="panel-head"><div><h2>方法：${esc(m.name)}</h2><small>${esc(m.idea)}</small></div></div>`+list(m.components||[],(c,i)=>`<div class="row" data-k="comp" data-i="${i}"><span class="kind-dot q"></span><div class="node-label"><b>${esc(c.name)}</b><span class="node-sub">${esc(c.role)}</span></div></div>`);
  h+=`<div class="panel-head"><div><h2>建议阅读顺序</h2></div></div>`+list(S.reading_order||[],(r,i)=>`<div class="row" data-k="read" data-i="${i}"><span class="kind-dot ok"></span><div class="node-label"><b>${esc(r.path.split('/').pop())}</b><span class="node-sub">${esc(r.why)}</span></div></div>`);
  h+=`<div class="panel-head"><div><h2>术语表</h2></div></div>`+list(S.glossary||[],(g,i)=>match(g.term+g.meaning)?`<div class="row" data-k="term" data-i="${i}"><span class="kind-dot"></span><div class="node-label"><b>${esc(g.term)}</b><span class="node-sub">${esc(g.meaning)}</span></div></div>`:'');
 } else if(view==='claims'){
  h+=`<div class="panel-head"><div><h2>${(S.claims||[]).length} 条结论</h2><small>绿色=成立，黄色=部分成立/待验证，红色=已被取代/撤回</small></div></div>`+list(S.claims||[],(c,i)=>match(c.statement+c.id)?`<div class="row" data-k="claim" data-i="${i}"><span class="kind-dot ${ST[c.status]||''}"></span><div class="node-label"><b>${esc(c.id)} · ${esc(c.statement)}</b><div class="tags">${chip(c.status,ST[c.status]==='ok'?'':(ST[c.status]||''))}${ck(c._check)}${(c.numbers||[]).slice(0,3).map(n=>chip(n.value)).join('')}</div></div></div>`:'');
 } else if(view==='experiments'){
  const groups={};(S.experiments||[]).forEach((e,i)=>{(groups[e.type]=groups[e.type]||[]).push([e,i])});
  Object.entries(groups).forEach(([g,es])=>{h+=`<div class="panel-head"><div><h2>${esc(g)}（${es.length}）</h2></div></div><div class="list">`+es.map(([e,i])=>match(e.question+e.finding+e.id)?`<div class="row" data-k="exp" data-i="${i}"><span class="kind-dot ${ST[e.status]||'q'}"></span><div class="node-label"><b>${esc(e.id)} · ${esc(e.question)}</b><span class="node-sub">${esc(e.finding)}</span><div class="tags">${chip(e.status,ST[e.status]==='ok'?'':(ST[e.status]||''))}${ck(e._check)}${(e.design?.compared||[]).slice(0,4).map(x=>chip(x)).join('')}</div></div></div>`:'').join('')+`</div>`});
 } else if(view==='timeline'){
  h+=`<div class="history">`+(S.phases||[]).map((p,i)=>match(p.title+p.summary)?`<div class="history-item row" data-k="phase" data-i="${i}" style="display:block;background:transparent"><b>${esc(p.period)}</b>${esc(p.title)}<small>${esc(p.summary)}</small></div>`:'').join('')+`</div>`;
 } else if(view==='invalid'){
  h+=`<div class="panel-head"><div><h2>${(S.invalidated||[]).length} 项</h2><small>引用时不要使用这些结论；右侧给出替代者</small></div></div>`+list(S.invalidated||[],(x,i)=>match(x.what+x.why)?`<div class="row" data-k="inv" data-i="${i}"><span class="kind-dot warn"></span><div class="node-label"><b>${esc(x.what)}</b><span class="node-sub">${esc(x.why)}</span>${x.replaced_by?`<div class="tags">${chip('→ '+x.replaced_by)}</div>`:''}</div></div>`:'');
 } else if(view==='open'){
  h+=list(S.open_questions||[],(x,i)=>match(x.question)?`<div class="row" data-k="open" data-i="${i}"><span class="kind-dot flag"></span><div class="node-label"><b>${esc(x.question)}</b></div></div>`:'');
 } else if(view==='audit'){
  h+=`<div class="panel-head"><div><h2>${D.findings.length} 条审计线索</h2><small>${esc(D.manual)}</small></div></div>`+list(D.findings,(f,i)=>match(f.kind+f.file+f.evidence)?`<div class="row" data-k="finding" data-i="${i}"><span class="kind-dot warn"></span><div class="node-label"><b>${esc(f.evidence)}</b><span class="node-sub">${esc(f.file)}</span><div class="tags">${chip(f.kind,'warn')}</div></div></div>`:'');
 }
 $('content').innerHTML=`<div class="search-wrap"><input class="search" id="q" placeholder="筛选…" value="${esc(query)}"></div>`+h;
 $('q').oninput=e=>{query=e.target.value.toLowerCase();const p=e.target.selectionStart;render();$('q').focus();$('q').setSelectionRange(p,p)};
 document.querySelectorAll('.row').forEach(r=>r.onclick=()=>{document.querySelectorAll('.row').forEach(x=>x.classList.remove('selected'));r.classList.add('selected');detail(r.dataset.k,+r.dataset.i)});
 if(!document.querySelector('.row.selected'))home();}
function kv(o){return `<dl class="kv">${Object.entries(o).filter(([k,v])=>v!=null&&v!=='').map(([k,v])=>`<dt>${esc(k)}</dt><dd>${v}</dd>`).join('')}</dl>`}
function home(){$('detail').innerHTML=`<div class="eyebrow">项目</div><h2>${esc(S.project)}</h2><p class="description">${esc(S.one_line)}</p>${kv({'结论':(S.claims||[]).length,'实验':(S.experiments||[]).length,'阶段':(S.phases||[]).length,'文件':Number(D.stats.files).toLocaleString(),'来源':`<code class="p">${esc(D.root)}</code>`})}${S._check_summary?`<div class="detail-section"><h3>证据核验（trace verify-map）</h3>${kv(Object.fromEntries(Object.entries(S._check_summary).map(([k,v])=>[ (NC[k]||[k])[0], v])))}</div>`:''}<div class="detail-section"><div class="note">由 agent 阅读作者的报告整理成论文语义；每个“文件:行号”和数字都由 LabWeft trace 在项目里实际核对（✓ = 引用处确有此数或可由该处表格复算）。</div></div>`}
function detail(k,i){let h='';
 if(k==='claim'){const c=S.claims[i];h=`<div class="eyebrow">结论 ${esc(c.id)}</div><h2>${esc(c.statement)}</h2>${kv({'状态':chip(c.status,ST[c.status]==='ok'?'':(ST[c.status]||''))})}`;
  if((c.numbers||[]).length)h+=`<div class="detail-section"><h3>关键数字</h3><table class="cells"><tbody>${c.numbers.map(n=>`<tr><td><b>${esc(n.value)}</b> ${nc(n._check)}<br><span class="muted">${esc(n.meaning)}</span><br><code class="p">${esc(n.source)}</code></td></tr>`).join('')}</tbody></table></div>`;
  if(c.caveats)h+=`<div class="detail-section"><h3>限制</h3><div class="note">${esc(c.caveats)}</div></div>`;
  const ex=(S.experiments||[]).filter(e=>(e.supports||[]).includes(c.id));if(ex.length)h+=`<div class="detail-section"><h3>支撑实验</h3><ul>${ex.map(e=>`<li>${esc(e.id)} · ${esc(e.question)}</li>`).join('')}</ul></div>`;h+=ev(c.evidence);
 } else if(k==='exp'){const e=S.experiments[i],d=e.design||{};h=`<div class="eyebrow">${esc(e.type)} · ${esc(e.id)}</div><h2>${esc(e.question)}</h2>${kv({'状态':chip(e.status),'对比':(d.compared||[]).map(x=>chip(x)).join(''),'固定':(d.fixed||[]).map(x=>chip(x)).join(''),'重复':esc(d.seeds),'指标':esc(d.metric),'支撑结论':(e.supports||[]).map(x=>chip(x)).join('')})}`;
  if((e.results||[]).length)h+=`<div class="detail-section"><h3>结果</h3>${bars(e.results)}<table class="cells"><thead><tr><th>条件</th><th>结果</th></tr></thead><tbody>${e.results.map(r=>`<tr><td>${esc(r.condition)}${r.note?`<br><span class="muted">${esc(r.note)}</span>`:''}</td><td class="n">${esc(r.value)}${r.sd!=null?' ± '+esc(r.sd):''} ${nc(r._check)}<br><span class="muted">${esc(r.n||'')}</span></td></tr>`).join('')}</tbody></table></div>`;
  h+=`<div class="detail-section"><h3>结论</h3><div class="note">${esc(e.finding)}</div></div>`+ev(e.evidence);
 } else if(k==='phase'){const p=S.phases[i];h=`<div class="eyebrow">${esc(p.period)}</div><h2>${esc(p.title)}</h2><p class="description">${esc(p.summary)}</p>`+ev(p.evidence);
 } else if(k==='inv'){const x=S.invalidated[i];h=`<div class="eyebrow">作废与取代</div><h2>${esc(x.what)}</h2>${kv({'原因':esc(x.why),'替代':esc(x.replaced_by)})}`+ev(x.evidence);
 } else if(k==='open'){const x=S.open_questions[i];h=`<div class="eyebrow">待解决</div><h2>${esc(x.question)}</h2>`+ev(x.evidence);
 } else if(k==='comp'){const c=S.method.components[i];h=`<div class="eyebrow">方法组件</div><h2>${esc(c.name)}</h2><p class="description">${esc(c.role)}</p>`;
 } else if(k==='read'){const r=S.reading_order[i];h=`<div class="eyebrow">建议阅读</div><h2>${esc(r.path.split('/').pop())}</h2><p class="description"><code class="p">${esc(r.path)}</code></p><div class="note">${esc(r.why)}</div>`;
 } else if(k==='term'){const g=S.glossary[i];h=`<div class="eyebrow">术语</div><h2>${esc(g.term)}</h2><p class="description">${esc(g.meaning)}</p>`;
 } else if(k==='finding'){const f=D.findings[i];h=`<div class="eyebrow">审计线索 · ${esc(f.kind)}</div><h2>${esc(f.evidence)}</h2><ul>${f.files.map(x=>`<li><code class="p">${esc(x)}</code></li>`).join('')}</ul><div class="note">打开文件核实后再下结论。</div>`;}
 $('detail').innerHTML=h;}
document.querySelectorAll('#nav button').forEach(b=>b.onclick=()=>{view=b.dataset.view;query='';render()});
stats();const hp=new URLSearchParams(location.hash.slice(1));if(hp.get('view')&&VIEWS[hp.get('view')])view=hp.get('view');render();
if(hp.get('sel')){const r=document.querySelectorAll('.row')[+hp.get('sel')];if(r)r.click();}
"""


def render_semantic(sem: dict, data: dict, out: Path, siblings=None) -> Path:
    css = (STATIC / "app.css").read_text(encoding="utf-8") + EXTRA_CSS
    sw = ""
    if siblings:
        sw = ('<div class="project-switcher"><strong>切换项目</strong><div>' + " ".join(
            f'<a href="{html.escape(href)}" class="{"current" if n == data["name"] else ""}">{html.escape(n)}</a>' for n, href in siblings)
              + "</div></div>")
    nav = "".join(f'<button data-view="{v}"{" class=active" if v == "summary" else ""}><span>{i}</span><span>{t}</span></button>'
                  for v, i, t in [("summary", "⌘", "研究概要"), ("claims", "✓", "结论"), ("experiments", "▤", "实验"),
                                  ("timeline", "↺", "研究历程"), ("invalid", "◇", "作废与取代"), ("open", "?", "待解决"),
                                  ("audit", "△", "审计线索")])
    j = lambda x: json.dumps(x, ensure_ascii=False).replace("</", "<\\/")
    doc = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>LabWeft · {html.escape(data['name'])} 研究地图</title><style>{css}</style></head><body>
<header class="topbar"><div class="brand">{BRAND}<div>LabWeft<small>研究语义地图 · 只读</small></div></div>
<div class="topright"><span class="pill">论文语义 · 证据可追溯</span><span class="muted">{html.escape(data['generated'])}</span></div></header>
{sw}<div class="shell"><aside class="sidebar"><div class="eyebrow">项目</div><div class="project-name">{html.escape(data['name'])}</div>
<nav id="nav">{nav}</nav><div class="sidebar-note"><span class="status-dot"></span> 按研究问题而非文件夹组织<p>结论 → 支撑实验 → 结果数字 → 原始证据，一路可点开。</p></div>
<div class="sidebar-foot"><span>{html.escape(data['root'])}</span></div></aside>
<main><section class="heading"><div><div class="eyebrow">从文件到研究</div><h1 id="page-title"></h1><p id="page-subtitle"></p></div></section>
<section id="stats" class="stats"></section><div class="workspace-body"><section id="content" class="content"></section><aside id="detail" class="detail"></aside></div>
<footer><span>LabWeft · 只读生成，未改动项目文件</span><span>数字均附证据路径；审计线索是待核实的疑点</span></footer></main></div>
<script id="sem" type="application/json">{j(sem)}</script><script id="data" type="application/json">{j(data)}</script><script>{SEM_JS}</script></body></html>"""
    out = Path(out)
    out.write_text(doc, encoding="utf-8")
    return out
