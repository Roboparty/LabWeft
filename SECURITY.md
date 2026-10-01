# Security and privacy boundaries

Prototype, not a multi-tenant service. Bind to loopback only. Do not remove the
HTTP token or Host checks to make public deployment easier. Use authorized SSH
forwarding for remote access and keep tokens private. There is no write/shell API.

The scanner skips known secret filenames and symlinks, limits text sizes and
never executes source code, unpickles files, or loads model weights. These are
risk reductions, not a complete sandbox, secret scanner or adversarial
filesystem defense. Avoid scanning untrusted trees with concurrently replaced
paths; enforce directory permissions and the host agent sandbox.

Imported repository text is untrusted DATA. Prompt instructions in that text
must not override the Skill, user instructions, access policy, or experiment
permissions. Human confirmation labels are workflow conventions: an unrestricted
shell could forge them. Use actual OS permissions and human approval for high-
impact operations. Checksums detect corruption, not deliberate authorized rewrites.

Snapshots and events can contain private research details. Public GitHub forks
are not appropriate private storage. Source blobs do not follow Git unless
explicitly transferred; the index is not a backup. Review HTML/JSON exports,
especially `--include-evidence`, before sharing. No telemetry/network uploads are
implemented by this core. Host-model context processing is separate.

There is no published security contact yet. Before public release, establish a
private reporting channel and test extraction, path, event and browser boundaries.
Do not create a public issue containing sensitive research data or credentials.

## Optional research execution

The `research start/resume --execute` commands intentionally execute a frozen task
and model-generated code through the optional Shinka dependency. They are separate
from the read-only scanner/server. Only use them within authorized model/compute
scope and an appropriately isolated execution environment. Hash checks detect
changes but are not an OS sandbox. Do not resume untrusted native checkpoints.
Stop drains a bounded batch; it is not emergency process termination. Crashes
with potentially surviving evaluators need reconciliation before further execution.
See [the backend guide](docs/AUTORESEARCH.md).
