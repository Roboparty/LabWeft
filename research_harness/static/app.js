/* LabWeft: framework-free, no CDN, no model requests, no telemetry. */
(() => {
'use strict';
const $ = id => document.getElementById(id);
const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pretty = x => x === null || x === undefined ? '待核实' : typeof x === 'object' ? JSON.stringify(x) : String(x);
const canonical = x => Array.isArray(x) ? `[${x.map(canonical).join(',')}]` : x && typeof x==='object' ? `{${Object.keys(x).sort().map(k=>`${JSON.stringify(k)}:${canonical(x[k])}`).join(',')}}` : JSON.stringify(x);
const label = {module:'研究模块',question:'研究问题',cell:'实验条件 / Cell',run:'运行 / Run',evaluation:'评估',claim:'研究结论',decision:'历史决策',artifact:'产物'};
const statusText = {recorded:'已记录',completed:'已完成',needs_review:'待核实',provisional:'暂时判断',accepted:'已确认',archived:'已归档',planned:'计划中'};
let data, view='map', selected=null, layout='tree', filter='', cellSelection=new Set(), metric='success_rate', differentOnly=false;
let expanded = new Set(), token='', savedKey='', sourcePage=0;
const snap = $('snapshot-data');
try { token = new URLSearchParams(location.search).get('token') || sessionStorage.getItem('rh-token') || ''; if(token)sessionStorage.setItem('rh-token',token); if(location.search.includes('token='))history.replaceState({},'',location.pathname); } catch (_) {}
function badge(n) { const cls=n.status==='needs_review'?'review':n.status==='provisional'?'provisional':''; return `<span class="badge ${cls}">${esc(statusText[n.status]||n.status||'已记录')}</span>`; }
function storageWrite() { try { localStorage.setItem(savedKey,JSON.stringify({expanded:[...expanded],selected,layout})); } catch (_) {} }
function toast(msg) { $('toast').textContent=msg;$('toast').hidden=false;setTimeout(()=>$('toast').hidden=true,3300); }
async function api(path) {const response=await fetch(path,{headers:{'X-Research-Token':token}});if(!response.ok)throw new Error(await response.text());return response;}
async function load() {
 try {
  data = snap ? JSON.parse(snap.textContent) : await (await api('/api/state')).json();
  savedKey='rh-view-'+data.project.id;
  expanded=new Set(Object.values(data.nodes).filter(n=>n.kind==='module'||n.id==='question-history').map(n=>n.id));
  try { const old=JSON.parse(localStorage.getItem(savedKey)||'null');if(old){expanded=new Set(old.expanded||[]);selected=old.selected;layout=old.layout||'tree';} else { expanded=new Set(Object.values(data.nodes).filter(n=>n.kind==='module'||n.id==='question-history').map(n=>n.id)); } }catch(_){}
  if(!selected || !data.nodes[selected])selected=Object.values(data.nodes).find(n=>n.kind==='decision')?.id || Object.values(data.nodes)[0]?.id;
  if(!cellSelection.size)Object.values(data.nodes).filter(n=>n.kind==='cell').forEach(n=>cellSelection.add(n.id));
  $('project-name').textContent=data.project.name;
  $('synthetic').hidden=!data.project.synthetic;
  $('mode').textContent=snap?'OFFLINE SNAPSHOT':'LOCAL · READ ONLY';
  $('revision').textContent='revision '+data.revision;
  $('footer-state').textContent=snap?'私有静态快照 · 不自动更新':'通过 CLI 更新后刷新即可';
  $('source-count').textContent=Object.values(data.files).filter(f=>!f.missing).length+' 个来源文件';
  const kinds=Object.values(data.nodes).filter(n=>n.status!=='archived');
  $('stats').innerHTML=[['研究问题',kinds.filter(n=>n.kind==='question').length,'◇'],['实验条件',kinds.filter(n=>n.kind==='cell').length,'▤'],['已记录运行',kinds.filter(n=>n.kind==='run').length,'◉'],['受保护的判断',kinds.filter(n=>n.protected&&['claim','decision'].includes(n.kind)).length,'✓']].map(([t,n,icon])=>`<div class="stat"><div><div class="stat-number">${n}</div><div class="stat-label">${t}</div></div><div class="stat-icon">${icon}</div></div>`).join('');
  const notices=[];
  if(data.scan?.source_aliases?.length)notices.push(`已配置来源：${data.scan.source_aliases.join('、')}。扫描完成仅表示这些来源已读取，不代表整个科研项目证据齐全。`);
  if(data.scan && data.scan.complete===false)notices.push('来源扫描未完成，当前视图是部分记录；未见文件不会被当作已删除。');
  if(data.drift?.length)notices.push(`${new Set(data.drift.map(d=>d.node_id)).size} 个对象引用的来源发生变化或缺失。旧证据保留；请检查新工作的适用范围。`);
  $('notice').hidden=!notices.length;$('notice').textContent=notices.join(' ');
  render();
 } catch(e) { $('content').innerHTML=`<div class="error">无法读取项目：${esc(e.message)}<p>实时模式请使用 <code>labweft serve</code> 输出的完整私有地址。离线 HTML 不需要服务。</p></div>`; }
}
function sortNodes(a,b){return (a.attrs?.order??100)-(b.attrs?.order??100)||a.label.localeCompare(b.label,'zh-CN',{numeric:true});}
function children(id) {return Object.values(data.nodes).filter(n=>n.parent_id===id && n.status!=='archived').sort(sortNodes);}
function select(id) { selected=id; storageWrite();renderDetail(); if(view==='map')renderMap(); }
function setView(v) {view=v;filter='';sourcePage=0;render();}
function render() {
 document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('active',b.dataset.view===view));
 const headings={map:['你的研究，不再从头解释。','按问题展开，追到每一次运行，继承已经确认的判断。'],compare:['差异在哪里，证据就在哪里。','先比较实际条件，再讨论结果；不把未知当成相同。'],decisions:['已经解决的问题，不必重新开始。','结论、适用范围、重新检查条件，一起保存。'],sources:['每一个判断，都有来源。','小型文本保存不可变快照；大型产物只登记位置，不冒充备份。'],history:['记住每一次修订的原因。','版本记录可以追溯。刷新视图不会重新调用模型。']};
 $('page-title').textContent=headings[view][0];$('page-subtitle').textContent=headings[view][1];
 ({map:renderMap,compare:renderCompare,decisions:renderDecisions,sources:renderSources,history:renderHistory}[view])();
 renderDetail();
}
function hasMatch(n) {if(!filter)return true;return (n.label+' '+n.description+' '+n.id).toLowerCase().includes(filter.toLowerCase())||children(n.id).some(hasMatch);}
function treeNode(n) {
 const kids=children(n.id).filter(k=>!['claim','decision'].includes(k.kind)).filter(hasMatch), open=expanded.has(n.id)||!!filter;
 const sub = n.kind==='cell'?Object.entries(n.attrs?.config||{}).filter(([k])=>['history_length','prediction_weight','hardware'].includes(k)).map(([k,v])=>`${k}=${pretty(v)}`).join(' · '):'';
 return `<li class="node-wrap"><div class="node-card ${selected===n.id?'selected':''}" data-select="${esc(n.id)}" role="button" tabindex="0"><button class="node-toggle" data-toggle="${esc(n.id)}" aria-label="展开或折叠 ${esc(n.label)}" aria-expanded="${open}">${kids.length?(open?'⌄':'›'):'·'}</button><span class="node-dot ${esc(n.kind)}"></span><span class="node-label">${esc(n.label)}${sub?`<small class="node-sub">${esc(sub)}</small>`:''}</span>${kids.length?`<span class="node-count">${kids.length} 个子项</span>`:''}${badge(n)}</div>${kids.length&&open?`<ul class="tree-list">${kids.map(treeNode).join('')}</ul>`:''}</li>`;
}
function renderMap() {
 $('content').innerHTML=`<div class="panel-head"><div><h2>研究地图</h2><small>PROJECT → QUESTION → CELL → RUN → EVIDENCE</small></div><div class="panel-tools"><div class="view-switch"><button data-layout="tree" class="${layout==='tree'?'active':''}">层级树</button><button data-layout="lineage" class="${layout==='lineage'?'active':''}">关系视图</button></div><button id="expand-all">展开</button><button id="collapse-all">收起</button></div></div><div class="search-wrap"><input class="search" id="map-search" placeholder="搜索模块、问题或实验…" value="${esc(filter)}" aria-label="搜索研究地图"></div><div id="map-body"></div><div class="tree-hint">箭头展开分支，点击卡片查看详情。关系线仅表示已记录的关系，不证明因果。</div>`;
 $('map-search').addEventListener('input',e=>{filter=e.target.value;drawMapBody();});
 $('expand-all').onclick=()=>{Object.keys(data.nodes).forEach(id=>expanded.add(id));storageWrite();drawMapBody();};
 $('collapse-all').onclick=()=>{expanded.clear();storageWrite();drawMapBody();};
 document.querySelectorAll('[data-layout]').forEach(b=>b.onclick=()=>{layout=b.dataset.layout;storageWrite();renderMap();});
 drawMapBody();
}
function drawMapBody() {
 const rootNodes=children(data.project.id).filter(n=>!['claim','decision'].includes(n.kind)).filter(hasMatch);
 if(layout==='tree')$('map-body').innerHTML=`<div class="tree"><ul class="tree-list">${rootNodes.map(treeNode).join('')||'<div class="empty">还没有研究关系。先运行 sync，再由现有 agent 读取证据并归类。扫描器不会凭目录名编造研究问题。</div>'}</ul></div>`;
 else {
  const groups=[['module','模块 / MODULES'],['question','问题 / QUESTIONS'],['cell','条件 / CELLS']];
  $('map-body').innerHTML=`<div class="lineage-board" id="lineage-board"><svg id="lineage-svg" class="lineage-svg" aria-hidden="true"></svg><div class="lineage-grid">${groups.map(([kind,title])=>`<div><div class="lane-label">${title}</div>${Object.values(data.nodes).filter(n=>n.kind===kind&&n.status!=='archived'&&hasMatch(n)).sort(sortNodes).map(n=>`<div class="lane-node ${n.id===selected?'selected':''}" id="lane-${esc(n.id)}" data-select="${esc(n.id)}" tabindex="0" role="button">${esc(n.label)}<small>${esc(statusText[n.status]||n.status)} · ${children(n.id).length} 个子项</small></div>`).join('')}</div>`).join('')}</div></div>`;
  requestAnimationFrame(drawLines);
 }
 bindNodeButtons($('map-body'));
}
function drawLines(){
 const board=$('lineage-board'),svg=$('lineage-svg');if(!board||!svg)return;
 const rect=board.getBoundingClientRect();svg.setAttribute('width',board.scrollWidth);svg.setAttribute('height',board.scrollHeight);
 const links=Object.values(data.nodes).map(n=>({source:n.parent_id,target:n.id,related:false})).concat(Object.values(data.edges).map(e=>({...e,related:true})));
 svg.innerHTML=links.map(e=>{const a=$('lane-'+e.source),b=$('lane-'+e.target);if(!a||!b)return '';const ar=a.getBoundingClientRect(),br=b.getBoundingClientRect();const x1=ar.right-rect.left+board.scrollLeft,y1=ar.top+ar.height/2-rect.top+board.scrollTop,x2=br.left-rect.left+board.scrollLeft,y2=br.top+br.height/2-rect.top+board.scrollTop;return `<path d="M${x1},${y1} C${x1+24},${y1} ${x2-24},${y2} ${x2},${y2}" fill="none" stroke="${e.related?'#b5bfae':'#ccdacb'}" stroke-width="1.3" ${e.related?'stroke-dasharray="4 4"':''}/>`;}).join('');
}
function bindNodeButtons(root){root.querySelectorAll('[data-select]').forEach(b=>{b.onclick=()=>select(b.dataset.select);b.onkeydown=e=>{if(e.key==='Enter')select(b.dataset.select);};});root.querySelectorAll('[data-toggle]').forEach(b=>b.onclick=e=>{e.stopPropagation();expanded.has(b.dataset.toggle)?expanded.delete(b.dataset.toggle):expanded.add(b.dataset.toggle);storageWrite();drawMapBody();});}
function kv(obj){return `<dl class="kv">${Object.entries(obj).map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(pretty(v))}</dd>`).join('')}</dl>`;}
function renderDetail(){
 const n=data.nodes[selected];
 if(!n){$('detail').innerHTML='<div class="eyebrow">INSPECTOR</div><h2>选中一个研究对象</h2><p class="description">查看它的研究目的、实际条件、证据来源和适用范围。</p>';return;}
 const refs=n.evidence||[],related=Object.values(data.edges).filter(e=>e.source===n.id||e.target===n.id),attrs=n.attrs||{};
 let html=`<div class="eyebrow">${esc(label[n.kind]||n.kind)} · INSPECTOR</div><h2>${esc(n.label)}</h2>${badge(n)} ${n.protected?'<span class="badge">人工保护</span>':''}<p class="description">${esc(n.description||'尚未记录解释。请先核对证据，不要从名称猜测。')}</p>`;
 if(attrs.config)html+=`<div class="detail-section"><h3>实际记录的条件</h3>${kv(attrs.config)}</div>`;
 if(attrs.metrics)html+=`<div class="detail-section"><h3>结果 / RECORDED METRICS</h3>${kv(attrs.metrics)}<p class="description">${esc(attrs.metric_selection||attrs.selection||'')}</p></div>`;
 if(n.kind==='run')html+=`<div class="detail-section"><h3>运行身份</h3>${kv({seed:attrs.seed,code_revision:attrs.code_revision,eval_protocol:attrs.eval_protocol,identity:attrs.identity_basis})}</div>`;
 if(attrs.scope)html+=`<div class="detail-section"><h3>适用范围 / SCOPE</h3>${kv(attrs.scope.required_context||attrs.scope)}${attrs.scope.covered_values?'<h3>已覆盖的因素取值</h3>'+kv(attrs.scope.covered_values):''}</div>`;
 if(attrs.reopen_if)html+=`<div class="detail-section"><h3>何时重新检查</h3><div class="note">${esc(attrs.reopen_if)}</div></div>`;
 if(n.confirmation)html+=`<div class="detail-section"><h3>确认记录</h3><div class="note">${esc(n.confirmation.note)}<br><small>${esc(n.confirmation.reviewer)} · ${esc(n.confirmation.at)}</small></div></div>`;
 if(attrs.next_action)html+=`<div class="detail-section"><h3>剩余问题</h3><div class="note">${esc(attrs.next_action)}</div></div>`;
 html+=`<div class="detail-section"><h3>来源 / EVIDENCE · ${refs.length}</h3>${refs.map(r=>{const f=data.files[r.file_id]||{};return `<button class="evidence-btn" data-sha="${esc(r.sha256)}" data-title="${esc((f.source||'')+'/'+(f.path||r.file_id))}">${esc(f.path||r.file_id)}<small>${esc(r.locator)} · ${esc(r.sha256.slice(0,12))}</small></button>`;}).join('')||'<div class="muted" style="font-size:11px;line-height:1.8">此节点没有直接文件证据。查看关联对象；没有来源的解释不能当作事实。</div>'}</div>`;
 if(n.evidence_ids?.length)html+=`<div class="detail-section"><h3>关联证据对象</h3>${n.evidence_ids.map(id=>`<button class="relation-btn" data-jump="${esc(id)}">${esc(data.nodes[id]?.label||id)} ↗</button>`).join('')}</div>`;
 if(related.length)html+=`<div class="detail-section"><h3>关系 / RELATIONS</h3>${related.map(e=>{const id=e.source===n.id?e.target:e.source;return `<button class="relation-btn" data-jump="${esc(id)}">${esc(e.relation)} · ${esc(data.nodes[id]?.label||id)}</button>`;}).join('')}</div>`;
 html+=`<div class="detail-section"><small class="muted" style="font-size:9px;overflow-wrap:anywhere">${esc(n.id)}</small></div>`;
 $('detail').innerHTML=html;
 $('detail').querySelectorAll('[data-sha]').forEach(b=>b.onclick=()=>showEvidence(b.dataset.sha,b.dataset.title));
 $('detail').querySelectorAll('[data-jump]').forEach(b=>b.onclick=()=>select(b.dataset.jump));
}
function calculateRows(){
 const cells=Object.values(data.nodes).filter(n=>n.kind==='cell'&&cellSelection.has(n.id)).sort(sortNodes);
 const dirty=new Set((data.drift||[]).map(d=>d.node_id));
 const dirtyRuns=new Set(Object.values(data.nodes).filter(n=>n.kind==='run'&&dirty.has(n.id)).map(n=>n.id));
 Object.values(data.nodes).filter(n=>n.kind==='evaluation'&&n.status!=='archived'&&dirty.has(n.id)).forEach(n=>dirtyRuns.add(n.parent_id));
 return cells.map(c=>{
 const runs=Object.values(data.nodes).filter(n=>n.kind==='run'&&n.parent_id===c.id),complete=runs.filter(n=>n.status==='completed');
  const cellConfig=c.attrs?.config,invalidCellConfig=cellConfig!==undefined&&(cellConfig===null||typeof cellConfig!=='object'||Array.isArray(cellConfig));
  const expected=invalidCellConfig?{}:cellConfig||{};
  const invalidRunConfig=complete.some(r=>r.attrs.config!==undefined&&(r.attrs.config===null||typeof r.attrs.config!=='object'||Array.isArray(r.attrs.config)));
  const cellConfigConflict=complete.some(r=>{const cfg=r.attrs.config??{};return typeof cfg==='object'&&!Array.isArray(cfg)&&Object.entries(expected).some(([k,v])=>!Object.hasOwn(cfg,k)||canonical(cfg[k])!==canonical(v));});
  const counts={};complete.forEach(r=>{if(r.attrs.seed!==null&&r.attrs.seed!==undefined){const k=JSON.stringify(r.attrs.seed);counts[k]=(counts[k]||0)+1;}});
  const protocols=new Set(complete.map(r=>JSON.stringify(r.attrs.eval_protocol??null)));
  const protocolOK=protocols.size===1&&!protocols.has('null');
  const conditions=new Set(complete.map(r=>canonical(Object.fromEntries(Object.entries(r.attrs.config||{}).filter(([k])=>!['seed','training.seed','run_id'].includes(k))))));
  const versions=new Set(complete.filter(r=>r.attrs.code_revision).map(r=>r.attrs.code_revision));
  const eligible=protocolOK&&conditions.size<=1&&versions.size<=1&&!invalidCellConfig&&!invalidRunConfig&&!cellConfigConflict?complete.filter(r=>r.attrs.seed!==null&&r.attrs.seed!==undefined&&counts[JSON.stringify(r.attrs.seed)]===1&&!dirtyRuns.has(r.id)):[];
  const used=eligible.filter(r=>typeof r.attrs.metrics?.[metric]==='number'&&Number.isFinite(r.attrs.metrics[metric]));
  const vals=used.map(r=>r.attrs.metrics[metric]),mean=vals.length?vals.reduce((a,b)=>a+b,0)/vals.length:null,sd=vals.length>1?Math.sqrt(vals.reduce((a,b)=>a+(b-mean)**2,0)/(vals.length-1)):null;
  let warnings=[];if(invalidCellConfig||invalidRunConfig)warnings.push('Cell 或 run 配置不是对象，未汇总');if(cellConfigConflict)warnings.push('Run 与所属 Cell 的记录配置冲突，未汇总');if(conditions.size>1||versions.size>1)warnings.push('条件或代码版本不同，未汇总');if(!protocolOK&&complete.length)warnings.push('协议未知或不一致，未汇总');if(Object.values(counts).some(n=>n>1))warnings.push('重复 seed 未纳入');if(complete.some(r=>dirtyRuns.has(r.id)))warnings.push('来源已变化或缺失，相关 run 未纳入当前汇总；历史快照仍可查看');if(complete.length!==runs.length)warnings.push('未完成/未确认运行未纳入');if(complete.some(r=>!r.attrs.code_revision))warnings.push('历史代码身份不完整');
  return {cell:c,runs,used,mean,sd,n:vals.length,warnings};
 });
}
function renderCompare(){
 const cells=Object.values(data.nodes).filter(n=>n.kind==='cell').sort(sortNodes),metricKeys=[...new Set(Object.values(data.nodes).filter(n=>n.kind==='run').flatMap(n=>Object.keys(n.attrs.metrics||{})))].sort();
 if(!metricKeys.includes(metric)&&metricKeys.length)metric=metricKeys[0];
 const rows=calculateRows(),keys=[...new Set(rows.flatMap(r=>Object.keys(r.cell.attrs.config||{})))].sort();
 const diff=k=>new Set(rows.map(r=>Object.hasOwn(r.cell.attrs.config||{},k)?JSON.stringify(r.cell.attrs.config[k]):'<MISSING>')).size>1;
 const stat=v=>v===null?'—':v.toFixed(4);
 let html=`<div class="panel-head"><div><h2>Cell 对比矩阵</h2><small>相同字段可折叠 · 未知条件不默认相同</small></div></div><div class="cell-picker">${cells.map(c=>`<label><input type="checkbox" data-cell="${esc(c.id)}" ${cellSelection.has(c.id)?'checked':''}>${esc(c.label)}</label>`).join('')}</div><div class="matrix-options"><label><input type="checkbox" id="diff-only" ${differentOnly?'checked':''}> 只看不同配置</label><label>指标 <select id="metric-select">${metricKeys.map(k=>`<option ${k===metric?'selected':''}>${esc(k)}</option>`).join('')}</select></label></div>`;
 if(rows.length)html+=`<div class="table-wrap"><table class="matrix"><thead><tr><th>模块 / 执行条件</th>${rows.map(r=>`<th><button class="linkbutton" data-cell-detail="${esc(r.cell.id)}">${esc(r.cell.label)} ↗</button></th>`).join('')}</tr></thead><tbody>${keys.filter(k=>!differentOnly||diff(k)).map(k=>`<tr class="${diff(k)?'diff':''}"><td>${esc(k)}</td>${rows.map(r=>`<td>${Object.hasOwn(r.cell.attrs.config||{},k)?esc(pretty(r.cell.attrs.config[k])):'<span class="unknown">待核实</span>'}</td>`).join('')}</tr>`).join('')}<tr><td>已记录运行数</td>${rows.map(r=>`<td>${r.runs.length}</td>`).join('')}</tr><tr><td>纳入的独立 seed</td>${rows.map(r=>`<td>${r.n}</td>`).join('')}</tr><tr><td>${esc(metric)}<span class="matrix-sub">均值 ± 样本 SD</span></td>${rows.map(r=>`<td><strong>${stat(r.mean)}</strong><span class="matrix-sub">SD ${stat(r.sd)}</span>${r.used.map(n=>`<button class="linkbutton matrix-sub" data-run="${esc(n.id)}">seed ${esc(n.attrs.seed)} → ${esc(pretty(n.attrs.metrics[metric]))}</button>`).join('')}</td>`).join('')}</tr><tr><td>核对提示</td>${rows.map(r=>`<td>${r.warnings.map(esc).join('<br>')||'仅描述性汇总；不自动判断优劣。'}</td>`).join('')}</tr></tbody></table></div>`;else html+='<div class="empty">选择至少一个 cell。</div>';
 const controls=['dataset_version','eval_protocol','train_steps'];
 const controlWarnings=controls.filter(k=>rows.some(r=>r.cell.attrs.config?.[k]===undefined)||diff(k));
 html+=`<div class="matrix-notes">统计单元是训练 seed，不是评估 episode。单个 seed 不给出跨 seed 标准差。${controlWarnings.length?`<br>以下条件的可比性尚未统一：${controlWarnings.map(esc).join('、')}。`:''}<br>配置相同不能证明实现相同；最终科学解释由 agent 和研究者核对证据。</div>`;
 $('content').innerHTML=html;
 document.querySelectorAll('[data-cell]').forEach(b=>b.onchange=()=>{b.checked?cellSelection.add(b.dataset.cell):cellSelection.delete(b.dataset.cell);renderCompare();});
 $('diff-only').onchange=e=>{differentOnly=e.target.checked;renderCompare();};$('metric-select').onchange=e=>{metric=e.target.value;renderCompare();};
 document.querySelectorAll('[data-run]').forEach(b=>b.onclick=()=>select(b.dataset.run));document.querySelectorAll('[data-cell-detail]').forEach(b=>b.onclick=()=>select(b.dataset.cellDetail));
}
function renderDecisions(){
 const nodes=Object.values(data.nodes).filter(n=>['decision','claim'].includes(n.kind));
 $('content').innerHTML=`<div class="panel-head"><div><h2>结论与历史决策</h2><small>保留已解决的问题，也保留重新审视的条件</small></div></div><div class="decision-list">${nodes.map(n=>`<article class="decision" data-select="${esc(n.id)}" tabindex="0" role="button">${badge(n)} ${n.protected?'<span class="badge">人工保护</span>':''}<h3>${esc(n.label)}</h3><p>${esc(n.description)}</p><div class="decision-meta">${esc(n.kind==='decision'?'DECISION':'CLAIM')} · ${n.evidence?.length||0} 个直接来源 · ${n.evidence_ids?.length||0} 个关联对象 ↗</div></article>`).join('')||'<div class="empty">还没有带来源的结论。工具不会从实验名称自动编造它。</div>'}</div>`;bindNodeButtons($('content'));
}
function renderSources(){
 $('content').innerHTML=`<div class="panel-head"><div><h2>证据来源</h2><small>内容快照与位置索引分开标识</small></div></div><div class="search-wrap"><input class="search" id="source-search" placeholder="按路径或来源别名搜索…" value="${esc(filter)}"></div><div class="source-list" id="source-list"></div>`;
 $('source-search').oninput=e=>{filter=e.target.value;sourcePage=0;drawSources();};drawSources();
}
function drawSources(){const files=Object.values(data.files).filter(f=>(f.source+'/'+f.path).toLowerCase().includes(filter.toLowerCase())).sort((a,b)=>a.path.localeCompare(b.path)),page=files.slice(sourcePage*40,(sourcePage+1)*40);$('source-list').innerHTML=page.map(f=>`<div class="source"><div class="source-name">${esc(f.path)}<small>${esc(f.source)} · ${(f.size/1024).toFixed(1)} KB · ${f.missing?'来源缺失':f.sha256?'已保存文本快照':'仅登记位置 / 非备份'}</small></div><button data-source-sha="${esc(f.sha256||'')}" data-title="${esc(f.path)}" ${f.sha256?'':'disabled'}>${f.sha256?'查看':'索引'}</button></div>`).join('')+`<div class="panel-tools" style="margin-top:17px"><button id="prev-source" ${sourcePage?'':'disabled'}>上一页</button><span class="muted" style="font-size:11px">${sourcePage*40+1}–${Math.min((sourcePage+1)*40,files.length)} / ${files.length}</span><button id="next-source" ${(sourcePage+1)*40<files.length?'':'disabled'}>下一页</button></div>`;$('prev-source').onclick=()=>{sourcePage--;drawSources();};$('next-source').onclick=()=>{sourcePage++;drawSources();};document.querySelectorAll('[data-source-sha]').forEach(b=>b.onclick=()=>showEvidence(b.dataset.sourceSha,b.dataset.title));}
function renderHistory(){ $('content').innerHTML=`<div class="panel-head"><div><h2>可追溯的更新</h2><small>每次写入都有版本、执行者和原因</small></div></div><div class="history">${[...data.history].reverse().map(e=>`<div class="history-item"><b>REVISION ${e.revision}</b>${esc(e.reason)}<small>${esc(e.actor)} · ${esc(e.at)}</small></div>`).join('')||'<div class="empty">工作空间刚建立，还没有更新。</div>'}</div>`; }
async function showEvidence(sha,title){$('modal').hidden=false;$('modal-title').textContent=title||'证据快照';$('modal-subtitle').textContent='SHA-256 '+sha;$('evidence-content').textContent='读取中…';try{let text;if(snap){text=data.evidence_texts?.[sha];if(text===undefined)throw new Error('此离线快照未包含原文。请在本地工作空间查看，或明确选择 --include-evidence 重新导出。');}else text=await(await api('/api/evidence?sha='+encodeURIComponent(sha))).text();$('evidence-content').textContent=text.split('\n').map((line,i)=>String(i+1).padStart(4,' ')+'  '+line).join('\n');}catch(e){$('evidence-content').textContent=e.message;}}
function download(name,text,type){const u=URL.createObjectURL(new Blob([text],{type})),a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);}
function init(){ $('nav').querySelectorAll('button').forEach(b=>b.onclick=()=>setView(b.dataset.view));$('refresh').onclick=()=>snap?toast('这是固定版本快照；请通过工具更新后重新导出。'):load();$('close-modal').onclick=()=>$('modal').hidden=true;$('modal').onclick=e=>{if(e.target===$('modal'))$('modal').hidden=true;};document.addEventListener('keydown',e=>{if(e.key==='Escape')$('modal').hidden=true;});$('copy-prompt').onclick=async()=>{const text=`使用 LabWeft 整理当前科研项目${data?'「'+data.project.name+'」':''}。先读已有记录，再增量检查代码与结果；核对 ablation 的目的、cell 差异、结果证据和历史决策，更新本地地图。不要启动实验、修改研究代码或上传数据。沿用已确认且仍适用的判断；不确定就保留缺口。`;try{await navigator.clipboard.writeText(text);toast('整理指令已复制，粘贴到你的现有 agent 对话。');}catch(_){$('modal').hidden=false;$('modal-title').textContent='复制到现有 agent 对话';$('modal-subtitle').textContent='不需要新开多个 agent';$('evidence-content').textContent=text;}};$('export-json').onclick=()=>{if(data){download('research-records-r'+data.revision+'.json',JSON.stringify(data,null,2),'application/json');toast('导出可能包含私有配置，分享前请检查。');}};window.addEventListener('resize',()=>{if(layout==='lineage'&&view==='map')drawLines();});load();}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
