# Notes for coding sessions

- `main` deploys to Render automatically. Merge into it only with the owner's go-ahead, except in the automated runs
  below.
- Automated runs go live on their own (owner, 26 Oct 2026: "on the automated runs, don't wait for my confirmation"):
  the daily update run (scheduled, 18:42 Berlin, `docs/daily_update.md`) merges its branch into `main` without asking, but only when the full test suite (browser tests included) passes on the merged
  result. If anything fails, nothing goes live and the owner is told. Data protection still applies
  (`docs/plan_data_protection.md`): anything flagged as possibly non-public or insider information is held for the
  owner's approval, never published by a run. Each run leaves a short summary of what went live (inbox, Telegram). The hourly cross-list lookup never updates the
  site: it only pushes the branch `lookups`, which the daily run merges (owner, 26 Oct 2026, to save resources).
- Before a merge that needs the owner's go-ahead, put the questions in `docs/open_questions.md` to the owner; record the
  answers there and remove what is settled. Automated runs list open questions in their summary instead of waiting.
- When a task the owner asked for finishes, tell them in one line on Telegram (`scripts/telegram.py send`; needs
  TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in the session): what finished and where to look. Status only, no data.
- Off-schedule updates are blocked (owner, 22 Oct 2026): any merge into `main` that is not an automated run (e.g. work
  done with the owner in a chat session) needs the owner to confirm it at least twice, in separate messages, after
  being told it is outside the daily run. Otherwise leave the work on a branch for the next daily run.
- Never commit anything local to one machine: `.venv`, `var/`, caches, or symbolic links. `tests/test_repo.py` fails
  if one is tracked; run the full test suite before every merge.
- Full test suite only once per release (owner, 26 Oct 2026: "stop running full tests before things are finally
  confirmed and signed off on"): while work is open, run only the tests for what changed; run the full suite once,
  after the owner's final sign-off (in the automated daily run: once, at the end), right before the merge. Workers
  never run the full suite.
- A second checkout (git worktree) gets its own environment with `uv sync`, never a symlink to another checkout's
  `.venv`: a committed link replaces the real folder on merge.
- Research reports for Future growth > Research & ideas follow the layout and priorities at the top of
  `data/business/reports.yaml`: adjacent products and technologies first, then other opportunities, then market trend.
