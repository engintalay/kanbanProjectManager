# AGENTS.md — Workflow Rules

## Commit / Push policy (STANDING)
- After **every** code change / feature / fix, run:
  ```bash
  git add -A && git commit -m "<concise message>" && git push origin main
  ```
- Commit message style: `feat:` / `fix:` / `chore:` / `docs:` (kebab, lowercase).
- Never commit secrets: `.env`, `.venv/`, `__pycache__/`, `db.sqlite3` are gitignored.
  Jira creds live in `/home/engin/.jiracreds.json` (outside repo).
- If user says "commit only when asked", do NOT commit automatically.

## Environment quirks
- System Python 3.14 is externally-managed; use `.venv`. LSP "could not be resolved" =
  false positives (venv not on LSP path) — ignore them.
- Shell hangs on `pkill` / background server. Run test client with inline `timeout 25`.

## Project
- Django skeleton (Faz 1) done + pushed. Faz 2+ in progress.
- Full plan: `PLAN.md`.
