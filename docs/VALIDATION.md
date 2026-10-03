# Validation record — v0.1.0 prototype

[简体中文](VALIDATION.zh-CN.md)


## Public source verification (2026-10-03)

The current Windows Python 3.14 suite ran **100 tests: 99 passed and one
symlink-capability test skipped**. JavaScript relation and research-tree tests
passed **19/19**. Git whitespace checks passed.

An independent reviewer checked the English/Chinese README and demo-guide links,
actual demo commands, and Edge offline pages at 1440px and 390px. The original
inline mark, Chinese → English → Chinese switching, candidate details, research
tree and Outline views passed, with zero page errors or horizontal overflow.
The review found and closed Chinese banner rendering and Run-focus wording issues.

Wheel and sdist were rebuilt from a clean Git archive and installed separately
in fresh Windows Python 3.14 environments. Both passed the saved research-tree
demo, `validate`, offline export, and project-local Codex Skill installation.
Each demo retained 37 preset candidates and 49 saved CPU evaluations, while
making zero new model calls or experiment evaluations. Independent archive review
verified branding, bundled UI/Skill/fixture hashes, and private-workspace exclusion.
Both installed-package exports also passed independent Edge desktop checks for
the inline mark, 37 candidate nodes, Chinese/English switching, and zero page
errors. These checks do not certify fresh-chat Skill discovery, every platform, or live
Shinka/model execution.

The latest main retains the contributor's organization-review and Run-lineage
fixes. GitHub source visibility was changed to Public with owner authorization;
private vulnerability reporting was enabled. Anonymous repository access returned
HTTP 200. Tool-source publication excludes private research maps and workspaces.
Scientific interpretation and broad reliability gates remain separately evaluated.

## Earlier local check (2026-09-28, bounded pilot)

The current Windows Python 3.14 suite has **64 tests: 63 passed and one
symlink-capability test skipped**. JavaScript syntax (`node --check`) and Git
whitespace checks pass. CLI and browser comparison now warn when the same
recorded training `run_id` appears in more than one selected Cell, as can happen
when checkpoints from one training run are evaluated separately. Per-Cell seed
counts must not be added as independent training replicates across those Cells.
An archived Cell leaves the current hierarchy and numeric comparison; archived
claims and decisions remain available in the historical decisions view with
their sources.

A fourth independent Edge round on an anonymous, bounded private offline
snapshot passed **48/48 browser checks with no console or page errors**. It
covered default empty comparison selection for a larger map, bilingual search
and selection controls, shared training-run warnings, language switching,
history, evidence-dialog keyboard focus and a narrow viewport. It checks those
UI paths, not the underlying scientific results or every accessibility path.

The final source tree was rebuilt as a wheel and source distribution. The
source archive contains no generated workspace state. A clean Windows Python
3.14 environment installed the wheel and ran the synthetic demo (four Cells,
12 Runs), `validate` (revision 3, no evidence errors or drift), and `compare`
successfully. This does not certify other operating systems or package indexes.

Independent review of a private map found a P1 Chinese wording error: some Run
descriptions named the wrong aggregate for a recorded percentage metric. The
affected descriptions were corrected and rechecked. This was a presentation
correction, not a recomputation of the
underlying scientific results. This local suite and review do not establish
whole-project scientific validation or public release readiness.

## Earlier bilingual and coverage iteration (2026-09-28)

An independent Edge agent tested a private offline snapshot in two
browser rounds, with no console
errors or uncaught JavaScript exceptions. The rounds covered first-load Chinese,
English switching and retained language preference, five views, the source list,
unlinked indexed text opened from an explicit evidence export, an isolated copy
with omitted-text labels and disabled buttons, update-history filters, navigation,
and 390px layout. A third independent Edge round on a fixed offline snapshot
after the historical-module change passed 27/27 checks with no console errors.
Its file and node timeline filters passed; this checks the tested history paths,
not every possible historical reassignment.

A read-only metadata inventory of a private project informed a deliberately
selected source-text sample. Selected content was collected and checked file by
file. Inventory, selected text, indexed files, mapped graph nodes and
independently replayed experiments are different denominators. The sample does
not establish whole-project scientific correctness. Old and corrected results,
and completed work versus later additions, retain distinct scopes.

