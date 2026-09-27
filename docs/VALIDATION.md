# Validation record — v0.1.0 prototype

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
