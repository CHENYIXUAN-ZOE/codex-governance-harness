# Operating modes

## Lite

Use when the task is local, low-risk, easily reversible, and does not require durable coordination. Do not invoke this Skill merely to formalize Lite work.

## Standard

Use when any of these materially apply:

- persistent project work;
- multiple files or stages;
- cross-session recovery;
- coordination with other people or agents;
- non-trivial acceptance criteria;
- meaningful architectural or product decisions.

Use a task plan and project authorities only to the extent they reduce uncertainty.

## Assured

Use when work can affect production, security, privacy, credentials, money, formal publication, external systems, regulated decisions, or difficult-to-reverse state.

Assured adds controls; it does not grant authority. Read `assured-controls.md`.

## Overrides

The user may request more governance. A request to reduce governance does not remove safety, authorization, truthfulness, or evidence requirements.
