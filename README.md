<p align="center">
  <img src="docs/assets/labweft-banner.en.png" alt="LabWeft — Weave experiments into understanding" width="100%">
</p>

<p align="center"><strong>English</strong> · <a href="README.zh-CN.md">简体中文</a></p>
<p align="center">Python 3.11+ · MIT · Local first · Alpha 0.1.0</p>

LabWeft turns experiments, results, and research decisions into an evidence-linked workspace. Your existing coding agent reads and interprets the project; a small local harness preserves the records and makes them explorable.

**Understand what changed, why it changed, and what the evidence actually supports.**

<p align="center"><a href="#quick-start">Quick start</a> · <a href="#connect-your-project">Connect your project</a> · <a href="docs/AUTORESEARCH.md">Automatic research</a> · <a href="docs/ARCHITECTURE.md">Architecture</a> · <a href="CONTRIBUTING.md">Contribute</a></p>

## See a research tree

![Interactive research tree with candidate lineage and evidence](docs/assets/research-tree.gif)

The bundled teaching example contains **37 preset candidates, 49 saved CPU evaluations, and six research directions**. Explore the lineage, inspect failed attempts, and trace results to their inputs. Opening this example replays saved synthetic results: it makes **zero new model calls or experiment evaluations**. [Example guide](docs/RESEARCH_TREE_DEMO.md).

## A workspace for the whole research story

| View | What you can explore |
|---|---|
| Research map | A semantic outline and an interactive research tree, with expandable branches and focused details. |
| Experiment lineage | Recorded parent versions, secondary references, and run-level derivations, with explanations of changes and outcomes. |
| Evidence | Source-linked text snapshots and hashes, including failures and missing or changed evidence. |
| Condition comparison | Experimental conditions (Cells) and runs, with scope checks and recorded seed-level statistics. |
| Findings and decisions | Evidence-supported conclusions, their limits, and the research choices they informed. |
| Timeline | Source-dated research events and workspace update history, with module filters. |

The interface opens in **Chinese** and switches to **English**. Multiple independent projects can share a local site with a project selector. Research text uses recorded translations when available and otherwise retains its original language.

## Quick start

From a source checkout, all you need for the examples is Python 3.11+:

```sh
git clone https://github.com/Roboparty/LabWeft.git
cd LabWeft
python labweft.py demo --scenario research-tree ./tree-preview --open --port 0
```

This generates a synthetic workspace and opens its read-only local preview. `--port 0` chooses an available port. Stop the preview with Ctrl+C; the workspace remains on disk. There is no model account, GPU, Node.js, or frontend installation requirement.

For a smaller condition-comparison example:

```sh
python labweft.py demo ./research-demo
python labweft.py serve ./research-demo --open
```

You can also install the local checkout with `python -m pip install .` and use the `labweft` command. LabWeft has not been published to PyPI.

## Connect your project

Keep tool source, project source, and private workspace records in separate directories:

```sh
python bootstrap.py --project /path/to/project --results /path/to/results --workspace /path/to/workspace --agent codex
```

Bootstrap installs one controller Skill and performs an initial factual scan. Source files stay in place; LabWeft stores its records under the workspace's `.research` directory. `--agent claude` and `--agent generic` provide other installation layouts.

Then ask your coding agent to read the project and use the Skill, for example:

> Read the source reports, code, experimental conditions, results, and researcher corrections. Organize the map by research purpose. Explain each version's change, motivation, comparator, and measured outcome. Link conclusions to evidence and preserve their scope. When new experiments arrive, update the existing map and comparisons.

The scanner collects facts; **the host agent supplies research interpretation**. LabWeft does not infer a scientific map from directory names alone. The [bundled Skill protocol](research_harness/skill/research-harness/references/PROTOCOL.md) specifies how to record that interpretation. Fresh-chat automatic Skill discovery and every client/platform combination have not yet been certified.

## Keep it local, share deliberately

```sh
python labweft.py export /path/to/workspace --output /private/map.html
python labweft.py export-site --output-dir /private/site /workspaces/project-a /workspaces/project-b
```

Offline exports bundle the interface. Add `--include-evidence` to include bounded text snapshots, subject to a 5 MiB limit per project. Review exports before sharing: they can contain private research. Large artifacts and original source files remain at their source locations; a workspace index is not a backup.

## Optional automatic research

The optional [Shinka backend](docs/AUTORESEARCH.md) adds durable search batches, stop/resume handling, and imported candidate evidence and lineage:

```sh
python -m pip install ".[shinka]"
python labweft.py research --help
```

Follow the backend guide before executing a campaign. Live searches require separately authorized model access, compute, and an appropriate execution environment. Their measured scores remain evidence for the specified task; they do not automatically establish a scientific conclusion. Core scanning, viewing, and demos do not require Shinka.

## Read more

| Guide | Contents |
|---|---|
| [Architecture](docs/ARCHITECTURE.md) | Storage model, evidence, semantic patches, and the controller workflow. |
| [Research tree example](docs/RESEARCH_TREE_DEMO.md) | Saved evaluations, replay behavior, and canvas navigation. |
| [Automatic research](docs/AUTORESEARCH.md) | Optional execution lifecycle and its boundaries. |
| [Known limits](docs/LIMITATIONS.md) · [Release gates](docs/RELEASE_GATES.md) | What has been checked and what remains open. |
| [Security](SECURITY.md) · [Contributing](CONTRIBUTING.md) | Privacy boundaries and contribution workflow. |
| [Handoff](docs/HANDOFF.md) · [Changelog](CHANGELOG.md) | Project continuity and recent changes. |

## Development

```sh
python -m unittest discover -s tests -v
node --test tests/test_relations.cjs tests/test_research_tree.cjs
```

Node.js is used for frontend development checks, not by end users. The Python core has no mandatory runtime dependencies. Validation checks record consistency; scientific interpretation still needs evidence review and independent evaluation. The local server is read-only and binds to loopback.

LabWeft is an **alpha open-source project** under the [MIT license](LICENSE). Focused bug reports, clearer evidence contracts, and reproducible examples are welcome. See [acknowledgements](ACKNOWLEDGEMENTS.md) for upstream influences and dependencies.
