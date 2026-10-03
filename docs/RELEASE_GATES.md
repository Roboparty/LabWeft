# Release and reliability gates

[简体中文](RELEASE_GATES.zh-CN.md)

LabWeft is a local alpha. A successful `validate` means its stored structure and
referenced text snapshots are internally consistent; it does not establish that
an agent's scientific interpretation is correct. We will not label a build
release-ready or claim mature-platform reliability from unit tests or a private
pilot alone.

| Gate | Evidence required | Current status |
|---|---|---|
| Provenance and incremental updates | A public, synthetic multi-stage corpus tests new folders, removed or changed metrics, old protocol fallback, repeated scans, independent seeds and protected corrections. No stale result enters a current comparison without a warning. Record the inventory, collection, semantic-mapping and verification denominators separately. | Core regression cases and a selected private-source pilot pass locally. The pilot is a coverage sample, not complete interpretation; a reusable public agent-evaluation corpus and blinded scoring remain open. |
| Research interpretation | Independent agents reconstruct purpose, conditions, protocol and completion scope from raw evidence. A documented rubric counts false claims, missed evidence and unnecessary experiment suggestions. | Bounded private pilots and internal independent checks exist. Historical and corrected views, and completed work versus later extensions, require separate identities; no general benchmark has passed. |
| Bilingual UI and event history | In local and offline pages, verify default Chinese, English switching, optional node translations with fallback to the recorded node text, omission labels, file/node/edge timeline changes, module filtering, and accessible navigation. | Bounded offline browser checks pass, including a 27/27 history round and a newer 48/48 UI/keyboard round with zero browser errors. Installed-package UI and exhaustive historical reassignment remain unverified. |
| Packaging | Build wheel and sdist, install each into clean Python 3.11+ environments, exercise CLI, bundled Skill and offline UI. | Wheel and sdist built and installed in separate clean Windows Python 3.14 environments; CLI demo, validation, comparison, export and Skill installation passed for an earlier build. Rebuild and recheck after the latest UI changes; other Python/OS combinations remain open. |
| Client and platform support | Run the full workflow in fresh client chats and supported OS/Python combinations; record versions, permissions and failures. | Current Codex desktop chat and Windows local checks; fresh-chat Skill discovery, other clients and supported Linux/macOS runs remain open. |
| Privacy and security | Review source exclusions, exports and endpoint defenses; document a private vulnerability-reporting channel and conduct a release scan for credentials and private research text. | Boundary tests exist; no private reporting channel is published. |
| Stewardship | Confirm maintainer/rights, third-party notices, support expectations and repository visibility before public release. | MIT source license and contribution notes exist. The repository owner explicitly authorized source publication on 2026-10-03. Public visibility must be verified separately; private research workspaces are excluded. This authorization does not close the reliability gates above. |

The precise local test history is in [VALIDATION.md](VALIDATION.md); known
technical limits are in [LIMITATIONS.md](LIMITATIONS.md). Private pilot data and
maps must stay outside the source repository.
