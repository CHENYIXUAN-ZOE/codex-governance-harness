---
name: evolve-governance-harness
description: Evolve a global or project Governance Harness through evidence, controlled experiments, representative evaluations, versioning, migration, and rollback. Use when recurring friction, a model or Codex capability change, audit findings, or repeated failures suggest governance should be added, simplified, replaced, or removed.
---

# Evolve Governance Harness

Change the Harness only when evidence justifies the maintenance and context cost.

## Workflow

1. Read `references/evolution-protocol.md`.
2. Define the observed problem with concrete failures, friction, audit evidence, or capability change.
3. Identify the current component and the assumption it encodes.
4. Classify the change:
   - core invariant;
   - routing or workflow mechanism;
   - project template or schema;
   - deterministic enforcement;
   - documentation only.
5. Establish a baseline with representative cases and relevant efficiency metrics.
6. Propose the smallest single-variable change.
7. Run validation and compare against the baseline.
8. Reject, revise, or promote the change based on evidence.
9. For promoted changes, update version, changelog, migration notes, rollback path, and affected evaluations.
10. Obtain explicit user approval before deploying a core-invariant change or changing live global state.

## Guardrails

- Do not add process solely because a new feature exists.
- Do not change multiple load-bearing assumptions in one experiment.
- Do not optimize only for quality; include context, time, user intervention, and maintenance cost.
- Prefer deleting obsolete rules over layering exceptions on top.
- Keep live installation unchanged until the source candidate passes its gate.
