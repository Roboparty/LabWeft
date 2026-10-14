"""Counting and verification primitives: questions people answer with `find | wc -l`, `sha256sum -c`, `diff -r`
and `git cat-file`, answered from the index first and from the source host only when the index cannot know.

Every answer says where it came from (index or live host) and whether it is exhaustive.
"""
from __future__ import annotations

import fnmatch
import json
import posixpath
import re
import shlex
import subprocess
from collections import Counter
from pathlib import Path

from ..store import HarnessError
from . import source
from .index import fid_range

TEMPLATE = re.compile(r"\d+")


def _scope_rows(con, scope: str, cols: str = "path"):
    scope = (scope or "").strip("/")
    if "::" in scope:  # inside one archive
        lo = scope if scope.endswith(("::", "/")) else scope + "/"
        return con.execute(f"SELECT {cols} FROM files WHERE path >= ? AND path < ?", (lo, lo + "￿"))
    if not scope:
        return con.execute(f"SELECT {cols} FROM files")
    rng = fid_range(con, scope)
    if not rng:
        return iter(())
    return con.execute(f"SELECT {cols} FROM files WHERE fid BETWEEN ? AND ?", rng)


def _rel(path: str, scope: str) -> str:
    scope = (scope or "").strip("/")
    if not scope:
        return path
    if path.startswith(scope + "/"):
        return path[len(scope) + 1:]
    if path.startswith(scope):  # archive scope "x.tgz::" or "x.tgz::sub/"
        return path[len(scope):].lstrip("/")
    return path


def archive_index_complete(con, archive: str) -> tuple[bool, str]:
    row = con.execute("SELECT status, reason FROM files WHERE path = ?", (archive,)).fetchone()
    if row is None:
        return False, "archive not in the index"
    if row[0] != "parsed":
        return False, f"probe did not finish this archive ({row[0]}: {row[1]})"
    f = con.execute("SELECT json FROM facts WHERE path = ?", (archive,)).fetchone()
    info = (json.loads(f[0]) or {}).get("archive", {}) if f else {}
    n = con.execute("SELECT COUNT(*) FROM files WHERE path >= ? AND path < ?", (archive + "::", archive + "::\uffff")).fetchone()[0]
    if info.get("truncated") or n >= 5000:
        return False, f"probe member list capped at {n}"
    return True, "index"


def archive_side(con, ws, name, scope: str) -> tuple[dict, str, list[str]]:
    """rel path -> (sha, size) for an archive scope `x.tgz::sub/`, from the index when its member list is complete,
    else from a full listing read on the host."""
    arch, _, inner = scope.partition("::")
    inner = inner.strip("/")
    ok, why = archive_index_complete(con, arch)
    if ok or ws is None:
        rows = {}
        for p, sha, size in _scope_rows(con, scope, "path, sha, size"):
            rows[_rel(p, scope)] = (sha, size)
        return rows, "index", ([] if ok else [why + "; pass a workspace for a live listing"])
    data = source.archive_listing(Path(ws), name, arch)
    rows = {}
    if inner and not any(m.startswith(inner + "/") for m in data["members"]):
        tops = sorted({m.split("/")[0] for m in data["members"]})[:20]
        raise HarnessError(f"no member of {arch} lies under {inner!r}; its top-level entries are {tops}")
    for m, info in data["members"].items():
        if inner and not m.startswith(inner + "/"):
            continue
        rows[m[len(inner) + 1:] if inner else m] = (None, info["size"])
    lim = [f"{why}: full member list read live on {data['host']} ({data['entries_files']} files, newest member {data['newest_member_mtime']})"]
    if not data["complete"]:
        lim.append("live listing did not finish: lower bound")
    return rows, f"live listing ({data['host']})", lim


