# Release and reliability gates

LabWeft is a local alpha. A successful `validate` means its stored structure and
referenced text snapshots are internally consistent; it does not establish that
an agent's scientific interpretation is correct. We will not label a build
release-ready or claim mature-platform reliability from unit tests or a private
pilot alone.

| Gate | Evidence required | Current status |
|---|---|---|
| Provenance and incremental updates | A public, synthetic multi-stage corpus tests new folders, removed or changed metrics, old protocol fallback, repeated scans, independent seeds and protected corrections. No stale result enters a current comparison without a warning. | Core regression cases pass locally; reusable public agent-evaluation corpus and blinded scoring remain open. |
| Research interpretation | Independent agents reconstruct purpose, conditions, protocol and completion scope from raw evidence. A documented rubric counts false claims, missed evidence and unnecessary experiment suggestions. | Two bounded private pilots and internal independent checks; not a general benchmark. |
| Packaging | Build wheel and sdist, install each into clean Python 3.11+ environments, exercise CLI, bundled Skill and offline UI. | Wheel and sdist built and installed in separate clean Windows Python 3.14 environments; CLI demo, validation, comparison, export and Skill installation pass. The exported UI was exercised in the private pilot, but installed-package UI interactions and other Python/OS combinations remain open. |
| Client and platform support | Run the full workflow in fresh client chats and supported OS/Python combinations; record versions, permissions and failures. | Current Codex desktop chat and Windows local checks; fresh-chat Skill discovery, other clients and supported Linux/macOS runs remain open. |
| Privacy and security | Review source exclusions, exports and endpoint defenses; document a private vulnerability-reporting channel and conduct a release scan for credentials and private research text. | Boundary tests exist; no private reporting channel is published. |
| Stewardship | Confirm maintainer/rights, third-party notices, support expectations and repository visibility before public release. | MIT source license and contribution notes exist; final ownership and publication decisions remain open. |

The precise local test history is in [VALIDATION.md](VALIDATION.md); known
technical limits are in [LIMITATIONS.md](LIMITATIONS.md). Private pilot data and
maps must stay outside the source repository.
