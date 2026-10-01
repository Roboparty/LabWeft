# Optional Shinka execution protocol

Use only for an explicit automatic-research execution request. Continue using one
host conversation. Do not install a second model account or launch additional
user-operated agent sessions. The optional runtime is installed in the actual
execution environment via `pip install ".[shinka]"` from the LabWeft checkout.

1. Read the workspace and existing user-authorized compute/model scope. Build a
   specification with `id`, `question`, `task_dir`, explicit relative `files`
   containing `initial.py` and `evaluate.py`, explicit `models`, `max_generations`
   (at least 2, includes baseline zero), `evaluation_timeout_seconds`, and a
   descriptive `evaluation_protocol`. Optional fields are `instructions`,
   `batch_size`, `max_evaluation_jobs`, `num_islands`, `max_api_cost_usd`.
2. `labweft research prepare WORKSPACE SPEC.json` freezes up to 5 MiB of small
   source/config inputs without importing them. Large data stays at the execution
   host. Relative task paths resolve against the spec file. Changed contracts
   need new ids; do not overwrite the original activity or reset its history.
3. `labweft research start WORKSPACE ID` previews the contract. If existing user
   authorization covers execution, add `--execute` to start. Otherwise obtain
   the missing scope after making this concrete preview available. Never ask
   again merely because another candidate is ready within the same scope.
4. Use `status` and `collect` to read progress and import evidence. The background
   worker advances bounded batches and collects after each batch. Scheduling a
   future chat wakeup is a separate host capability and requires a user request.
   Before presenting or exporting results, apply the
   [per-version annotation contract](PROTOCOL.md#per-version-change-annotations)
   to every baseline and proposal: inspect its actual parent, code/config delta,
   proposal rationale and evaluation outcome. Preserve the distinction between
   proposed benefit and observed result. Check and restore these semantic
   annotations after subsequent backend collections; native reports alone are
   not the finished research explanation.
5. `stop` drains the current batch; `resume --execute` continues a clean `paused`
   activity using the same database and original absolute generation allowance.
   Unknown launch/worker outcomes or `needs_review` require inspection of actual
   process identities and evidence. Do not manually change phases, delete results,
   or create fresh budgets to bypass ambiguity. Automatic crash reconciliation is
   not implemented. Do not kill unrelated processes.

The adapter is for a Python program and local native scheduler on the execution
machine. It does not allocate GPUs or implement SSH, and does not yet implement
Luna's fixed physical-start ledger. Generation budgets are not exact API-call or
simulation-attempt counts. Monetary caps are native estimates, not invoices.
Failed generations, native retry logs and unknown costs must remain available.

Imported records are provisional backend reports, not accepted scientific claims,
human confirmations, qualified datasets or completed independent training seeds.
Use the original research protocol to assess evidence and scope separately. Hashes
are not a code sandbox; run trusted tasks in an appropriate isolated environment.
Core scans and browser views never trigger execution or model calls.