def count(con, scope: str = "", name: str | None = None, what: str = "files", group_by: str | None = None,
          include_archives: bool = False, limit: int = 40, ws=None, source_name=None) -> dict:
    """Count files (or directories) under `scope`, optionally filtered by a basename glob, grouped by direct child
    folder or by path template (digits -> #). Directories include empty ones the probe recorded."""
    scope = (scope or "").strip("/")
    pats = [p for p in (name or "").split(",") if p] or None
    files, dirs = [], set()
    arch_lim, origin = [], "index"
    if "::" in scope:
        rows, origin, arch_lim = archive_side(con, ws, source_name, scope)
        scope_for_rel = scope.split("::")[0] + "::"
        inner = scope.partition("::")[2].strip("/")
        it = (((scope_for_rel + (inner + "/" if inner else "") + r),) for r in rows)  # full paths for the loop below
    else:
        it = _scope_rows(con, scope)
    all_files = []
    for (p,) in it:
        if "::" in p and "::" not in scope and not include_archives:
            continue
        base = posixpath.basename(p.split("::")[-1])
        rel = _rel(p, scope)
        all_files.append(p)
        d = posixpath.dirname(rel)
        while d:
            dirs.add(d)
            d = posixpath.dirname(d)
        if pats and not any(fnmatch.fnmatchcase(base, g) for g in pats):
            continue
        files.append(rel)
    empty, policy_skipped = [], 0
    if "::" not in scope:
        like = (scope + "/%") if scope else "%"
        skipped_files, tallied = 0, True
        for (p, k, reason) in con.execute("SELECT DISTINCT path, kind, reason FROM skips WHERE kind IN ('empty_dir', 'skip_dir') AND path LIKE ?", (like,)):
            rel = _rel(p, scope)
            if k == "empty_dir":
                empty.append(rel)
            else:
                policy_skipped += 1
                try:
                    t = json.loads(reason) if reason and reason.startswith("{") else None
                except ValueError:
                    t = None
                if t and "files" in t:
                    skipped_files += t["files"]
                    tallied = tallied and t.get("complete", False)
                else:
                    tallied = False
            d = rel
            while d:
                dirs.add(d)
                d = posixpath.dirname(d)
    skipped = con.execute("SELECT COUNT(DISTINCT path) FROM skips WHERE kind NOT IN ('empty_dir', 'skip_dir') AND path LIKE ?",
                          ((scope + "/%") if scope else "%",)).fetchone()[0] if "::" not in scope else 0
    out = {"scope": scope or ".", "name": name, "origin": origin}
    if what in ("dirs", "both"):
        named = [d for d in dirs if not pats or any(fnmatch.fnmatchcase(posixpath.basename(d), g) for g in pats)]
        top = sorted({d.split("/")[0] for d in dirs})
        direct = {posixpath.dirname(_rel(p, scope)) for p in all_files}
        out["dirs"] = {"total_recursive": len(named) if pats else len(dirs), "direct_children": len(top),
                       "empty_leaf_dirs": len(empty), "dirs_holding_files": len(direct & dirs)}
        if pats:
            out["dirs"]["matching_names"] = sorted(named)[:limit]
    if what in ("files", "both"):
        out["files"] = len(files)
        if group_by:
            key = (lambda r: r.split("/")[0] if "/" in r else ".") if group_by == "child" else \
                  (lambda r: TEMPLATE.sub("#", r))
            groups = Counter(key(r) for r in files)
            out["groups"] = [{"key": k, "files": n} for k, n in groups.most_common(limit)]
            out["groups_total"] = len(groups)
        elif len(files) <= limit:
            out["paths"] = sorted(files)
    lim = [l for l in arch_lim if "lower bound" in l or "workspace" in l]
    notes = [l for l in arch_lim if l not in lim]
    if skipped:
        lim.append(f"{skipped} paths under this scope were skipped by the probe (unreadable/excluded): use --live for an exact count")
    if policy_skipped and "::" not in scope:
        if tallied and not pats:
            out["files_including_skipped_folders"] = out.get("files", 0) + skipped_files
            notes.append(f"{policy_skipped} cache/vendor folders (__pycache__, .git, ...) hold {skipped_files} more files (counted, not read): "
                         "`files_including_skipped_folders` is the find | wc -l answer")
        else:
            lim.append(f"{policy_skipped} cache/vendor folders (__pycache__, .git, ...) were not listed by this index: their files are "
                       "missing from the count -- use --live for find | wc -l")
    out["status"] = "found" if (files or dirs) else "not_found"
    out["exhaustive"] = not lim
    out["limitations"] = lim or notes or ["counts come from the index snapshot; files created after the scan are not included"]
    return out


