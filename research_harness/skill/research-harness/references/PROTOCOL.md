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
