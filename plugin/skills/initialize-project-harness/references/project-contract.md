# Project contract

The project contract is a small authority map, not a second documentation system.

Prefer this minimum shape when it adds value:

```json
{
  "schema_version": 1,
  "harness_version": "0.1.0",
  "project_name": "Example",
  "governance_mode": "standard",
  "domain_modules": ["software"],
  "authority": {
    "project": "PROJECT.md",
    "architecture": "docs/architecture.md",
    "current_state": "docs/status/NOW.md",
    "decisions": "docs/decisions"
  },
  "verification": {
    "default": ["scripts/check"]
  }
}
```

Omit absent optional authorities rather than creating empty files. Point to existing names and locations. A contract must not claim a command or source was verified when it was not.

Use a root `AGENTS.md` as the human-readable map. Keep detailed facts in their actual authorities.

Lite work has no persistent contract by default. Assured contracts require `authority.risks` and at least one verification command.

The canonical schema is `schemas/project-harness.schema.json` at the plugin root. The deterministic tools additionally reject absolute local paths and `..` references that escape the project root.
