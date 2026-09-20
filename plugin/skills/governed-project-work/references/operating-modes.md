# Operating modes

## Lite

Use for bounded, low-risk work without durable coordination needs, including mechanical edits across several files and ordinary read-only lookups. Do not invoke this Skill merely to formalize Lite work.

## Standard

Use when any of these materially apply:

- cross-session recovery with state that future work needs;
- coordination with other people or agents;
- non-trivial acceptance criteria;
- meaningful architectural or product decisions.

Use a task plan and project authorities only to the extent they reduce uncertainty. File count and persistence alone are insufficient triggers. An existing authority map is enough; a machine contract is optional.

## Assured

Use for material effects on production, security, sensitive data, credentials, money, formal publication, regulated decisions, or difficult-to-reverse state. Classify the actual action: an ordinary external lookup is different from sending, deleting, deploying, or changing access. Read-only processing of sensitive data may still need appropriate controls.

Assured adds controls; it does not grant authority. Read `assured-controls.md`.

## Overrides

The user may request more governance. A request to reduce governance does not remove safety, authorization, truthfulness, or evidence requirements.
