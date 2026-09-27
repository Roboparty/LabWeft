# Architecture v0.1

## Product contract

One existing, tool-capable agent controls a user-authorized workflow. The user
does not manually coordinate several agents. The local core has no model SDK.
A Skill describes the domain procedure; the model uses normal shell/file tools.

The scanner does factual extraction. The host agent inspects source and history,
then writes semantic patches. The core validates these patches and persists
transactions. The frontend is a read-only projection, not the source of truth.

## Identity

A research workspace owns a generated project ID saved in `manifest.json`.
It is not derived from a directory, Git remote spelling, or branch. Sources have
explicit aliases and machine-local paths. Runs prefer recorded `run_id`; otherwise
source alias plus relative run directory is a clearly labeled fallback.

A folder rename with no recorded identity needs reconciliation; identical config
or hash is not enough to merge scientific identity. Changed configuration attached
to an existing cell is flagged and excluded rather than silently reassigned.
New independent seeds are distinct runs. A shared baseline is one set of runs
referenced by multiple research questions.

## Persistence

The authoritative state is the ordered event directory. Each event has revision,
previous hash, timestamp, actor, reason and upserted records. Writes use a local
process lock and an expected base revision. An event is flushed to a temporary
file and atomically renamed into place. Reads replay and validate the event chain.
No LLM regenerates the old state. Same content is a no-op. Failed validation does
not partially update state.

This detects accidental corruption, but is not a cryptographic signature or
append-only filesystem. An OS user can rewrite files and recompute hashes. It is
not a distributed system; competing Git edits require deliberate reconciliation.
Replay is linear in history size. Production work includes snapshots and schema
migration, without making caches authoritative.

## Facts and judgments

`module`, `question`, `cell`, `run`, `evaluation`, `claim`, `decision`, `artifact`
are graph objects. `parent_id` is the navigational tree. Typed edges capture
comparison, support, contradiction, derivation, checkpoint inheritance and other
explicit relationships. They do not encode automatically proved causality.

Evidence references bind a file ID to a specific content hash and locator.
Accepted claims and decisions require a direct immutable source and a scope.
Linked node IDs are convenient navigation, not independent proof. Later source
changes flag applicability review without erasing the original snapshot.

A decision has required context, covered factor values, replication keys and
reopening conditions. It only counts as approved reuse after explicit human
confirmation. Unknown or extra conditions yield review, not automatic training.
The CLI is not a security boundary against an agent with arbitrary shell access;
host permissions and human authorization remain essential.

## Data adapters

Core ingestion recognizes `metrics.json`, `results.json`, `metrics.csv`,
`config.json`, `config.toml`, and optional `run.json`. The first metric filename
by that priority is used per run directory; additional sources are inventoried
and flagged, not silently pooled. If the primary file disappears and another
becomes primary, the run enters `needs_review` and retains old evidence until
an agent reconciles the transition. Conflicting protocol fields across metric,
run and configuration sources also block pooling. CSV uses the last row and does
not invent completion. JSON requires explicit completion to enter summaries.

Large binary files are metadata only; no pickle/torch load. Known secret names,
symlinks and dependency/internal directories are excluded. Source code is
parsed with Python AST only. YAML and arbitrary files remain evidence for host
inspection. There is no execution of instructions in input files.

## UI

Bundled HTML/CSS/JS use no CDN, frontend build or runtime dependency. The local
HTTP service exposes only state and known text evidence. It binds to loopback,
checks Host, requires a random API token and rejects cross-site fetches. There
is no shell, file-write, experiment-launch or synchronization HTTP endpoint.

Offline export embeds one state snapshot and optional referenced text. JSON
escapes `<`, `>`, `&` and Unicode separators; the frontend escapes dynamic labels
and uses textContent for evidence. Exports are still private artifacts and must
be reviewed before public sharing.

## Provider boundary

Skills for Codex and Claude use their respective discovery locations. Generic
agents can read the same Skill and command protocol. This is capability-based
integration: the host must read files and run commands. It is not an API router,
model fallback service, OAuth proxy or universal compatibility guarantee.
