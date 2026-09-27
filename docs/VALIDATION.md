# Validation record — v0.1.0 prototype

## Current local regression status (2026-09-28)

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

An independent blind agent used only a newly staged 13→22→28-file private source
subset. It kept the corrected canonical results, separate experiment identities,
incomplete follow-ups and an older negative result in their proper scopes. Its
recomputation found that two reports used population and sample SD respectively
for three training seeds. The full pilot's private evidence map now records this
as a provisional caveat. The blind agent did not map custom summary JSON/CSV into
Cell/Run nodes, so its empty comparison was a workflow gap; the Skill now says
to perform evidence-bound normalization for such sources and to verify SD
conventions. This is not a scored public benchmark or a claim of general agent
reliability.

A second staged blind run followed the revised Skill in a fresh private
workspace with 5→12→18 selected source files. It normalized a custom mechanism
JSON into four cells and twelve independent runs, plus one cell and three runs
from a custom CSV. Every cell compared with three training seeds and matched
independently recomputed mean/sample SD. `validate` passed with 30 nodes,
no evidence errors or drift; repeated scans did not overwrite the semantic
mapping. The run also preserved separate incomplete and negative-result scopes.
Its feedback identified a missing minimal Cell/Run patch example, now added to
the bundled protocol. This still lacks a public scored agent benchmark and
does not establish broad host-model reliability.

A third, narrow documentation check followed only the new protocol example in
a fresh synthetic workspace, without consulting implementation code. One Cell
and three completed Runs compared at mean 0.6666667 and sample SD 0.0416333;
`validate` passed and a repeat scan did not overwrite the mapping. The example
now spells out metric units and duplicate-seed handling. This checks clarity of
that example, not the performance of arbitrary agents or custom formats.

The final Windows Python 3.14 suite still runs 58 tests: 57 pass and one symlink
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
client or NAS service reliability. The earlier entries below record the original
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
