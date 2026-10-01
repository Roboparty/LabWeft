# Optional Shinka research backend

[中文](AUTORESEARCH.zh-CN.md)

LabWeft now has an explicit `research` CLI workflow. Normal `sync`, `assess`,
`serve`, and the browser remain read-only with respect to research source and
execution. The core still needs only Python 3.11+. Shinka is an optional engine,
not a mandatory model SDK or a second user-operated agent conversation.

## Scope of this first adapter

- Freeze a small Python task, protocol name, explicit model list, finite absolute
  generation budget, evaluation timeout, concurrency, and optional API cost estimate.
- Run Shinka's native program search and local evaluator scheduler in a background
  worker on the **same machine** as the LabWeft workspace. For remote compute,
  install and invoke this workflow on the remote machine. This is not an SSH/GPU
  resource scheduler; it does not allocate or inspect GPUs.
- Stop after the current bounded batch drains, then resume the same native database.
- Import native candidates, parent relationships, correct/incorrect reports,
  scores, metrics, code hashes, and raw cost metadata into existing graph objects.
- Preserve unknown costs and keep backend success separate from independent
  verification, scientific claims, and data qualification.

## Install and prepare

In the chosen execution environment:

```sh
python -m pip install ".[shinka]"
python labweft.py init /path/to/workspace --name "My study"
python labweft.py research prepare /path/to/workspace /path/to/campaign.json
python labweft.py research start /path/to/workspace study-id
```

The last command only previews the frozen contract. Preparation reads explicitly
listed small files (5 MiB total), copies them to a task snapshot, and hashes them;
it never imports task code or contacts a model. Paths in `files` are relative to
`task_dir`; `task_dir` is relative to the specification file. List any small
helper/config files the evaluator needs. Keep large datasets and artifacts on the
execution host; reference them from the evaluator with your own frozen manifest.

See [the synthetic specification](../examples/shinka/campaign.json). Replace its
model placeholder before use. Credentials are supplied by the execution environment,
not stored in the specification. The same id is idempotent for identical inputs;
changing inputs or limits requires a new id. Candidate scope is a single Python
initial program; whole-repository mutation is not implemented.

The optional extra pins SakanaAI/ShinkaEvolve to
`9912af12d423504b8d580f4179fd15f5f88b8c50` (upstream version label `0.0.7`).
Start checks the installation's direct-URL commit metadata. A version string alone
is insufficient because the upstream API can change without changing that label.
This adapter uses `ShinkaEvolveRunner`, `EvolutionConfig`, `DatabaseConfig`, and
`LocalJobConfig`. Review and test the adapter when updating the dependency pin.
No upstream source is vendored. See [attribution](../ACKNOWLEDGEMENTS.md).

## Execute and observe

```sh
python labweft.py research start /path/to/workspace study-id --execute
python labweft.py research status /path/to/workspace study-id
python labweft.py research collect /path/to/workspace study-id
python labweft.py serve /path/to/workspace
python labweft.py research stop /path/to/workspace study-id
python labweft.py research resume /path/to/workspace study-id --execute
```

`--execute` is a deliberate execution boundary, not an authorization system. The
host agent must already have permission for the model/compute/task scope. Preparing
a campaign does not authorize its execution. Source hashes detect input changes;
they do **not** sandbox arbitrary candidate or evaluator code. Use an isolated
environment with appropriate permissions for real execution. The HTTP UI gains
no write, shell or launch endpoint.

Shinka is the only experiment dispatcher. The adapter disables embedding,
meta-summary, novelty-judge and prompt-evolution model calls, and W&B logging;
only the explicitly named mutation models are configured. Parent selection and
island search remain native. This first configuration intentionally does not enable
every Shinka search feature. Logs stay in `worker.log` and the native result directory.

`max_generations` is an absolute budget including generation zero, not a fresh
allowance on each resume. The first batch has at least two generations so the
pinned native runner can resume a database with a nonzero last iteration. Later
batches advance by `batch_size` up to the original total. Small batches provide
more stop opportunities but add runner setup overhead. A stop racing with a batch
already reserved under the control lock drains that batch too. Evaluator timeouts
are native per-job limits; they are not a whole-campaign wall-clock deadline.

`max_api_cost_usd` is the upstream provider-cost estimate limit, with native
accounting retained across batches. It is **not** a hard invoiced-dollar cap and
does not include GPU rent or all infrastructure costs. A generation may involve
several proposal attempts or native evaluator recovery attempts; the generation
limit is not an exact physical-start or API-request limit. Raw native attempt logs
remain available. Domain adapters requiring fixed attempt ledgers, like Luna,
need that additional executor contract before deployment.

## Lifecycle and interruption

`ready → starting → running → completed`, with `paused` at a drained stop boundary
and `needs_review` on errors or incomplete native coverage. A machine-local OS lock
permits one worker per activity. Stop writes a request; it does not signal or kill
any process. Clean resume retains ids, hashes, results and native cost records.

An abrupt worker/machine crash during a batch is **not automatically resumed**:
native evaluator children may still be active, and the database alone cannot
prove their state. Status exposes a released worker lock and a `needs_review`
effective phase for an abandoned running activity. A launch that stays `starting`
without a worker is also ambiguous, and repeated start/resume is rejected.
Inspect logs, actual evaluator identities and native artifacts before manual
reconciliation; do not delete state/locks, silently reset budgets, or edit the
phase to make it runnable. Automatic orphan reconciliation is not implemented.

## Evidence and identity

Each activity binds to the LabWeft project id and an immutable contract hash.
Native program ids map deterministically to cell/run/evaluation ids; each real
Shinka program record stays distinct, including failed programs and native copies.
Native retry attempts remain in the native logs rather than becoming independent
LabWeft experiments. `derived_from` records the native parent relation. Missing
parents remain explicit unresolved ids. Re-collecting identical facts is a no-op;
reusing a native id with different code is rejected before graph writes.

Reports are read from `native/programs.sqlite` through a read-only transaction.
Small normalized JSON reports and code are saved as immutable LabWeft text blobs;
nonfinite numbers become unknown, and oversized or unsupported records are rejected.
The importer does not execute code, read native pickle checkpoints, infer training
seeds, declare a winner, or promote scores into a scientific finding. Native
Shinka itself may load its own checkpoint state when explicitly executed/resumed;
never resume an untrusted result directory.

The original statistical `compare` command receives no fabricated seed or completed
training run from this adapter. Imported evaluations remain provisional and billed
cost remains null; domain qualification must be recorded separately with evidence.
Ordinary graph and offline export views can inspect the question, candidates,
lineage, result attributes and source snapshots. No dedicated control panel is added.

Runtime files live under `.research/autoresearch/<id>/` and are ignored by a local
Git ignore file. Evidence and research events follow the existing workspace model.
Keep the complete runtime directory for recovery; copying the graph alone does
not back up native artifacts. Do not commit private study data to the tool repository.

## Validation boundary

Run `python -m unittest discover -s tests -v`. Offline tests use explicitly synthetic
native-format fixtures and an injected backend to verify lifecycle, failed-result
retention, imports, drift, idempotence, budgets, pause/resume and ambiguous crashes.
They also check the public adapter's configuration and the cheap example evaluator.
These tests do not demonstrate live provider calls, Shinka search improvements,
GPU execution, SSH scheduling, or Luna physical/data qualification. An actual
authorized small Shinka run is the next deployment check in the target environment.

The [2026-10-01 validation record](validation/shinka-backend-20261001.json) records
87 passing tests, one existing Windows symlink skip, a clean core-only wheel install,
actual CPU evaluator cases, and the separate pinned-source API signature check.
