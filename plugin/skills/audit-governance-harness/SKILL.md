---
name: audit-governance-harness
description: Audit a global or project Governance Harness for drift, conflicting authorities, excessive context, missing controls, stale assumptions, unsafe installation behavior, and weak completion evidence. Use when the user asks to review, diagnose, health-check, simplify, or improve governance. Default to read-only reporting unless changes are explicitly requested.
---

# Audit Governance Harness

Produce an evidence-backed audit before proposing changes.

Use `scripts/audit_project.py` for the deterministic project-contract and local-authority checks. It is read-only.

## Workflow

1. Confirm whether the target is source, installed global state, a project Harness, or all three.
2. Inspect without mutation and list the instruction, Skill, config, rule, hook, schema, template, and evidence surfaces in scope.
3. Identify the authority for each governance concern and detect duplicates or conflicts.
4. Apply `references/audit-rubric.md`.
5. Separate findings from hypotheses and include file or runtime evidence.
6. Prioritize by impact:
   - P0: immediate authorization, data, destructive, or unrecoverable risk;
   - P1: systematic incorrect behavior or inability to verify;
   - P2: meaningful drift, waste, or maintainability problem;
   - P3: optional improvement.
7. Recommend the smallest effective action, including deletion when a component has no demonstrated value.
8. If the user requested fixes, apply scoped changes and rerun the relevant checks. Otherwise stop after the report.

The script validates structure and references but does not execute project verification commands. Run relevant verification separately when the audit scope includes behavioral correctness.

## Audit output

Return:

- scope and observed state;
- findings ordered by priority;
- evidence for each finding;
- recommended minimal change;
- items intentionally retained;
- validation gaps and residual risk.
