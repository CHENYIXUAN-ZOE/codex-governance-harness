# Completion evidence

Choose evidence that tests the requested outcome, not merely that an action ran.

Examples:

- code behavior: targeted tests, type checks, lint, runtime reproduction, diff review;
- UI behavior: rendered inspection, interaction test, screenshot or video when useful;
- data work: schema validation, reconciled totals, representative records, reproducible query;
- documents: content review plus render/layout verification when layout matters;
- configuration: parser or schema check plus an isolated load test;
- external actions: returned identifier and read-back confirmation when authorized.

If full verification is unavailable:

1. run the strongest safe partial check;
2. state exactly what was not verified and why;
3. do not describe the result as fully complete.
