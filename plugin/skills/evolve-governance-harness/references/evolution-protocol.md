# Evolution protocol

## Evidence triggers

Valid triggers include:

- the same failure or correction recurring;
- irrelevant context repeatedly loaded;
- false completion or missing verification;
- project state failing to survive a new task;
- a deterministic capability replacing a textual reminder;
- a model or Codex capability making scaffolding plausibly redundant;
- an audit finding with material impact.

## Evaluation dimensions

Compare:

- requested outcome success;
- false-completion and regression rate;
- user intervention count;
- context and token weight;
- elapsed time and tool calls;
- recovery across tasks;
- governance artifacts created or maintained;
- residual safety and authorization risk.

## Experiment rules

- Keep representative prompts and artifacts fixed.
- Change one assumption at a time.
- Include both trigger and non-trigger cases.
- Preserve raw outputs and diffs.
- Treat an evaluator as evidence, not unquestionable truth.
- Revert when quality or safety degrades beyond the accepted threshold.

## Promotion

- Experimental: source-only candidate.
- Candidate: validated in isolated and representative cases.
- Stable: user-approved and installed with rollback.
- Deprecated: retained only for migration.
- Removed: no longer loaded or installed.

Core invariants require explicit user approval. Mechanisms can evolve within approved invariants when validation and rollback are complete.