def count_live(ws: Path, name: str, scope: str, pattern: str | None, what: str = "files") -> dict:
    cfg = source.load(ws, name)
    sub = source._safe(scope or ".")
    if "::" in sub:
        arch, _, inner = sub.partition("::")
        lister = f"timeout 300 unzip -Z1 {shlex.quote(arch)}" if arch.lower().endswith(".zip") else f"timeout 300 tar -tf {shlex.quote(arch)}"
        cmd = f"set -o pipefail; cd {shlex.quote(cfg['root'])} && {lister} | sed 's#^\\./##' | grep -v '/$' | grep -c '^{re.escape(inner.strip('/'))}' ; echo __RC__$?"
    else:
        typ = "d" if what == "dirs" else "f"
        nm = f"-name {shlex.quote(pattern)}" if pattern else ""
        mind = "-mindepth 1" if typ == "d" else ""
        cmd = f"cd {shlex.quote(cfg['root'])} && timeout 300 find {shlex.quote(sub)} {mind} -type {typ} {nm} 2>/dev/null | wc -l; echo __RC__${{PIPESTATUS[0]}}"
    if cfg.get("host"):
        host, raw = source._remote(cfg, cmd, 330, "live count")
    else:
        host, raw = None, subprocess.run(["bash", "-c", cmd], capture_output=True, timeout=330).stdout
    text = raw.decode(errors="replace").split()
    n = int(text[0]) if text and text[0].isdigit() else None
    rc = next((t.replace("__RC__", "") for t in text if t.startswith("__RC__")), "?")
    done = rc in ("0", "1")
    return {"scope": scope, "name": pattern, "what": what, "origin": f"live ({host or 'local'})", "count": n,
            "status": "found" if done else "unknown", "exhaustive": done,
            "limitations": [] if done else [f"listing did not finish (exit {rc}): count is a lower bound"]}


HEX = re.compile(r"\b([0-9a-fA-F]{64}|[0-9a-fA-F]{40}|[0-9a-fA-F]{32})\b")
ALGO = {64: "sha256", 40: "sha1", 32: "md5"}


def _sidecars(con, path: str) -> list[str]:
    d, base = posixpath.dirname(path), posixpath.basename(path)
    rows = [r[0] for r in con.execute("SELECT path FROM files WHERE dir = ?", (d,))]
    out = []
    for p in rows:
        b = posixpath.basename(p).lower()
        if p == path:
            continue
        if b.startswith(base.lower()) and b.endswith((".sha256", ".sha256sum", ".sha1", ".md5", ".sum", ".checksum")) \
                or re.match(r"^(sha256|sha1|md5)sums?(\.txt)?$", b) or b in ("checksums.txt", "checksum.txt"):
            out.append(p)
    return out


def _text(con, ws, name, path) -> str | None:
    """Sidecars are tiny: read them live (verification must not trust a stale snapshot), snapshot as fallback."""
    try:
        return source.read_bytes(ws, name, path, max_bytes=256 * 1024).decode(errors="replace")
    except (HarnessError, OSError):
        row = con.execute("SELECT text FROM texts WHERE path = ?", (path,)).fetchone()
        return row[0] if row else None


LIST_LINE = re.compile(r"^\s*([0-9a-fA-F]{64})\s+\*?(\S.*?)\s*$|^\s*(\S.*?)\s+([0-9a-fA-F]{64})\s*$")


