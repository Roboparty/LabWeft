# LabWeft development handoff

[简体中文](HANDOFF.zh-CN.md)

## Confirmed product choices

Local-first. Existing coding agent is the controller. One user conversation,
not several user-operated agents. Model/provider-agnostic tool protocol. Stable
research-project identity separate from repo/branch/path. Small core with a Skill
entry, persistent evidence and a clickable map. User records stay separate from
tool source. No default training, code rewrite, public upload or dataset migration.

Store facts, interpretations, human decisions and scope separately. Historical
verification (such as bounded hardware checks) constrains new suggestions. New
seed is replication; equivalent-looking config is not proof of duplication.
Preserve unknowns, human corrections and old snapshots. A scientific finding may
be negative; a full factorial experiment table is not a mandatory goal.

Every research version must visibly state what changed, why, relative to which
parent/comparator, and what actually happened. Include before/after values,
proposal attribution and source evidence; preserve failed and prepared-only
versions. Keep these explanations in version details and study tables after
imports and exports. See the [per-version annotation contract](../research_harness/skill/research-harness/references/PROTOCOL.md#per-version-change-annotations).

## Implemented modules

- `research_tree_demo.py`, `fixtures/research_tree.json`: fast portable replay via
  `demo --scenario research-tree`. Includes saved synthetic CPU measurements,
  candidate sources and evidence snapshots, with no new execution or model calls.
  The Chinese generation/design handoff is `docs/RESEARCH_TREE_DEMO.zh-CN.md`.

- `autoresearch.py`, `research_worker.py`, `backends/shinka.py`: optional pinned
  Shinka backend, frozen task contracts, durable bounded batches, drained stop and
  resume, native report import. See `docs/AUTORESEARCH.md` before extending or
  executing. Model-backed execution and Luna integration still require deployment
  validation; offline fixtures do not establish search effectiveness.

- `store.py`: project identity, immutable text blobs, event replay, local lock,
  revision conflicts, schema/reference checks, human-protection convention.
- `scan.py`: conservative inventory and static Python symbols; JSON/TOML/CSV
  ingestion; no source execution or historical commit fabrication.
- `reasoning.py`: descriptive seed comparisons, source drift, bounded scope check.
- `server.py`: read-only loopback service with token and safe offline export.
- `cli.py`, `rh.py`, `bootstrap.py`: simple entry points and Skill installation.
- `static/`: expandable map with inline study tables, relationship view, grouped
  model-family comparison, decisions, evidence, bilingual interface, sourced
  research timeline and separate record revisions.
- `skill/`: one-controller procedure and semantic patch contract.
- `tests/`: deterministic regression tests; `demo.py`: synthetic showcase.

## What should be next

First run a real repository through ordinary Codex, Codex + EvoSkills, and this
Skill on the same model, permissions and source material. Evaluate initial
reconstruction, then a fresh session with changed results. Do not claim one
approach wins until measured. Investigate false duplicate proposals AND false
exemptions of necessary experiments.

Before broadening scope, fix problems surfaced by these cases: user-confirmed
hardware result with missing original files; renamed experiment; independent
new seed; changed effective batch/precision/protocol; stale result folder; shared
baseline; custom YAML configs; multi-repository research identity; repeated scans
and retained human corrections. Add lightweight future-run capture to reduce
historical gaps, without requiring retroactive training reruns.

Then improve import adapters (starting with common actual user layouts), durable
job checkpoints for interrupted long scans, record migrations, source reconciliation,
component-level UI editing and accessibility improvements for the multilingual
UI. Multi-project offline export and project switching are now available;
continue cross-agent compatibility tests before optional remote adapters.

The 2026-10-03 main refresh retains the optional Shinka backend, saved research
tree replay, and contributor fixes for organization review and run-level lineage.
It adds original branding and paired English/Chinese READMEs. Source publication
has explicit owner authorization; verify repository visibility separately.

Do not start by implementing another chat product, GPU scheduler, model gateway,
plugin marketplace, ten messaging platforms, vector database or public hosting.

## Release gate

Name/namespace and ownership confirmed. License and any future copied code audited.
README demo runs from a clean clone. Recorded OS/browser/agent compatibility matrix.
Real-project regression fixture with permission to publish, or a faithful synthetic
substitute. No private project snapshots, credentials, or hidden paths in release.
Source/decision changes demonstrably traceable. Published benchmark protocol and
limitations. Verify the confirmed GitHub repository before any integration; publish only after explicit authorization.
