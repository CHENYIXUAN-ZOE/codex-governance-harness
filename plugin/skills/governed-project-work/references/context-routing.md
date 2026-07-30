# Context routing

Load context in this order:

1. Applicable instruction files.
2. The project authority map or nearest equivalent.
3. The smallest source directly governing the requested outcome.
4. Current implementation and verification surfaces.
5. Decision, risk, or historical context only when the task depends on it.

Do not preload an entire documentation tree. Search indexes, headings, file names, and explicit links first.

Treat these as different authority classes:

- durable repository facts: versioned project files;
- live external facts: the connected system that owns them;
- current task intent: the user's prompt and accepted clarifications;
- recall: chat summaries and Memory, which require confirmation against current authorities.

When sources conflict, identify the conflict rather than silently selecting the most convenient one.
