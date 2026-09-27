#!/usr/bin/env python3
"""One local setup command; no dependency download or agent orchestration."""
import argparse
import json
from pathlib import Path
from research_harness.cli import configure_stdio, install_skill
from research_harness.store import Store, HarnessError
from research_harness.scan import sync
from research_harness.server import export_html
p = argparse.ArgumentParser(description="Install the skill, index a selected project, export its initial factual map")
p.add_argument("--project", type=Path, required=True)
p.add_argument("--workspace", type=Path, help="Writable location for .research and the Skill (default: project directory)")
p.add_argument("--results", type=Path)
p.add_argument("--agent", choices=["auto", "codex", "claude", "generic"], default="auto")
a = p.parse_args()
configure_stdio()
try:
    root = a.project.expanduser().resolve()
    if not root.is_dir():
        raise HarnessError("Select an existing project directory")
    workspace = (a.workspace or root).expanduser().resolve()
    store = Store(workspace)
    store.init(root.name)
    sources = {"code": str(root)}
    if a.results:
        sources["results"] = str(a.results.expanduser().resolve())
    store.set_sources(sources)
    result = install_skill(a.agent, workspace, False)
    result["workspace"] = str(workspace)
    result["project_source"] = str(root)
    result["scan"] = sync(store)
    result["initial_map"] = str(export_html(store, workspace / ".research" / "map.html"))
    result["next"] = "在你的现有 agent 对话中说：使用 LabWeft 整理这个项目，核对研究目的和 ablation，继承历史判断，更新地图；不启动实验。初始扫描图只是事实索引，不是模型已经完成科学分析。"
    print(json.dumps(result, ensure_ascii=False, indent=2))
except (HarnessError, OSError) as exc:
    p.exit(2, str(exc) + "\n")
