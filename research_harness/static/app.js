/* LabWeft: framework-free, no CDN, no model requests, no telemetry. */
(() => {
'use strict';
const $ = id => document.getElementById(id);
const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let lang = 'zh';
try { lang = localStorage.getItem('labweft-language') === 'en' ? 'en' : 'zh'; } catch (_) {}
{const m=/lang=(zh|en)/.exec(location.hash);if(m)lang=m[1];}
const words = {
 zh: {brandTagline:'科研工作空间 · v0.1',workspace:'工作空间',loadingProject:'正在读取项目…',synthetic:'合成示例 · 非真实实验',navMap:'研究地图',navCompare:'Cell 对比',navDecisions:'结论与决策',navSources:'证据来源',navHistory:'更新时间线',oneWorkspace:'一个对话，一个工作空间。',sidebarNote:'使用你自己的 agent。浏览地图不需要调用模型。',copyPrompt:'复制整理指令 ↗',localNote:'本地记录 · 默认不上传',headingEyebrow:'从实验到证据',exportJson:'导出记录 JSON',footer:'研究记录与模型判断分开保存。扫描 ≠ 理解；图表 ≠ 科学证明。',evidenceSnapshot:'证据快照',close:'关闭 ×',refresh:'↻ 刷新',offline:'离线快照',localReadOnly:'本地 · 只读',revision:'版本',offlineFooter:'私有静态快照 · 不自动更新',liveFooter:'通过 CLI 更新后刷新即可',sourceFiles:'个来源文件',questions:'研究问题',cells:'实验条件',runs:'已记录运行',protectedDecisions:'受保护的判断',sourceConfigured:'已配置来源：',scanScope:'。扫描完成仅表示这些来源已读取，不代表整个科研项目证据齐全。',partialScan:'来源扫描未完成，当前视图是部分记录；未见文件不会被当作已删除。',driftNotice:'个对象引用的来源发生变化或缺失。旧证据保留；请检查新工作的适用范围。',loadError:'无法读取项目：',liveHelp:'实时模式请使用 labweft serve 输出的完整私有地址。离线 HTML 不需要服务。',unknown:'待核实',recorded:'已记录',completed:'记录为完成',needs_review:'待核实',provisional:'据来源整理',accepted:'人工已确认',archived:'历史归档',planned:'计划中',statusInfoTitle:'状态如何理解',statusInfo:'“据来源整理”表示已整理来源，尚未经过研究者确认；“记录为完成”仅表示来源记录运行完成，不代表结果被独立复现；“人工已确认”表示有人确认当前记录；“历史归档”保留旧版本，退出当前地图层级和数值汇总；历史结论、决策与来源仍可查看。',protected:'人工保护',module:'研究模块',question:'研究问题',cell:'实验条件 / Cell',run:'运行 / Run',evaluation:'评估',claim:'研究结论',decision:'历史决策',artifact:'产物',mapTitle:'你的研究，不再从头解释。',mapSubtitle:'按问题展开，追到每一次运行，继承已经确认的判断。',compareTitle:'差异在哪里，证据就在哪里。',compareSubtitle:'先比较实际条件，再讨论结果；不把未知当成相同。',decisionsTitle:'已经解决的问题，不必重新开始。',decisionsSubtitle:'结论、适用范围、重新检查条件，一起保存。',sourcesTitle:'每一个判断，都有来源。',sourcesSubtitle:'小型文本保存不可变快照；大型产物只登记位置，不冒充备份。',historyTitle:'记住每一次修订的原因。',historySubtitle:'版本记录可以追溯。刷新视图不会重新调用模型。',childItems:'个子项',expandToggle:'展开或折叠',mapEmpty:'还没有研究关系。先运行 sync，再由现有 agent 读取证据并归类。扫描器不会凭目录名编造研究问题。',mapPanel:'研究地图',tree:'层级树',relationsView:'关系视图',expand:'展开',collapse:'收起',mapSearch:'搜索模块、问题或实验…',mapHint:'箭头展开分支，点击卡片查看详情。关系线仅表示已记录的关系，不证明因果。',modules:'模块',inspector:'详情',selectObject:'选中一个研究对象',selectObjectHelp:'查看它的研究目的、实际条件、证据来源和适用范围。',noDescription:'尚未记录解释。请先核对证据，不要从名称猜测。',actualConditions:'实际记录的条件',results:'结果 / 已记录指标',runIdentity:'运行身份',scope:'适用范围',coveredValues:'已覆盖的因素取值',reopenIf:'何时重新检查',confirmation:'确认记录',nextAction:'剩余问题',sources:'来源',noDirectEvidence:'此节点没有直接文件证据。查看关联对象；没有来源的解释不能当作事实。',linkedEvidence:'关联证据对象',relations:'关系',comparePanel:'Cell 对比矩阵',compareHint:'相同字段可折叠 · 未知条件不默认相同',diffOnly:'只看不同配置',metric:'指标',conditions:'模块 / 执行条件',recordedRuns:'已记录运行数',includedSeeds:'纳入的独立 seed',meanSd:'均值 ± 样本 SD',reviewHints:'核对提示',noCells:'选择至少一个 cell。',descriptiveOnly:'仅描述性汇总；不自动判断优劣。',unitNote:'统计单元是训练 seed，不是评估 episode。单个 seed 不给出跨 seed 标准差。',comparability:'以下条件的可比性尚未统一：',implementationNote:'配置相同不能证明实现相同；最终科学解释由 agent 和研究者核对证据。',configInvalid:'Cell 或 run 配置不是对象，未汇总',configConflict:'Run 与所属 Cell 的记录配置冲突，未汇总',conditionConflict:'条件或代码版本不同，未汇总',protocolConflict:'协议未知或不一致，未汇总',duplicateSeed:'重复 seed 未纳入',driftExcluded:'来源已变化或缺失，相关 run 未纳入当前汇总；历史快照仍可查看',incompleteExcluded:'未完成/未确认运行未纳入',revisionMissing:'历史代码身份不完整',decisionsPanel:'结论与历史决策',decisionsHint:'保留已解决的问题，也保留重新审视的条件',directSources:'个直接来源',linkedObjects:'个关联对象',noDecisions:'还没有带来源的结论。工具不会从实验名称自动编造它。',sourcesPanel:'证据来源',sourcesHint:'内容快照与位置索引分开标识',sourcesSearch:'按路径或来源别名搜索…',missingSource:'来源缺失',savedSnapshot:'已保存文本快照',offlineTextOmitted:'离线未附原文',locationOnly:'仅登记位置 / 非备份',view:'查看',index:'索引',previous:'上一页',next:'下一页',noSources:'没有匹配的来源文件。',timelinePanel:'更新时间线',timelineHint:'查看每次写入的文件与研究模块变化；点击节点可跳转详情。',allChanges:'全部变化',fileChanges:'文件变化',nodeChanges:'研究模块变化',edgeChanges:'关系变化',allModules:'全部模块',changeAdded:'新增',changeUpdated:'更新',changeRemoved:'移除',changeUnknown:'变化',oldHistory:'此版本只记录原因，未保存逐项变化。',historyEmpty:'工作空间刚建立，还没有更新。',noMatchingHistory:'没有符合筛选条件的更新。',files:'文件',nodes:'节点',edges:'关系',unknownActor:'执行者未记录',unknownReason:'原因未记录',loading:'读取中…',snapshotOmitted:'此离线快照未包含原文。请在本地工作空间查看，或明确选择 --include-evidence 重新导出。',staticSnapshot:'这是固定版本快照；请通过工具更新后重新导出。',copied:'整理指令已复制，粘贴到你的现有 agent 对话。',copyToAgent:'复制到现有 agent 对话',noNewAgent:'不需要新开多个 agent',exportWarning:'导出可能包含私有配置，分享前请检查。',prompt:'使用 LabWeft 整理当前科研项目{project}。先读已有记录，再增量检查代码与结果；核对 ablation 的目的、cell 差异、结果证据和历史决策，更新本地地图。不要启动实验、修改研究代码或上传数据。沿用已确认且仍适用的判断；不确定就保留缺口。'},
 en: {brandTagline:'RESEARCH WORKSPACE · v0.1',workspace:'WORKSPACE',loadingProject:'Loading project…',synthetic:'Synthetic example · not a real experiment',navMap:'Research map',navCompare:'Cell comparison',navDecisions:'Claims & decisions',navSources:'Evidence sources',navHistory:'Update timeline',oneWorkspace:'One conversation. One workspace.',sidebarNote:'Use your own agent. Browsing the map does not call a model.',copyPrompt:'Copy organizing prompt ↗',localNote:'Local records · no upload by default',headingEyebrow:'FROM EXPERIMENTS TO EVIDENCE',exportJson:'Export records JSON',footer:'Research records and model judgments are stored separately. Scan ≠ understanding; chart ≠ scientific proof.',evidenceSnapshot:'Evidence snapshot',close:'Close ×',refresh:'↻ Refresh',offline:'OFFLINE SNAPSHOT',localReadOnly:'LOCAL · READ ONLY',revision:'revision',offlineFooter:'Private static snapshot · does not update automatically',liveFooter:'Refresh after updating through the CLI',sourceFiles:'source files',questions:'Research questions',cells:'Experimental cells',runs:'Recorded runs',protectedDecisions:'Protected judgments',sourceConfigured:'Configured sources: ',scanScope:'. A completed scan only means these sources were read; it does not establish complete project coverage.',partialScan:'Source scan is incomplete. This is a partial view; unseen files are not treated as deleted.',driftNotice:'objects reference changed or missing sources. Old evidence remains; review the scope of new work.',loadError:'Could not load project: ',liveHelp:'In live mode use the full private address from labweft serve. Offline HTML needs no server.',unknown:'Unverified',recorded:'Recorded',completed:'Reported complete',needs_review:'Needs review',provisional:'Source-based',accepted:'Human confirmed',archived:'Archived',planned:'Planned',statusInfoTitle:'Reading the statuses',statusInfo:'“Source-based” means organized from sources and not yet confirmed by the researcher. “Reported complete” means the source records a finished run; it is not independent replication. “Human confirmed” records a person’s confirmation. “Archived” retains older records outside the current map hierarchy and numeric summaries; historical claims, decisions, and sources remain available.',protected:'Human protected',module:'Research module',question:'Research question',cell:'Experimental cell',run:'Run',evaluation:'Evaluation',claim:'Research claim',decision:'Historical decision',artifact:'Artifact',mapTitle:'Your research, without starting from scratch.',mapSubtitle:'Follow each question to its runs and preserve confirmed judgments.',compareTitle:'Follow differences to the evidence.',compareSubtitle:'Compare recorded conditions before interpreting results; unknown does not mean equal.',decisionsTitle:'Keep resolved questions within reach.',decisionsSubtitle:'Store claims, scope, and conditions for reopening together.',sourcesTitle:'Trace every judgment to a source.',sourcesSubtitle:'Small text gets immutable snapshots; large artifacts have location records, not backup claims.',historyTitle:'Remember why each revision happened.',historySubtitle:'The timeline is traceable. Refreshing the view does not call a model.',childItems:'children',expandToggle:'Expand or collapse',mapEmpty:'No research relationships yet. Run sync, then have your agent read evidence and organize it. The scanner does not infer research questions from directory names.',mapPanel:'Research map',tree:'Hierarchy',relationsView:'Relations',expand:'Expand',collapse:'Collapse',mapSearch:'Search modules, questions, or experiments…',mapHint:'Expand branches with arrows and select cards for details. Lines show recorded relationships, not causation.',modules:'Modules',inspector:'INSPECTOR',selectObject:'Select a research object',selectObjectHelp:'Inspect its purpose, actual conditions, sources, and scope.',noDescription:'No explanation recorded. Check the evidence before inferring from names.',actualConditions:'Recorded conditions',results:'Results / recorded metrics',runIdentity:'Run identity',scope:'Scope',coveredValues:'Covered factor values',reopenIf:'When to review again',confirmation:'Confirmation record',nextAction:'Open questions',sources:'Sources',noDirectEvidence:'This object has no direct file evidence. Check related objects; unsupported explanations are not facts.',linkedEvidence:'Related evidence objects',relations:'Relationships',comparePanel:'Cell comparison matrix',compareHint:'Collapse shared fields · unknown conditions are not assumed equal',diffOnly:'Show differing configurations only',metric:'Metric',conditions:'Module / execution condition',recordedRuns:'Recorded runs',includedSeeds:'Independent seeds included',meanSd:'mean ± sample SD',reviewHints:'Review notes',noCells:'Select at least one cell.',descriptiveOnly:'Descriptive summary only; no automatic ranking.',unitNote:'The statistical unit is a training seed, not an evaluation episode. One seed has no cross-seed SD.',comparability:'Comparability is unresolved for: ',implementationNote:'Matching configurations do not prove identical implementations. The agent and researcher must verify the scientific interpretation against evidence.',configInvalid:'Cell or run configuration is not an object; omitted',configConflict:'Run configuration conflicts with its cell; omitted',conditionConflict:'Conditions or code revisions differ; omitted',protocolConflict:'Protocol unknown or inconsistent; omitted',duplicateSeed:'Duplicate seeds excluded',driftExcluded:'Changed or missing sources: affected runs excluded from current summary; historical snapshots remain available',incompleteExcluded:'Incomplete or unconfirmed runs excluded',revisionMissing:'Historical code identity incomplete',decisionsPanel:'Claims and historical decisions',decisionsHint:'Keep resolved questions and the conditions for revisiting them',directSources:'direct sources',linkedObjects:'related objects',noDecisions:'No sourced claims yet. The tool does not infer them from experiment names.',sourcesPanel:'Evidence sources',sourcesHint:'Content snapshots and location indexes are labeled separately',sourcesSearch:'Search paths or source aliases…',missingSource:'Source missing',savedSnapshot:'Text snapshot saved',offlineTextOmitted:'Text omitted from offline export',locationOnly:'Location only / not a backup',view:'View',index:'Index',previous:'Previous',next:'Next',noSources:'No matching source files.',timelinePanel:'Update timeline',timelineHint:'See file and research module changes per revision; select nodes to open details.',allChanges:'All changes',fileChanges:'File changes',nodeChanges:'Research module changes',edgeChanges:'Relationship changes',allModules:'All modules',changeAdded:'Added',changeUpdated:'Updated',changeRemoved:'Removed',changeUnknown:'Changed',oldHistory:'This older revision records its reason but has no itemized changes.',historyEmpty:'No updates yet; the workspace was just created.',noMatchingHistory:'No updates match these filters.',files:'Files',nodes:'Nodes',edges:'Relationships',unknownActor:'Actor not recorded',unknownReason:'Reason not recorded',loading:'Loading…',snapshotOmitted:'This offline snapshot does not include the original text. View it in the local workspace, or explicitly re-export with --include-evidence.',staticSnapshot:'This is a fixed snapshot. Update it through the tool, then export again.',copied:'Prompt copied; paste it into your existing agent chat.',copyToAgent:'Copy to existing agent chat',noNewAgent:'No need to start multiple agents',exportWarning:'The export may contain private configuration. Review before sharing.',prompt:'Use LabWeft to organize the current research project {project}. Read existing records first, then incrementally inspect code and results. Check each ablation’s purpose, cell differences, result evidence, and historical decisions. Update the local map. Do not start experiments, change research code, or upload data. Carry forward confirmed judgments where still applicable; leave unresolved gaps visible.'}
};
const t = key => words[lang][key] ?? key;
words.zh.sharedTrainingRuns = '所选 Cell 有 {count} 个重复的 run_id 值。它们可能是同一训练的不同 checkpoint，也可能是身份冲突；核对前不要把各行 seed 数相加当作独立重复。';
words.en.sharedTrainingRuns = '{count} recorded run_id values recur across selected cells. They may be checkpoint views or identity collisions; do not add per-row seed counts as independent replicates before reconciliation.';
words.zh.compareSearch = '筛选实验条件…'; words.en.compareSearch = 'Filter experimental cells…';
words.zh.selectVisible = '选择筛选结果'; words.en.selectVisible = 'Select filtered';
words.zh.clearSelection = '清空选择'; words.en.clearSelection = 'Clear selection';
words.zh.selectedCells = '已选 {count} 个 Cell'; words.en.selectedCells = '{count} cells selected';
words.zh.groupSelected = '已选 {count} 个'; words.en.groupSelected = '{count} selected';
Object.assign(words.zh,{projectEventModule:'研究主题',projectEventDateType:'日期性质',allProjectEvents:'全部事件',eventDay:'明确日期',eventRangeStart:'阶段起点',eventAsOf:'截至记录'});
Object.assign(words.en,{projectEventModule:'Research theme',projectEventDateType:'Date meaning',allProjectEvents:'All events',eventDay:'Dated event',eventRangeStart:'Period start',eventAsOf:'As-of record'});
words.zh.noMatchingProjectEvents='没有符合筛选条件的研究事件。';words.en.noMatchingProjectEvents='No research events match these filters.';
words.zh.currentBranch='当前研究路径';words.en.currentBranch='Current research path';
words.zh.switchProject='切换项目';words.en.switchProject='Switch project';
words.zh.studyModules='研究模块';words.en.studyModules='Research modules';
words.zh.multiWorkspace='多个项目，分别建档。';words.en.multiWorkspace='Several projects, separate records.';
words.zh.keyResult='关键结果';words.en.keyResult='Key result';
words.zh.fullFindingDetails='完整说明、范围与来源';words.en.fullFindingDetails='Full account, scope and sources';
words.zh.evidenceCount='条直接来源';words.en.evidenceCount='direct sources';
Object.assign(words.zh,{mappedSources:'地图已关联',unmappedSources:'尚未映射',allIndexedSources:'全部索引',sourceScopeHint:'未映射只表示当前地图没有引用；不等于文件无用或已经核验。'});
Object.assign(words.en,{mappedSources:'Linked to map',unmappedSources:'Not yet mapped',allIndexedSources:'All indexed',sourceScopeHint:'Unmapped means the current map has no reference; it does not mean the file is useless or verified.'});
Object.assign(words.zh,{sourceAuditDetails:'来源核对详情',auditTable:'核对记录',auditOnlyNote:'这里记录来源核对与缺口，不代表新增实验结果。',auditNoEvidence:'尚无直接实验结果可核验；请按下方线索继续采集。',perRunMetrics:'逐次运行的记录指标',runRowsNoPooling:'每行是一条 Run 记录；这里不跨协议汇总，也不把评估 episode 当作独立训练 seed。',runDetails:'打开 Run 详情'});
Object.assign(words.en,{sourceAuditDetails:'Source audit details',auditTable:'Audit records',auditOnlyNote:'This records source checks and gaps; it does not establish a new experimental result.',auditNoEvidence:'No direct experimental result is available to verify; follow the collection leads below.',perRunMetrics:'Recorded metrics by run',runRowsNoPooling:'Each row is one Run record. This table does not pool protocols or treat evaluation episodes as independent training seeds.',runDetails:'Open Run details'});
words.zh.returnToTimeline='← 返回研究历程';words.en.returnToTimeline='← Back to research history';
Object.assign(words.zh,{researchLogic:'研究逻辑：按研究问题、方法与实验设计组织；目录和阶段只用于定位来源。',mainFindings:'核心研究结论',secondaryFindings:'补充研究结论',historicalDecisions:'研究决策',auditRecords:'来源核对与其他记录',noMainFindings:'尚未标注有证据的核心研究结论。请先核对研究问题、比较条件和结果来源。',noHistoricalDecisions:'尚无单独记录的研究决策。',sourceBasis:'证据级别',findingScope:'结论范围',findingType:'结论类型',researchTheme:'研究主题',otherTheme:'跨主题记录',primaryFinding:'核心结论',secondaryFinding:'补充结论'});
Object.assign(words.en,{researchLogic:'Research logic follows questions, methods and study designs; directories and phases locate sources.',mainFindings:'Main research findings',secondaryFindings:'Supporting research findings',historicalDecisions:'Research decisions',auditRecords:'Source audits and other records',noMainFindings:'No sourced main finding has been marked yet. Check the research question, comparison and results first.',noHistoricalDecisions:'No separate research decision has been recorded.',sourceBasis:'Evidence basis',findingScope:'Finding scope',findingType:'Finding type',researchTheme:'Research theme',otherTheme:'Cross-theme records',primaryFinding:'Main finding',secondaryFinding:'Supporting finding'});
Object.assign(words.zh,{researchRole:'研究角色',studyDesign:'实验设计',role_research_area:'研究主题',role_method_family:'方法族',role_baseline_family:'基线族',role_study:'实验系列',role_ablation_group:'消融组',role_generalization:'泛化实验',role_evidence_audit:'来源核对'});
Object.assign(words.en,{researchRole:'Research role',studyDesign:'Study design',role_research_area:'Research area',role_method_family:'Method family',role_baseline_family:'Baseline family',role_study:'Study',role_ablation_group:'Ablation group',role_generalization:'Generalization',role_evidence_audit:'Evidence audit'});
Object.assign(words.zh,{finding_effect:'效果',finding_mechanism_interpretation:'机制解释',finding_negative_result:'负结果',finding_boundary:'适用边界',finding_status:'进展状态',basis_source_report:'来源报告',basis_source_recalculation:'按来源复算',basis_independent_rerun:'独立重跑',basis_user_testimony:'研究者说明'});
Object.assign(words.en,{finding_effect:'Effect',finding_mechanism_interpretation:'Mechanism interpretation',finding_negative_result:'Negative result',finding_boundary:'Scope boundary',finding_status:'Progress status',basis_source_report:'Source report',basis_source_recalculation:'Recalculated from source',basis_independent_rerun:'Independent rerun',basis_user_testimony:'Researcher account'});
Object.assign(words.zh,{studyOverview:'实验详情',studyResults:'结果指标',studyEvidence:'直接来源',studyRelatedFindings:'相关结论',studyNoTable:'本节尚无可核对的数值表；请查看下方实验条件和来源。',studyNoDescription:'本节的实验条件与结果见下方记录。',groupSelectAll:'选中整组',groupClearAll:'取消整组',groupShowCells:'展开实验条件',groupCells:'个实验条件',projectTimeline:'研究历程',recordTimeline:'记录修订',projectTimelineHint:'按来源记载的研究事件日期，从早到晚展开。日期不是文件导入时间。',recordTimelineHint:'LabWeft 工作空间的写入历史；它不是实验发生时间。',noProjectEvents:'尚无带日期和直接来源的项目事件，不能从文件修改时间推造研究历程。',eventEvidence:'日期与事件来源',eventRelated:'查看对应研究模块',eventDateBasis:'日期口径',timelineDirection:'项目进展方向'});
Object.assign(words.en,{studyOverview:'Study details',studyResults:'Results',studyEvidence:'Direct sources',studyRelatedFindings:'Related findings',studyNoTable:'No source-checked numeric table is recorded for this section. Inspect its conditions and sources below.',studyNoDescription:'Study conditions and results are recorded below.',groupSelectAll:'Select group',groupClearAll:'Clear group',groupShowCells:'Show conditions',groupCells:'conditions',projectTimeline:'Research history',recordTimeline:'Record revisions',projectTimelineHint:'Source-dated research events, earliest to latest. These are not file-import dates.',recordTimelineHint:'LabWeft workspace writes; these are not experiment dates.',noProjectEvents:'No project events with both a date and direct source are recorded. File timestamps cannot establish research history.',eventEvidence:'Date and event sources',eventRelated:'Open research module',eventDateBasis:'Date basis',timelineDirection:'Research progresses'});
words.zh.studySection='研究小节';words.en.studySection='Study section';
words.zh.navHistory='研究时间线';words.en.navHistory='Research timeline';
words.zh.historyTitle='研究历程与记录修订。';words.en.historyTitle='Research history and record revisions.';
words.zh.historySubtitle='先看项目真实事件，再按需追溯工具记录。';words.en.historySubtitle='Start with dated research events, then inspect workspace changes.';
words.zh.projectTimelineHint='从已索引来源中最早可核对的事件到最近事件；“截至日”与实验完成日分别标明。';
words.en.projectTimelineHint='From the earliest sourced event in this workspace to the latest; report as-of dates remain distinct from completion dates.';
words.zh.decisionsTitle='先看研究发现，再追溯证据。'; words.en.decisionsTitle='Start with findings, then trace the evidence.';
words.zh.decisionsSubtitle='核心结论按研究主题组织；来源核对和决策分别保留。'; words.en.decisionsSubtitle='Main findings follow research themes; source audits and decisions stay distinct.';
words.zh.prompt='使用 LabWeft 整理当前科研项目{project}。先读已有状态、最终报告、实验设计与研究者纠正，写出有来源的科学纲要：目标、方法与基线、研究问题、实验系列、消融因素、评价终点及候选核心结论。按科学设计建分层地图，不把目录名或阶段号当作科学分类。逐条从结论反向核对报告、实际配置、逐运行结果与反证；只将有证据且有适用范围的结论设为核心。增量文件应更新已有研究关系与结论，不重复建立运行身份。不要启动实验、修改研究代码或上传数据。';
words.en.prompt='Use LabWeft to organize this research project {project}. First read existing state, final reports, study plans and researcher corrections. Draft a sourced scientific outline: objective, methods and baselines, questions, study hierarchy, ablation factors, endpoints and candidate main findings. Organize the map by study design, not directory names or phase numbers. Verify each finding backwards through reports, effective configurations, run results and counterevidence; mark a main finding only with evidence and scope. New files should update existing research relationships and conclusions without duplicating run identity. Do not start experiments, change research code or upload data.';
const pretty = x => x === null || x === undefined ? t('unknown') : typeof x === 'object' ? JSON.stringify(x) : String(x);
const canonical = x => Array.isArray(x) ? `[${x.map(canonical).join(',')}]` : x && typeof x==='object' ? `{${Object.keys(x).sort().map(k=>`${JSON.stringify(k)}:${canonical(x[k])}`).join(',')}}` : JSON.stringify(x);
const label = n => n.kind==='question'&&n.attrs?.presentation_kind==='section'?t('studySection'):t(n.kind) === n.kind ? n.kind : t(n.kind);
const statusText = status => t(status) === status ? status || t('recorded') : t(status);
function displayLabel(node) { const value=node?.attrs?.i18n?.[lang]?.label; return typeof value==='string'&&value.trim()?value:node?.label||''; }
function displayDescription(node) { const value=node?.attrs?.i18n?.[lang]?.description; return typeof value==='string'&&value.trim()?value:node?.description||''; }
function findingPriority(n) { const p=n?.attrs?.finding?.priority; return p==='primary'||p==='secondary'||p==='audit'?p:'uncategorized'; }
function isFeaturedClaim(n) { return n.kind==='claim'&&['primary','secondary'].includes(findingPriority(n)); }
function themeOf(n) { let current=n, root=null, seen=new Set(); while(current&&!seen.has(current.id)){seen.add(current.id);if(current.kind==='module')root=current;current=data.nodes[current.parent_id];}return root; }
function findingSummary(n) { const f=n.attrs?.finding||{},e=f.endpoint||{},v=f.estimate||{}; const result=v.delta!==undefined?v.delta:v.value; const resultText=result===undefined?'':`${typeof result==='number'&&result>0&&v.delta!==undefined?'+':''}${result} ${e.unit||''}`.trim(); return [e.dataset||e.task,e.metric,resultText,v.n===undefined?'':`n=${v.n} ${v.sample_unit||''}`.trim()].filter(Boolean).join(' · '); }
function enumLabel(prefix,value){const key=prefix+value;return t(key)===key?value:t(key);}
function roleLabel(n){const role=n.attrs?.role;return role?t('role_'+role)==='role_'+role?role:t('role_'+role):'';}
function initialExpanded(){const ids=new Set();for(const n of Object.values(data.nodes).filter(n=>n.kind==='module'&&n.status!=='archived'&&n.attrs?.role!=='evidence_audit')){const parent=data.nodes[n.parent_id];if(n.parent_id===data.project.id||parent?.parent_id===data.project.id)ids.add(n.id);}return ids;}
words.zh.tree='大纲';words.en.tree='Outline';words.zh.relationsView='研究树';words.en.relationsView='Research tree';
let data, view='map', selected=null, layout='lineage', filter='', compareFilter='', sourceMode='mapped', cellSelection=new Set(), metric='success_rate', differentOnly=false;
let relationInspect=false;
let treeCamera={x:0,y:0,scale:1},treeCollapsed=new Set(),treeSecondary=false,treeFullscreen=false,treeFitMode=false,treeShowAll=false;
let expanded = new Set(), collapsedDuringSearch=new Set(), token='', savedKey='', sourcePage=0, historyType='all', historyModule='all', timelineView='project', projectTimelineModule='all', projectTimelineType='all', timelineReturnEvent=null, compareOpenGroups=new Set();
const snap = $('snapshot-data');
try { token = new URLSearchParams(location.search).get('token') || sessionStorage.getItem('rh-token') || ''; if(token)sessionStorage.setItem('rh-token',token); if(location.search.includes('token='))history.replaceState({},'',location.pathname); } catch (_) {}
function badge(n) { const cls=n.status==='needs_review'?'review':n.status==='provisional'?'provisional':''; return `<span class="badge ${cls}">${esc(statusText(n.status))}</span>`; }
function mapBadge(n) { return n.status==='provisional'&&['module','question','cell'].includes(n.kind)?'':badge(n); }
function canOpenEvidence(sha) { return !!sha && (!snap || typeof data.evidence_texts?.[sha] === 'string'); }
function staticLanguage(){document.documentElement.lang=lang==='zh'?'zh-CN':'en';document.querySelectorAll('[data-i18n]').forEach(el=>{if(el.id==='project-name'&&data)return;el.textContent=t(el.dataset.i18n);});document.querySelectorAll('[data-lang]').forEach(el=>el.setAttribute('aria-pressed',String(el.dataset.lang===lang)));document.title=`LabWeft · ${t('workspace')}`;}
function setLanguage(next){if(next!==lang){lang=next;try{localStorage.setItem('labweft-language',lang);}catch(_){}}staticLanguage();if(data){loadLabels();render();}}
function storageWrite() { try { localStorage.setItem(savedKey,JSON.stringify({version:4,expanded:[...expanded],selected,layout})); } catch (_) {} }
function toast(msg) { $('toast').textContent=msg;$('toast').hidden=false;setTimeout(()=>$('toast').hidden=true,3300); }
async function api(path) {const response=await fetch(path,{headers:{'X-Research-Token':token}});if(!response.ok)throw new Error(await response.text());return response;}
async function load() {
 try {
  data = snap ? JSON.parse(snap.textContent) : await (await api('/api/state')).json();
  savedKey='rh-view-'+data.project.id;
  expanded=initialExpanded();
  try { const old=JSON.parse(localStorage.getItem(savedKey)||'null');if(old?.version===4){expanded=new Set(old.expanded||[]);selected=old.selected;layout=old.layout||'lineage';} }catch(_){}
  if(!selected || !data.nodes[selected]||data.nodes[selected].status==='archived')selected=Object.values(data.nodes).filter(n=>n.kind==='module'&&n.parent_id===data.project.id&&n.status!=='archived').sort(sortNodes)[0]?.id || Object.values(data.nodes).find(n=>n.kind==='claim'&&findingPriority(n)==='primary')?.id || Object.values(data.nodes)[0]?.id;
  {const m=/node=([\w-]+)/.exec(location.hash);if(m&&data.nodes[m[1]]){selected=m[1];let p=m[1],seen=new Set();while(data.nodes[p]&&!seen.has(p)){seen.add(p);expanded.add(p);p=data.nodes[p].parent_id;}}}
  for(const id of cellSelection)if(data.nodes[id]?.kind!=='cell'||data.nodes[id].status==='archived')cellSelection.delete(id);
  if(!cellSelection.size){const available=Object.values(data.nodes).filter(n=>n.kind==='cell'&&n.status!=='archived');if(available.length<=8)available.forEach(n=>cellSelection.add(n.id));}
   loadLabels();
   render();
  } catch(e) { $('content').innerHTML=`<div class="error">${esc(t('loadError'))}${esc(e.message)}<p>${esc(t('liveHelp'))}</p></div>`; }
}
function loadLabels(){
 $('project-name').textContent=data.project.name;$('synthetic').hidden=!data.project.synthetic;
 renderProjectSwitcher();
 $('mode').textContent=t(snap?'offline':'localReadOnly');$('revision').textContent=t('revision')+' '+data.revision;
 $('footer-state').textContent=t(snap?'offlineFooter':'liveFooter');
 $('source-count').textContent=Object.values(data.files).filter(f=>!f.missing).length+' '+t('sourceFiles');
 const kinds=Object.values(data.nodes).filter(n=>n.status!=='archived');
 $('stats').innerHTML=[['studyModules',kinds.filter(n=>n.kind==='module').length,'◇'],['cells',kinds.filter(n=>n.kind==='cell').length,'▤'],['runs',kinds.filter(n=>n.kind==='run').length,'◉'],['protectedDecisions',kinds.filter(n=>n.protected&&['claim','decision'].includes(n.kind)).length,'✓']].map(([key,n,icon])=>`<div class="stat"><div><div class="stat-number">${n}</div><div class="stat-label">${esc(t(key))}</div></div><div class="stat-icon">${icon}</div></div>`).join('');
 const notices=[];
 if(data.scan?.source_aliases?.length)notices.push(t('sourceConfigured')+data.scan.source_aliases.join(lang==='zh'?'、':', ')+t('scanScope'));
 if(data.scan && data.scan.complete===false)notices.push(t('partialScan'));
 if(data.drift?.length)notices.push(`${new Set(data.drift.map(d=>d.node_id)).size} ${t('driftNotice')}`);
 $('notice').hidden=!notices.length;$('notice').textContent=notices.join(' ');
}
function renderProjectSwitcher(){
 const bar=$('project-switcher'),root=$('project-links'),links=Array.isArray(data.site_links)?data.site_links:[];
 bar.hidden=links.length<2;root.replaceChildren();
 const note=document.querySelector('[data-i18n="oneWorkspace"]');if(note)note.textContent=t(links.length>1?'multiWorkspace':'oneWorkspace');
 for(const item of links){const anchor=document.createElement('a');anchor.href=item.href;anchor.textContent=item.name;anchor.setAttribute('aria-current',item.id===data.project.id?'page':'false');root.append(anchor);}
}
function sortNodes(a,b){const stableName=n=>n.attrs?.i18n?.zh?.label||n.label;return (a.attrs?.order??100)-(b.attrs?.order??100)||stableName(a).localeCompare(stableName(b),'zh-CN',{numeric:true})||a.id.localeCompare(b.id);}
function compareTreePath(a,b){const path=n=>{const out=[],seen=new Set();while(n&&n.id!==data.project.id&&!seen.has(n.id)){seen.add(n.id);out.unshift(n);n=data.nodes[n.parent_id];}return out;},left=path(a),right=path(b);for(let i=0;i<Math.min(left.length,right.length);i++){const order=sortNodes(left[i],right[i]);if(order)return order;}return left.length-right.length;}
function children(id) {return Object.values(data.nodes).filter(n=>n.parent_id===id && n.status!=='archived').sort(sortNodes);}
function isMapNode(n){return n.kind!=='decision'&&n.kind!=='artifact'&&(n.kind!=='claim'||isFeaturedClaim(n));}
function scrollMapTarget(target){if(!target)return;const trail=document.querySelector('.map-trail'),minimum=window.matchMedia('(max-width:700px)').matches?150:80;target.style.scrollMarginTop=`${Math.max(minimum,Math.ceil((trail?.getBoundingClientRect().height||0)+16))}px`;target.scrollIntoView({block:'start',behavior:'auto'});}
function select(id) { selected=id;if(layout==='lineage')relationInspect=true;expanded.add(id);collapsedDuringSearch.delete(id);let parent=data.nodes[id]?.parent_id,seen=new Set();while(data.nodes[parent]&&!seen.has(parent)){seen.add(parent);expanded.add(parent);collapsedDuringSearch.delete(parent);parent=data.nodes[parent].parent_id;}if(view==='map'&&filter&&data.nodes[id]&&!hasMatch(data.nodes[id]))filter='';storageWrite();renderDetail(); if(view==='map'){renderMap();if(layout==='tree')requestAnimationFrame(()=>scrollMapTarget([...document.querySelectorAll('.node-card')].find(card=>card.dataset.select===id)));} }
function setView(v) {view=v;filter='';collapsedDuringSearch.clear();sourcePage=0;render();window.scrollTo(0,0);}
function render() {
 document.body.classList.toggle('research-tree-view',view==='map'&&layout==='lineage');
 if(view!=='map'){treeFullscreen=false;document.body.classList.remove('tree-expanded');}
 document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('active',b.dataset.view===view));
 document.querySelector('.workspace-body').dataset.view=view;document.body.dataset.view=view;
 $('page-title').textContent=t(view+'Title');$('page-subtitle').textContent=t(view+'Subtitle');
 ({map:renderMap,semantic:renderSemantic,compare:renderCompare,decisions:renderDecisions,sources:renderSources,history:renderHistory}[view])();
 renderDetail();
}
function hasMatch(n) {if(!filter)return true;return (displayLabel(n)+' '+displayDescription(n)+' '+n.label+' '+n.description+' '+n.id).toLowerCase().includes(filter.toLowerCase())||children(n.id).some(hasMatch);}
function studySummary(n){const summaries=n.attrs?.study_summary;return summaries?.[lang]||summaries?.zh||summaries?.en||null;}
function nestedFindings(id,limit=3){const found=[],queue=[...children(id)],seen=new Set();while(queue.length&&found.length<limit){const n=queue.shift();if(seen.has(n.id))continue;seen.add(n.id);if(isFeaturedClaim(n))found.push(n);else if(['module','question'].includes(n.kind))queue.push(...children(n.id));}return found;}
function studyPanel(n){
 const attrs=n.attrs||{},summary=studySummary(n),description=summary?.intro||displayDescription(n),hasDescription=description&&description!==displayLabel(n),claims=nestedFindings(n.id),rows=summary?.rows||[],columns=summary?.columns||[];
 const audit=attrs.role==='evidence_audit',presentation=n.kind==='claim'?attrs.finding_card?.[lang]:null;
 const table=columns.length&&rows.length?`<div class="study-table-wrap"><table class="study-table"><thead><tr>${columns.map(c=>`<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(value=>`<td>${esc(value)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`:'';
 const metrics=(summary?.metrics||[]).map(m=>`<div class="study-metric"><strong>${esc(m.value)}</strong><span>${esc(m.label)}</span></div>`).join('');
 const related=claims.length?`<div class="study-related"><b>${esc(t('studyRelatedFindings'))}</b>${claims.map(c=>`<button data-select="${esc(c.id)}">${esc(displayLabel(c))}${findingSummary(c)?`<small>${esc(findingSummary(c))}</small>`:''}</button>`).join('')}</div>`:'';
 const sources=(n.evidence||[]).length?`<div class="study-sources"><b>${esc(t('studyEvidence'))} · ${n.evidence.length}</b>${n.evidence.map(r=>{const f=data.files[r.file_id]||{};return `<button data-inline-evidence="${esc(r.sha256)}" data-title="${esc(f.path||r.file_id)}" ${canOpenEvidence(r.sha256)?'':'disabled'}>${esc(f.path?f.path.split('/').slice(-2).join('/'):r.file_id)}${r.locator&&r.locator!=='file'?` <small>${esc(r.locator)}</small>`:''} ↗</button>`;}).join('')}</div>`:'';
 const concrete=['cell','run','evaluation'].includes(n.kind),facts=concrete?`${attrs.metrics?`<div class="study-facts"><h4>${esc(t('results'))}</h4>${metricKv(attrs.metrics)}${attrs.metric_selection||attrs.selection?`<p>${esc(attrs.metric_selection||attrs.selection)}</p>`:''}</div>`:''}${n.kind==='run'?`<div class="study-facts"><h4>${esc(t('runIdentity'))}</h4>${kv({seed:attrs.seed,code_revision:attrs.code_revision,eval_protocol:attrs.eval_protocol,identity:attrs.identity_basis})}</div>`:''}${attrs.config&&Object.keys(attrs.config).length?`<details class="study-technical" ${n.kind==='cell'?'open':''}><summary>${esc(t('actualConditions'))} · ${Object.keys(attrs.config).length}</summary>${kv(attrs.config)}</details>`:''}`:'';
 const scientificScope=attrs.scope?`<details class="study-technical"><summary>${esc(t('scope'))}</summary>${kv(attrs.scope)}</details>`:'';
 const design=attrs.design&&n.kind==='module'?`<details class="study-technical"><summary>${esc(t('studyDesign'))}</summary>${kv(attrs.design)}</details>`:'';
 const childRuns=n.kind==='cell'?children(n.id).filter(c=>c.kind==='run'):[];
 const runLinks=childRuns.map(c=>`<button data-select="${esc(c.id)}">${esc(displayLabel(c))} ↗</button>`).join('');
 const runTable=n.kind==='cell'&&!attrs.metrics&&childRuns.length?`<div class="study-run-section"><h4>${esc(t('perRunMetrics'))} · ${childRuns.length}</h4><p>${esc(t('runRowsNoPooling'))}</p><div class="study-table-wrap"><table class="study-table study-run-table"><thead><tr><th>seed</th><th>${esc(t('results'))}</th><th>${esc(t('runIdentity'))}</th><th>${esc(t('view'))}</th></tr></thead><tbody>${childRuns.map(r=>`<tr><td>${esc(pretty(r.attrs?.seed))}<small>${esc(statusText(r.status))}</small></td><td>${Object.entries(r.attrs?.metrics||{}).map(([key,value])=>`<div><b>${esc(key)}</b> <span title="${esc(pretty(value))}">${esc(compactMetric(value))}</span></div>`).join('')||esc(t('unknown'))}</td><td>${esc(pretty(r.attrs?.eval_protocol))}</td><td><button type="button" data-select="${esc(r.id)}">${esc(t('runDetails'))} ↗</button></td></tr>`).join('')}</tbody></table></div></div>`:'';
 const runSection=runTable||(runLinks?`<div class="study-related"><b>${esc(t('recordedRuns'))} · ${childRuns.length}</b>${runLinks}</div>`:'');
 const edges=Object.values(data.edges).filter(e=>e.source===n.id||e.target===n.id),relations=edges.length?`<details class="study-technical"><summary>${esc(t('relations'))} · ${edges.length}</summary>${edges.map(e=>{const other=data.nodes[e.source===n.id?e.target:e.source];return other?`<button class="study-relation" data-select="${esc(other.id)}">${esc(displayLabel(other))} ↗</button>`:'';}).join('')}</details>`:'';
 const technical=attrs.finding&&n.kind==='claim'?`<details class="study-technical"><summary>${esc(t('findingScope'))}</summary>${attrs.finding.type||attrs.finding.basis?kv(Object.fromEntries([['type',attrs.finding.type],['basis',attrs.finding.basis]].filter(([,v])=>v!==undefined))):''}${attrs.finding.endpoint?kv(attrs.finding.endpoint):''}${attrs.finding.estimate?kv(attrs.finding.estimate):''}</details>`:'';
 return `<section class="study-panel ${audit?'is-audit':''}" aria-label="${esc(t(audit?'sourceAuditDetails':'studyOverview'))}"><div class="study-panel-heading">${esc(label(n))} · ${esc(t(audit?'sourceAuditDetails':'studyOverview'))}${audit?` · ${(n.evidence||[]).length} ${esc(t('evidenceCount'))}`:''}</div>${audit?`<p class="study-audit-note">${esc(t((n.evidence||[]).length?'auditOnlyNote':'auditNoEvidence'))}</p>`:''}${hasDescription?`<p>${esc(description)}</p>`:''}${presentation?`<div class="study-claim-result"><strong>${esc(presentation.value)}</strong><span>${esc(presentation.label)}</span></div><p class="study-claim-limit">${esc(presentation.limit)}</p>`:''}${metrics?`<div class="study-metrics">${metrics}</div>`:''}${table?`<h4>${esc(t(audit?'auditTable':'studyResults'))}</h4>${table}`:''}${summary?.note?`<p class="study-note">${esc(summary.note)}</p>`:''}${facts}${runSection}${related}${sources}${scientificScope}${design}${technical}${relations}${!hasDescription&&!metrics&&!table&&!facts&&!related&&!sources?`<p class="study-note">${esc(t('studyNoDescription'))}</p>`:''}</section>`;
}
function selectedLineage(){const path=[],seen=new Set();let n=data.nodes[selected];while(n&&!seen.has(n.id)){seen.add(n.id);if(n.status!=='archived'&&isMapNode(n))path.push(n);n=data.nodes[n.parent_id];}return path.reverse();}
function treeNode(n,depth=0,pathIds=new Set()) {
 const kids=children(n.id).filter(isMapNode).filter(hasMatch),isSelected=selected===n.id,open=(expanded.has(n.id)||!!filter&&!collapsedDuringSearch.has(n.id))&&(kids.length>0||isSelected),panelOpen=isSelected&&expanded.has(n.id),onPath=pathIds.has(n.id);
 const sub = n.kind==='cell'?Object.entries(n.attrs?.config||{}).filter(([k])=>['history_length','prediction_weight','hardware'].includes(k)).map(([k,v])=>`${k}=${pretty(v)}`).join(' · '):n.kind==='claim'?findingSummary(n):n.kind==='module'?roleLabel(n):'';
 return `<li class="node-wrap ${onPath?'branch-path':''} ${isSelected?'branch-current':''}" data-depth="${Math.min(depth,4)}"><div class="node-card ${isSelected?'selected':''} ${open?'is-open':'is-closed'}" data-select="${esc(n.id)}" role="button" tabindex="0" aria-current="${isSelected?'true':'false'}"><button class="node-toggle" data-toggle="${esc(n.id)}" aria-label="${esc(t('expandToggle'))} ${esc(displayLabel(n))}" aria-expanded="${open}"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="${open?'M4 7l6 6 6-6':'M7 4l6 6-6 6'}"/></svg></button><span class="node-dot ${esc(n.kind)}"></span><span class="node-label">${esc(displayLabel(n))}${sub?`<small class="node-sub">${esc(sub)}</small>`:''}</span>${kids.length?`<span class="node-count">${kids.length} ${esc(t('childItems'))}</span>`:''}${mapBadge(n)}</div>${panelOpen?studyPanel(n):''}${kids.length&&open?`<ul class="tree-list">${kids.map(child=>treeNode(child,depth+1,pathIds)).join('')}</ul>`:''}</li>`;
}
function renderMap() {
 document.body.classList.toggle('research-tree-view',layout==='lineage');
 $('content').innerHTML=`<div class="panel-head"><div><h2>${esc(t('mapPanel'))}</h2><small>${esc(t('researchLogic'))}</small></div><div class="panel-tools"><div class="view-switch"><button data-layout="tree" class="${layout==='tree'?'active':''}">${esc(t('tree'))}</button><button data-layout="lineage" class="${layout==='lineage'?'active':''}">${esc(t('relationsView'))}</button></div><button id="expand-all">${esc(t('expand'))}</button><button id="collapse-all">${esc(t('collapse'))}</button></div></div><div class="search-wrap"><input class="search" id="map-search" placeholder="${esc(t('mapSearch'))}" value="${esc(filter)}" aria-label="${esc(t('mapSearch'))}"></div><div id="map-body"></div><div class="tree-hint">${esc(t('mapHint'))}</div><details class="status-help"><summary>${esc(t('statusInfoTitle'))}</summary><p>${esc(t('statusInfo'))}</p></details>`;
 $('map-search').addEventListener('input',e=>{filter=e.target.value;collapsedDuringSearch.clear();drawMapBody();});
 $('expand-all').onclick=()=>{treeCollapsed.clear();Object.keys(data.nodes).forEach(id=>expanded.add(id));collapsedDuringSearch.clear();treeCamera={x:0,y:0,scale:1};storageWrite();drawMapBody();};
 $('collapse-all').onclick=()=>{treeCollapsed=new Set(Object.values(data.nodes).filter(n=>n.kind==='cell').map(n=>n.id));expanded.clear();Object.keys(data.nodes).forEach(id=>collapsedDuringSearch.add(id));treeCamera={x:0,y:0,scale:1};storageWrite();drawMapBody();};
 document.querySelectorAll('[data-layout]').forEach(b=>b.onclick=()=>{layout=b.dataset.layout;storageWrite();renderMap();});
 if(timelineReturnEvent){$('content').insertAdjacentHTML('afterbegin',`<button class="timeline-return" id="return-to-timeline" type="button">${esc(t('returnToTimeline'))}</button>`);$('return-to-timeline').onclick=()=>{view='history';timelineView='project';render();const target=document.querySelector(`[data-project-event="${timelineReturnEvent}"]`);if(target){target.open=true;target.scrollIntoView({block:'center'});}};}
 drawMapBody();
}
// BEGIN grouped-relation-model
// This is only a display projection: no experimental identities or edges change.
function projectedCellRelations(nodeMap, edgeList) {
 const owner=id=>{let n=nodeMap[id],seen=new Set();if(!n||!['cell','run'].includes(n.kind))return null;while(n&&!seen.has(n.id)){if(n.status==='archived')return null;seen.add(n.id);if(n.kind==='cell')return n.id;n=nodeMap[n.parent_id];}return null;};
 const out=new Map();
 for(const edge of edgeList){
  const source=owner(edge.source),target=owner(edge.target)||(edge.relation==='derived_from'?edge.target:null);
  if(!source||!target||source===target)continue;
  const projected=!!edge.projected||source!==edge.source||target!==edge.target;
  if(projected&&!['derived_from','inspired_by','compares'].includes(edge.relation))continue;
  const key=JSON.stringify([source,target,edge.relation]);
  if(!out.has(key))out.set(key,{...edge,source,target,projected,originalEdges:[]});
  const item=out.get(key);item.projected=item.projected&&projected;
  item.originalEdges.push(...(edge.originalEdges||[{id:edge.id,source:edge.source,target:edge.target}]).map(e=>({...e})));
 }
 return [...out.values()];
}
function groupedRelationModel(nodeMap, edgeList) {
 edgeList=projectedCellRelations(nodeMap,edgeList);
 const active=Object.values(nodeMap).filter(n=>n.status!=='archived');
 const byId=new Map(active.map(n=>[n.id,n]));
 const owners=active.filter(n=>n.kind==='module'||n.kind==='question');
 const order=(a,b)=>(a.attrs?.order??100)-(b.attrs?.order??100)||String(a.label).localeCompare(String(b.label),'zh-CN',{numeric:true})||a.id.localeCompare(b.id);
 const ownerOf=n=>{let p=n.parent_id,seen=new Set();while(byId.has(p)&&!seen.has(p)){seen.add(p);const item=byId.get(p);if(item.kind==='module'||item.kind==='question')return p;p=item.parent_id;}return '__unassigned__';};
 const groups=new Map(owners.map(n=>[n.id,{id:n.id,owner:n,cells:[],claims:[],parent:new Map(),children:new Map(),roots:[],warnings:[]} ]));
 const cellGroup=new Map();
 for(const n of active){
  if(n.kind!=='cell'&&n.kind!=='claim')continue;
  const owner=ownerOf(n);
  if(!groups.has(owner))groups.set(owner,{id:owner,owner:null,cells:[],claims:[],parent:new Map(),children:new Map(),roots:[],warnings:[]});
  const group=groups.get(owner);
  if(n.kind==='cell'){group.cells.push(n);cellGroup.set(n.id,owner);}else group.claims.push(n);
 }
 const derived=edgeList.filter(e=>e.relation==='derived_from'&&byId.has(e.source)&&byId.has(e.target));
 for(const group of groups.values()){
  group.cells.sort(order);group.claims.sort(order);
  for(const n of group.cells){
   const explicit=derived.filter(e=>e.source===n.id);
   const local=explicit.filter(e=>cellGroup.get(e.target)===group.id).map(e=>e.target).sort();
   const parent=local.includes(n.parent_id)?n.parent_id:local[0];
   if(parent)group.parent.set(n.id,parent);
   else if(!explicit.length&&cellGroup.get(n.parent_id)===group.id)group.parent.set(n.id,n.parent_id);
   if(explicit.length>1)group.warnings.push({id:n.id,type:'multiple_parents'});
  }
  // Break only the rendered tree's cycle, retaining the actual relation in details.
  for(const n of group.cells){let p=n.id,seen=new Set();while(group.parent.has(p)){if(seen.has(p)){group.parent.delete(p);group.warnings.push({id:p,type:'cycle'});break;}seen.add(p);p=group.parent.get(p);}}
  for(const n of group.cells){const p=group.parent.get(n.id);if(p){if(!group.children.has(p))group.children.set(p,[]);group.children.get(p).push(n);}else group.roots.push(n);}
 }
 const lineage=n=>{const path=[],seen=new Set();while(n&&!seen.has(n.id)){seen.add(n.id);path.unshift(n);n=byId.get(n.parent_id);}return path;};
 const sorted=[...groups.values()].sort((a,b)=>{if(!a.owner)return 1;if(!b.owner)return -1;const ap=lineage(a.owner),bp=lineage(b.owner);for(let i=0;i<Math.min(ap.length,bp.length);i++){const d=order(ap[i],bp[i]);if(d)return d;}return ap.length-bp.length;});
 const cross=edgeList.filter(e=>cellGroup.has(e.source)&&cellGroup.has(e.target)&&cellGroup.get(e.source)!==cellGroup.get(e.target));
 return {groups:sorted,cross};
}
// END grouped-relation-model
// BEGIN research-tree-model
function resolveTreeFocus(nodeMap, focusId) {
 if(typeof focusId!=='string')return null;
 let n=nodeMap[focusId],seen=new Set();
 if(n?.kind==='run')while(n&&n.kind!=='cell'&&!seen.has(n.id)){if(n.status==='archived')return null;seen.add(n.id);n=nodeMap[n.parent_id];}
 return n&&n.status!=='archived'&&['module','question','cell'].includes(n.kind)?n.id:null;
}
function recordedTreeFocus(nodeMap){return Object.values(nodeMap).filter(n=>n.status!=='archived').map(n=>resolveTreeFocus(nodeMap,n.attrs?.current_focus)).find(Boolean)||null;}
// Without recorded cell lineage the tree shows the research hierarchy: module lanes, questions, their conditions.
function hasCellLineage(nodeMap,edgeList){return edgeList.some(e=>e.relation==='derived_from'&&nodeMap[e.source]?.kind==='cell'&&nodeMap[e.target]?.kind==='cell');}
function hierarchyTreeModel(nodeMap, edgeList, collapsed=new Set()) {
 const live=Object.values(nodeMap).filter(n=>n.status!=='archived'),order=(a,b)=>(a.attrs?.order??100)-(b.attrs?.order??100)||String(a.label).localeCompare(String(b.label),undefined,{numeric:true})||a.id.localeCompare(b.id);
 const questions=live.filter(n=>n.kind==='question').sort(order),cellsOf=new Map(),parent=new Map();
 for(const c of live.filter(n=>n.kind==='cell')){if(!cellsOf.has(c.parent_id))cellsOf.set(c.parent_id,[]);cellsOf.get(c.parent_id).push(c);}
 const laneOf=q=>{let p=nodeMap[q.parent_id],seen=new Set();while(p&&p.kind!=='module'&&!seen.has(p.id)){seen.add(p.id);p=nodeMap[p.parent_id];}return p||null;};
 const groups=new Map();for(const q of questions){const m=laneOf(q),key=m?.id||'';if(!groups.has(key))groups.set(key,{owner:m,questions:[]});groups.get(key).questions.push(q);}
 const ordered=[...groups.entries()].sort((a,b)=>a[1].owner&&b[1].owner?order(a[1].owner,b[1].owner):a[1].owner?-1:1);
 const nodes=[],lanes=[],links=[];let top=62;
 for(const [key,g] of ordered){
  let rows=0;const start=top;
  for(const q of g.questions){
   const cells=(cellsOf.get(q.id)||[]).sort(order),open=cells.length&&!collapsed.has(q.id);
   const y0=start+26+rows*38;
   if(open){cells.forEach((c,i)=>{parent.set(c.id,q.id);nodes.push({id:c.id,node:c,lane:key,level:1,x:190+420,y:y0+i*38,hidden:0});links.push({source:q.id,target:c.id,secondary:false,projected:false,originalEdges:[]});});}
   nodes.push({id:q.id,node:q,lane:key,level:0,x:190,y:open?y0+(cells.length-1)*19:y0,hidden:open?0:cells.length});
   rows+=open?cells.length:1;
  }
  const height=Math.max(1,rows)*38+28;
  lanes.push({id:key,owner:g.owner,y:start,height,count:g.questions.length,rootOnly:false});top+=height;
 }
 const ids=new Set(nodes.map(n=>n.id));
 const secondary=edgeList.filter(e=>e.relation!=='derived_from'&&ids.has(e.source)&&ids.has(e.target)&&!(e.relation==='compares'&&parent.get(e.target)===parent.get(e.source))).map(e=>({source:e.target,target:e.source,secondary:true,relation:e.relation}));
 return {nodes,lanes,links,secondary,parent,warnings:[],width:1120,height:Math.max(340,top+20),total:questions.length+[...cellsOf.values()].reduce((a,b)=>a+b.length,0),hierarchy:true};
}
function researchTreeModel(nodeMap, edgeList, collapsed=new Set(), focusId=null) {
 if(!hasCellLineage(nodeMap,edgeList)&&Object.values(nodeMap).some(n=>n.kind==='question'&&n.status!=='archived'))return hierarchyTreeModel(nodeMap,edgeList,collapsed);
 focusId=resolveTreeFocus(nodeMap,focusId);
 edgeList=projectedCellRelations(nodeMap,edgeList);
 const grouped=groupedRelationModel(nodeMap,edgeList),cells=grouped.groups.flatMap(g=>g.cells),byId=new Map(cells.map(n=>[n.id,n]));
 const parent=new Map(),warnings=[],order=(a,b)=>(a.attrs?.order??100)-(b.attrs?.order??100)||a.id.localeCompare(b.id);
 for(const n of cells){
  const declared=edgeList.filter(e=>e.relation==='derived_from'&&e.source===n.id);
  const known=declared.filter(e=>byId.has(e.target)).map(e=>e.target).sort();
  const p=known.includes(n.parent_id)?n.parent_id:known[0];
  if(p)parent.set(n.id,p);else if(!declared.length&&byId.has(n.parent_id))parent.set(n.id,n.parent_id);
  if(declared.length>1)warnings.push({id:n.id,type:'multiple_parents'});
  if(declared.some(e=>!byId.has(e.target)))warnings.push({id:n.id,type:'missing_parent'});
 }
 for(const n of [...cells].sort(order)){let p=n.id,seen=new Set();while(parent.has(p)){if(seen.has(p)){parent.delete(p);warnings.push({id:p,type:'cycle'});break;}seen.add(p);p=parent.get(p);}}
 const depth=new Map(),level=id=>{if(depth.has(id))return depth.get(id);const d=parent.has(id)?level(parent.get(id))+1:0;depth.set(id,d);return d;};
 cells.forEach(n=>level(n.id));
 let scope=null;
 if(focusId&&nodeMap[focusId]?.status!=='archived'&&nodeMap[focusId]){
  scope=new Set();
  for(const n of cells){let current=n,seen=new Set();while(current&&!seen.has(current.id)){seen.add(current.id);if(current.id===focusId){scope.add(n.id);break;}current=nodeMap[current.parent_id];}}
  // Keep every recorded origin, including secondary parents, as context.
  const pending=[...scope];while(pending.length){const id=pending.pop(),origins=[parent.get(id),...edgeList.filter(e=>e.source===id&&e.relation==='derived_from').map(e=>e.target)];for(const origin of origins)if(byId.has(origin)&&!scope.has(origin)){scope.add(origin);pending.push(origin);}}
 }
 const visible=cells.filter(n=>{if(scope&&!scope.has(n.id))return false;let p=parent.get(n.id);while(p){if(collapsed.has(p))return false;p=parent.get(p);}return true;}),visibleIds=new Set(visible.map(n=>n.id));
 const children=new Map();for(const n of cells){const p=parent.get(n.id);if(p){if(!children.has(p))children.set(p,[]);children.get(p).push(n.id);}}
 const countDesc=id=>(children.get(id)||[]).reduce((sum,child)=>sum+1+countDesc(child),0);
 const nodes=[],lanes=[];let top=62;
 const layoutGroups=scope?[{id:focusId,owner:nodeMap[focusId],cells:cells.filter(n=>scope.has(n.id))}]:grouped.groups;
 for(const group of layoutGroups){
  const members=group.cells.filter(n=>visibleIds.has(n.id));if(!members.length)continue;
  const memberIds=new Set(members.map(n=>n.id)),localChildren=new Map();
  for(const n of members){const p=parent.get(n.id);if(memberIds.has(p)){if(!localChildren.has(p))localChildren.set(p,[]);localChildren.get(p).push(n);}}
  for(const list of localChildren.values())list.sort(order);
  let leaf=0;const ys=new Map();
  const place=n=>{const kids=localChildren.get(n.id)||[];const y=kids.length?kids.map(place).reduce((a,b)=>a+b,0)/kids.length:top+26+leaf++*38;ys.set(n.id,y);return y;};
  members.filter(n=>!memberIds.has(parent.get(n.id))).sort(order).forEach(place);
  const height=Math.max(1,leaf)*38+28;
  lanes.push({id:group.id,owner:group.owner,y:top,height,count:members.length,rootOnly:members.every(n=>!parent.has(n.id))});
  for(const n of members)nodes.push({id:n.id,node:n,lane:group.id,level:level(n.id),x:190+level(n.id)*142,y:ys.get(n.id),hidden:collapsed.has(n.id)?countDesc(n.id):0});
  top+=height;
 }
 const links=nodes.filter(n=>parent.has(n.id)&&visibleIds.has(parent.get(n.id))).map(n=>{const edge=edgeList.find(e=>e.relation==='derived_from'&&e.source===n.id&&e.target===parent.get(n.id));return {source:parent.get(n.id),target:n.id,secondary:false,projected:!!edge?.projected,originalEdges:edge?.originalEdges||[]};});
 const secondary=edgeList.filter(e=>visibleIds.has(e.source)&&visibleIds.has(e.target)&&!(e.relation==='derived_from'&&parent.get(e.source)===e.target)).map(e=>({source:e.target,target:e.source,secondary:true,relation:e.relation}));
 return {nodes,lanes,links,secondary,parent,warnings:warnings.filter(w=>visibleIds.has(w.id)),width:Math.max(900,280+Math.max(0,...nodes.map(n=>n.level))*142),height:Math.max(340,top+20),total:cells.length};
}
// END research-tree-model
function currentTreeFocus(){return recordedTreeFocus(data.nodes);}
let treeHierarchyInit=false;
function displayedTreeModel(){
 if(!treeHierarchyInit&&!hasCellLineage(data.nodes,Object.values(data.edges))){treeHierarchyInit=true;let keep=data.nodes[selected];while(keep&&keep.kind!=='question')keep=data.nodes[keep.parent_id];const qs=Object.values(data.nodes).filter(n=>n.kind==='question');for(const q of qs)if(q.id!==keep?.id)treeCollapsed.add(q.id);}
 return researchTreeModel(data.nodes,Object.values(data.edges),treeCollapsed,treeShowAll||filter?null:currentTreeFocus());}
function treeOutcome(n){
 if(n.status==='failed'||children(n.id).some(r=>r.kind==='run'&&(r.status==='failed'||r.attrs?.backend_correct===false)))return 'failed';
 const selection=n.attrs?.selection;if(typeof selection==='string'){if(/^(保留|keep)/i.test(selection))return 'retained';if(/^(退步|同分|discard|tie)/i.test(selection))return 'unselected';}
 return 'recorded';
}
function hierarchyTreeLabel(p){const text=displayLabel(p.node),max=p.level===0?30:36;return (text.length>max?text.slice(0,max-1)+'…':text)+(p.hidden?`  ▸${p.hidden}`:'');}
function shortTreeLabel(n){const text=displayLabel(n),match=text.match(/^[A-Za-z]+\d+\b/);if(match)return match[0];if(Number.isInteger(n.attrs?.generation))return 'G'+n.attrs.generation;const runs=children(n.id).filter(r=>r.kind==='run'),runId=runs[0]?.attrs?.id;if(typeof runId==='string'&&runId.length<=24)return runId+(runs.length>1?' +'+(runs.length-1):'');const part=text.split('·')[0].trim();return part.length>11?part.slice(0,10)+'…':part;}
function treeNodeInspector(n){
 if(!n)return '';
 const local=(zh,en)=>lang==='zh'?zh:en;
 const related=Object.values(data.edges).filter(e=>e.source===n.id||e.target===n.id).filter(e=>data.nodes[e.source]&&data.nodes[e.target]);
 const links=related.map(e=>{const outgoing=e.source===n.id,id=outgoing?e.target:e.source;let relation=e.relation;if(relation==='derived_from')relation=outgoing?local('继承自','Derived from'):local('派生版本','Derivative');else if(relation==='inspired_by')relation=outgoing?local('参考自','Inspired by'):local('被参考于','Inspiration for');return `<button class="tree-source-link" data-select="${esc(id)}"><small>${esc(relation)}</small><span>${esc(shortTreeLabel(data.nodes[id]))}</span></button>`;}).join('');
 return `<aside class="tree-node-inspector" aria-label="${esc(t('inspector'))}"><header><span>${esc(local('节点详情','Node inspector'))}</span><button id="close-relation-detail" aria-label="${esc(t('close'))}">×</button></header><h3>${esc(displayLabel(n))}</h3><p>${esc(n.attrs?.selection||displayDescription(n)||'')}</p>${n.attrs?.metrics?metricKv(n.attrs.metrics):''}<div class="tree-source-links">${links}</div>${n.kind==='cell'?`<button id="tree-fold-selected" class="smallbtn">${esc(treeCollapsed.has(n.id)?local('展开后续','Expand descendants'):local('折叠后续','Fold descendants'))}</button>`:''}<details class="tree-evidence"><summary>${esc(local('实验记录与证据','Runs and evidence'))}</summary>${studyPanel(n)}</details></aside>`;
}
function renderResearchTree(){
 const model=displayedTreeModel(),positions=new Map(model.nodes.map(n=>[n.id,n]));
 const local=(zh,en)=>lang==='zh'?zh:en,n=relationInspect?data.nodes[selected]:null,path=new Set();
 if(n){let id=n.id;while(id&&!path.has(id)){path.add(id);id=model.parent.get(id);}}
 const colX=i=>model.hierarchy?190+i*420:190+i*142;
 const axes=Array.from({length:Math.max(0,...model.nodes.map(n=>n.level))+1},(_,i)=>`<text x="${colX(i)}" y="29" text-anchor="${model.hierarchy?'start':'middle'}" class="tree-level">${model.hierarchy?esc([local('研究问题','Research question'),local('实验条件 · 结果','Condition · result')][i]||''):'L'+i}</text>`).join('');
 const lanes=model.lanes.map((lane,i)=>{const name=lane.owner?displayLabel(lane.owner):local('未分组','Ungrouped');return `<g class="tree-lane"><rect x="0" y="${lane.y}" width="${model.width}" height="${lane.height}" fill="${i%2?'#f6f8f633':'#edf2ef55'}"/><line x1="160" x2="${model.width-25}" y1="${lane.y+lane.height-1}" y2="${lane.y+lane.height-1}"/><text x="15" y="${lane.y+lane.height/2+4}" ${lane.owner?`data-select="${esc(lane.owner.id)}" role="button" tabindex="0"`:''}><title>${esc(name)}</title>${esc(name.length>15?name.slice(0,14)+'…':name)}</text></g>`;}).join('');
 const textWidth=text=>[...text].reduce((w,ch)=>w+(/[\u2e80-\uffff]/.test(ch)?13:7),0);
 const edgePath=e=>{const a=positions.get(e.source),b=positions.get(e.target);const ax=model.hierarchy&&!e.secondary?Math.min(b.x-40,a.x+15+textWidth(hierarchyTreeLabel(a))+10):a.x;const mid=(ax+b.x)/2;return `M${ax},${a.y} C${mid},${a.y} ${mid},${b.y} ${b.x},${b.y}`;};
 const lines=[...model.links,...(treeSecondary?model.secondary:[])].map(e=>`<path class="tree-connection ${e.secondary?'secondary':''} ${n?(path.has(e.source)&&path.has(e.target)?'on-path':'muted'):''}" d="${edgePath(e)}"><title>${esc(e.projected?local('运行谱系：','Run lineage: ')+(e.originalEdges||[]).map(x=>x.source+' → '+x.target).join('; '):local('已记录关系','Recorded relation'))}</title></path>`).join('');
 const dots=model.nodes.map(p=>{const match=!filter||(displayLabel(p.node)+' '+displayDescription(p.node)+' '+p.id).toLowerCase().includes(filter.toLowerCase()),outcome=treeOutcome(p.node);return `<g class="research-dot ${outcome} ${p.id===selected&&n?'selected':''} ${!match?'filtered':''}" transform="translate(${p.x} ${p.y})" data-select="${esc(p.id)}" data-tree-node="${esc(p.id)}" role="button" tabindex="0" aria-label="${esc(local('查看 ','Inspect ')+displayLabel(p.node))}"><title>${esc(displayLabel(p.node))}${p.node.attrs?.selection?' — '+esc(p.node.attrs.selection):''}</title><circle class="node-halo" r="15"/><circle class="node-hit" r="20"/><circle class="node-dot-shape" r="8"/>${outcome==='failed'?'<path class="node-failure-mark" d="M-3,-3 L3,3 M-3,3 L3,-3"/>':''}${model.hierarchy?`<text x="15" y="4" class="node-label">${esc(hierarchyTreeLabel(p))}</text>`:`<text y="-20" text-anchor="middle" class="node-code">${esc(shortTreeLabel(p.node))}</text>${p.hidden?`<text y="30" text-anchor="middle" class="node-hidden">+${p.hidden}</text>`:''}`}</g>`;}).join('');
 const maxLevel=Math.max(0,...model.nodes.map(n=>n.level));
 const vertical=Array.from({length:maxLevel+1},(_,i)=>`<line class="tree-guide" x1="${colX(i)}" x2="${colX(i)}" y1="43" y2="${model.height-10}"/>`).join('');
 return `<div class="research-tree-shell ${treeFullscreen?'is-expanded':''}"><div class="research-tree-toolbar"><div class="tree-legend"><span class="recorded">${esc(local('已记录','Recorded'))}</span><span class="retained">${esc(local('保留','Retained'))}</span><span class="unselected">${esc(local('未选用','Not selected'))}</span><span class="failed">${esc(local('失败','Failed'))}</span></div><div class="tree-actions"><button id="tree-secondary" aria-pressed="${treeSecondary}">${esc(local('次级关系','Secondary links'))}</button><button id="tree-zoom-out" aria-label="${esc(local('缩小研究树','Zoom out'))}">−</button><span id="tree-zoom-value">${Math.round(treeCamera.scale*100)}%</span><button id="tree-zoom-in" aria-label="${esc(local('放大研究树','Zoom in'))}">+</button><button id="tree-fit">${esc(local('适应','Fit'))}</button><button id="tree-full">${esc(treeFullscreen?local('退出画布','Close canvas'):local('展开画布','Expand canvas'))}</button></div></div><div class="research-canvas" id="research-canvas" ${model.hierarchy?'data-hierarchy="1"':''}><svg id="research-tree-svg" viewBox="0 0 ${model.width} ${model.height}" ${model.hierarchy?`style="height:auto;aspect-ratio:${model.width}/${model.height}"`:''} aria-label="${esc(local('研究谱系树','Research lineage tree'))}"><g id="research-tree-transform" transform="translate(${treeCamera.x} ${treeCamera.y}) scale(${treeCamera.scale})">${lanes}${vertical}${axes}${lines}${dots}</g></svg>${!model.nodes.length?`<div class="tree-empty">${esc(local('暂无候选节点，可切换大纲查看记录。','No candidate nodes; use Outline to inspect records.'))}</div>`:''}${treeNodeInspector(n)}</div><div class="research-tree-foot"><span>${model.nodes.length} / ${model.total} ${esc(local('节点','nodes'))}${model.warnings.length?' · '+esc(local('关系待核查','Relations need review')):''}</span><span>${esc(local('拖动平移 · Ctrl＋滚轮缩放 · Shift＋点击折叠 · L 表示派生层级','Drag to pan · Ctrl+wheel to zoom · Shift+click to fold · L = lineage depth'))}</span></div></div>`;
}
function bindResearchTree(){
 const svg=$('research-tree-svg'),canvas=$('research-canvas');if(!svg)return;
 svg.setAttribute('preserveAspectRatio',canvas.clientWidth<600&&!treeFitMode?'xMinYMin slice':'xMidYMid meet');
 const model=displayedTreeModel();
 canvas.classList.toggle('is-focused',!!currentTreeFocus()&&!treeShowAll&&!filter);
 canvas.querySelectorAll('.node-code').forEach(text=>{if(text.getComputedTextLength()>112){text.setAttribute('textLength','112');text.setAttribute('lengthAdjust','spacingAndGlyphs');}});
 if(currentTreeFocus()){
  const label=document.createElement('label');label.className='tree-scope-control';
  const input=document.createElement('input');input.type='checkbox';input.checked=treeShowAll;input.id='tree-show-all';
  input.onchange=()=>{treeShowAll=input.checked;treeCamera={x:0,y:0,scale:1};drawMapBody();};
  label.append(input,document.createTextNode(lang==='zh'?'全部研究方向':'All research tracks'));
  canvas.parentElement.querySelector('.tree-actions').prepend(label);
 }
 const paint=()=>{$('research-tree-transform')?.setAttribute('transform',`translate(${treeCamera.x} ${treeCamera.y}) scale(${treeCamera.scale})`);const label=$('tree-zoom-value');if(label)label.textContent=Math.round(treeCamera.scale*100)+'%';};
 const zoom=factor=>{const next=Math.max(.35,Math.min(3,treeCamera.scale*factor)),ratio=next/treeCamera.scale;treeCamera.x=model.width/2-(model.width/2-treeCamera.x)*ratio;treeCamera.y=model.height/2-(model.height/2-treeCamera.y)*ratio;treeCamera.scale=next;paint();};
 $('tree-zoom-in').onclick=()=>zoom(1.25);$('tree-zoom-out').onclick=()=>zoom(.8);
 $('tree-fit').onclick=()=>{treeCamera={x:0,y:0,scale:1};treeFitMode=true;svg.setAttribute('preserveAspectRatio','xMidYMid meet');paint();};
 $('tree-secondary').onclick=()=>{treeSecondary=!treeSecondary;drawMapBody();};
 $('tree-full').onclick=()=>{treeFullscreen=!treeFullscreen;document.body.classList.toggle('tree-expanded',treeFullscreen);drawMapBody();};
 canvas.addEventListener('wheel',e=>{if(!e.ctrlKey)return;e.preventDefault();zoom(e.deltaY<0?1.1:1/1.1);},{passive:false});
 const point=e=>new DOMPoint(e.clientX,e.clientY).matrixTransform(svg.getScreenCTM().inverse());
 let drag=null;
 canvas.onpointerdown=e=>{if(e.button!==0||e.target.closest('[data-select],aside,button'))return;drag={p:point(e),x:treeCamera.x,y:treeCamera.y};canvas.setPointerCapture(e.pointerId);canvas.classList.add('dragging');};
 canvas.onpointermove=e=>{if(!drag)return;const p=point(e);treeCamera.x=drag.x+p.x-drag.p.x;treeCamera.y=drag.y+p.y-drag.p.y;paint();};
 canvas.onpointerup=canvas.onpointercancel=()=>{drag=null;canvas.classList.remove('dragging');};
 const fold=id=>{if(treeCollapsed.has(id))treeCollapsed.delete(id);else treeCollapsed.add(id);drawMapBody();};
 canvas.querySelectorAll('[data-tree-node]').forEach(el=>el.onclick=e=>{const id=el.dataset.treeNode;if(e.shiftKey||(model.hierarchy&&data.nodes[id]?.kind==='question')){e.preventDefault();if(model.hierarchy&&data.nodes[id]?.kind==='question'){if(treeCollapsed.has(id))treeCollapsed.delete(id);else treeCollapsed.add(id);selected=id;relationInspect=true;drawMapBody();}else fold(id);}else select(id);});
 const foldButton=$('tree-fold-selected');if(foldButton)foldButton.onclick=()=>fold(selected);
}
function drawMapBody() {
 const rootNodes=children(data.project.id).filter(isMapNode).filter(hasMatch);
 const lineage=selectedLineage(),pathIds=new Set(lineage.map(n=>n.id));
 const trail=lineage.length?`<div class="map-trail"><span>${esc(t('currentBranch'))}</span><div>${lineage.map((n,index)=>`${index?'<i aria-hidden="true">›</i>':''}<button type="button" data-select="${esc(n.id)}" aria-current="${index===lineage.length-1?'page':'false'}">${esc(displayLabel(n))}</button>`).join('')}</div></div>`:'';
 if(layout==='tree')$('map-body').innerHTML=`${trail}<div class="tree"><ul class="tree-list">${rootNodes.map(n=>treeNode(n,0,pathIds)).join('')||`<div class="empty">${esc(t('mapEmpty'))}</div>`}</ul></div>`;
 else $('map-body').innerHTML=renderResearchTree();
 bindNodeButtons($('map-body'));
 const close=$('close-relation-detail');if(close)close.onclick=()=>{relationInspect=false;drawMapBody();};
 if(layout==='lineage')bindResearchTree();
 $('map-body').querySelectorAll('[data-inline-evidence]').forEach(b=>b.onclick=()=>showEvidence(b.dataset.inlineEvidence,b.dataset.title));
}
function bindNodeButtons(root){root.querySelectorAll('[data-select]').forEach(b=>{b.onclick=()=>select(b.dataset.select);b.onkeydown=e=>{if(e.target===b&&(e.key==='Enter'||e.key===' ')){e.preventDefault();select(b.dataset.select);}};});root.querySelectorAll('[data-toggle]').forEach(b=>b.onclick=e=>{e.stopPropagation();const id=b.dataset.toggle,wasOpen=b.getAttribute('aria-expanded')==='true';if(wasOpen){expanded.delete(id);collapsedDuringSearch.add(id);let parent=selected,seen=new Set();while(parent&&parent!==id&&!seen.has(parent)){seen.add(parent);parent=data.nodes[parent]?.parent_id;}if(parent===id)selected=id;}else{expanded.add(id);collapsedDuringSearch.delete(id);if(!children(id).some(isMapNode))selected=id;}storageWrite();renderDetail();drawMapBody();});}
function kv(obj){return `<dl class="kv">${Object.entries(obj).map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(pretty(v))}</dd>`).join('')}</dl>`;}
function compactMetric(value){return typeof value==='number'&&Number.isFinite(value)&&!Number.isInteger(value)&&String(value).split('.')[1]?.length>4?`≈${value.toFixed(4)}`:pretty(value);}
function metricKv(obj){return `<dl class="kv">${Object.entries(obj).map(([k,v])=>`<dt>${esc(k)}</dt><dd title="${esc(pretty(v))}">${esc(compactMetric(v))}</dd>`).join('')}</dl>`;}
function renderDetail(){
 if(view==='semantic'){renderSemanticDetail();return;}
 const n=data.nodes[selected];
 if(!n){$('detail').innerHTML=`<div class="eyebrow">${esc(t('inspector'))}</div><h2>${esc(t('selectObject'))}</h2><p class="description">${esc(t('selectObjectHelp'))}</p>`;return;}
 const refs=n.evidence||[],related=Object.values(data.edges).filter(e=>e.source===n.id||e.target===n.id),attrs=n.attrs||{};
 let html=`<div class="eyebrow">${esc(label(n))} · ${esc(t('inspector'))}</div><h2>${esc(displayLabel(n))}</h2>${badge(n)} ${n.protected?`<span class="badge">${esc(t('protected'))}</span>`:''}<p class="description">${esc(displayDescription(n)||t('noDescription'))}</p>`;
 const overview=studySummary(n);if(overview){html+=`<div class="detail-section"><h3>${esc(t('studyResults'))}</h3>${overview.metrics?.length?`<div class="study-metrics">${overview.metrics.map(m=>`<div class="study-metric"><strong>${esc(m.value)}</strong><span>${esc(m.label)}</span></div>`).join('')}</div>`:''}${overview.columns?.length&&overview.rows?.length?`<div class="study-table-wrap"><table class="study-table"><thead><tr>${overview.columns.map(c=>`<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${overview.rows.map(row=>`<tr>${row.map(v=>`<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`:''}${overview.note?`<p class="study-note">${esc(overview.note)}</p>`:''}</div>`;}
 html+=`<details class="status-help"><summary>${esc(t('statusInfoTitle'))}</summary><p>${esc(t('statusInfo'))}</p></details>`;
 if(attrs.role)html+=`<div class="detail-section"><h3>${esc(t('researchRole'))}</h3><div class="note">${esc(roleLabel(n))}</div></div>`;
 if(attrs.design)html+=`<div class="detail-section"><h3>${esc(t('studyDesign'))}</h3>${kv(attrs.design)}</div>`;
 if(attrs.config)html+=`<div class="detail-section"><h3>${esc(t('actualConditions'))}</h3>${kv(attrs.config)}</div>`;
 if(attrs.metrics)html+=`<div class="detail-section"><h3>${esc(t('results'))}</h3>${kv(attrs.metrics)}<p class="description">${esc(attrs.metric_selection||attrs.selection||'')}</p></div>`;
 if(n.kind==='run')html+=`<div class="detail-section"><h3>${esc(t('runIdentity'))}</h3>${kv({seed:attrs.seed,code_revision:attrs.code_revision,eval_protocol:attrs.eval_protocol,identity:attrs.identity_basis})}</div>`;
 if(attrs.scope)html+=`<div class="detail-section"><h3>${esc(t('scope'))}</h3>${kv(attrs.scope.required_context||attrs.scope)}${attrs.scope.covered_values?'<h3>'+esc(t('coveredValues'))+'</h3>'+kv(attrs.scope.covered_values):''}</div>`;
 if(attrs.reopen_if)html+=`<div class="detail-section"><h3>${esc(t('reopenIf'))}</h3><div class="note">${esc(attrs.reopen_if)}</div></div>`;
 if(n.confirmation)html+=`<div class="detail-section"><h3>${esc(t('confirmation'))}</h3><div class="note">${esc(n.confirmation.note)}<br><small>${esc(n.confirmation.reviewer)} · ${esc(n.confirmation.at)}</small></div></div>`;
 if(attrs.next_action)html+=`<div class="detail-section"><h3>${esc(t('nextAction'))}</h3><div class="note">${esc(attrs.next_action)}</div></div>`;
 if(attrs.finding){const f=attrs.finding;html+=`<div class="detail-section"><h3>${esc(t('findingScope'))}</h3>${f.type?`<div class="note">${esc(t('findingType'))}: ${esc(enumLabel('finding_',f.type))}</div>`:''}${f.endpoint?kv(f.endpoint):''}${f.estimate?kv(f.estimate):''}${f.basis?`<p class="description">${esc(t('sourceBasis'))}: ${esc(enumLabel('basis_',f.basis))}</p>`:''}</div>`;}
 html+=`<div class="detail-section"><h3>${esc(t('sources'))} · ${refs.length}</h3>${refs.map(r=>{const f=data.files[r.file_id]||{},available=canOpenEvidence(r.sha256);return `<button class="evidence-btn" data-sha="${esc(r.sha256)}" data-title="${esc((f.source||'')+'/'+(f.path||r.file_id))}" ${available?'':'disabled'}>${esc(f.path||r.file_id)}<small>${esc(r.locator)} · ${esc((r.sha256||'').slice(0,12))}${snap&&!available?' · '+esc(t('offlineTextOmitted')):''}</small></button>`;}).join('')||`<div class="muted" style="font-size:11px;line-height:1.8">${esc(t('noDirectEvidence'))}</div>`}</div>`;
 if(n.evidence_ids?.length)html+=`<div class="detail-section"><h3>${esc(t('linkedEvidence'))}</h3>${n.evidence_ids.map(id=>`<button class="relation-btn" data-jump="${esc(id)}">${esc(displayLabel(data.nodes[id])||id)} ↗</button>`).join('')}</div>`;
 if(related.length)html+=`<div class="detail-section"><h3>${esc(t('relations'))}</h3>${related.map(e=>{const id=e.source===n.id?e.target:e.source;return `<button class="relation-btn" data-jump="${esc(id)}">${esc(e.relation)} · ${esc(displayLabel(data.nodes[id])||id)}</button>`;}).join('')}</div>`;
 html+=`<div class="detail-section"><small class="muted" style="font-size:9px;overflow-wrap:anywhere">${esc(n.id)}</small></div>`;
 $('detail').innerHTML=html;
 $('detail').querySelectorAll('[data-sha]').forEach(b=>b.onclick=()=>showEvidence(b.dataset.sha,b.dataset.title));
 $('detail').querySelectorAll('[data-jump]').forEach(b=>b.onclick=()=>select(b.dataset.jump));
}
function calculateRows(){
 const cells=Object.values(data.nodes).filter(n=>n.kind==='cell'&&n.status!=='archived'&&cellSelection.has(n.id)).sort(sortNodes);
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
  let warnings=[];if(invalidCellConfig||invalidRunConfig)warnings.push(t('configInvalid'));if(cellConfigConflict)warnings.push(t('configConflict'));if(conditions.size>1||versions.size>1)warnings.push(t('conditionConflict'));if(!protocolOK&&complete.length)warnings.push(t('protocolConflict'));if(Object.values(counts).some(n=>n>1))warnings.push(t('duplicateSeed'));if(complete.some(r=>dirtyRuns.has(r.id)))warnings.push(t('driftExcluded'));if(complete.length!==runs.length)warnings.push(t('incompleteExcluded'));if(complete.some(r=>!r.attrs.code_revision))warnings.push(t('revisionMissing'));
  return {cell:c,runs,used,mean,sd,n:vals.length,warnings};
 });
}
function compareGroupOf(cell){
 const model=cell.attrs?.config?.model;
 if(model!==null&&model!==undefined&&String(model).trim())return {key:'model:'+String(model).toLocaleLowerCase(),name:String(model),node:null};
 let current=data.nodes[cell.parent_id],fallback=null,seen=new Set();
 while(current&&!seen.has(current.id)){seen.add(current.id);if(current.kind==='module'){fallback??=current;if(['study','ablation_group','baseline_family','method_family','generalization'].includes(current.attrs?.role))return {key:'module:'+current.id,name:displayLabel(current),node:current};}current=data.nodes[current.parent_id];}
 return fallback?{key:'module:'+fallback.id,name:displayLabel(fallback),node:fallback}:{key:'unassigned',name:t('unknown'),node:null};
}
function renderCompare(){
 const cells=Object.values(data.nodes).filter(n=>n.kind==='cell'&&n.status!=='archived').sort(sortNodes),metricKeys=[...new Set(Object.values(data.nodes).filter(n=>n.kind==='run'&&n.status!=='archived'&&data.nodes[n.parent_id]?.status!=='archived').flatMap(n=>Object.keys(n.attrs.metrics||{})))].sort();
 const shownCells=cells.filter(c=>(displayLabel(c)+' '+JSON.stringify(c.attrs?.config||{})).toLowerCase().includes(compareFilter.toLowerCase()));
 const modelGroups=new Map();for(const c of shownCells){const group=compareGroupOf(c);if(!modelGroups.has(group.key))modelGroups.set(group.key,{...group,cells:[]});modelGroups.get(group.key).cells.push(c);}
 const groupEntries=[...modelGroups.values()].sort((a,b)=>a.node&&b.node?compareTreePath(a.node,b.node):a.name.localeCompare(b.name,lang==='zh'?'zh-CN':'en'));
 const groupPicker=groupEntries.map(g=>{const count=g.cells.filter(c=>cellSelection.has(c.id)).length,all=count===g.cells.length;return `<section class="compare-group"><div class="compare-group-head"><strong>${esc(g.name)} <small>${g.cells.length} ${esc(t('groupCells'))} · ${esc(t('groupSelected').replace('{count}',count))}</small></strong><button data-group="${esc(g.key)}" type="button">${esc(t(all?'groupClearAll':'groupSelectAll'))}</button></div><details data-group-details="${esc(g.key)}" ${compareOpenGroups.has(g.key)?'open':''}><summary>${esc(t('groupShowCells'))} · ${g.cells.length}</summary><div class="cell-picker">${g.cells.map(c=>`<label><input type="checkbox" data-cell="${esc(c.id)}" ${cellSelection.has(c.id)?'checked':''}>${esc(displayLabel(c))}</label>`).join('')}</div></details></section>`;}).join('');
 if(!metricKeys.includes(metric)&&metricKeys.length)metric=metricKeys[0];
 const rows=calculateRows(),keys=[...new Set(rows.flatMap(r=>Object.keys(r.cell.attrs.config||{})))].sort();
 const diff=k=>new Set(rows.map(r=>Object.hasOwn(r.cell.attrs.config||{},k)?JSON.stringify(r.cell.attrs.config[k]):'<MISSING>')).size>1;
 const stat=v=>v===null?'—':v.toFixed(4);
 let html=`<div class="panel-head"><div><h2>${esc(t('comparePanel'))}</h2><small>${esc(t('compareHint'))}</small></div></div><div class="compare-picker-tools"><input class="search" id="compare-search" type="search" aria-label="${esc(t('compareSearch'))}" placeholder="${esc(t('compareSearch'))}" value="${esc(compareFilter)}"><button id="select-visible" type="button">${esc(t('selectVisible'))}</button><button id="clear-selection" type="button">${esc(t('clearSelection'))}</button><span>${esc(t('selectedCells').replace('{count}',cellSelection.size))}</span></div><div class="compare-groups">${groupPicker}</div><div class="matrix-options"><label><input type="checkbox" id="diff-only" ${differentOnly?'checked':''}> ${esc(t('diffOnly'))}</label><label>${esc(t('metric'))} <select id="metric-select">${metricKeys.map(k=>`<option ${k===metric?'selected':''}>${esc(k)}</option>`).join('')}</select></label></div>`;
 if(rows.length)html+=`<div class="table-wrap"><table class="matrix"><thead><tr><th>${esc(t('conditions'))}</th>${rows.map(r=>`<th><button class="linkbutton" data-cell-detail="${esc(r.cell.id)}">${esc(displayLabel(r.cell))} ↗</button></th>`).join('')}</tr></thead><tbody>${keys.filter(k=>!differentOnly||diff(k)).map(k=>`<tr class="${diff(k)?'diff':''}"><td>${esc(k)}</td>${rows.map(r=>`<td>${Object.hasOwn(r.cell.attrs.config||{},k)?esc(pretty(r.cell.attrs.config[k])):`<span class="unknown">${esc(t('unknown'))}</span>`}</td>`).join('')}</tr>`).join('')}<tr><td>${esc(t('recordedRuns'))}</td>${rows.map(r=>`<td>${r.runs.length}</td>`).join('')}</tr><tr><td>${esc(t('includedSeeds'))}</td>${rows.map(r=>`<td>${r.n}</td>`).join('')}</tr><tr><td>${esc(metric)}<span class="matrix-sub">${esc(t('meanSd'))}</span></td>${rows.map(r=>`<td><strong>${stat(r.mean)}</strong><span class="matrix-sub">SD ${stat(r.sd)}</span>${r.used.map(n=>`<button class="linkbutton matrix-sub" data-run="${esc(n.id)}">seed ${esc(n.attrs.seed)} → ${esc(pretty(n.attrs.metrics[metric]))}</button>`).join('')}</td>`).join('')}</tr><tr><td>${esc(t('reviewHints'))}</td>${rows.map(r=>`<td>${r.warnings.map(esc).join('<br>')||esc(t('descriptiveOnly'))}</td>`).join('')}</tr></tbody></table></div>`;else html+=`<div class="empty">${esc(t('noCells'))}</div>`;
 const controls=['dataset_version','eval_protocol','train_steps'];
 const controlWarnings=controls.filter(k=>rows.some(r=>r.cell.attrs.config?.[k]===undefined)||diff(k));
 const runCells=new Map();
 for(const row of rows)for(const run of row.used){const id=run.attrs?.run_id;if(id!==null&&id!==undefined){if(!runCells.has(String(id)))runCells.set(String(id),new Set());runCells.get(String(id)).add(row.cell.id);}}
 const sharedRuns=[...runCells.values()].filter(cells=>cells.size>1).length;
 html+=`<div class="matrix-notes">${esc(t('unitNote'))}${sharedRuns?`<br><strong>${esc(t('sharedTrainingRuns').replace('{count}',sharedRuns))}</strong>`:''}${controlWarnings.length?`<br>${esc(t('comparability'))}${controlWarnings.map(esc).join(lang==='zh'?'、':', ')}.`:''}<br>${esc(t('implementationNote'))}</div>`;
 $('content').innerHTML=html;
 $('compare-search').oninput=e=>{if(e.isComposing)return;compareFilter=e.target.value;const cursor=e.target.selectionStart;renderCompare();$('compare-search').focus();$('compare-search').setSelectionRange(cursor,cursor);};
 $('select-visible').onclick=()=>{shownCells.forEach(c=>cellSelection.add(c.id));renderCompare();};
 $('clear-selection').onclick=()=>{cellSelection.clear();renderCompare();};
 document.querySelectorAll('[data-group]').forEach(b=>b.onclick=()=>{const group=modelGroups.get(b.dataset.group);if(!group)return;const all=group.cells.every(c=>cellSelection.has(c.id));group.cells.forEach(c=>all?cellSelection.delete(c.id):cellSelection.add(c.id));renderCompare();});
 document.querySelectorAll('[data-group-details]').forEach(d=>d.ontoggle=()=>{d.open?compareOpenGroups.add(d.dataset.groupDetails):compareOpenGroups.delete(d.dataset.groupDetails);});
 document.querySelectorAll('[data-cell]').forEach(b=>b.onchange=()=>{b.checked?cellSelection.add(b.dataset.cell):cellSelection.delete(b.dataset.cell);renderCompare();});
 $('diff-only').onchange=e=>{differentOnly=e.target.checked;renderCompare();};$('metric-select').onchange=e=>{metric=e.target.value;renderCompare();};
 document.querySelectorAll('[data-run]').forEach(b=>b.onclick=()=>select(b.dataset.run));document.querySelectorAll('[data-cell-detail]').forEach(b=>b.onclick=()=>select(b.dataset.cellDetail));
}
function renderDecisions(){
 const nodes=Object.values(data.nodes).filter(n=>['decision','claim'].includes(n.kind));
 const card=(n,tier)=>{const attrs=n.attrs||{},presentation=attrs.finding_card?.[lang]||null,refs=n.evidence||[],scope=attrs.scope,term=tier==='primary'?'primaryFinding':tier==='secondary'?'secondaryFinding':tier==='decision'?'historicalDecisions':'auditRecords';
  const hero=presentation?`<div class="finding-hero"><strong>${esc(presentation.value)}</strong><span>${esc(presentation.label)}</span></div>`:findingSummary(n)?`<div class="finding-hero finding-hero-fallback"><span>${esc(findingSummary(n))}</span></div>`:'';
  const context=presentation?`<p class="finding-context">${esc(presentation.context)}</p><p class="finding-limit">${esc(presentation.limit)}</p>`:`<p class="finding-context">${esc(displayDescription(n))}</p>`;
  const sources=refs.length?`<div class="finding-source-list"><h5>${esc(t('sources'))} · ${refs.length}</h5>${refs.map(r=>{const f=data.files[r.file_id]||{};return `<button type="button" data-finding-sha="${esc(r.sha256)}" data-title="${esc(f.path||r.file_id)}" ${canOpenEvidence(r.sha256)?'':'disabled'}>${esc(f.path||r.file_id)}<small>${esc(r.locator)} · ${esc(r.sha256.slice(0,12))}</small></button>`;}).join('')}</div>`:'';
  const fields=`${scope?`<div class="finding-extra"><h5>${esc(t('scope'))}</h5>${kv(scope.required_context||scope)}${scope.covered_values?kv(scope.covered_values):''}</div>`:''}${attrs.finding?.endpoint||attrs.finding?.estimate?`<div class="finding-extra"><h5>${esc(t('findingScope'))}</h5>${attrs.finding.endpoint?kv(attrs.finding.endpoint):''}${attrs.finding.estimate?kv(attrs.finding.estimate):''}</div>`:''}${attrs.reopen_if?`<div class="finding-extra"><h5>${esc(t('reopenIf'))}</h5><p>${esc(attrs.reopen_if)}</p></div>`:''}${attrs.next_action?`<div class="finding-extra"><h5>${esc(t('nextAction'))}</h5><p>${esc(attrs.next_action)}</p></div>`:''}${n.confirmation?`<div class="finding-extra"><h5>${esc(t('confirmation'))}</h5><p>${esc(n.confirmation.note)} · ${esc(n.confirmation.reviewer)} · ${esc(n.confirmation.at)}</p></div>`:''}`;
  return `<article class="decision finding-card finding-card-${tier}" data-finding-id="${esc(n.id)}"><div class="finding-card-top"><span class="finding-tier">${esc(t(term))}</span><span class="finding-count">${refs.length} ${esc(t('evidenceCount'))}</span></div><h3>${esc(displayLabel(n))}</h3>${hero}${context}<details class="finding-more"><summary>${esc(t('fullFindingDetails'))}</summary>${presentation?`<p class="finding-full-text">${esc(displayDescription(n))}</p>`:''}${fields}${sources}<small class="finding-id">${esc(n.id)}</small></details></article>`;};
 const themed=(list,tier)=>{const groups=new Map();for(const n of list){const theme=themeOf(n),key=theme?.id||'_other';if(!groups.has(key))groups.set(key,{theme,items:[]});groups.get(key).items.push(n);}return [...groups.values()].sort((a,b)=>a.theme&&b.theme?sortNodes(a.theme,b.theme):a.theme?-1:b.theme?1:0).map(g=>`<section class="finding-theme"><h4>${esc(g.theme?displayLabel(g.theme):t('otherTheme'))}</h4>${g.items.sort(compareTreePath).map(n=>card(n,tier)).join('')}</section>`).join('');};
 const primary=nodes.filter(n=>n.kind==='claim'&&findingPriority(n)==='primary');
 const secondary=nodes.filter(n=>n.kind==='claim'&&findingPriority(n)==='secondary');
 const decisions=nodes.filter(n=>n.kind==='decision');
 const audit=nodes.filter(n=>n.kind==='claim'&&!['primary','secondary'].includes(findingPriority(n)));
 const section=(title,list,tier,empty)=>`<section class="finding-section finding-section-${tier}"><div class="finding-section-head"><h3>${esc(t(title))}</h3><span>${list.length}</span></div>${list.length?themed(list,tier):`<div class="finding-empty">${esc(t(empty))}</div>`}</section>`;
 $('content').innerHTML=`<div class="panel-head"><div><h2>${esc(t('decisionsPanel'))}</h2><small>${esc(t('decisionsHint'))}</small></div></div><div class="decision-list">${section('mainFindings',primary,'primary','noMainFindings')}${secondary.length?section('secondaryFindings',secondary,'secondary','noMainFindings'):''}${section('historicalDecisions',decisions,'decision','noHistoricalDecisions')}${audit.length?`<details class="audit-records"><summary>${esc(t('auditRecords'))} · ${audit.length}</summary>${themed(audit,'audit')}</details>`:''}</div><details class="status-help"><summary>${esc(t('statusInfoTitle'))}</summary><p>${esc(t('statusInfo'))}</p></details>`;
 $('content').querySelectorAll('[data-finding-sha]').forEach(b=>b.onclick=()=>showEvidence(b.dataset.findingSha,b.dataset.title));
}
function renderSources(){
 const mappedIds=new Set(Object.values(data.nodes).flatMap(n=>(n.evidence||[]).map(r=>r.file_id))),allCount=Object.keys(data.files).length;
 if(!mappedIds.size)sourceMode='all';
 $('content').innerHTML=`<div class="panel-head"><div><h2>${esc(t('sourcesPanel'))}</h2><small>${esc(t('sourcesHint'))}</small></div></div><div class="source-modes">${[['mapped',mappedIds.size],['unmapped',allCount-mappedIds.size],['all',allCount]].map(([mode,count])=>`<button type="button" data-source-mode="${mode}" aria-pressed="${sourceMode===mode}">${esc(t(mode==='mapped'?'mappedSources':mode==='unmapped'?'unmappedSources':'allIndexedSources'))} · ${count}</button>`).join('')}</div><p class="source-scope-hint">${esc(t('sourceScopeHint'))}</p><div class="search-wrap"><input class="search" id="source-search" placeholder="${esc(t('sourcesSearch'))}" value="${esc(filter)}"></div><div class="source-list" id="source-list"></div>`;
 $('source-search').oninput=e=>{filter=e.target.value;sourcePage=0;drawSources();};drawSources();
 $('content').querySelectorAll('[data-source-mode]').forEach(b=>b.onclick=()=>{sourceMode=b.dataset.sourceMode;sourcePage=0;renderSources();});
}
function drawSources(){
 const mappedIds=new Set(Object.values(data.nodes).flatMap(n=>(n.evidence||[]).map(r=>r.file_id)));
 const files=Object.values(data.files).filter(f=>(sourceMode==='all'||(sourceMode==='mapped')===mappedIds.has(f.id))&&(f.source+'/'+f.path).toLowerCase().includes(filter.toLowerCase())).sort((a,b)=>a.path.localeCompare(b.path)),page=files.slice(sourcePage*40,(sourcePage+1)*40);
 $('source-list').innerHTML=(page.map(f=>{const available=canOpenEvidence(f.sha256),omitted=!!snap&&!!f.sha256&&!available;return `<div class="source"><div class="source-name">${esc(f.path)}<small>${esc(f.source)} · ${((f.size||0)/1024).toFixed(1)} KB · ${esc(t(f.missing?'missingSource':omitted?'offlineTextOmitted':f.sha256?'savedSnapshot':'locationOnly'))}</small></div><button data-source-sha="${esc(f.sha256||'')}" data-title="${esc(f.path)}" ${available?'':'disabled'}>${esc(t(available?'view':'index'))}</button></div>`;}).join('')||`<div class="empty">${esc(t('noSources'))}</div>`)+`<div class="panel-tools" style="margin-top:17px"><button id="prev-source" ${sourcePage?'':'disabled'}>${esc(t('previous'))}</button><span class="muted" style="font-size:11px">${files.length?sourcePage*40+1:0}–${Math.min((sourcePage+1)*40,files.length)} / ${files.length}</span><button id="next-source" ${(sourcePage+1)*40<files.length?'':'disabled'}>${esc(t('next'))}</button></div>`;
 $('prev-source').onclick=()=>{sourcePage--;drawSources();};$('next-source').onclick=()=>{sourcePage++;drawSources();};
 document.querySelectorAll('[data-source-sha]').forEach(b=>b.onclick=()=>showEvidence(b.dataset.sourceSha,b.dataset.title));
}
function moduleOfNode(id,parentId){
 let current=id||parentId,seen=new Set();
 while(current&&!seen.has(current)){seen.add(current);const node=data.nodes[current];if(node?.kind==='module')return current;current=node?.parent_id||(!node&&current===id?parentId:null);}
 return null;
}
function historyChangeLabel(change){return t({added:'changeAdded',updated:'changeUpdated',missing:'missingSource',restored:'changeAdded',metadata:'changeUpdated',archived:'archived',removed:'changeRemoved'}[change]||'changeUnknown');}
function historyMatchesModule(item,type,fileModules){
 if(historyModule==='all')return true;
 if(type==='nodes')return (item.module_id||moduleOfNode(item.id,item.parent_id))===historyModule;
 if(type==='files')return fileModules.get(item.id)?.has(historyModule)||false;
 if(type==='edges'){const edge=data.edges[item.id];return !!edge&&(moduleOfNode(edge.source)===historyModule||moduleOfNode(edge.target)===historyModule);}
 return false;
}
function timelineSwitch(){return `<div class="timeline-switch" role="group" aria-label="${esc(t('navHistory'))}"><button type="button" data-timeline-view="project" aria-pressed="${timelineView==='project'}">${esc(t('projectTimeline'))}</button><button type="button" data-timeline-view="record" aria-pressed="${timelineView==='record'}">${esc(t('recordTimeline'))}</button></div>`;}
function bindTimelineSwitch(){$('content').querySelectorAll('[data-timeline-view]').forEach(b=>b.onclick=()=>{timelineView=b.dataset.timelineView;renderHistory();});}
function eventRootModule(n){let current=data.nodes[n.parent_id],seen=new Set();while(current&&!seen.has(current.id)){seen.add(current.id);if(current.kind==='module'&&current.parent_id===data.project.id)return current.id;current=data.nodes[current.parent_id];}return null;}
function eventTime(n){const label=n.attrs?.project_event?.date_label?.zh||'';const match=label.match(/(?:^|\D)(\d{1,2}):(\d{2})(?:\D|$)/);return match?Number(match[1])*60+Number(match[2]):null;}
function renderProjectTimeline(events){
 const roots=[...new Set(events.map(eventRootModule).filter(Boolean))].map(id=>data.nodes[id]).sort(sortNodes);
 const shown=events.filter(n=>(projectTimelineModule==='all'||eventRootModule(n)===projectTimelineModule)&&(projectTimelineType==='all'||n.attrs.project_event.date_precision===projectTimelineType));
 const cards=shown.map(n=>{const event=n.attrs.project_event,refs=n.evidence||[],related=(event.related_ids||[]).filter(id=>data.nodes[id]);return `<article class="project-event"><details data-project-event="${esc(n.id)}"><summary><time datetime="${esc(event.date)}">${esc(event.date_label?.[lang]||event.date)}</time><span class="project-event-copy"><strong>${esc(displayLabel(n))}</strong><small>${esc(displayDescription(n))}</small></span><span class="event-chevron" aria-hidden="true">⌄</span></summary><div class="project-event-detail">${event.date_basis?.[lang]?`<p><b>${esc(t('eventDateBasis'))}：</b>${esc(event.date_basis[lang])}</p>`:''}${related.length?`<div class="project-event-links"><b>${esc(t('eventRelated'))}</b>${related.map(id=>`<button data-event-node="${esc(id)}">${esc(displayLabel(data.nodes[id]))} ↗</button>`).join('')}</div>`:''}<div class="project-event-links"><b>${esc(t('eventEvidence'))} · ${refs.length}</b>${refs.map(r=>{const f=data.files[r.file_id]||{};return `<button data-event-sha="${esc(r.sha256)}" data-title="${esc(f.path||r.file_id)}" ${canOpenEvidence(r.sha256)?'':'disabled'}>${esc(r.locator||f.path||r.file_id)} ↗</button>`;}).join('')}</div></div></details></article>`;}).join('');
 $('content').innerHTML=`<div class="panel-head"><div><h2>${esc(t('timelinePanel'))}</h2><small>${esc(t('projectTimelineHint'))}</small></div></div>${timelineSwitch()}<div class="history-filters"><label>${esc(t('projectEventModule'))} <select id="project-timeline-module"><option value="all">${esc(t('allModules'))}</option>${roots.map(n=>`<option value="${esc(n.id)}" ${projectTimelineModule===n.id?'selected':''}>${esc(displayLabel(n))}</option>`).join('')}</select></label><label>${esc(t('projectEventDateType'))} <select id="project-timeline-type">${[['all','allProjectEvents'],['day','eventDay'],['range_start','eventRangeStart'],['as_of','eventAsOf']].map(([value,key])=>`<option value="${value}" ${projectTimelineType===value?'selected':''}>${esc(t(key))}</option>`).join('')}</select></label></div>${shown.length?`<div class="project-timeline">${cards}<div class="timeline-end">↓ ${esc(t('timelineDirection'))}</div></div>`:`<div class="empty">${esc(events.length?t('noMatchingProjectEvents'):t('noProjectEvents'))}</div>`}`;
 $('project-timeline-module').onchange=e=>{projectTimelineModule=e.target.value;renderHistory();};$('project-timeline-type').onchange=e=>{projectTimelineType=e.target.value;renderHistory();};
 bindTimelineSwitch();$('content').querySelectorAll('[data-event-node]').forEach(b=>b.onclick=()=>{timelineReturnEvent=b.closest('[data-project-event]')?.dataset.projectEvent||null;view='map';select(b.dataset.eventNode);render();const target=document.querySelector(`.node-card[data-select="${b.dataset.eventNode}"]`);if(target){target.focus({preventScroll:true});requestAnimationFrame(()=>scrollMapTarget(target));}});$('content').querySelectorAll('[data-event-sha]').forEach(b=>b.onclick=()=>showEvidence(b.dataset.eventSha,b.dataset.title));
}
function renderHistory(){
 const projectEvents=Object.values(data.nodes).filter(n=>n.kind==='artifact'&&n.status!=='archived'&&n.attrs?.project_event?.date&&(n.evidence||[]).length).sort((a,b)=>a.attrs.project_event.date.localeCompare(b.attrs.project_event.date)||((eventTime(a)??-1)-(eventTime(b)??-1))||displayLabel(a).localeCompare(displayLabel(b)));
 if(timelineView==='project'){renderProjectTimeline(projectEvents);return;}
 const modules=Object.values(data.nodes).filter(n=>n.kind==='module');
 const fileModules=new Map();
 for(const node of Object.values(data.nodes)){const moduleId=moduleOfNode(node.id,node.parent_id);if(!moduleId)continue;for(const ref of node.evidence||[]){if(!fileModules.has(ref.file_id))fileModules.set(ref.file_id,new Set());fileModules.get(ref.file_id).add(moduleId);}}
 if(historyModule!=='all'&&!modules.some(n=>n.id===historyModule))historyModule='all';
 const options=[['all','allChanges'],['files','fileChanges'],['nodes','nodeChanges'],['edges','edgeChanges']];
 const entries=[...(data.history||[])].reverse().map(entry=>{
  const changes=entry.changes,groups={files:[],nodes:[],edges:[]};
  if(changes)for(const type of ['files','nodes','edges'])groups[type]=(Array.isArray(changes[type])?changes[type]:[]).filter(item=>historyMatchesModule(item,type,fileModules));
  if(changes&&(historyType!=='all'||historyModule!=='all')&&!Object.entries(groups).some(([type,items])=>(historyType==='all'||historyType===type)&&items.length))return '';
  if(!changes&&(historyType!=='all'||historyModule!=='all'))return '';
  const section=(type,items)=>!items.length||(historyType!=='all'&&historyType!==type)?'':`<div class="history-group"><h4>${esc(t(type))} · ${items.length}</h4>${items.map(item=>{
   const name=type==='files'?`${item.source?item.source+'/':''}${item.path||item.id}`:type==='nodes'?displayLabel(data.nodes[item.id])||item.label||item.id:item.id;
   const kind=type==='nodes'&&item.kind?`<span class="history-kind">${esc(t(item.kind))}</span>`:'';
   const link=type==='nodes'&&data.nodes[item.id]?`<button class="history-change" data-history-node="${esc(item.id)}"><span class="history-change-tag">${esc(historyChangeLabel(item.change))}</span>${kind}<span class="history-change-name">${esc(name)}</span>↗</button>`:type==='files'&&data.files[item.id]?`<button class="history-change" data-history-file="${esc(item.id)}"><span class="history-change-tag">${esc(historyChangeLabel(item.change))}</span><span class="history-change-name">${esc(name)}</span>↗</button>`:`<div class="history-change"><span class="history-change-tag">${esc(historyChangeLabel(item.change))}</span>${kind}<span class="history-change-name">${esc(name)}</span></div>`;
   return link;
  }).join('')}</div>`;
  return `<article class="history-item"><b>${esc(t('revision'))} ${esc(entry.revision)}</b><div>${esc(entry.reason||t('unknownReason'))}</div><small>${esc(entry.actor||t('unknownActor'))} · ${esc(entry.at||'')}</small>${changes?`<details class="history-details" ${groups.files.length+groups.nodes.length+groups.edges.length<=5?'open':''}><summary>${['files','nodes','edges'].filter(type=>historyType==='all'||historyType===type).map(type=>`${esc(t(type))} ${groups[type].length}`).join(' · ')}</summary>${section('files',groups.files)}${section('nodes',groups.nodes)}${section('edges',groups.edges)}</details>`:`<p class="history-legacy">${esc(t('oldHistory'))}</p>`}</article>`;
 }).filter(Boolean);
 $('content').innerHTML=`<div class="panel-head"><div><h2>${esc(t('timelinePanel'))}</h2><small>${esc(t('recordTimelineHint'))}</small></div></div>${timelineSwitch()}<div class="history-filters"><div class="view-switch" role="group" aria-label="${esc(t('allChanges'))}">${options.map(([type,key])=>`<button data-history-type="${type}" class="${historyType===type?'active':''}" aria-pressed="${historyType===type}">${esc(t(key))}</button>`).join('')}</div><label>${esc(t('modules'))} <select id="history-module"><option value="all">${esc(t('allModules'))}</option>${modules.map(n=>`<option value="${esc(n.id)}" ${historyModule===n.id?'selected':''}>${esc(displayLabel(n))}</option>`).join('')}</select></label></div><div class="history">${entries.join('')||`<div class="empty">${esc(t((data.history||[]).length?'noMatchingHistory':'historyEmpty'))}</div>`}</div>`;
 bindTimelineSwitch();
 document.querySelectorAll('[data-history-type]').forEach(button=>button.onclick=()=>{historyType=button.dataset.historyType;renderHistory();});
 $('history-module').onchange=e=>{historyModule=e.target.value;renderHistory();};
 document.querySelectorAll('[data-history-node]').forEach(button=>button.onclick=()=>{view='map';select(button.dataset.historyNode);render();});
 document.querySelectorAll('[data-history-file]').forEach(button=>button.onclick=()=>{const file=data.files[button.dataset.historyFile];if(file){setView('sources');filter=file.path;renderSources();}});
}
let focusBeforeModal=null;
function openModal(){focusBeforeModal=document.activeElement;$('modal').hidden=false;$('close-modal').focus();}
function closeModal(){if($('modal').hidden)return;$('modal').hidden=true;if(focusBeforeModal?.isConnected)focusBeforeModal.focus();focusBeforeModal=null;}
async function showEvidence(sha,title){openModal();$('modal-title').textContent=title||t('evidenceSnapshot');$('modal-subtitle').textContent='SHA-256 '+sha;$('evidence-content').textContent=t('loading');try{let text;if(snap){text=data.evidence_texts?.[sha];if(text===undefined)throw new Error(t('snapshotOmitted'));}else text=await(await api('/api/evidence?sha='+encodeURIComponent(sha))).text();$('evidence-content').textContent=text.split('\n').map((line,i)=>String(i+1).padStart(4,' ')+'  '+line).join('\n');}catch(e){$('evidence-content').textContent=e.message;}}
function download(name,text,type){const u=URL.createObjectURL(new Blob([text],{type})),a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);}
function init(){
 staticLanguage();document.querySelectorAll('[data-lang]').forEach(button=>button.onclick=()=>setLanguage(button.dataset.lang));
 $('nav').querySelectorAll('button').forEach(b=>b.onclick=()=>setView(b.dataset.view));
 $('refresh').onclick=()=>snap?toast(t('staticSnapshot')):load();
 $('close-modal').onclick=closeModal;
 $('modal').onclick=e=>{if(e.target===$('modal'))closeModal();};
 document.addEventListener('keydown',e=>{if($('modal').hidden)return;if(e.key==='Escape'){e.preventDefault();closeModal();}else if(e.key==='Tab'){e.preventDefault();const focusable=[$('close-modal'),$('evidence-content')],index=focusable.indexOf(document.activeElement);focusable[(index+(e.shiftKey?-1:1)+focusable.length)%focusable.length].focus();}});
 $('copy-prompt').onclick=async()=>{const text=t('prompt').replace('{project}',data?`「${data.project.name}」`:'');try{await navigator.clipboard.writeText(text);toast(t('copied'));}catch(_){openModal();$('modal-title').textContent=t('copyToAgent');$('modal-subtitle').textContent=t('noNewAgent');$('evidence-content').textContent=text;}};
 $('export-json').onclick=()=>{if(data){download('research-records-r'+data.revision+'.json',JSON.stringify(data,null,2),'application/json');toast(t('exportWarning'));}};
 window.addEventListener('keydown',e=>{if(e.key==='Escape'&&treeFullscreen){treeFullscreen=false;document.body.classList.remove('tree-expanded');drawMapBody();}});
 {const m=/view=(\w+)/.exec(location.hash);if(m&&['map','semantic','compare','decisions','sources','history'].includes(m[1]))view=m[1];}{const m=/tab=(\w+)/.exec(location.hash);if(m&&['summary','claims','experiments','timeline','invalid','open'].includes(m[1]))semTab=m[1];}{const m=/sel=((?:claim|exp|phase|inv|open|comp|read):\d+)/.exec(location.hash);if(m)semSel=m[1];}
 load();
}
/* Paper view: an agent-written semantic map (claims, experiments by research question, timeline), every number
   checked by `labweft trace verify-map`, published with `labweft trace publish-map`. */
