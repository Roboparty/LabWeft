# Semantic patch protocol v1

`rh context WORKSPACE --full` returns the persisted project, revision, nodes,
files and edges. `rh apply WORKSPACE PATCH.json` applies full-object upserts to
nodes/edges, not arbitrary filesystem edits. There is no automatic deletion or
source-code execution. Each successful transaction records actor, reason, time,
previous hash, and monotonically increasing revision. A repeat with no actual
changes does not create a new revision. Empty or stale evidence is an error.

## Node kinds and relationship types

Kinds: `module`, `question`, `cell`, `run`, `evaluation`, `artifact`, `claim`,
`decision`. Parent points to a node or the manifest project ID. A parent tree is
only navigation; explicit edges represent shared baselines and cross-links.
Relations: `derived_from`, `compares`, `supports`, `contradicts`,
`uses_checkpoint`, `supersedes`, `inspired_by`. Never confuse method derivation
with inherited weights. Every edge endpoint must exist.

## Scientific structure before source indexing

Write a source-attributed scientific outline before the semantic patch: project
objective, method and baseline families, hypotheses, study/ablation hierarchy,
actual comparison factors, evaluation endpoints, and candidate main findings.
The outline is a working interpretation, not a claim that every file was read.
Source directories, phase numbers and manuscript table numbers locate evidence;
they do not define the research taxonomy. Reconcile the outline with the
researcher's prior corrections and revise it as new sources arrive. Preserve
node IDs and event history when moving a node to a better semantic parent.

`module` may be nested to represent a project-specific research track, method
family, study or ablation group. The following optional `attrs` are compatible
with existing workspaces and give the host agent and UI a common vocabulary:

```json
{
  "role": "study",
  "design": {
    "hypothesis": "The single factor being tested",
    "factor": "an effective-configuration field or scientific manipulation",
    "levels": ["control", "treatment"],
    "held_constant": ["dataset_version", "eval_protocol"],
    "co_varying": [],
    "selection_rule": "pre-specified or post-hoc, with source"
  }
}
```

Use roles such as `research_area`, `method_family`, `baseline_family`, `study`,
`ablation_group`, `generalization`, or `evidence_audit` only when the source
supports them; unknown roles remain unassigned. `held_constant` is a verified
claim about effective conditions, not a guess from similar names. A project may
use other roles and need not contain any particular experiment family.

The `claim` kind is for empirical findings, mechanistic interpretations, negative
results and scope boundaries. An optional `attrs.finding` object marks findings
that should be prominent in the research map and groups source-audit notes away
from the main conclusions:

```json
{
  "finding": {
    "type": "effect",
    "priority": "primary",
    "comparison": {
      "baseline_cell_ids": ["cell-control"],
      "treatment_cell_ids": ["cell-treatment"],
      "factor": "verified changed factor"
    },
    "endpoint": {
      "metric": "success_rate",
      "unit": "percentage points",
      "dataset": "recorded dataset",
      "protocol": "recorded protocol",
      "readout": "recorded readout"
    },
    "estimate": {"delta": 1.2, "sample_unit": "training seed", "n": 3},
    "basis": "source_report",
    "limitations": ["conditions not fully matched"]
  }
}
```

`priority` is `primary`, `secondary`, or `audit`. Omit it on older records;
the UI keeps them accessible as uncategorized records instead of silently
promoting them to main findings. `type` may be `effect`,
`mechanism_interpretation`, `negative_result`, `boundary`, or `status`.
`primary` and `secondary` claims require direct immutable evidence and a
non-empty `attrs.scope`; the validator rejects prominent unsourced findings.
Qualitative findings may omit `estimate`, but must describe direct support and
limits. The example numbers above are synthetic placeholders, never values to
copy into a real project. Do not assign numeric confidence scores without a
defined calibration procedure. `basis` distinguishes a source report,
independent recomputation, actual rerun, or attributed user testimony. A
positive comparison under one endpoint does not automatically win under another.

`decision` means a scoped action, selection or reuse judgment; it is not a
synonym for scientific conclusion. Keep unconfirmed recommendations as proposals.
The existing accepted/protected/confirmation requirements continue to apply.

Node IDs, kind and evidence identity are durable. Reuse existing IDs when
reclassifying an imported candidate. `kind` is immutable. To retire something,
set `status: archived`; do not erase evidence. Nodes with `protected: true` can
not be changed by `apply`. The `confirm` command is a deliberate human operation;
this CLI restriction is not an authentication system against an adversarial
agent with unrestricted local shell access.

```json
{
  "base_revision": 2,
  "reason": "Mapped the history ablation after inspecting effective configuration and source",
  "nodes": [
    {
      "id": "question-history",
      "kind": "question",
      "label": "Does history help under the current evaluation protocol?",
      "parent_id": "PROJECT_ID_FROM_CONTEXT",
      "status": "provisional",
      "description": "Record whether purpose is explicit in source notes or inferred.",
      "attrs": {"purpose_basis": "agent_inference"},
      "evidence": [{"file_id": "EXISTING_FILE_ID", "sha256": "EXISTING_64_CHARACTER_HASH", "locator": "lines 8-19"}]
    }
  ],
  "edges": []
}
```

