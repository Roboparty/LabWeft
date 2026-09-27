# Contributing

Start with the product contract in `docs/HANDOFF.md`. Keep issues and changes
focused on user friction or evidence correctness, not a larger agent count.

Add regression tests for every identity, scope, provenance or aggregation fix.
Input adapters must not execute code or silently invent metadata. UI changes must
work without a CDN or frontend build for end users. Use synthetic or authorized
fixtures only. Distinguish unit validation from end-to-end model evaluation.

For a new adapter, provide its accepted input format, a small example, missing-
field behavior, ambiguity handling and a test. For a new agent integration,
document the client version, discovery path, permission setup and what was
actually tested. Do not label an untested model as supported in production.

Run `python -m unittest discover -s tests -v` before proposing changes. Record any
third-party copied or adapted code and its license at a pinned version. The
source repository is `Roboparty/LabWeft`; check access and visibility before
opening public issues or publishing private research examples.
