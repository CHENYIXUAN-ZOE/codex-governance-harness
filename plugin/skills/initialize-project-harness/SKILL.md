---
name: initialize-project-harness
description: Initialize, adopt, or upgrade a minimal project-level Harness by mapping existing authorities, selecting proportional governance, and creating only missing durable artifacts. Use when the user asks to create a project Harness, when starting a new persistent project with authorization to establish governance, or when migrating an existing project into the two-layer governance model.
---

# Initialize Project Harness

Create an adapter to the project that already exists. Do not impose a universal documentation tree.

Use `scripts/initialize_project.py` for deterministic planning and file creation. It is dry-run by default; pass `--apply` only after reviewing the emitted plan.

## Workflow

1. Confirm the intended project root and inspect applicable instructions.
2. Inventory existing product, architecture, status, decision, risk, and verification authorities.
3. Read `references/project-contract.md` and choose the smallest contract that can point to those authorities.
4. Select governance intensity and domain modules with `references/project-profiles.md`.
5. Present consequential assumptions when ownership, authority, or risk is unclear.
6. Run the initializer without `--apply` and inspect its complete write plan.
7. Apply only the missing minimum:
   - a root `AGENTS.md` map when durable project guidance is absent;
   - `.harness/project.json` when a machine-readable authority map adds value;
   - durable status, decision, risk, or verification artifacts only when the project genuinely needs them.
8. Preserve existing files and conventions. Never replace an existing authority with a duplicate.
9. Run `../audit-governance-harness/scripts/audit_project.py` against the result.
10. Report created, reused, and intentionally omitted artifacts.

## Safety

- Do not initialize persistent governance for a Lite task.
- Do not write outside the requested project.
- Do not overwrite an existing `AGENTS.md`, project configuration, or authority without explicit agreement.
- Do not install or modify the global Harness as part of project initialization.
- Do not bypass an initializer conflict by deleting or replacing the existing contract.