def verify_list(con, ws: Path, name: str, path: str, compute: bool = True, limit: int = 40) -> dict:
    """`sha256sum -c` for a checksum list (SHA256SUMS, CODE_SHA256SUMS.txt, ...): every entry checked against the
    file it names (index hash, else computed on the host), plus files next to the list that it does not cover."""
    text = _text(con, ws, name, path) or ""
    entries = []
    for line in text.splitlines():
        m = LIST_LINE.match(line)
        if m:
            h, n = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
            entries.append((n.strip().lstrip("./"), h.lower()))
    if not entries:
        raise HarnessError(f"{path} has no `<sha256>  <name>` lines")
    base = posixpath.dirname(path)
    shas = {}
    resolved = {}
    for n, _ in entries:
        for cand in (posixpath.normpath(posixpath.join(base, n)), n.lstrip("/")):
            row = con.execute("SELECT sha FROM files WHERE path = ?", (cand,)).fetchone()
            if row is not None:
                resolved[n] = cand
                shas[cand] = row[0]
                break
    unresolved = [n for n, _ in entries if n not in resolved]
    if unresolved:
        # lists written elsewhere (`cd run && sha256sum ... > ../FILES.sha256`, or names relative to a parent):
        # find one entry by suffix near the list, take its base folder and re-resolve every entry from there
        top = path.split("/")[0]
        rng = fid_range(con, top) if "/" in path else None
        for n in unresolved[:5]:
            q = "SELECT path FROM files WHERE path LIKE ? " + ("AND fid BETWEEN ? AND ? " if rng else "") + "LIMIT 3"
            hits = [r[0] for r in con.execute(q, (f"%/{n}",) + (tuple(rng) if rng else ()))]
            if len(hits) == 1:
                newbase = hits[0][: -len(n)].rstrip("/")
                for m, _ in entries:
                    if m in resolved:
                        continue
                    cand = posixpath.normpath(posixpath.join(newbase, m))
                    row = con.execute("SELECT sha FROM files WHERE path = ?", (cand,)).fetchone()
                    if row is not None:
                        resolved[m] = cand
                        shas[cand] = row[0]
                base = newbase
                break
    todo = [p for p in resolved.values() if not shas.get(p)]
    origin = "index hashes"
    if todo and compute:
        cfg = source.load(ws, name)
        listing = "\n".join(todo[:3000]).encode()
        cmd = f"cd {shlex.quote(cfg['root'])} && tr '\\n' '\\0' | timeout 900 xargs -0 sha256sum 2>/dev/null; true"
        if cfg.get("host"):
            _, raw = source._remote(cfg, cmd, 960, "checksum list", stdin=listing)
        else:
            raw = subprocess.run(["bash", "-c", cmd], input=listing, capture_output=True, timeout=960).stdout
        for line in raw.decode(errors="replace").splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2 and len(parts[0]) == 64:
                shas[parts[1].strip().lstrip("*")] = parts[0]
        origin += f" + {len(todo)} computed on the host"
    ok, bad, missing, unknown = [], [], [], []
    for n, h in entries:
        p = resolved.get(n)
        if p is None:
            missing.append(n)
        elif not shas.get(p):
            unknown.append(n)
        elif shas[p] == h:
            ok.append(n)
        else:
            bad.append({"file": p, "listed": h[:16], "actual": shas[p][:16]})
    listed = set(resolved.values())
    covered_dirs = {posixpath.dirname(p) for p in listed}
    extra = sorted(r[0] for d in covered_dirs for r in con.execute("SELECT path FROM files WHERE dir = ?", (d,))
                   if r[0] not in listed and r[0] != path and not r[0].lower().endswith((".sha256", "sums.txt", ".md5")))
    dup = Counter(h for _, h in entries)
    same_hash = [[n for n, h in entries if h == x] for x, c in dup.items() if c > 1]
    return {"list": path, "entries": len(entries), "ok": len(ok), "mismatch": bad[:limit], "mismatch_total": len(bad),
            "missing_files": missing[:limit], "missing_total": len(missing), "not_hashed": unknown[:limit],
            "unlisted_files_in_covered_folders": extra[:limit], "unlisted_total": len(extra),
            "entries_sharing_a_hash": same_hash[:10], "origin": origin,
            "verdict": "all_match" if len(ok) == len(entries) else "problems",
            "names_resolved_from": base or ".",
            "status": "found", "limitations": ["names are resolved relative to the list's folder, the source root, or the folder "
                                               "where one listed name is found by suffix (reported as names_resolved_from)"]}