Before the latest historical-module timeline test was added, the Windows Python
3.14 suite contained 61 tests: 60 passed and one symlink-capability test skipped.
That result is an interim checkpoint, not a final result for the latest tree.
Offline export now defaults to omitting source text; `--include-evidence` may
embed indexed text snapshots, including files unlinked to semantic nodes, up to
5 MiB total and marks omitted snapshots. The browser round tested the omitted
state with an isolated copy; it did not prove every selected private source fits
in one offline export.

## Earlier local regression status (2026-09-28)

After a second bounded private-project pilot, Windows Python 3.14 runs 58 tests:
57 pass and one symlink capability test skips. `node --check` passes. A synthetic
incremental fixture exercises a new protocol folder, new result cell and added
training seed while preserving a previously mapped question. Separate regression
cases verify that a file-count boundary cannot mark unseen files missing, that
changed or missing metric evidence leaves current aggregates, and that an older
secondary metric file cannot silently replace a removed primary file. Another
test checks metric selection when the only available key is not `success_rate`.
An internal agent reproduced the three baseline failures and checked the current aggregate
and drift warning in the actual offline browser matrix. The private source files and browser artifacts remain
outside this repository.

An existing official Skill installation from the previous commit was copied into
an isolated directory and upgraded in place. Managed-file hashes now allow an
unchanged installation to upgrade while still refusing edited files.

An independent blind agent used only a newly staged private source subset. It
kept distinct experiment identities and source-reported completion boundaries
separate while retaining older evidence. Its recomputation found an inconsistent
statistical convention across source summaries; the private map recorded a
source-bound caveat.
The blind agent did not map custom summary JSON/CSV into
Cell/Run nodes, so its empty comparison was a workflow gap; the Skill now says
to perform evidence-bound normalization for such sources and to verify SD
conventions. This is not a scored public benchmark or a claim of general agent
reliability.

A second staged blind run followed the revised Skill in a fresh private
workspace. It normalized custom JSON and CSV into evidence-bound Cells and
independent Runs. Their descriptive comparisons matched independent
recomputation. `validate` passed with no evidence errors or drift; repeated
scans did not overwrite the semantic
mapping. The run also preserved separate completion scopes.
Its feedback identified a missing minimal Cell/Run patch example, now added to
the bundled protocol. This still lacks a public scored agent benchmark and
does not establish broad host-model reliability.

A third, narrow documentation check followed only the new protocol example in
a fresh synthetic workspace, without consulting implementation code. One Cell
and three completed Runs compared at mean 0.6666667 and sample SD 0.0416333;
`validate` passed and a repeat scan did not overwrite the mapping. The example
now spells out metric units and duplicate-seed handling. This checks clarity of
that example, not the performance of arbitrary agents or custom formats.

At that earlier checkpoint, Windows Python 3.14 ran 58 tests: 57 passed and one symlink
capability test skips. JavaScript syntax and Git whitespace checks pass. Both a
wheel and an sdist were built; the sdist manifest was corrected to include docs
and source examples while excluding generated example workspace state and its
machine-local source path. Each artifact installed into a separate new virtual
environment. In both, the `labweft` entry point completed synthetic demo,
`validate`, `compare`, offline export and project Skill installation. The demo
produced four cells, twelve runs and a valid revision-3 workspace. Package
installation was tested only on this Windows Python 3.14 host.

These checks cover a selected small-text subset and synthetic failure cases, not
whole-project scientific correctness, historical training replay, every agent
client or network-storage service reliability. The earlier entries below record the original
prototype and first pilot at their respective times.

Prepared 2026-09-28. Tested locally in Linux with Python 3.13.5, Node 22.16.0 for
JavaScript syntax checking, and the system Chromium driven by Playwright.
Node and Playwright are development/test tools, not runtime requirements.

## Completed

`python -m unittest discover -s tests -v`: **44 tests passed**. Raw output:
[unit-tests.txt](validation/unit-tests.txt). These cover identity, no-op scans,
read-only extraction, missing/partial data, secret filename and symlink exclusion,
protected corrections, revision conflicts, event/blob integrity, accepted-claim
references, config/run identity conflicts, seed pooling, scoped reuse, export
escaping, Skill installer safety, HTTP token and Host access controls.

