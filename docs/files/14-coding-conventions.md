# Coding Conventions (cross-cutting — read once, applies to every module)

Any AI agent or person implementing modules 1–11 should read this file before writing code, instead of being told these conventions again per module or per session.

## Python style
- No list comprehensions — use explicit `for` loops. It's slightly more verbose but easier to trace through when debugging a live trading decision.
- No `sorted()` — write the sort/comparison explicitly where ordering is needed (e.g. ranking symbols, ordering proposals by confidence).
- No `if __name__ == "__main__":` guards — entry points call their startup function directly.
- Prefer the simplest implementation that's correct over a clever one, with a short comment explaining *why* a step exists, not just what it does — this matters more here than usual, since every decision/risk/execution path needs to be auditable by someone who didn't write it.

## Dependencies
- Don't add a new external library unless the task genuinely can't be done with the standard library or a dependency already established in the project (`aiohttp`, `websockets`, `pytest` per the existing `requirements.txt`). If a module seems to need something new (e.g. an exchange SDK for module 7's n8n/Binance boundary), call it out explicitly rather than adding it silently — treat it as a decision to log in `docs/implementation-log.md`, not a default.

## Documentation output
- When a module's spec asks for a written artifact (a report, a config reference, a schema doc) rather than just code, produce it as a standalone file the user can download, not only inline explanation — module docs and `docs/implementation-log.md` entries should be actual files, consistent with how the rest of this module set is delivered.

## Scope not covered here
These are Python-specific conventions because every module in this set (1–11) is Python. If a future module introduces a Node.js component (e.g. a dashboard or webhook relay), use modular architecture with Firebase for backend/auth, per standing preference — but nothing in the current module set calls for that.
