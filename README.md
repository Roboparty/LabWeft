# LabWeft

**Let your existing coding agent organize research—without forgetting what you already learned.**

[简体中文](README.zh-CN.md) · [Architecture](docs/ARCHITECTURE.md) · [Boundaries](docs/LIMITATIONS.md) · [Development handoff](docs/HANDOFF.md)

**v0.1.0 local prototype.** LabWeft is the confirmed project name. The intended
repository is [Roboparty/LabWeft](https://github.com/Roboparty/LabWeft); this
source checkout has not been verified against its remote history or published
to PyPI.

One conversation. One workspace. No manual multi-agent setup.

LabWeft is a **harness with a Skill entry point**: the host agent reasons
about the research, while a small local program indexes evidence, validates
updates, preserves decisions, compares cells and renders a research map.
It has no mandatory model provider, external account, network call, database
server, Node.js install, or frontend build step. Python 3.11+ is the only runtime.
The model service used by your coding agent is separate and may require network
access, payment and permission to process your code.

## Try the demonstration

From this directory, no pip install required:

```sh
python labweft.py demo ./research-demo
python labweft.py serve ./research-demo --open
```

The browser shows an expandable research tree, a relationship view, cell/config
comparison, source snapshots and decision history. **All demonstration metrics
and decisions are synthetic. No training was performed.**

An offline interactive page is also generated at
`research-demo/.research/map.html`. It contains synthetic evidence. For real
projects, source-text inclusion requires an explicit export option.

## Connect a real project, once

```sh
python bootstrap.py --project /path/to/your/project --results /path/to/results --agent codex
```

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
Installation paths and the command protocol are implemented; real Codex/Claude/
other-provider sessions have not yet been end-to-end tested.

## Optional package installation

In your usual isolated Python environment:

```sh
python -m pip install .
labweft --help
labweft install-skill --agent codex --project /path/to/your/project
```

User-wide Skill installation (`--user`) is explicit. The installer refuses to overwrite an
edited Skill and never overwrites `AGENTS.md` or `CLAUDE.md`.

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
labweft serve /path/to/project --open
```

These are normally called by the agent, not manually sequenced by the researcher.
From a source checkout, replace `labweft` with `python /path/to/LabWeft/labweft.py`.
The former `rh` command, `research_harness` Python package, and
`research-harness-local` distribution name remain available for compatibility.
`sync` reads sources; it does not independently infer research motives. `apply`
accepts the structured analysis written by the host agent after reading evidence.
See the [patch protocol](research_harness/skill/research-harness/references/PROTOCOL.md).

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
in `docs/VALIDATION.md`. These do not establish scientific accuracy, production
security, or end-to-end model compatibility.

Before a public beta: run real mixed-format projects through the same host-model
baselines, test fresh installs on multiple OSes, improve parser adapters and
historical identity reconciliation, add migrations and audit the safety boundaries.
ClearML-level product reliability is a target, not a property of this prototype.

## Inspiration and license

Original implementation in this bundle. We borrow architectural ideas rather
than bundling six agent frameworks. See [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md)
for primary references and the distinction between ideas and copied code.

MIT license is included for this original prototype. Confirm final maintainership,
project name and third-party notices before publication. This checkout does not
imply a GitHub push, release, or public visibility change.