def checksum(con, ws: Path, name: str, path: str, compute: bool = True) -> dict:
    """sha256 of a file (index hash when the probe computed it, else `sha256sum` on the host) compared with every
    sidecar checksum file next to it (x.tar.gz.sha256, SHA256SUMS, ...)."""
    path = source._safe(path)
    txt = con.execute("SELECT text FROM texts WHERE path = ?", (path,)).fetchone()
    if txt and sum(1 for line in (txt[0] or "").splitlines()[:50] if LIST_LINE.match(line)) >= 2:
        return verify_list(con, ws, name, path, compute)  # the path is itself a checksum list
    row = con.execute("SELECT sha, size FROM files WHERE path = ?", (path,)).fetchone()
    if row is None:
        raise HarnessError(f"{path} is not in the index; use the path printed by trace ls")
    sha, origin = row[0], "index (probe hash)"
    claims = []
    for sc in _sidecars(con, path):
        text = _text(con, ws, name, sc) or ""
        base = posixpath.basename(path)
        for line in text.splitlines():
            m = HEX.search(line)
            if not m:
                continue
            names = line.replace(m.group(1), " ").strip(" *\t")
            if names and base not in names and len(text.splitlines()) > 1:
                continue  # a SUMS file line for another file
            claims.append({"sidecar": sc, "algo": ALGO[len(m.group(1))], "value": m.group(1).lower(), "line": line.strip()[:200]})
    need = {c["algo"] for c in claims} | {"sha256"}
    digests = {"sha256": sha} if sha else {}
    missing = [a for a in sorted(need) if a not in digests]
    if missing and compute:
        cfg = source.load(ws, name)
        cmds = " ; ".join(f"echo {a} $(timeout 1500 {a}sum -- {shlex.quote(path)} | cut -c1-{ {'sha256': 64, 'sha1': 40, 'md5': 32}[a]})" for a in missing)
        cmd = f"cd {shlex.quote(cfg['root'])} && {cmds}"
        if cfg.get("host"):
            host, raw = source._remote(cfg, cmd, 1600, "checksum")
        else:
            host, raw = "local", subprocess.run(["bash", "-c", cmd], capture_output=True, timeout=1600).stdout
        for line in raw.decode(errors="replace").splitlines():
            parts = line.split()
            if len(parts) == 2 and HEX.fullmatch(parts[1]):
                digests[parts[0]] = parts[1].lower()
        origin = (origin + " + " if sha else "") + f"computed live on {host}"
    for c in claims:
        have = digests.get(c["algo"])
        c["match"] = None if have is None else (have == c["value"])
    verdict = ("no_sidecar" if not claims else
               "match" if all(c["match"] for c in claims) else
               "mismatch" if any(c["match"] is False for c in claims) else "unknown")
    return {"path": path, "size": row[1], "digests": digests, "origin": origin, "sidecars": claims, "verdict": verdict,
            "status": "found" if digests else "unknown",
            "limitations": [] if digests else ["hash not computed (pass --compute or the host timed out)"]}


def compare(con, a: str, b: str, limit: int = 40, ws=None, source_name=None) -> dict:
    """Set comparison of two trees by relative path: a directory, or an archive (`x.tgz::` / `x.tgz::sub/`).
    Same-named files are compared by sha when both sides were hashed."""
    notes = []

    def side(scope):
        if "::" in scope:
            rows, _, lim = archive_side(con, ws, source_name, scope)
            notes.extend(lim)
            return rows
        rows = {}
        for p, sha, size in _scope_rows(con, scope, "path, sha, size"):
            if "::" in p and "::" not in scope:
                continue
            rel = _rel(p, scope.strip("/"))
            # archives often hold a top folder named like the live one: strip it if every member shares it
            rows[rel] = (sha, size)
        return rows
    A, B = side(a), side(b)
    for X, Y in ((A, B), (B, A)):
        tops = {k.split("/")[0] for k in X}
        if len(tops) == 1 and "/" in next(iter(X), "") and not (set(X) & set(Y)):
            t = tops.pop() + "/"
            stripped = {k[len(t):]: v for k, v in X.items()}
            if set(stripped) & set(Y):
                X.clear()
                X.update(stripped)
    only_a, only_b = sorted(set(A) - set(B)), sorted(set(B) - set(A))
    both = sorted(set(A) & set(B))
    differ = [k for k in both if A[k][0] and B[k][0] and A[k][0] != B[k][0]]
    unknown = [k for k in both if not (A[k][0] and B[k][0]) and A[k][1] != B[k][1]]
    same = len(both) - len(differ) - len(unknown)

    def by_dir(keys):
        # roll up to the top two levels: "what is missing" reads as folders, not 1000 leaf paths
        c = Counter("/".join(posixpath.dirname(k).split("/")[:2]) or "." for k in keys)
        return [{"dir": d, "files": n} for d, n in c.most_common(15)]
    return {"a": a, "b": b, "files_a": len(A), "files_b": len(B), "in_both": len(both),
            "identical_or_unhashed_same_size": same, "content_differs": differ[:limit], "size_differs_unhashed": unknown[:limit],
            "only_in_a": only_a[:limit], "only_in_a_total": len(only_a), "only_in_a_by_dir": by_dir(only_a),
            "only_in_b": only_b[:limit], "only_in_b_total": len(only_b), "only_in_b_by_dir": by_dir(only_b),
            "status": "found" if (A or B) else "not_found",
            "limitations": notes + ["folders from the index snapshot; members listed live carry sizes but no hashes"]}


