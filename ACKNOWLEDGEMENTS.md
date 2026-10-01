# Design references and attribution

Reviewed on 2026-09-28. This prototype is independently implemented. It does not
vendor source code, prompts, model weights, UI assets or brand assets from the
projects below, and does not depend on their runtimes. The list credits design
inspiration, not endorsement or a claim that their capabilities were reimplemented.

| Reference | Idea informing this prototype |
|---|---|
| [Agent Skills specification](https://agentskills.io/specification) | A small, portable SKILL.md entry with on-demand reference material. |
| [Codex Skills](https://developers.openai.com/codex/skills/) | Local/project Skill discovery; the host remains the coding agent. |
| [Claude Code Skills](https://code.claude.com/docs/en/skills) | Same workflow in a client-specific discovery directory. |
| [EvoScientist / EvoSkills](https://github.com/EvoScientist/EvoSkills) | Persistent research knowledge and installable research workflows. |
| [Xcientist](https://github.com/OpenDFM/Xcientist) | Research progress organized around inspectable evidence and stages. |
| [SENPAI](https://github.com/wandb/senpai) | Explicit experiment identity, artifacts and result contracts. |
| [Beads](https://github.com/gastownhall/beads) | Agent-accessible durable state inside existing developer workflows. |
| [TypeSafe / Jev patterns](https://docs.typesafe.ai/patterns) | Small typed judgments and programmatic control flow. No Jev model is used here. |
| [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) | Durable event records and replaceable integration boundaries. |
| [ClearML](https://github.com/clearml/clearml) | Everyday inspection, comparisons and provenance-oriented experiment UX. |

Licenses are not inherited by reading architectural ideas. Any future copied or
adapted source must be reviewed against its actual license at the chosen commit,
with the required notices retained. Do not silently copy third-party SKILL.md
content and rebrand it. This file is a design bibliography, not a license audit.

LabWeft is the confirmed project name; Research Harness was the prototype name.
No claim of first invention, exclusive functionality, universal model support,
or parity with the systems above is made.

## Optional executable dependency (2026-10-01)

The `shinka` extra now optionally installs
[SakanaAI/ShinkaEvolve](https://github.com/SakanaAI/ShinkaEvolve) at commit
`9912af12d423504b8d580f4179fd15f5f88b8c50`, licensed Apache-2.0 upstream.
LabWeft's adapter is independently authored against its public Python interfaces
and native result schema. No Shinka source, prompts or assets are copied into
this repository. The earlier no-runtime-dependency statement describes the core;
it does not apply when this optional extra is explicitly installed. Retain and
review upstream license/notice material if distributing its dependency artifacts.
