# Codex Governance Harness Maintenance

This repository is the source of truth for the personal Codex Governance Harness.
It is not the live installation.

## Required context

Before changing governance behavior, read:

1. `docs/architecture/ARCHITECTURE.md`
2. `docs/ROADMAP.md`
3. `docs/governance/RISK-REGISTER.md`
4. `docs/status/NOW.md`

Read the relevant ADR before changing a decision it governs.

## Safety boundary

- Never modify `~/.codex`, `~/.agents`, an existing project Harness, or a plugin marketplace unless the user explicitly authorizes the deployment stage.
- Develop and validate in this repository first.
- Test install, update, and uninstall behavior against an isolated temporary `CODEX_HOME`.
- Preserve unrelated user configuration. Installation must merge narrowly, show a diff, create a backup, and support rollback.
- Do not add global hooks, MCP servers, external services, or destructive automation without a separate decision record and validation plan.

## Change protocol

- Keep the global kernel small, model-neutral, and capability-oriented.
- Put durable invariants in `global/AGENTS.md`; put reusable procedures in focused Skills; put project facts in project-owned sources.
- Do not duplicate an authority across files. Link to it.
- Treat core-invariant changes as high impact: document the rationale, update evaluations, and obtain explicit user approval before deployment.
- Prefer the smallest change that resolves observed evidence.
- Remove obsolete scaffolding when evaluation shows it is no longer load-bearing.

## Validation

Before reporting a source change complete:

1. Run the plugin validator.
2. Run the Skill validator for every changed Skill.
3. Run repository tests and structural checks available for the current phase.
4. Search for placeholders, broken relative references, and unexpected writes outside this repository.
5. Update `docs/status/NOW.md` and `CHANGELOG.md` when the source state materially changes.

## Completion

State what changed, what was validated, what remains uninstalled, and which phase gate is next.