let semTab='summary',semSel=null,semQuery='';
const SEM_ST={'成立':'','部分成立':'review','待验证':'review','已被取代':'provisional','已撤回':'provisional','有效':'','作废':'provisional','进行中':'review'};
const SEM_TONE={'成立':'ok','有效':'ok','部分成立':'warn','待验证':'warn','进行中':'warn','已被取代':'old','已撤回':'old','作废':'old'};
const SEM_CK={verified:'✓',partly:'◐',problem:'⚠',unchecked:'·'};
const SEM_NC={ok:'✓',ok_derived:'✓≈',number_not_at_source:'⚠',path_missing:'⚠',line_out_of_range:'⚠',unreadable:'?',no_source:'?'};
function semBadge(txt,cls=''){return `<span class="badge ${cls}">${esc(txt)}</span>`}
function semTxt(zh,en){return lang==='en'?en:zh}
const SEM_EN={'成立':'Holds','部分成立':'Partly holds','待验证':'To verify','已被取代':'Superseded','已撤回':'Retracted','有效':'Valid','作废':'Void','进行中':'Ongoing','主实验':'Main experiment','消融':'Ablation','对照':'Control','基线':'Baseline','诊断/机制分析':'Diagnostic / mechanism','机制分析':'Mechanism','重评':'Re-evaluation','复评':'Re-evaluation','超参搜索':'Hyperparameter search','可视化':'Visualization'};
function semWord(x){return lang==='en'&&SEM_EN[x]?SEM_EN[x]:x}
function semStatus(s){return s?`<span class="pv-status ${SEM_TONE[s]||'warn'}">${esc(semWord(s))}</span>`:''}
function semCheck(ck){const ok=ck==='verified',bad=ck==='problem';return ck?`<span class="pv-check ${ok?'ok':bad?'bad':'part'}" title="${esc(semTxt('数字核对：','Number check: ')+ck)}">${ok?'✓':bad?'!':'◐'}</span>`:''}
function semNum(n){const ok=n._check==='ok'||n._check==='ok_derived';return `<span class="pv-num ${n._check?ok?'ok':'bad':''}" title="${esc((n.meaning||'')+(n.source?'\n'+n.source:''))}"><b>${esc(n.value)}</b>${n.meaning?`<i>${esc(String(n.meaning).length>22?String(n.meaning).slice(0,21)+'…':n.meaning)}</i>`:''}</span>`}
function semBars(results,limit=8){
 const rows=(results||[]).slice(0,limit),vals=rows.map(r=>typeof r.value==='number'?r.value:null);
 const nums=vals.filter(v=>v!==null),max=nums.length?Math.max(...nums):0,bars=nums.length>=2&&Math.min(...nums)>=0&&max>0;
 return `<div class="pv-results">${rows.map((r,i)=>{const v=vals[i],w=bars&&v!==null?Math.max(2,100*v/max):0,ok=r._check==='ok'||r._check==='ok_derived';
  return `<div class="pv-row"><span class="pv-cond" title="${esc(r.condition)}">${esc(r.condition)}</span><span class="pv-track">${bars?`<span class="pv-bar" style="width:${w.toFixed(1)}%"></span>`:''}</span><span class="pv-val">${esc(r.value)}${r.sd!=null?`<small> ± ${esc(r.sd)}</small>`:''}${r._check?`<em class="${ok?'ok':'bad'}">${ok?'✓':'!'}</em>`:''}</span></div>`;}).join('')}${(results||[]).length>limit?`<div class="pv-more">+${results.length-limit} ${esc(semTxt('个条件','more conditions'))}</div>`:''}</div>`;
}
function renderSemantic(){
 const S=data.semantic;
 if(!S){$('content').innerHTML=`<div class="pv-empty"><div class="pv-eyebrow">${esc(semTxt('研究语义','PAPER VIEW'))}</div><h2>${esc(semTxt('还没有发布研究语义地图','No semantic map yet'))}</h2><p>${esc(semTxt('让 agent 按 references/SEMANTIC_MAP.md 读报告写出地图，然后运行 labweft trace publish-map。','Have your agent write one (references/SEMANTIC_MAP.md), then run labweft trace publish-map.'))}</p></div>`;return;}
 const claims=S.claims||[],exps=S.experiments||[],cs=S._check_summary;
 const pct=cs&&cs.checked?Math.round(100*((cs.ok||0)+(cs.ok_derived||0))/cs.checked):null;
 const tabs=[['summary',semTxt('概要','Overview'),''],['claims',semTxt('结论','Claims'),claims.length],['experiments',semTxt('实验','Experiments'),exps.length],['timeline',semTxt('历程','Timeline'),(S.phases||[]).length],['invalid',semTxt('作废与取代','Superseded'),(S.invalidated||[]).length],['open',semTxt('待解决','Open questions'),(S.open_questions||[]).length]];
 const q=x=>!semQuery||String(x).toLowerCase().includes(semQuery);
 const sel=id=>semSel===id?' selected':'';
 let body='';
 if(semTab==='summary'){
  const m=S.method||{},top=claims.map((c,i)=>[c,i]).filter(([c])=>(c.numbers||[]).length).slice(0,4);
  body=`<div class="pv-abstract"><div class="pv-label">${esc(semTxt('研究背景','Background'))}</div><p>${esc(S.background||'')}</p></div>`+
   (m.name||m.idea?`<div class="pv-method"><div class="pv-label">${esc(semTxt('方法','Method'))}</div><h3>${esc(m.name||'')}</h3><p>${esc(m.idea||'')}</p>${(m.components||[]).length?`<div class="pv-components">${m.components.map((c,i)=>`<button type="button" class="pv-component${sel('comp:'+i)}" data-sem="comp:${i}"><span>${String(i+1).padStart(2,'0')}</span><b>${esc(c.name)}</b><small>${esc(c.role||'')}</small></button>`).join('')}</div>`:''}</div>`:'')+
   (top.length?`<div class="pv-section-title">${esc(semTxt('核心发现','Key findings'))}</div><div class="pv-highlights">${top.map(([c,i])=>{const n=c.numbers[0];return `<button type="button" class="pv-highlight${sel('claim:'+i)}" data-sem="claim:${i}"><span class="pv-hl-num">${esc(n.value)}</span><span class="pv-hl-meaning">${esc(n.meaning||'')}</span><span class="pv-hl-claim"><code>${esc(c.id)}</code> ${esc(c.statement)}</span></button>`}).join('')}</div>`:'')+
   ((S.reading_order||[]).length?`<div class="pv-section-title">${esc(semTxt('建议阅读顺序','Where to start reading'))}</div><ol class="pv-reading">${S.reading_order.map((r,i)=>`<li class="${sel('read:'+i).trim()}" data-sem="read:${i}"><b>${esc(String(r.path).split('/').pop())}</b><span>${esc(r.why||'')}</span></li>`).join('')}</ol>`:'');
 } else if(semTab==='claims'){
  body=`<div class="pv-list">${claims.map((c,i)=>q(c.statement+c.id+(c.status||''))?`<article class="pv-claim tone-${SEM_TONE[c.status]||'warn'}${sel('claim:'+i)}" data-sem="claim:${i}"><header><code>${esc(c.id)}</code>${semStatus(c.status)}${semCheck(c._check)}</header><p>${esc(c.statement)}</p>${(c.numbers||[]).length?`<div class="pv-nums">${c.numbers.slice(0,4).map(semNum).join('')}${c.numbers.length>4?`<span class="pv-num more">+${c.numbers.length-4}</span>`:''}</div>`:''}</article>`:'').join('')}</div>`;
 } else if(semTab==='experiments'){
  const g={};exps.forEach((e,i)=>{(g[e.type||'—']=g[e.type||'—']||[]).push([e,i])});
  body=Object.entries(g).map(([k,es])=>{const shown=es.filter(([e])=>q(e.question+(e.finding||'')+e.id));return shown.length?`<div class="pv-section-title">${esc(semWord(k))}<span>${shown.length}</span></div><div class="pv-list">${shown.map(([e,i])=>{const d=e.design||{};return `<article class="pv-exp${e.status==='作废'?' is-void':''}${sel('exp:'+i)}" data-sem="exp:${i}"><header><code>${esc(e.id)}</code>${semStatus(e.status)}${semCheck(e._check)}${d.metric?`<span class="pv-metric">${esc(d.metric)}</span>`:''}</header><h3>${esc(e.question)}</h3>${(e.results||[]).length?semBars(e.results):''}${e.finding?`<p class="pv-finding">${esc(e.finding)}</p>`:''}</article>`}).join('')}</div>`:''}).join('');
 } else if(semTab==='timeline'){
  body=`<ol class="pv-timeline">${(S.phases||[]).map((p,i)=>q(p.title+p.summary+p.period)?`<li class="${sel('phase:'+i).trim()}" data-sem="phase:${i}"><time>${esc(p.period||'')}</time><div><h3>${esc(p.title)}</h3><p>${esc(p.summary||'')}</p></div></li>`:'').join('')}</ol>`;
 } else if(semTab==='invalid'){
  body=`<div class="pv-list">${(S.invalidated||[]).map((x,i)=>q(x.what+x.why)?`<article class="pv-void${sel('inv:'+i)}" data-sem="inv:${i}"><h3>${esc(x.what)}</h3>${x.why?`<p>${esc(x.why)}</p>`:''}${x.replaced_by?`<div class="pv-replaced"><span>${esc(semTxt('取代为','Replaced by'))}</span>${esc(x.replaced_by)}</div>`:''}</article>`:'').join('')}</div>`;
 } else {
  body=`<ol class="pv-open">${(S.open_questions||[]).map((x,i)=>q(x.question)?`<li class="${sel('open:'+i).trim()}" data-sem="open:${i}">${esc(x.question)}</li>`:'').join('')}</ol>`;
 }
 const facts=[[claims.length,semTxt('条结论','claims')],[exps.length,semTxt('个实验','experiments')],[(S.phases||[]).length,semTxt('个阶段','phases')]];
 $('content').innerHTML=`<header class="pv-masthead"><div class="pv-eyebrow">${esc(semTxt('研究语义 · 论文视图','PAPER VIEW'))}</div><h1>${esc(S.project||data.project?.name||'')}</h1>${S.one_line?`<p class="pv-lede">${esc(S.one_line)}</p>`:''}<div class="pv-facts">${facts.map(([n,l])=>`<span><b>${n}</b>${esc(l)}</span>`).join('')}${pct!==null?`<span class="pv-verified" title="${esc(semTxt('trace verify-map 在项目原文中逐条核对','checked line by line in the project by trace verify-map'))}"><b>${pct}%</b>${esc(semTxt('数字已核对','numbers verified'))} · ${cs.checked}</span>`:''}</div></header>`+
  `<div class="pv-tabs" role="tablist">${tabs.map(([k,l,n])=>`<button type="button" data-semtab="${k}" class="${semTab===k?'active':''}">${esc(l)}${n!==''?`<span>${n}</span>`:''}</button>`).join('')}</div>`+
  (semTab==='summary'?'':`<div class="pv-filter"><input class="search" id="sem-q" placeholder="${esc(semTxt('筛选…','Filter…'))}" value="${esc(semQuery)}"></div>`)+
  `<div class="pv-body">${body||`<div class="empty">${esc(semTxt('没有匹配的内容。','Nothing matches.'))}</div>`}</div>`;
 $('content').querySelectorAll('[data-semtab]').forEach(b=>b.onclick=()=>{semTab=b.dataset.semtab;semSel=null;semQuery='';renderSemantic();renderSemanticDetail();});
 $('content').querySelectorAll('[data-sem]').forEach(b=>b.onclick=()=>{semSel=b.dataset.sem;renderSemantic();renderSemanticDetail();});
 const qi=$('sem-q');if(qi)qi.oninput=e=>{semQuery=e.target.value.toLowerCase();const p=e.target.selectionStart;renderSemantic();$('sem-q').focus();$('sem-q').setSelectionRange(p,p);};
}
function semEvidence(list){
 const S=data.semantic,L=S._links||{};
 if(!(list||[]).length)return '';
 return `<div class="detail-section"><h3>${esc(t('sources'))}</h3>${list.map(loc=>{const path=String(loc).replace(/:(\d+)(\s*[-–]\s*\d+)?\s*$/,''),k=L[path];
  const open=k&&canOpenEvidence(k.sha256)?`<button type="button" class="evidence-btn" data-sem-sha="${esc(k.sha256)}" data-title="${esc(loc)}">${esc(loc)}<small>${esc(t('view'))}</small></button>`:`<div class="evidence-btn" style="cursor:default">${esc(loc)}</div>`;
  const nodes=(k?.nodes||[]).filter(id=>data.nodes[id]).slice(0,4).map(id=>`<button type="button" class="relation-btn" data-sem-node="${esc(id)}">→ ${esc(label(data.nodes[id]))}: ${esc(displayLabel(data.nodes[id]))}</button>`).join('');
  return open+nodes;}).join('')}</div>`;
}
function renderSemanticDetail(){
 const S=data.semantic;let h='';
 if(!S||!semSel){h=`<div class="eyebrow">${esc(semTxt('研究语义','PAPER VIEW'))}</div><h2 class="pv-detail-title">${esc(semTxt('读者指南','Reader guide'))}</h2>`;
  const cs=S?._check_summary;if(cs&&cs.checked){const good=(cs.ok||0)+(cs.ok_derived||0),pc=Math.round(100*good/cs.checked);h+=`<div class="detail-section"><h3>${esc(semTxt('证据核验','Evidence check'))}</h3><div class="pv-ring" style="--p:${pc}"><b>${pc}%</b><span>${good} / ${cs.checked}</span></div><p class="pv-note">${esc(semTxt('每条结论和实验里的数字，都由 trace verify-map 对回项目原文的那一行；由多行、多种子算出的均值 ± SD 也会被复算。','Every number in claims and experiments is checked against the cited line in the project by trace verify-map, including means ± SD recomputed from rows or seed replicates.'))}</p></div><div class="detail-section"><h3>${esc(semTxt('怎么读','How to read'))}</h3><p class="pv-note">${esc(semTxt('点开任一结论或实验，右侧会显示关键数字、适用范围、支撑关系和可打开的原文证据。','Select a claim or experiment to see its key numbers, scope, supporting links and openable source evidence.'))}</p></div>`;}
  $('detail').innerHTML=h;return;}
 const [kind,idx]=semSel.split(':'),i=+idx;
 if(kind==='claim'){const c=S.claims[i];h=`<div class="eyebrow">${esc(semTxt('结论','CLAIM'))} ${esc(c.id)}</div><h2 class="pv-detail-title">${esc(c.statement)}</h2><p>${semStatus(c.status)} ${semCheck(c._check)}</p>`;
  if((c.numbers||[]).length)h+=`<div class="detail-section"><h3>${esc(semTxt('关键数字','Key numbers'))}</h3>${c.numbers.map(n=>{const ok=n._check==='ok'||n._check==='ok_derived';return `<div class="pv-keynum"><div><b>${esc(n.value)}</b>${n._check?`<em class="${ok?'ok':'bad'}">${ok?'✓':'!'}</em>`:''}</div><p>${esc(n.meaning||'')}</p>${n.source?`<small>${esc(n.source)}</small>`:''}</div>`}).join('')}</div>`;
  if(c.caveats)h+=`<div class="detail-section"><h3>${esc(t('scope'))}</h3><p class="description">${esc(c.caveats)}</p></div>`;
  const ex=(S.experiments||[]).map((e,j)=>[e,j]).filter(([e])=>(e.supports||[]).includes(c.id));
  if(ex.length)h+=`<div class="detail-section"><h3>${esc(semTxt('支撑实验','Supporting experiments'))}</h3>${ex.map(([e,j])=>`<button type="button" class="relation-btn" data-sem-goto="exp:${j}">${esc(e.id)} · ${esc(e.question)}</button>`).join('')}</div>`;
  h+=semEvidence(c.evidence);
 } else if(kind==='exp'){const e=S.experiments[i],d=e.design||{};h=`<div class="eyebrow">${esc(semWord(e.type))} · ${esc(e.id)}</div><h2 class="pv-detail-title">${esc(e.question)}</h2><p>${semStatus(e.status)} ${semCheck(e._check)}</p>${kv({[semTxt('对比','Compared')]:(d.compared||[]).join(' / '),[semTxt('固定','Fixed')]:(d.fixed||[]).join(' / '),[semTxt('重复','Replicates')]:d.seeds,[t('metric')]:d.metric})}`;
  if((e.results||[]).length)h+=`<div class="detail-section"><h3>${esc(t('results'))}</h3>${semBars(e.results,99)}</div>`;
  h+=`<div class="detail-section"><h3>${esc(semTxt('结论','Finding'))}</h3><div class="note">${esc(e.finding)}</div></div>`;
  if((e.supports||[]).length)h+=`<div class="detail-section"><h3>${esc(semTxt('支撑的结论','Supports'))}</h3>${e.supports.map(id=>{const j=(S.claims||[]).findIndex(c=>c.id===id);return j<0?'':`<button type="button" class="relation-btn" data-sem-goto="claim:${j}">${esc(id)} · ${esc(S.claims[j].statement)}</button>`}).join('')}</div>`;
  h+=semEvidence(e.evidence);
 } else if(kind==='phase'){const p=S.phases[i];h=`<div class="eyebrow">${esc(p.period)}</div><h2>${esc(p.title)}</h2><p class="description">${esc(p.summary)}</p>`+semEvidence(p.evidence);
 } else if(kind==='inv'){const x=S.invalidated[i];h=`<div class="eyebrow">${esc(semTxt('作废与取代','SUPERSEDED'))}</div><h2>${esc(x.what)}</h2>${kv({[semTxt('原因','Why')]:x.why,[semTxt('替代','Replaced by')]:x.replaced_by})}`+semEvidence(x.evidence);
 } else if(kind==='open'){const x=S.open_questions[i];h=`<div class="eyebrow">${esc(semTxt('待解决','OPEN'))}</div><h2>${esc(x.question)}</h2>`+semEvidence(x.evidence);
 } else if(kind==='comp'){const c=S.method.components[i];h=`<div class="eyebrow">${esc(semTxt('方法组件','COMPONENT'))}</div><h2>${esc(c.name)}</h2><p class="description">${esc(c.role)}</p>`;
 } else if(kind==='read'){const r=S.reading_order[i];h=`<div class="eyebrow">${esc(semTxt('建议阅读','READ FIRST'))}</div><h2>${esc(r.path.split('/').pop())}</h2><p class="description">${esc(r.why)}</p>`+semEvidence([r.path]);}
 $('detail').innerHTML=h;
 $('detail').querySelectorAll('[data-sem-sha]').forEach(b=>b.onclick=()=>showEvidence(b.dataset.semSha,b.dataset.title));
 $('detail').querySelectorAll('[data-sem-node]').forEach(b=>b.onclick=()=>{setView('map');select(b.dataset.semNode);});
 $('detail').querySelectorAll('[data-sem-goto]').forEach(b=>b.onclick=()=>{const g=b.dataset.semGoto;semTab=g.startsWith('exp')?'experiments':'claims';semSel=g;renderSemantic();renderSemanticDetail();});
}
Object.assign(words.zh,{navSemantic:'研究语义',semanticTitle:'像读论文一样读你的项目。',semanticSubtitle:'结论 → 支撑实验 → 数字 → 原始证据；每个数字都在项目里核对过。'});
Object.assign(words.en,{navSemantic:'Paper view',semanticTitle:'Read your project like a paper.',semanticSubtitle:'Claims → supporting experiments → numbers → raw evidence; every number checked in the project.'});


if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
