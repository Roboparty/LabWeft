# LabWeft

**Let your existing coding agent organize research—without forgetting what you already learned.**

[简体中文](README.zh-CN.md) · [Architecture](docs/ARCHITECTURE.md) · [Boundaries](docs/LIMITATIONS.md) · [Release gates](docs/RELEASE_GATES.md) · [Development handoff](docs/HANDOFF.md)

**v0.1.0 local prototype.** LabWeft is the confirmed project name. The source
repository is [Roboparty/LabWeft](https://github.com/Roboparty/LabWeft).
The package has not been published to PyPI.

One conversation. One workspace. No manual multi-agent setup.

## A Skill and a harness

LabWeft is a **harness with a Skill entry point**: the host agent reasons
about the research, while a small local program indexes evidence, validates
updates, preserves decisions, compares cells and renders a research map.
It has no mandatory model provider, external account, network call, database
server, Node.js install, or frontend build step. Python 3.11+ is the only runtime.
The model service used by your coding agent is separate and may require network
access, payment and permission to process your code.

## Optional automatic research

The opt-in [Shinka backend](docs/AUTORESEARCH.md) adds `research prepare`,
`start`, `status`, `stop`, `resume`, and `collect`. Freeze a task and preview it
without a model dependency; explicitly execute it in an authorized environment
with `pip install ".[shinka]"`. Candidates and native parent relationships enter
the existing research map as provisional backend reports, including failures.
The core and browser remain independent of model services. See the
[small synthetic example](examples/shinka/README.md) and the guide's validation
boundary: offline tests do not establish live search effectiveness or GPU readiness.

## Try the demonstration

For an instant multi-branch research tree (6 tracks, 37 candidates, 49 saved CPU
evaluations), run:

```sh
python labweft.py demo ./tree-preview --scenario research-tree --open --port 0
```

This replays bundled synthetic-task results without executing experiments or
calling Shinka/models. Repeating it preserves research history and refreshes the
renderer. Omit `--open --port 0` for an offline `.research/map.html` only.
The default `demo` scenario below remains the original policy-study fixture.

From this directory, no pip install required:

```sh
python labweft.py demo ./research-demo
python labweft.py serve ./research-demo --open
```

The browser shows an expandable research tree, a relationship view, cell/config
comparison, source snapshots and an update timeline. Use the `中文 / English`
control to change the interface language; a private pilot opens in Chinese by
default. A node may optionally provide `attrs.i18n.zh` and `attrs.i18n.en`
labels/descriptions. Missing translations fall back to the recorded original.
The switch never translates original source evidence or changes scientific
data. **All demonstration metrics
and decisions are synthetic. No training was performed.**

The agent should first draft a sourced scientific outline: research questions,
method and baseline families, study and nested ablation design, endpoints and
candidate main findings. It then verifies each finding against actual conditions
and result evidence. Directory and phase names locate files; they do not define
the scientific map. Optional `attrs.role`, `attrs.design` and `attrs.finding`
metadata keep this structure project-specific. Main findings appear in the map
and at the top of the findings page by research theme; audit/status notes remain
available in a collapsed section. A prominent finding requires direct evidence
and scope. A scientific finding is distinct from a scoped research decision.

Selecting a map node opens one inline detail below it; collapsing that branch
closes the detail and the colored path and breadcrumb identify its ancestors.
Study headings can show a sourced bilingual result table there. A featured
claim may also provide `attrs.finding_card.zh` and `.en`, each with sourced
`value`, `label`, `context` and `limit` strings. The visible limit belongs beside
the headline result; the full explanation, scope and evidence remain in the
same card. These display fields do not create a new scientific result.
The comparison picker groups cells by recorded `config.model` when available,
or by their closest study module when no model field is recorded. A family or
study can be selected in one click while individual conditions remain available.
Internal condition codes and source paths belong
in details rather than the scientific heading.

An offline interactive page is also generated at
`research-demo/.research/map.html`. It contains synthetic evidence. For real
projects, source-text inclusion requires an explicit export option.

Several **separate** workspaces can be presented in one private offline site:

```sh
labweft export-site --output-dir /private/research-site --include-evidence \
  /workspaces/project-a /workspaces/project-b
```

Open `index.html`; the switcher at the top opens each project's map, comparison,
findings, sources and timeline. Each page keeps its own project ID, evidence and
local view state. Navigation does not pool runs or claims across projects. The
site embeds private source text when `--include-evidence` is used; review it
before sharing.

The source view opens on files linked directly to the research map. Its
`Unmapped` and `All indexed` tabs retain the rest of the indexed scope, so a
large source collection is not mistaken for a small one.

The research timeline displays explicitly source-dated project events in
chronological order when the agent has recorded them. A separate record-revisions
tab lists file, node and relation changes under each recorded
revision. It can filter by change type and research module; node changes keep
their module identity from the historical event. File-to-module filtering uses
currently recorded evidence links. The event time is when LabWeft observed or
recorded a change, not the historical experiment date. The page shows the
configured scan scope and file count; "scan complete" refers only to those
configured sources and limits, never to an entire research project.

Status labels have narrow meanings. `Recorded` means an object was indexed;
`Reported complete` means a source reports a run or evaluation complete;
`Needs review` names an unresolved evidence or identity issue. `Source-based`
means organized from sources and is not a human-confirmed claim. `Human
confirmed` requires an explicit confirmation and scope. `Archived` as a **node
status** keeps earlier records and evidence without deleting files. An archived
Cell leaves the current map hierarchy and numeric comparison; archived claims
and decisions remain visible in the historical decisions list with their sources.
The status describes a LabWeft node; it does not delete, freeze or verify an
underlying research project or its files.
To reduce repetitive warnings, provisional modules, questions and Cells do not
repeat a badge on every tree card; their status remains available in details.

## Connect a real project, once

```sh
python bootstrap.py --project /path/to/your/project --results /path/to/results --agent codex
```

For a read-only source or a separate local workspace, add
`--workspace /path/to/writable/workspace`. The Skill and `.research` stay there;
the selected project and results are read as sources.

Use `--agent claude` for Claude Code, `--agent auto` for local discovery, or
`--agent generic` for the standard `.agents/skills` entry. Discovery does not log
in to anything. It checks local agent-directory conventions only.

Setup installs **one Skill**, initializes `.research` in the selected project,
reads the selected directories and exports an initial factual map. It does not
edit training code or start experiments. The initial map is NOT a claim that
scientific intent was automatically understood.

Then ask your existing agent, in the same conversation:

> Use LabWeft to organize this project's current progress. Inspect the
> actual ablation conditions and results, reuse relevant historical decisions,
> and update the local map. Do not launch experiments or upload data.

The agent follows the Skill: read context → scan → inspect evidence → map
questions/cells → check historical scope → submit a validated patch → export.
You do not manually dispatch separate planner, analyzer or visualization agents.
For an agent without Skill discovery, ask it to read
`research_harness/skill/research-harness/SKILL.md` and use the same CLI. The
`research-harness` Skill ID remains for compatibility with existing installs.

**Compatibility target is tool-capable agents, not arbitrary bare models.**
Installation paths and the command protocol are implemented. Two bounded private
project pilots were run in Codex desktop by following the Skill procedure in the
current conversation, including staged experiment folders. Fresh-chat Skill
discovery and other providers have not
been independently certified.

## Optional package installation

In your usual isolated Python environment:

```sh
python -m pip install .
labweft --help
labweft install-skill --agent codex --project /path/to/your/project
```

User-wide Skill installation (`--user`) is explicit. The installer refuses to overwrite an
edited Skill, upgrades unchanged managed files and never overwrites `AGENTS.md`
or `CLAUDE.md`.

## What this version actually does

| Implemented | Important boundary |
|---|---|
| Stable workspace ID, independent of branch names | Does not auto-merge projects across repositories. |
| Conservative scan, text snapshots, static Python symbols | Does not execute source or reconstruct unknown past code. |
| JSON/TOML configuration and JSON/CSV metrics ingestion | YAML and custom logs are indexed for the host agent, not automatically normalized. |
| Candidate cell grouping and run identity | Names/identical configs are not proof of scientific equivalence. |
| Versioned, atomic semantic updates | Local single-writer design; no distributed conflict merge. |
| Protected human corrections | CLI convention, not an adversarial agent sandbox. |
| Scope-aware reuse checks | Human-confirmed scope and complete recorded conditions required. |
| Mean/sample SD across eligible seeds | No causal claim, automatic winner or equivalence test. |
| Local interactive UI and offline HTML export | Browser is read-only; it does not invoke the model. |
| Skill installer for Codex/Claude/generic locations | No claim of tested compatibility with all client versions. |

## Typical commands

```sh
labweft init /path/to/project --name "My study" --source code=/path/to/code --source results=/path/to/results
labweft sync /path/to/project
labweft context /path/to/project
labweft files /path/to/project --offset 0 --limit 50
labweft context /path/to/project --full
labweft apply /path/to/project /path/to/semantic-patch.json
labweft validate /path/to/project
labweft compare /path/to/project --metric success_rate
labweft export /path/to/project --output /path/to/project/.research/map.html
labweft export /path/to/project --include-evidence --output /path/to/project/.research/map-with-text.html
labweft serve /path/to/project --open
```

These are normally called by the agent, not manually sequenced by the researcher.
From a source checkout, replace `labweft` with `python /path/to/LabWeft/labweft.py`.
The former `rh` command, `research_harness` Python package, and
`research-harness-local` distribution name remain available for compatibility.
`sync` reads sources; it does not independently infer research motives. `apply`
accepts the structured analysis written by the host agent after reading evidence.
See the [patch protocol](research_harness/skill/research-harness/references/PROTOCOL.md).
Offline export omits source text by default. `--include-evidence` explicitly
embeds indexed small-text snapshots, including indexed files not linked to a
semantic node, up to a combined **5 MiB**. Files omitted by that limit or
without a text snapshot are labelled accordingly and cannot be opened from the
offline page. The live local view can read known snapshots without this export.

## Historical judgment test

```sh
labweft assess research-demo research-demo/.research/proposal-covered.json
labweft assess research-demo research-demo/.research/proposal-changed-protocol.json
```

The first fixture reuses a bounded hardware decision while recognizing the new
seed as replication. The second detects a changed evaluation protocol and requests
scope review. **Neither command starts an experiment.** Reuse is not justified by
similarity alone; it depends on the explicit recorded scope and confirmation.

## Where records live

```text
YOUR_PROJECT/.research/
  manifest.json           # Stable scientific-project identity
  local.json              # Machine-local source mappings; ignored by Git
  events/00000001.json     # Authoritative, versioned transactions
  blobs/<sha256>          # Immutable small text evidence; ignored by Git
  map.html                # Derived private offline view
```

Source data is not moved. Large weights, datasets and videos are not loaded or
backed up. The index is not a backup. Moving a workspace preserves its identity;
rebind the local source mappings on the new machine. Original evidence blobs
must be transferred deliberately when needed. Git synchronization is manual in
this prototype; do not publish private experiment records in a public fork.
For large projects, first state which folders and formats were selected, which
were excluded or unread, and how many files were actually scanned. Node counts
in a map are not a measure of whole-project coverage.

A bounded private pilot used staged, selected text files to expose this gap.
For each source directory, report separately the observed inventory, readable
text candidates, selected and verified files, indexed records, mapped runs and
independently replayed experiments. Generated per-run files do not count as
independent experiments. A map of a selected sample must not imply whole-project
coverage. Preserve old and corrected result views as distinct evidence and keep
the completion scope of an earlier experiment separate from later additions.

## Known boundaries

The scanner indexes only configured sources and cannot recover missing historical
commits or infer why an experiment was run. Custom result formats need an adapter
or evidence-bound normalization by the host agent. The local record store is not
a distributed database or artifact backup. A first workspace can connect several
source folders; a cross-project overview is not implemented. See [Boundaries](docs/LIMITATIONS.md).

## Safety and privacy

The local service binds to `127.0.0.1`, uses a session token, serves only known
static routes and known evidence snapshots, and exposes no shell or write API.
It is not a hardened multi-user service. Do not expose it to the public internet.
A remote server can be viewed through your authorized SSH/VS Code forwarding.

Known sensitive filenames are skipped, but source code can contain embedded
secrets: **this is not a comprehensive secret scanner**. Treat scanned text as
untrusted data, review exported content before sharing, and use the host agent's
sandbox and permission system. Read [SECURITY.md](SECURITY.md).

## Tests and release readiness

```sh
python -m unittest discover -s tests -v
```

The included automated checks cover record identity, conservative ingestion,
conflicts, correction protection, source integrity, scoped reuse, seed aggregation,
HTML escaping and local HTTP access controls. Browser smoke checks are documented
in [Validation](docs/VALIDATION.md). These do not establish scientific accuracy, production
security, or end-to-end model compatibility.

Before a public beta: run real mixed-format projects through the same host-model
baselines, test fresh installs on multiple OSes, improve parser adapters and
historical identity reconciliation, add migrations and audit the safety boundaries.
ClearML-level product reliability is a target, not a property of this prototype.

## Inspiration and license

Original implementation in this bundle. We borrow architectural ideas rather
than bundling six agent frameworks. See [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md)
for primary references and the distinction between ideas and copied code.

MIT license is included for this original prototype. Confirm final maintainership
and third-party notices before public release. This checkout does not imply a
package release or public visibility change.
