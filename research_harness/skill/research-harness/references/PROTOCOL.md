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

## Research Organization and Display

The map projects recorded Run-to-Run derivations between their owning Cells.
This is read-only provenance aggregation, not a claim that every replicate has
the same ancestry. Duplicate visual links retain their Run sources; intra-Cell
replication is not a new condition. Multiple origins and cycles remain visible.
Record the actual Run relationship instead of inventing a Cell-level one for
the renderer.

An optional `attrs.current_focus: "STABLE_NODE_ID"` on a project-level module
selects the current research line. The focused view retains recorded origins;
All research tracks and Outline expose the full history. It does not change
scientific status, evidence, or run counts.
Use a visible module, question or Cell ID; a Run ID resolves to its owning Cell.
Archived declarations and unsupported focus targets do not hide the full map.

Keep the research reasoning chain separate from implementation execution flow
and the run ledger. Each major step identifies the question, baseline, change,
observed result and ensuing decision. Source names and runtime phases are not
research reasoning. The `organization` report in `context`/`validate` provides
structural review hints; warnings neither invalidate schema nor establish
scientific quality. Independent studies may legitimately have no lineage edges.

## Per-version change annotations

Every version, attempt or candidate shown in a research map needs a readable
change explanation, including the initial baseline and failed or unexecuted
versions. This is a host-agent authoring requirement, not a claim that the scanner,
backend importer or schema validator infers or enforces scientific completeness.

Record the following on each version:

- **Compared with:** the recorded parent or explicitly chosen comparator and its
  stable ID. For an initial baseline, describe the starting condition. A previous
  prepared snapshot may differ from the previous executed version; say which is
  being compared. Unknown ancestry stays unknown.
- **What changed:** concrete code, method, configuration or data changes, with
  before/after values and units where applicable. Include changes to evaluators,
  acceptance thresholds, budgets or other controlled conditions. If only code
  changed, do not report an unchanged configuration as an unchanged version.
- **Why:** the failure, question or hypothesis motivating the change. Attribute
  manual edits and automatic proposals separately. A proposal's rationale is an
  intention, not evidence that the change worked.
- **What happened:** whether the version was only prepared, executed, interrupted
  or failed, and the observed endpoint and remaining limitations. Do not substitute
  a search score or intermediate milestone for task success. If several factors
  changed together, identify them without assigning a single-factor effect.
- **Evidence:** immutable references to the effective configurations, code snapshots
  or diffs, proposal/parent records and actual evaluation results. Missing historical
  evidence is an explicit gap, not permission to invent a change or rerun work.

Use the existing node `description` for the readable explanation and the study's
bilingual `attrs.study_summary` for a compact version/change/motivation/outcome
table. Optional `attrs.version_change` may retain structured before/after data,
comparator IDs and proposal attribution, but metadata hidden in that object does
not replace the visible explanation. Use direct node evidence references; a diff
link or adjacent version number alone does not establish provenance.

Retain supported relationships as typed edges: `derived_from` for recorded
derivation and `compares` for a comparison. Neither implies inherited success.
Keep duplicate backend records identifiable without counting them as new versions
or physical executions when their evidence identifies a shared candidate/run.

After `sync`, `research collect` or another import, check that existing explanations
and references survived. A backend projection may replace node fields; reconcile
and reapply the semantic annotations using stable IDs before the final export.
Review the map's version details and study table, not just a separate changelog.

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

Visible `module` and study-section headings state what is being compared or
what the section does. Use short declarative titles. Keep source directories,
phase numbers, manuscript table numbers, and internal condition codes in
evidence locators or details. If a `question` node merely restates its sole
parent module, archive it, move its children and direct evidence to the module,
and retain its ID in history. A genuine subtopic may remain a `question` node
with `attrs.presentation_kind: "section"` and a declarative heading. A genuinely
unresolved question may keep its interrogative form outside the study outline.

For a study with checked numerical results, attach a bilingual
`attrs.study_summary` to the module or section the reader clicks. The map shows
one inline detail immediately below the selected heading; collapsing the branch
also closes that detail:

```json
{
  "study_summary": {
    "zh": {
      "intro": "比较条件与评测方式的简短说明",
      "metrics": [{"label": "独立训练 seed", "value": "3"}],
      "columns": ["条件", "成功率", "协议"],
      "rows": [["合成基线", "50.0%", "合成评测"]],
      "note": "合成示例；指出统计单位、共变因素与不能合并的 cohort。"
    },
    "en": {
      "intro": "Short account of the comparison and evaluation",
      "metrics": [{"label": "Independent training seeds", "value": "3"}],
      "columns": ["Condition", "Success rate", "Protocol"],
      "rows": [["Synthetic control", "50.0%", "Synthetic evaluation"]],
      "note": "Synthetic example; state the sample unit and cohort boundaries."
    }
  }
}
```

Every factual row needs direct evidence on the same node or an explicitly
linked child with an immutable source reference. Calculate displayed means
from verified run identities where possible; identify a paper-only or
source-reported aggregate as such. Do not combine epochs, readouts, protocols,
models or cohorts to fill a convenient table. A study with no checked result
should explain the design and missing evidence instead of inventing rows.
Do not leave a visible section that only repeats the parent, names a source
batch, or makes the reader open every Cell to see a result. Give a meaningful
section its own inline table and cohort note, or move the question to a clearly
marked evidence-gap branch when the underlying result is unavailable.

Project research history is different from LabWeft's revision history. A
source-dated milestone may be stored as an `artifact` with
`attrs.project_event` and direct evidence; it appears only on the research
timeline. Use a calendar date quoted in the source body, never filesystem mtime
or a number in a path:

```json
{
  "project_event": {
    "date": "2026-01-20",
    "date_precision": "as_of",
    "date_label": {"zh": "2026 年 1 月 20 日", "en": "20 Jan 2026"},
    "date_basis": {
      "zh": "这一天是报告截至日期，不是全部训练的结束日期。",
      "en": "This is the report's as-of date, not the end date of every run."
    },
    "related_ids": ["module-synthetic-study"]
  }
}
```

`date_precision` is `day` for an explicit occurrence or completion,
`range_start` for a sourced start of a range, or `as_of` for a dated status,
report or archive. State the action and date meaning in both languages. A
dated summary does not prove that all its underlying runs finished that day.
The UI keeps a separate "Record revisions" tab for tool writes.

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

For a featured claim, optional `attrs.finding_card` makes the card readable
without opening raw records. Supply **both** `zh` and `en`, each with exactly
`value`, `label`, `context`, and `limit`. The value includes its unit; the label
names the measurement; context names the cohort, protocol and comparison;
limit states the most decision-changing boundary. The map reuses the value
and limit in the selected claim detail. Every number and limit must be checked
against the claim's direct immutable evidence, `attrs.finding`, and scope.
This is display copy, not a second result ledger. The validator requires a
sourced Claim and nonempty bilingual fields, but scientific agreement still
needs human/agent review. Keep counterexamples visible; do not infer a headline
from a folder or regex over prose.

```json
{
  "finding_card": {
    "zh": {"value": "+1.2 pp", "label": "成功率差值", "context": "合成例子：同协议、三个独立训练 seed 的对照", "limit": "只覆盖这里的合成条件。"},
    "en": {"value": "+1.2 pp", "label": "Success-rate difference", "context": "Synthetic example: matched protocol and three independent training seeds", "limit": "Applies only to this synthetic condition."}
  }
}
```

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