Placeholders above are not valid IDs/hashes; replace from `files` and `context`.
The actual source snapshot must exist. Referencing a file is not proof that the
text supports the claim; the agent must check it. An accepted claim/decision
requires non-empty scope and at least one direct immutable source snapshot.
Linked nodes aid navigation but do not replace direct evidence.

## Minimal Cell/Run mapping for a custom result file

After reading an unrecognized JSON or CSV source, one scientific condition is a
Cell and each independent training seed is a child Run. The following is one
**synthetic** completed seed. Replace the project ID, source file ID/hash,
locator, run identity, protocol and values with verified source facts. Add one
Run per independently completed seed; do not copy a reported aggregate into
three invented seed runs.

```json
{
  "base_revision": 2,
  "reason": "Mapped a custom result after checking run completion and protocol",
  "nodes": [
    {
      "id": "cell-policy-a",
      "kind": "cell",
      "label": "Policy A under heldout-v1",
      "parent_id": "PROJECT_ID_FROM_CONTEXT",
      "status": "recorded",
      "description": "One verified condition; seed is not a cell factor.",
      "attrs": {"config": {"model": "policy-A", "eval_protocol": "heldout-v1"}},
      "evidence": [{"file_id": "EXISTING_FILE_ID", "sha256": "EXISTING_64_CHARACTER_HASH", "locator": "$.conditions[0]"}]
    },
    {
      "id": "run-policy-a-s7",
      "kind": "run",
      "label": "Recorded run identifier for seed 7",
      "parent_id": "cell-policy-a",
      "status": "completed",
      "description": "Completion and training-seed identity verified in the source; success_rate is a fraction in [0, 1].",
      "attrs": {
        "config": {"model": "policy-A", "eval_protocol": "heldout-v1", "seed": 7},
        "seed": 7,
        "run_id": "source-run-s7",
        "eval_protocol": "heldout-v1",
        "code_revision": null,
        "metrics": {"success_rate": 0.62}
      },
      "evidence": [{"file_id": "EXISTING_FILE_ID", "sha256": "EXISTING_64_CHARACTER_HASH", "locator": "$.conditions[0].runs[0]"}]
    }
  ],
  "edges": []
}
```

For `compare`, each Run needs a unique training `seed`, numeric value under a
shared metric key in `attrs.metrics`, a known `attrs.eval_protocol`, a compatible
`attrs.config` that equals its Cell config except seed, and `status: completed`
only when completion is supported. Record unknown code revision as `null`; never
substitute today's checkout. Preserve metric units in the key or description.
Retries or duplicate records of the same training seed are not independent
replicates; resolve their identity and select the valid result before pooling.
`compare` computes arithmetic mean and **sample SD** across eligible independent
training seeds; with one seed the SD is unknown. Verify whether a source report
uses sample or population SD before comparing its printed `±` to this output.
Missing dataset version, training steps or code identity should remain explicit
comparison limits. Run `validate` and `compare` after the patch, then rescan to
check the semantic mapping survives incremental source indexing.

## Scope-aware reuse decision

```json
{
  "action": "reuse",
  "question_id": "question-hardware",
  "scope": {
    "required_context": {
      "dataset_version": "data-v1",
      "eval_protocol": "eval-v1",
      "implementation_id": "policy-v1",
      "precision": "fp32",
      "train_steps": 20000
    },
    "covered_values": {"hardware": ["GPU-A", "GPU-B"]},
    "replication_keys": ["seed"]
  },
  "reopen_if": "Relevant implementation, precision, data or evaluation changes, or new contradictory evidence."
}
```

This is `attrs` on a decision node. Scope checks require every listed field;
new configuration fields outside the scope trigger review, not automatic
rejection and not automatic experimental execution. The decision must be
accepted and explicitly human-confirmed before the deterministic checker treats
it as approved coverage. Imported testimony needs an attributed user-note source;
never manufacture an audited experiment record from testimony.

## JSON proposal for assess

```json
{
  "question_id": "question-hardware",
  "config": {
    "dataset_version": "data-v1",
    "eval_protocol": "eval-v1",
    "implementation_id": "policy-v1",
    "precision": "fp32",
    "train_steps": 20000,
    "hardware": "GPU-B",
    "seed": 4
  }
}
```

Outputs separate coverage, review, repeat candidates and replication. They never
start training. A repeated seed is not automatically duplicate science, and a
new seed is not automatically necessary. The research purpose decides.

## Known import boundary

Native ingestion recognizes `metrics.json`, `results.json`, `metrics.csv`, paired
with `config.json`/`config.toml` and optional `run.json`. YAML, other custom output
names and logs are evidence sources for the host agent, not automatically
normalized runs. The agent can add nodes in this protocol after inspecting them.
Historical identity is taken only from recorded `run.json` fields; today's
source is never automatically assigned to an old run. Two dirs with equal config
are candidate cells, not proven equivalence. Missing seeds and unverified
completion are excluded from seed-level aggregates.
