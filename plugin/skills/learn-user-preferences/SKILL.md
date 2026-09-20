---
name: learn-user-preferences
description: Learn low-risk personal working preferences from user feedback, retrieve relevant local memory in a new task, and inspect, correct, disable, or undo remembered preferences. Use when feedback reveals a reusable preference or the user asks what is remembered; do not turn task facts or permissions into preferences.
---

# Learn User Preferences

Use a small, inspectable memory instead of adding a global rule for every correction. The mechanism is authorized by the user's request to maintain personal preferences; within that authorization, routine low-risk updates do not require a new approval each time. Do not activate persistent learning for a different user without their authorization.

## Decide what the feedback means

- Distinguish a one-task instruction, a project convention, and a broadly reusable preference. Use project scope unless cross-project relevance is supported by the feedback. Ask only when an unresolved distinction materially affects the work; otherwise use a narrow candidate or keep it in the current task.
- Infer communication, output, or working-method preferences from direct user feedback. Store a short positive formulation and its applicable conditions, not a transcript, personality profile, or an example treated as a universal rule. Preserve the user's underlying objective; disagreement with an answer is not automatically a request to agree more readily.
- Keep professional judgment grounded in the current project's evidence. Preferences guide how to help, not what facts are true. Current instructions and project requirements override recalled preferences; explain a consequential conflict without silently replacing the current goal.
- Never store secrets, sensitive personal attributes, third-party profiles, task facts, access rights, standing consent, permission elevation, security exceptions, external sending/publishing instructions, or changes to governance authority. Do not infer these from repetition. The script's category checks and common unsafe-text rejection catch obvious mistakes; they are not a semantic safety guarantee.

## Retrieve and apply

Run the helper by its installed skill path, using the actual `CODEX_HOME` (default `~/.codex`). Read relevant memory once near the start of a substantive task and again when feedback or a changed context makes it useful. Do not create a file just to read it.

```bash
python3 scripts/preferences.py list --project /absolute/project/root
python3 scripts/preferences.py list --category communication
```

`list` returns compact global records and, only with `--project`, records for that exact canonical project root. Add `--key` or `--category` to narrow retrieval; `--all` includes disabled records and `--details` includes brief evidence sources for inspection. Mutation responses show only the affected preference, and undo shows only its outcome. A missing store returns an empty list. An unavailable or damaged store must not derail the user's task: continue with current context and report the limitation only when relevant. Never reset a damaged store automatically.

Treat `candidate` as a reversible hypothesis: softly adapt when relevant, without overriding contrary evidence or announcing a permanent conclusion. `promoted` means two clear corrections from independent contexts support it; `explicit` means the user directly requested durable use. Both remain defeasible preferences. A project preference is relevant only in that project; it does not become a global preference merely through repetition. When equally applicable records conflict, prefer the current request, then the more specific scope, and consider confidence and recency; if still unresolved, do not invent a resolution from stale memory.

## Record, revise, or stop using

Use `--help` for the complete CLI. Mutations preview by default; add `--apply` to persist a reviewed low-risk update under the user's existing authorization. The JSON response distinguishes `preview`, `applied`, and `unchanged`.

```bash
python3 scripts/preferences.py record --scope global --key evidence-based-judgment \
  --category workflow --value 'Base recommendations on current project evidence and explain material disagreement.' \
  --when 'When the user questions or revises a recommendation.' \
  --source-summary 'The user requested durable independent professional judgment.' \
  --evidence explicit --event-id TASK_ID:TURN_ID:preference --context-id TASK_ID --apply
```

- Choose one stable key for one meaning within one scope. First retrieve existing relevant records; reuse the key rather than producing near-duplicates. Use `--scope project --project /absolute/root` for local preferences. Do not manufacture evidence from earlier sessions you cannot inspect.
- `inferred` records stay candidates. `correction` becomes promoted after **two independent context IDs**; repeated messages about the same ongoing issue share one context ID and do not inflate confidence. Use an actual task ID when available, otherwise a stable identifier derived from that task, never a fresh random context for each correction. A changed opinion alone is not a correction supporting the old preference.
- Use `explicit` only for a directly stated durable request, such as “以后都这样”, whose scope is supported. Current-task instructions do not qualify. Event IDs identify actual feedback occurrences; retry with the same ID. IDs are stored as hashes, not conversation content.
- `record` adds supporting evidence but refuses to silently change an existing formulation. Use `replace` with the same arguments to correct or narrow it; replacement resets the evidence for the new interpretation. Do not promote a replacement based on the old interpretation's history.
- Use `disable --scope … --key … --event-id … --apply` when the user says the preference is wrong or should stop applying. It retains the short record for inspection and one-step recovery; do not describe this as deleting personal data. `list --all` shows it. Re-enable only through a deliberate `replace` supported by new user feedback.
- Use `undo --event-id … --apply` to reverse the most recent successful storage change. One rollback snapshot is kept, with no transcript history. Undo itself cannot be undone; undone event IDs remain consumed so replay cannot recreate revoked learning. A genuinely new correction needs a new event ID.

The store is `CODEX_HOME/governance-harness/preferences.json`; project preferences are separate scoped entries in that same local file. The helper uses atomic replacement, a cooperating-process lock, restricted file mode, and rejects symlink targets. It does not write project files or global instructions. It is a bounded local memory, not a background listener: learning and retrieval happen only when the agent invokes this skill. Only say “已记住” after a successful write; if persistence is blocked, state that it was applied only in the current task. Do not promise perfect recall or that a preference can never be forgotten.
