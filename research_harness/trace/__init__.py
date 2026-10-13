"""REA-style investigation toolkit: reverse-engineer a research project into evidence-backed facts.

`probe` runs next to the data (stdlib only, Python 3.8+) and emits facts; `index` ingests them
into a disposable local SQLite cache; `analyze` answers the agent's questions with three-valued,
coverage-aware results. Semantics are still written by the agent through the normal patch path.
"""
