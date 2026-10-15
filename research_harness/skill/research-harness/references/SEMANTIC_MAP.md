# 研究语义地图（paper 语义）— 输出格式

目标：像读一篇论文 / 一份研究进展报告那样，把这个项目的研究内容按“科研语义”整理出来，而不是按文件夹或文件名。
每一条都必须能追到证据（项目内文件路径 + 行号/字段），数字必须与证据一致。

写一个 UTF-8 JSON 文件，结构：
{
  "project": "项目名",
  "one_line": "一句话：这个项目在研究什么、目前最重要的结论是什么",
  "background": "研究背景与要解决的问题（2-4 句，用作者自己的术语，并解释术语）",
  "method": {"name": "方法名", "idea": "核心思想（2-4 句）", "components": [{"name": "组件/模块", "role": "它做什么"}]},
  "glossary": [{"term": "术语/缩写（如 Readout90、QH、RH5、CLEAR Moderate、PBN-16384）", "meaning": "含义"}],
  "phases": [{"period": "日期或阶段", "title": "这一阶段在做什么", "summary": "做了什么、得到什么、为什么转向下一阶段", "evidence": ["path:line"]}],
  "claims": [{"id": "C1", "statement": "论文式结论（中文，一句话，含关键数字）", "status": "成立|部分成立|已被取代|已撤回|待验证",
              "numbers": [{"value": "88.56 ± 1.07", "meaning": "什么指标、什么条件、几个 seed、SD 口径", "source": "path:line"}],
              "evidence": ["path:line"], "caveats": "作者自己写明的限制"}],
  "experiments": [{"id": "E1", "question": "这个实验要回答的研究问题（论文语义，如：去掉 QH 是否损害 PushT 成功率？）",
                   "type": "主实验|消融|对照|超参搜索|诊断/机制分析|复现/重评|基线",
                   "design": {"compared": ["对比的条件，用研究含义命名"], "fixed": ["保持不变的设置"], "seeds": "训练 seed × 评测 seed × episodes", "metric": "指标与评测协议"},
                   "results": [{"condition": "条件（研究含义）", "value": 88.56, "sd": 1.07, "n": "3 train seeds", "note": "", "source": "path:line"}],
                   "finding": "结论（一两句）", "status": "有效|已被取代|作废|进行中", "supports": ["C1"], "evidence": ["path:line"]}],
  "invalidated": [{"what": "被作废/取代的研究或数字", "why": "原因（作者原话概括）", "replaced_by": "替代的研究/数字", "evidence": ["path:line"]}],
  "open_questions": [{"question": "尚未解决的问题或待完成的实验", "evidence": ["path:line"]}],
  "reading_order": [{"path": "建议先读的文档", "why": "为什么"}]
}

要求：
- 以作者的报告/README/FINAL/STATUS 等文档为主线理解研究，再用结果文件核对数字。实验与结论按研究含义组织（主实验、消融、对照、机制分析、重评），同一个实验散落在多个文件夹也要合并成一条。
- 数字只写有证据的；能复算的用 trace reconcile / experiments 或读原始文件核对。冲突的数字写明哪个是最新/有效的。
- 被作者标记为 do_not_use / 作废 / 已取代的内容放进 invalidated，不要当成有效结论。
- 覆盖面：claims 10-30 条，experiments 15-40 个（挑真正重要的），phases 覆盖整个项目时间线。
- 全部用中文书写（专有名词保留原文）。
