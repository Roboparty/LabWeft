"""Versioned JSON transactions: immutable evidence, optimistic writes, local locking.

The event directory is authoritative. Each transaction is one atomically replaced
file; state is replayed, not reconstructed by an LLM. This is a local single-writer
prototype, not a distributed database or a tamper-proof audit system.
"""
from __future__ import annotations
import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from datetime import datetime, timezone
from typing import Any, Iterator
import uuid

KINDS = {"module", "question", "cell", "run", "evaluation", "claim", "decision", "artifact"}
RELATIONS = {"derived_from", "compares", "supports", "contradicts", "uses_checkpoint", "supersedes", "inspired_by"}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")

class HarnessError(Exception):
    """An actionable user/configuration error."""

class Conflict(HarnessError):
    """Caller must reload state and reconcile before retrying."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def stable_id(prefix: str, *parts: str) -> str:
    return prefix + "-" + digest(list(parts))[:20]


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except (OSError, ValueError) as exc:
        raise HarnessError(f"Cannot read valid JSON from {path}: {exc}") from exc


def atomic_write(path: Path, data: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = data.encode("utf-8") if isinstance(data, str) else data
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def json_write(path: Path, data: Any) -> None:
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n")


@contextlib.contextmanager
def local_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Locks are automatically released on process exit; do not delete the lockfile.
    with open(path, "a+b") as f:
        if os.name == "nt":
            import msvcrt
            if f.tell() == 0:
                f.write(b"0")
                f.flush()
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def assert_id(value: Any, label: str = "id") -> None:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise HarnessError(f"Invalid {label}: {value!r}")


def validate_state(state: dict) -> None:
    nodes, files = state["nodes"], state["files"]
    project_id = state["project"]["id"]
    for key, item in files.items():
        assert_id(key, "file id")
        if item.get("id") != key:
            raise HarnessError("File key and identity differ")
        sha = item.get("sha256")
        if sha is not None and not HASH_RE.fullmatch(str(sha)):
            raise HarnessError(f"Invalid file hash: {key}")
    for key, node in nodes.items():
        assert_id(key, "node id")
        if key == project_id or node.get("id") != key or node.get("kind") not in KINDS:
            raise HarnessError(f"Invalid node: {key}")
        if not isinstance(node.get("label"), str) or not node["label"].strip():
            raise HarnessError(f"Missing label: {key}")
        if node.get("status", "recorded") not in {"recorded", "completed", "needs_review", "provisional", "accepted", "archived", "planned", "running", "failed"}:
            raise HarnessError(f"Unknown status: {key}")
        if not isinstance(node.get("evidence_ids", []), list):
            raise HarnessError(f"evidence_ids must be an array: {key}")
        if not isinstance(node.get("attrs", {}), dict):
            raise HarnessError(f"attrs must be an object: {key}")
        parent = node.get("parent_id", project_id)
        if parent not in nodes and parent != project_id:
            raise HarnessError(f"Unknown parent {parent} for {key}")
        seen, cursor = {key}, parent
        while cursor in nodes:
            if cursor in seen:
                raise HarnessError(f"Hierarchy cycle involving {key}")
            seen.add(cursor)
            cursor = nodes[cursor].get("parent_id", project_id)
        refs = node.get("evidence", [])
        if not isinstance(refs, list):
            raise HarnessError(f"Evidence must be a list: {key}")
        for ref in refs:
            if not isinstance(ref, dict) or ref.get("file_id") not in files:
                raise HarnessError(f"Unknown evidence file for {key}")
            if not HASH_RE.fullmatch(str(ref.get("sha256", ""))):
                raise HarnessError(f"Evidence needs an immutable content hash: {key}")
        for nid in node.get("evidence_ids", []):
            if nid not in nodes:
                raise HarnessError(f"Unknown evidence node {nid} for {key}")
        if node["kind"] in {"claim", "decision"} and node.get("status") == "accepted":
            if not node.get("evidence"):
                raise HarnessError(f"Accepted {node['kind']} requires direct immutable evidence or a user-note source: {key}")
            if not node.get("attrs", {}).get("scope"):
                raise HarnessError(f"Accepted {node['kind']} requires an explicit scope: {key}")
        if node["kind"] == "decision" and node.get("attrs", {}).get("action") == "reuse":
            scope = node.get("attrs", {}).get("scope", {})
            if not isinstance(scope.get("required_context"), dict):
                raise HarnessError(f"Reuse decision needs required_context: {key}")
            if not scope.get("required_context") or not isinstance(scope.get("covered_values", {}), dict):
                raise HarnessError(f"Reuse decision requires non-empty context and covered_values: {key}")
    for key, edge in state["edges"].items():
        assert_id(key, "edge id")
        if edge.get("id") != key or edge.get("relation") not in RELATIONS:
            raise HarnessError(f"Invalid edge {key}")
        if edge.get("source") not in nodes or edge.get("target") not in nodes:
            raise HarnessError(f"Dangling edge {key}")
    try:
        canonical(state)
    except (ValueError, TypeError) as exc:
        raise HarnessError(f"State is not finite JSON: {exc}") from exc


class Store:
    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace).expanduser().resolve()
        self.root = self.workspace / ".research"

    def exists(self) -> bool:
        return (self.root / "manifest.json").is_file()

    def init(self, name: str, *, synthetic: bool = False) -> dict:
        self.workspace.mkdir(parents=True, exist_ok=True)
        with local_lock(self.root / "writer.lock"):
            if self.exists():
                return self.load()
            manifest = {"schema_version": 1, "id": "project-" + uuid.uuid4().hex,
                        "name": name, "description": "", "synthetic": synthetic, "created_at": now()}
            (self.root / "events").mkdir(parents=True, exist_ok=True)
            (self.root / "blobs").mkdir(parents=True, exist_ok=True)
            json_write(self.root / "manifest.json", manifest)
            json_write(self.root / "local.json", {"sources": {"project": str(self.workspace)}})
            atomic_write(self.root / ".gitignore", "# Research records may be private. Review before committing.\nlocal.json\nwriter.lock\nblobs/\n.tmp-*\n")
        return self.load()

    def load(self) -> dict:
        if not self.exists():
            raise HarnessError(f"No workspace at {self.workspace}. Run: labweft init {self.workspace}")
        manifest = read_json(self.root / "manifest.json")
        if manifest.get("schema_version") != 1:
            raise HarnessError("Unsupported schema version; migrate explicitly before opening")
        state = {"schema_version": 1, "project": manifest, "revision": 0,
                 "nodes": {}, "edges": {}, "files": {}, "last_hash": "", "history": [], "scan": {}}
        for path in sorted((self.root / "events").glob("*.json")):
            event = read_json(path)
            checksum = event.get("hash")
            body = {k: v for k, v in event.items() if k != "hash"}
            if checksum != digest(body) or event.get("previous_hash") != state["last_hash"]:
                raise HarnessError(f"Event integrity check failed: {path.name}. Restore/reconcile; do not silently reset.")
            if event.get("revision") != state["revision"] + 1:
                raise HarnessError(f"Event revision gap/conflict: {path.name}")
            for category in ("nodes", "edges", "files"):
                for item in event.get(category, []):
                    state[category][item["id"]] = item
            if "scan" in event:
                state["scan"] = event["scan"]
            state["revision"] = event["revision"]
            state["last_hash"] = checksum
            state["history"].append({k: event[k] for k in ("revision", "at", "actor", "reason")})
        validate_state(state)
        return state

    def sources(self) -> dict[str, str]:
        config = self.root / "local.json"
        raw = read_json(config).get("sources", {}) if config.exists() else {}
        return {alias: str((Path(path).expanduser() if Path(path).expanduser().is_absolute() else self.workspace / path).resolve()) for alias, path in raw.items()}

    def set_sources(self, sources: dict[str, str]) -> None:
        if not self.exists():
            raise HarnessError("Initialize the workspace first")
        for alias, path in sources.items():
            assert_id(alias, "source alias")
            if not Path(path).expanduser().is_dir():
                raise HarnessError(f"Source is not a directory: {path}")
        with local_lock(self.root / "writer.lock"):
            json_write(self.root / "local.json", {"sources": {k: str(Path(v).expanduser().resolve()) for k, v in sources.items()}})

    def blob(self, raw: bytes) -> str:
        sha = hashlib.sha256(raw).hexdigest()
        path = self.root / "blobs" / sha
        if not path.exists():
            atomic_write(path, raw)
        return sha

    def read_blob(self, sha: str) -> str:
        if not HASH_RE.fullmatch(sha):
            raise HarnessError("Invalid evidence hash")
        path = self.root / "blobs" / sha
        if not path.is_file():
            raise HarnessError("Evidence snapshot is unavailable locally; index is not a backup. Restore the blob from its authorized source.")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha:
            raise HarnessError("Evidence snapshot integrity check failed")
        return raw.decode("utf-8", errors="replace")

    def commit(self, patch: dict, *, actor: str = "agent", human: bool = False, scanner: bool = False) -> dict:
        if not isinstance(patch, dict):
            raise HarnessError("Patch must be a JSON object")
        allowed = {"base_revision", "reason", "nodes", "edges"}
        if scanner:
            allowed |= {"files", "scan"}
        extra = set(patch) - allowed
        if extra:
            raise HarnessError(f"Unknown or reserved patch fields: {sorted(extra)}")
        if not str(patch.get("reason", "")).strip():
            raise HarnessError("Every update needs a reason")
        with local_lock(self.root / "writer.lock"):
            state = self.load()
            if patch.get("base_revision") != state["revision"]:
                raise Conflict(f"Expected base_revision {state['revision']}, received {patch.get('base_revision')}. Reload and reconcile.")
            next_state = copy.deepcopy(state)
            changes = {}
            for category in ("nodes", "edges", "files"):
                entries = patch.get(category, [])
                if not isinstance(entries, list) or any(not isinstance(x, dict) for x in entries):
                    raise HarnessError(f"{category} must be an array of objects")
                changed = []
                seen = set()
                for raw in entries:
                    item = copy.deepcopy(raw)
                    iid = item.get("id")
                    assert_id(iid)
                    if iid in seen:
                        raise HarnessError(f"Duplicate id in one transaction: {iid}")
                    seen.add(iid)
                    old = state[category].get(iid)
                    if category == "nodes":
                        if old and old["kind"] != item.get("kind"):
                            raise HarnessError(f"Node kind is immutable: {iid}")
                        if not human:
                            if old and old.get("protected") and old != item:
                                raise HarnessError(f"Human-protected node cannot be overwritten by an agent: {iid}")
                            if item.get("protected") and not (old and old.get("protected")):
                                raise HarnessError("Only explicit human confirmation can protect a node")
                            if item.get("confirmation") != (old or {}).get("confirmation"):
                                raise HarnessError("Agent cannot create or change human confirmation records")
                        for ref in item.get("evidence", []):
                            if not isinstance(ref, dict):
                                raise HarnessError("Each evidence reference must be an object")
                            if not HASH_RE.fullmatch(str(ref.get("sha256", ""))):
                                raise HarnessError(f"Invalid evidence hash: {iid}")
                            self.read_blob(ref["sha256"])
                    if old != item:
                        next_state[category][iid] = item
                        changed.append(item)
                changes[category] = changed
            if scanner and "scan" in patch:
                next_state["scan"] = patch["scan"]
            validate_state(next_state)
            # A wording-only change to the scanner's explanatory note is not a
            # new observation about the research project.
            scan_changed = ({k: v for k, v in next_state["scan"].items() if k != "note"} !=
                            {k: v for k, v in state["scan"].items() if k != "note"})
            if not any(changes.values()) and not scan_changed:
                return {"revision": state["revision"], "changed": False, "counts": {k: 0 for k in changes}}
            event = {"revision": state["revision"] + 1, "previous_hash": state["last_hash"],
                     "at": now(), "actor": actor, "reason": patch["reason"], **changes}
            if scan_changed:
                event["scan"] = next_state["scan"]
            event["hash"] = digest(event)
            path = self.root / "events" / f"{event['revision']:08d}.json"
            if path.exists():
                raise Conflict("Concurrent revision exists; reconcile instead of overwriting")
            json_write(path, event)
            return {"revision": event["revision"], "changed": True,
                    "counts": {k: len(v) for k, v in changes.items()}}

    def confirm(self, node_id: str, note: str, reviewer: str) -> dict:
        if not note.strip() or not reviewer.strip():
            raise HarnessError("Human confirmation needs a note and reviewer")
        state = self.load()
        if node_id not in state["nodes"]:
            raise HarnessError(f"Unknown node {node_id}")
        node = copy.deepcopy(state["nodes"][node_id])
        node["protected"] = True
        node["confirmation"] = {"reviewer": reviewer, "note": note, "at": now()}
        return self.commit({"base_revision": state["revision"], "reason": "Human confirmation: " + note,
                            "nodes": [node]}, actor="human:" + reviewer, human=True)