GIT_OK = re.compile(r"^[0-9A-Za-z_./@^~\-]{1,120}$")


def git(ws: Path, name: str, repo: str, refs: list[str]) -> dict:
    """Read-only git questions on the source host: does each ref/commit exist in this checkout's object store,
    what is it, and which branches contain it."""
    cfg = source.load(ws, name)
    repo = source._safe(repo or ".")
    bad = [r for r in refs if not GIT_OK.match(r)]
    if bad:
        raise HarnessError(f"refused refs {bad}: only commit ids, branch or tag names")
    q = shlex.quote
    sd = q(posixpath.normpath(posixpath.join(cfg["root"].replace("\\", "/"), repo)))  # read-only access to another user's checkout
    parts = [f"echo __HEAD__; timeout 30 git -C {q(repo)} rev-parse --abbrev-ref HEAD 2>&1; timeout 30 git -C {q(repo)} log -1 --format='%H %cI %s' 2>&1"]
    for r in refs:
        parts.append(f"echo __REF__ {q(r)}; timeout 30 git -C {q(repo)} cat-file -t {q(r)} 2>&1; echo __RC__$?; "
                     f"timeout 30 git -C {q(repo)} log -1 --format='%H %cI %an %s' {q(r)} -- 2>/dev/null; "
                     f"echo __BR__; timeout 30 git -C {q(repo)} branch -a --contains {q(r)} 2>/dev/null | head -n 10")
    # older git honours safe.directory only from global config: point GIT_CONFIG_GLOBAL at a throwaway file
    cmd = (f"cd {q(cfg['root'])} && export GIT_OPTIONAL_LOCKS=0; g=$(mktemp) && printf '[safe]\\n\\tdirectory = %s\\n\\tdirectory = *\\n' {sd} > $g "
           f"&& export GIT_CONFIG_GLOBAL=$g; " + "; ".join(parts) + "; rm -f $g")
    if cfg.get("host"):
        host, raw = source._remote(cfg, cmd, 300, "git")
    else:
        host, raw = "local", subprocess.run(["bash", "-c", cmd], capture_output=True, timeout=300).stdout
    text = raw.decode(errors="replace")
    head_block, *ref_blocks = text.split("__REF__ ")
    head = [l for l in head_block.replace("__HEAD__", "").splitlines() if l.strip()]
    out = {"repo": repo, "host": host, "head": head[:2], "refs": []}
    for blk in ref_blocks:
        ref, _, rest = blk.partition("\n")
        typ, _, rest = rest.partition("__RC__")
        rc, _, rest = rest.partition("\n")
        info, _, br = rest.partition("__BR__")
        exists = rc.strip() == "0"
        missing = re.search(r"Not a valid object name|could not get object info|unknown revision|bad revision", typ)
        out["refs"].append({"ref": ref.strip(), "exists_in_objects": True if exists else (False if missing else None),
                            "type": typ.strip() if exists else None,
                            "error": None if exists else typ.strip()[:200],
                            "commit": info.strip() or None,
                            "branches": [b.strip(" *") for b in br.splitlines() if b.strip()]})
    if "not a git repository" in text:
        out["status"] = "not_found"
        out["limitations"] = [f"{repo} is not a git checkout on {host}"]
    else:
        out["status"] = "found"
        out["limitations"] = ["exists_in_objects=false means this checkout's object store lacks it (shallow clone, "
                              "never fetched, or a typo) -- not that the commit never existed"]
    return out
