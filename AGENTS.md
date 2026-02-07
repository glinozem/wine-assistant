# AGENTS — repo contract for Codex

This file defines the working rules for AI agents (Codex) in this repository.
Goal: predictable diffs, safe changes, and consistent validation.

## Core rules (must)
1) **No direct work on `master`.**
   - Always create a feature branch: `git switch -c <topic>`
   - Never commit to `master`.

2) **Never edit or commit local env/secrets.**
   - Forbidden: `.env`, `.env.*` (except `.env.example`), `.env.backup`, `*.key`, `*.pem`, `*.p12`,
     any tokens/keys/secrets.
   - If documentation is needed, update **only** `.env.example` and docs.

3) **Keep diffs minimal.**
   - Only change files required for the task.
   - No broad refactors, renames, formatting sweeps, dependency bumps unless explicitly requested.
   - If a change touches more than ~5 files, explain why before proceeding.

4) **Always validate before “done”.**
   - Run: `make lint` and `make test`
   - If running under Codex/Windows and environment is odd, use:
     `make PY=.\.venv\Scripts\python.exe check` (or `lint`/`test` accordingly).

## Working loop (expected)
- Start: `git status -sb` and show planned scope (what files will change).
- Before editing: show `/diff` (or `git diff --stat`) to confirm scope.
- Implement small incremental changes.
- After editing: show `/diff` and summarize what changed + why.
- Validate: `make lint` + `make test` (paste key output).
- Finish: `git status -sb` should be clean (no untracked artifacts).

## Output / communication
- Prefer concrete, copy-pasteable instructions.
- If tests fail, do not guess: paste the error, propose the smallest fix, rerun checks.
- If uncertain about a repo convention, inspect existing patterns in this repo first.
