# Known boundaries, not marketing claims

The included code is an alpha prototype created for the agreed local-first,
one-conversation research-workspace design. It is not a full ClearML replacement.

## Research understanding

The scanner does not infer scientific intent or reconstruct unknown old inputs.
Those tasks are delegated to the user's host agent through the Skill. A well-
formed patch can still contain a scientifically wrong interpretation. Model
output and source support need independent evaluation.

Automatic parsing covers a small documented set of JSON/TOML/CSV layouts. YAML,
Hydra's resolved configs, TensorBoard, W&B, ClearML, MLflow, custom robotics logs
and per-episode result formats need adapters or agent-assisted normalization.
Current source inspection provides a Python symbol index, not a whole-program
analysis of gradients, information leakage, deployment paths or dynamic imports.

## Historical identity and statistics

No recorded run ID: rename/move requires reconciliation. Repeated IDs across
folders are flagged. Current inventory is not a training-time code snapshot.
Metadata-only binary files have no verified content identity. Checkpoint/lineage
relations must be supplied from actual recorded evidence.

Summaries compute descriptive means and sample standard deviations across
unambiguous completed seeds. There is no bootstrap CI, paired statistical test,
equivalence test, experiment-budget optimizer, causal identification, or automatic
ranking. Multiple protocols/configurations/code versions are not silently pooled.
Seed is read from recorded fields; this cannot prove actual RNG independence.

## Persistence and operations

One workspace can attach several source directories. Cross-project overview,
controlled cross-project knowledge sharing and remote workers are not implemented.
Cross-machine Git merges, network filesystem lock behavior, collaboration roles,
schema migrations and crash/power-loss durability need additional work.

Evidence snapshots are local and excluded by the workspace Git ignore. Copying
only the event index does NOT back up or replicate their bytes. No automatic
GitHub repository creation, branch creation, upload, sync, issue/project creation,
checkpoint deletion or experiment scheduling is included.

## Agent integration

The installer and protocol are tested locally, and one bounded private project
was exercised by following the Skill in a Codex desktop conversation. Automatic
Skill discovery in a fresh chat and other model clients have not been certified.
Discovery can vary with client version, policy, sandbox, managed settings and permissions.
A bare model without filesystem/tool access cannot use this software by itself.
No hidden additional model account is required by this code.

## Interface and security

The UI is read-only. Its refresh button fetches persisted state; it does not
launch source scanning or semantic reasoning. The one-conversation flow comes
from the installed Skill. Arbitrary schema editing still requires the host agent
or CLI. Local/browser views are tested, but not all OS/browser combinations.

This is not a hardened public service. Known filename exclusion is not a full
secret scanner. Treat all source text as untrusted. File hashing alone does not
prevent malicious replacement by an authorized OS user. A `human:` actor label
is not cryptographic authentication. Keep the host agent sandbox and approvals.
