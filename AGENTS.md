# Working on this tool

This is the LabWeft tool source repository, not a user's research-data repository.
`labweft.py` / `labweft` are the new entry points; `rh.py` / `rh`,
`research_harness`, and the `research-harness` Skill ID remain compatible.
Read README.md, docs/ARCHITECTURE.md, docs/LIMITATIONS.md and docs/HANDOFF.md.
Keep changes local and narrow. Do not publish a repository or copy real private
research data into examples without explicit authorization.

Run `python -m unittest discover -s tests -v`. Core has no runtime dependencies.
Example: `python rh.py demo ./research-demo`. UI assets are bundled and must not
require npm or a CDN for end users. Test export escaping and evidence display.

Maintain one-controller Skill workflow. No extra user-operated agent sessions.
The scanner records facts; the host agent interprets research. Never fabricate
historic inputs, run provenance, scientific findings, test coverage or model
compatibility. Preserve human corrections and typed scope. Use immutable evidence
snapshots and optimistic version checks; do not turn a scan into source execution.

No training, checkpoint deletion, GitHub writes or external model calls are
required to develop this prototype. Consult ACKNOWLEDGEMENTS.md before importing
third-party code; preserve licenses and attribution when code is actually reused.
