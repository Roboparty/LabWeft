"""One controller, one durable workspace, no mandatory subagents or model account."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import sys
from . import __version__
from .store import Store, HarnessError, atomic_write, read_json, json_write, validate_state
from .scan import sync
from .reasoning import compare, assess, drift
from .organization import organization
from .server import export_html, export_site, serve


def configure_stdio() -> None:
    """Keep JSON output UTF-8 when Windows redirects stdout to an agent tool."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


def source_args(values: list[str]) -> dict:
    out = {}
    for value in values:
        if "=" not in value:
            raise HarnessError("Source format: alias=/absolute/or/relative/path")
        alias, path = value.split("=", 1)
        out[alias] = str(Path(path).expanduser().resolve())
    return out


# Unmodified SKILL.md from 61f221b, before managed installation records existed.
LEGACY_SKILL_HASHES = {"c3d6a2e5436023d383ab3649896d8e4840a1092b9d67d554a4e9b8666768db37"}


def install_skill(agent: str, project: Path | None, user: bool) -> dict:
    if user and project:
        raise HarnessError("Choose --user or --project, not both")
    base = Path.home() if user else (project or Path.cwd()).expanduser().resolve()
    if agent == "auto":
        # Discovery is deliberately local; no credentials, shell profiles or network inspected.
        agents = [a for a, d in (("codex", ".codex"), ("claude", ".claude")) if (Path.home() / d).exists() or (base / d).exists()]
        if not agents:
            agents = ["generic"]
    else:
        agents = [agent]
    src = Path(__file__).parent / "skill" / "research-harness"
    managed = {path.relative_to(src).as_posix(): path.read_bytes()
               for path in src.rglob("*") if path.is_file() and path.name != "LOCAL_COMMAND.md"}
    paths = []
    repo_launcher = Path(__file__).parent.parent / "labweft.py"
    command_parts = [sys.executable, str(repo_launcher)] if repo_launcher.exists() else [sys.executable, "-m", "research_harness"]
    posix_command = shlex.join(command_parts)
    powershell_command = "& " + " ".join("'" + part.replace("'", "''") + "'" for part in command_parts)
    shell_command = (
        "PowerShell:\n\n```powershell\n" + powershell_command + "\n```\n"
        if sys.platform == "win32" else
        "POSIX shell:\n\n```sh\n" + posix_command + "\n```\n"
    )
    for item in agents:
        prefix = ".claude" if item == "claude" else ".agents"
        dest = base / prefix / "skills" / "research-harness"
        if dest.is_symlink():
            raise HarnessError(f"Skill location is a symlink: {dest}")
        if str(dest) in paths:
            continue
        if dest.exists():
            marker_path = dest / "INSTALL_MANIFEST.json"
            marker = read_json(marker_path) if marker_path.exists() else None
            if marker is not None and (marker.get("schema_version") != 1 or not isinstance(marker.get("managed"), dict)):
                raise HarnessError(f"Invalid managed Skill record: {marker_path}")
            for rel, expected in managed.items():
                existing = dest / rel
                if existing.is_symlink():
                    raise HarnessError(f"Managed Skill file is a symlink: {existing}")
                if not existing.exists():
                    if marker is not None and rel in marker["managed"]:
                        raise HarnessError(f"Managed Skill file is missing: {existing}")
                    continue
                current_hash = hashlib.sha256(existing.read_bytes()).hexdigest()
                expected_hash = hashlib.sha256(expected).hexdigest()
                recorded_hash = marker["managed"].get(rel) if marker else None
                trusted = {expected_hash}
                if recorded_hash:
                    trusted.add(recorded_hash)
                elif marker is None and rel == "SKILL.md":
                    trusted.update(LEGACY_SKILL_HASHES)
                if current_hash not in trusted:
                    raise HarnessError(f"Existing skill differs: {dest}. Refusing to overwrite user edits; back up/reconcile explicitly.")
            for rel, expected in managed.items():
                target = dest / rel
                if not target.exists() or target.read_bytes() != expected:
                    atomic_write(target, expected)
        else:
            shutil.copytree(src, dest)
        json_write(dest / "INSTALL_MANIFEST.json", {"schema_version": 1,
                   "managed": {rel: hashlib.sha256(raw).hexdigest() for rel, raw in managed.items()}})
        # Only our generated location file is updated; never touch AGENTS.md/CLAUDE.md.
        (dest / "references" / "LOCAL_COMMAND.md").write_text(
            "# Executable for this installation\n\nUse `labweft` (or legacy `rh`) if installed. Otherwise use this command prefix:\n\n"
            + shell_command + "\n"
            "This is local to this machine. Reinstall the skill after moving the tool or interpreter.\n", encoding="utf-8")
        paths.append(str(dest))
    return {"installed": paths, "agent": agents,
            "compatibility": "This command checks Skill-format and local-command installation; verify discovery and the research workflow in the target client.",
            "next": "In your existing agent conversation, ask it to use LabWeft to organize this project; do not open additional agents."}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="labweft", description="LabWeft: local-first research workspace (prototype)")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)
    from .autoresearch import add_cli
    add_cli(sub)
    s = sub.add_parser("init", help="Create a persistent research workspace, without moving source files")
    s.add_argument("workspace", nargs="?", default=".")
    s.add_argument("--name")
    s.add_argument("--source", action="append", default=[])
    s = sub.add_parser("sync", help="Read-only scan; ingest recorded facts, not inferred research intent")
    s.add_argument("workspace", nargs="?", default=".")
    s.add_argument("--source", action="append", default=[])
    s.add_argument("--max-files", type=int, default=10000)
    s.add_argument("--max-bytes", type=int, default=32 * 1024 * 1024)
    s = sub.add_parser("context", help="Read project state before any research action")
    s.add_argument("workspace", nargs="?", default=".")
    s.add_argument("--node")
    s.add_argument("--full", action="store_true")
    s = sub.add_parser("files", help="Paginate source inventory without flooding model context")
    s.add_argument("workspace", nargs="?", default=".")
    s.add_argument("--offset", type=int, default=0)
    s.add_argument("--limit", type=int, default=50)
    s = sub.add_parser("evidence", help="Read immutable text evidence with line numbers")
    s.add_argument("workspace")
    s.add_argument("--sha", required=True)
    s.add_argument("--start-line", type=int, default=1)
    s.add_argument("--lines", type=int, default=160)
    s = sub.add_parser("apply", help="Validate and atomically apply one semantic patch")
    s.add_argument("workspace")
    s.add_argument("patch")
    s.add_argument("--actor", default="agent")
    s = sub.add_parser("confirm", help="Explicit human confirmation; never run by an agent without authorization")
    s.add_argument("workspace")
    s.add_argument("node")
    s.add_argument("--note", required=True)
    s.add_argument("--reviewer", required=True)
    s = sub.add_parser("compare", help="Compare cells using recorded configs and eligible seeds")
    s.add_argument("workspace", nargs="?", default=".")
    s.add_argument("--cell", action="append")
    s.add_argument("--metric", help="Metric key; auto-select success_rate or a sole recorded key")
    s = sub.add_parser("assess", help="Check a proposed condition against scoped historical decisions")
    s.add_argument("workspace")
    s.add_argument("proposal")
    s = sub.add_parser("validate", help="Check schema, revision chain, references and evidence snapshots")
    s.add_argument("workspace", nargs="?", default=".")
    s = sub.add_parser("export", help="Create a private offline interactive HTML snapshot")
    s.add_argument("workspace", nargs="?", default=".")
    s.add_argument("--output", required=True)
    s.add_argument("--include-evidence", action="store_true", help="Explicitly copy indexed small-text snapshots into the HTML (up to 5 MiB); may expose private material")
    s = sub.add_parser("export-site", help="Create one private offline site with a project switcher")
    s.add_argument("workspaces", nargs="+", help="Workspaces in project-switch order; first opens at index.html")
    s.add_argument("--output-dir", required=True)
    s.add_argument("--include-evidence", action="store_true", help="Embed each project's indexed small-text snapshots; private material")
    s = sub.add_parser("serve", help="Open a loopback-only read-only dashboard; no cloud account")
    s.add_argument("workspace", nargs="?", default=".")
    s.add_argument("--port", type=int, default=8787)
    s.add_argument("--open", action="store_true")
    s = sub.add_parser("install-skill", help="Install one workflow entry point; no multi-agent setup")
    s.add_argument("--agent", choices=["auto", "codex", "claude", "generic"], default="auto")
    s.add_argument("--project", type=Path)
    s.add_argument("--user", action="store_true")
    s = sub.add_parser("demo", help="Create a clearly synthetic, working ablation example")
    s.add_argument("workspace", nargs="?", default="./research-demo")
    s.add_argument("--scenario", choices=["policy", "research-tree"], default="policy", help="policy: original fixture; research-tree: instant replay of saved tree results")
    s.add_argument("--port", type=int, default=8787, help="Preview server port with --open; use 0 for a free port")
    s.add_argument("--open", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parser().parse_args(argv)
    try:
        if args.command == "research":
            from .autoresearch import dispatch
            emit(dispatch(args))
            return 0
        if args.command == "install-skill":
            emit(install_skill(args.agent, args.project, args.user))
            return 0
        if args.command == "export-site":
            emit(export_site([Path(path) for path in args.workspaces], Path(args.output_dir),
                             include_evidence=args.include_evidence))
            return 0
        store = Store(args.workspace)
        if args.command == "init":
            state = store.init(args.name or Path(args.workspace).resolve().name)
            if args.source:
                store.set_sources(source_args(args.source))
            emit({"project": state["project"], "workspace": str(store.workspace), "sources": store.sources()})
        elif args.command == "sync":
            if args.max_files < 1 or args.max_bytes < 1:
                raise HarnessError("Scan limits must be positive")
            if args.source:
                store.set_sources({**store.sources(), **source_args(args.source)})
            emit(sync(store, max_files=args.max_files, max_bytes=args.max_bytes))
        elif args.command == "context":
            state = store.load()
            if args.node:
                if args.node not in state["nodes"]:
                    raise HarnessError("Unknown node id")
                emit(state["nodes"][args.node])
            elif args.full:
                emit(state)
            else:
                nodes = list(state["nodes"].values())
                top = [n for n in nodes if n["kind"] not in {"run", "evaluation", "artifact"}]
                emit({"project": state["project"], "base_revision": state["revision"], "nodes": top,
                      "node_count": len(nodes), "file_count": len(state["files"]), "drift": drift(state),
                      "scan": state["scan"], "history": state["history"][-12:], "organization": organization(state),
                      "next": "Use files for paginated evidence, context --node ID, or --full. Read evidence before applying a semantic patch."})
        elif args.command == "files":
            state = store.load()
            items = sorted(state["files"].values(), key=lambda f: (f["source"], f["path"]))
            start, limit = max(0, args.offset), max(1, min(200, args.limit))
            emit({"items": items[start:start + limit], "total": len(items),
                  "next_offset": start + limit if start + limit < len(items) else None})
        elif args.command == "evidence":
            lines = store.read_blob(args.sha).splitlines()
            start, size = max(1, args.start_line), max(1, min(500, args.lines))
            emit({"sha256": args.sha, "text": "\n".join(f"{i + 1}: {line}" for i, line in enumerate(lines) if start <= i + 1 < start + size),
                  "total_lines": len(lines), "next_start_line": start + size if start + size <= len(lines) else None})
        elif args.command == "apply":
            emit(store.commit(read_json(Path(args.patch)), actor=args.actor))
        elif args.command == "confirm":
            emit(store.confirm(args.node, args.note, args.reviewer))
        elif args.command == "compare":
            emit(compare(store.load(), args.cell, args.metric))
        elif args.command == "assess":
            emit(assess(store.load(), read_json(Path(args.proposal))))
        elif args.command == "validate":
            state = store.load()
            failures = []
            for n in state["nodes"].values():
                for ref in n.get("evidence", []):
                    try:
                        store.read_blob(ref["sha256"])
                    except HarnessError as exc:
                        failures.append({"node": n["id"], "error": str(exc)})
            emit({"valid": not failures, "revision": state["revision"], "nodes": len(state["nodes"]),
                  "evidence_errors": failures, "drift": drift(state), "organization": organization(state),
                  "scope": "Mechanical validation only; not validation of scientific truth or host-model reliability."})
            return 1 if failures else 0
        elif args.command == "export":
            output = export_html(store, Path(args.output).expanduser().resolve(), include_evidence=args.include_evidence)
            emit({"output": str(output), "privacy": "Private snapshot, not uploaded. Review records and source text before sharing."})
        elif args.command == "serve":
            serve(store, args.port, args.open)
        elif args.command == "demo":
            if args.scenario == "research-tree":
                from .research_tree_demo import create_research_tree_demo
                emit(create_research_tree_demo(store.workspace))
            else:
                from .demo import create_demo
                emit(create_demo(store.workspace))
            if args.open:
                serve(store, args.port, True)
        return 0
    except (HarnessError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
