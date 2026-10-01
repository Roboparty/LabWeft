"""Adapter for one pinned upstream Shinka API; no vendored upstream code."""
from __future__ import annotations

from contextlib import closing
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import sqlite3
import sys

from ..store import HarnessError

REVISION = "9912af12d423504b8d580f4179fd15f5f88b8c50"
DEPENDENCY = "shinka-evolve @ git+https://github.com/SakanaAI/ShinkaEvolve.git@" + REVISION
MAX_RECORD_BYTES = 2 * 1024 * 1024


def finite_values(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: finite_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [finite_values(item) for item in value]
    return value


def inspect_installation() -> dict:
    """Read package metadata only: no import, dotenv loading or provider access."""
    try:
        dist = importlib.metadata.distribution("shinka-evolve")
    except importlib.metadata.PackageNotFoundError as exc:
        raise HarnessError('Shinka is optional. Install this checkout with pip install ".[shinka]" in the execution environment.') from exc
    origin = json.loads(dist.read_text("direct_url.json") or "{}")
    revision = origin.get("vcs_info", {}).get("commit_id")
    if revision != REVISION:
        raise HarnessError(f"Shinka requires upstream revision {REVISION}; installed provenance is {revision!r}. Install the pinned extra.")
    return {"distribution": "shinka-evolve", "version": dist.version, "revision": revision}


def read_programs(directory: Path) -> list[dict]:
    """Take a consistent read-only SQLite snapshot; never load pickle checkpoints."""
    path = directory / "programs.sqlite"
    if not path.exists():
        return []
    if path.is_symlink() or directory.is_symlink():
        raise HarnessError("Refusing a symlinked Shinka database")
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            required = {"id", "code", "parent_id", "generation", "correct", "combined_score",
                        "public_metrics", "private_metrics", "metadata", "island_idx"}
            columns = {r[1] for r in db.execute("PRAGMA table_info(programs)")}
            if not required <= columns:
                raise HarnessError("Unsupported Shinka programs schema; no results imported")
            result = []
            for row in db.execute("SELECT " + ",".join(sorted(required)) + " FROM programs ORDER BY generation, id"):
                item = dict(row)
                if not isinstance(item["id"], str) or not item["id"]:
                    raise HarnessError("Missing native candidate identity")
                if type(item["generation"]) is not int or item["generation"] < 0:
                    raise HarnessError("Invalid native generation")
                if not isinstance(item["code"], str) or len(item["code"].encode()) > MAX_RECORD_BYTES:
                    raise HarnessError("Candidate code exceeds the small-text import limit")
                for key in ("public_metrics", "private_metrics", "metadata"):
                    raw = item[key] or "{}"
                    if len(raw.encode()) > MAX_RECORD_BYTES:
                        raise HarnessError("Candidate metadata exceeds the small-text import limit")
                    item[key] = finite_values(json.loads(raw, parse_constant=lambda value: None))
                    if not isinstance(item[key], dict):
                        raise HarnessError(f"Invalid {key} for {item['id']}")
                score = item["combined_score"]
                item["combined_score"] = score if isinstance(score, (int, float)) and math.isfinite(score) else None
                item["correct"] = bool(item["correct"]) if item["correct"] in (0, 1) else None
                item["code_sha256"] = hashlib.sha256(item["code"].encode()).hexdigest()
                # Preserve raw metadata as evidence, never equate provider estimates to paid costs.
                result.append(item)
            return result
    except (sqlite3.Error, ValueError, TypeError) as exc:
        raise HarnessError(f"Cannot read native results: {exc}") from exc


class ShinkaBackend:
    name = "shinka"

    def preflight(self) -> dict:
        return inspect_installation()

    def run_batch(self, contract: dict, directory: Path, target: int) -> None:
        """Finish a bounded native run before accepting the next stop/resume boundary.

        Targets are absolute generation counts, including generation zero. The same
        database and native cost accounting are reused. No second GPU scheduler exists.
        """
        self.preflight()
        from shinka.core import EvolutionConfig, ShinkaEvolveRunner
        from shinka.database import DatabaseConfig
        from shinka.launch import LocalJobConfig

        task = directory / "task"
        seconds = contract["evaluation_timeout_seconds"]
        timeout = f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"
        evo = EvolutionConfig(
            task_sys_msg=contract["question"] + "\n" + contract["instructions"],
            init_program_path=str(task / "initial.py"), results_dir=str(directory / "native"),
            num_generations=target, job_type="local", language="python",
            llm_models=contract["models"], llm_dynamic_selection="ucb",
            # No hidden embedding/meta/prompt-evolution model requests in this adapter.
            embedding_model=None, meta_rec_interval=None, evolve_prompts=False,
            max_novelty_attempts=1, max_patch_resamples=3, max_patch_attempts=1,
            max_api_costs=contract["max_api_cost_usd"], enable_wandb_logging=False,
            enable_controlled_oversubscription=False,
        )
        runner = ShinkaEvolveRunner(
            evo_config=evo,
            db_config=DatabaseConfig(num_islands=contract["num_islands"]),
            job_config=LocalJobConfig(eval_program_path=str(task / "evaluate.py"), time=timeout,
                                      python_executable=sys.executable),
            max_evaluation_jobs=contract["max_evaluation_jobs"], max_proposal_jobs=1,
            max_db_workers=1, verbose=False,
        )
        runner.run()

    def collect(self, directory: Path) -> list[dict]:
        return read_programs(directory / "native")
