# Changelog

## Unreleased — LabWeft P0 local handoff

The second bounded private-project pilot exercised folder-by-folder source
addition, corrected evaluation provenance and later ablation branches. It found
three current-view errors: an exact file-count scan limit could mark unseen
files missing; changed or missing run evidence could remain in a current
aggregate; and an older metric file could silently replace a deleted primary
result. The scanner, CLI comparison and offline matrix now preserve historical
sources, flag ambiguity and withhold affected runs. Synthetic regression tests
cover the fixes and incremental folder addition. Private project data is excluded.
CLI comparison now auto-selects a sole recorded metric when `success_rate` is
absent, and requests an explicit key when several alternatives exist.
The Skill installer records managed-file hashes and safely upgrades unchanged
installations; a previous bundled Skill was migrated in an isolated test.
An independent staged blind review found a population-versus-sample SD mismatch
between two source reports. The Skill now directs agents to normalize custom
structured results into evidence-bound runs and verify SD conventions. Added a
source-distribution manifest that includes docs and source examples but excludes
generated example workspace state. Wheel and sdist installations pass local
CLI, export and Skill-installation smoke checks in separate Windows environments.
A second blind staged run successfully mapped custom summary JSON and CSV to
comparable Cell/Run records. The bundled patch protocol now includes a minimal
mapping example and specifies the attributes required for sample-SD comparison.
A separate synthetic documentation check followed that example without reading
implementation code, then prompted clarification of metric units and retries.

Imported the Research Harness 0.1.0 source as the LabWeft starting point.
Branded the UI, docs and new `labweft` launcher while keeping `rh`, the
`research_harness` package and the `research-harness` Skill ID compatible.
Corrected the accepted-claim evidence protocol and made the export test use
explicit UTF-8 on Windows. The synthetic fixture keeps its evidence snapshots
so a fresh checkout can validate and export it.

## 0.1.0 — local prototype

One-controller Skill and dependency-free local Python core. Stable project IDs,
text evidence snapshots, conservative config/metrics ingestion, transactional
semantic patches, human-protection convention, bounded historical scope checks,
seed-level comparison, expandable local research map and offline export.

Synthetic policy study with four cells and twelve hand-authored runs. Forty-four
unit tests and recorded browser smoke tests. Installer templates for Codex,
Claude and generic clients; real model/client compatibility still needs testing.

The 0.1.0 entry describes the original prototype. Later pilots used bounded
private sources outside this source repository. No package has been released to PyPI.