JavaScript syntax: `node --check research_harness/static/app.js` passed.

Browser smoke tests on the actual exported HTML content passed: expandable tree,
search, relationship view, cell selection/difference-only view, numeric summary,
run drill-down, evidence text viewer, decisions/history/sources, and 390px-wide
layout without page-level horizontal overflow. No page JavaScript errors were
reported. Raw details: [browser-smoke.json](validation/browser-smoke.json).
Screenshots in `docs/assets/` use synthetic fixture data only.

Wheel build with `python -m pip wheel . --no-deps --no-build-isolation` passed.
Package contents and isolated CLI/assets were checked separately. No model calls
or real experiments were performed.

## Not completed or not established

The environment's browser policy blocks navigation to `file://` and loopback HTTP
addresses. Therefore browser interactions were exercised with the exported HTML
loaded through Playwright `set_content`, not by claiming a completed browser-to-
live-server session. The HTTP API was tested directly using Python's HTTP client.
End-user local browser behavior still needs cross-machine verification.

The GitHub Actions OS/Python matrix is configured but was not run on GitHub.
Windows/macOS operation, real Codex/Claude Code Skill invocation, other model
providers, arbitrary research repositories, long-history performance, crash/power-
loss behavior, migrations and multi-user threat models are not certified.

Passing tests checks the specified mechanical invariants. It does not prove
scientific interpretations, completeness of evidence discovery, model reliability,
absence of all vulnerabilities, or parity with a mature experiment platform.

## 2026-09-28 Windows P0 recheck

The LabWeft local checkout was tested with Windows Python 3.14. The 44-test
suite completed successfully: 43 passed and the symlink test skipped because
this host does not support creating that link. The first baseline run exposed
one test-only default-GBK decode error; the export test now explicitly reads
UTF-8, matching the exported file. No provenance rule was relaxed.

`python labweft.py demo` produced a synthetic workspace with four cells and
twelve runs. `validate` returned `valid: true`, revision 3, 37 nodes, and no
evidence errors or drift. `compare` returned four cells with no warnings;
offline export completed. `node --check research_harness/static/app.js` and a
wheel build with no runtime dependencies completed. Edge headless loaded the
exported `file://` HTML and produced a screenshot showing the LabWeft brand,
map and detail pane. Browser interactions and a VS Code Codex session were not
automated in this recheck.

## 2026-09-28 Codex desktop internal iteration

A bounded private project subset was processed in the current Codex desktop
conversation by following the Skill's single-controller procedure. The scanner
created a factual index; the agent checked source reports and statistics before
submitting a versioned semantic patch. An independent internal agent tested the
CLI and actual Edge interactions with the offline map. Private research files,
the test report and browser artifacts remain outside this source repository.

The internal test found that a cell could display one configuration while all
its child runs shared a different configuration, yet both CLI and browser views
still pooled their metrics. Both now withhold the aggregate and show a conflict.
It also found that changing only scanner explanatory text could create a new
revision; wording-only changes no longer do so. Redirected Windows CLI output
now uses UTF-8. `bootstrap.py --workspace` was added and exercised on a separate
writable workspace while reading a source directory; it writes the Skill, state
and map to the workspace, not the source.

The updated Windows suite runs **48 tests: 47 passed, one symlink capability
test skipped**. JavaScript syntax checking passes. A wheel build without runtime
dependencies succeeded; its `labweft`/`rh` entry points, bundled Skill and updated
UI asset were inspected. The private pilot validated
repeat sync, source drift with preserved old blobs, numeric aggregation and
browser matrix/evidence navigation. It did not re-run historical experiments,
audit checkpoints or certify whole-project scientific conclusions. Automatic
Skill discovery in a new client chat and other hosts remain untested.

The available WSL interpreter is Python 3.10, below LabWeft's Python 3.11
minimum; it cannot run this version's tests because `tomllib` is absent. This
iteration has not independently re-run the suite on a supported Linux runtime.
