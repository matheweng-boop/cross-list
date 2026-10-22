# Notes for coding sessions

- `main` deploys to Render automatically. Merge into it only with the owner's go-ahead.
- Before asking for that go-ahead, put the questions in `docs/open_questions.md` to the owner; record the answers
  there and remove what is settled.
- The daily update run (scheduled, 18:42 Berlin) follows `docs/daily_update.md`: it pulls the owner's comments from
  the live site, prepares a branch and merges it into `main` only after the owner's go-ahead in that run's session.
- Off-schedule updates are blocked (owner, 22 Oct 2026): any other merge into `main` needs the owner to confirm it
  at least twice, in separate messages, after being told it is outside the daily run. Otherwise leave the work on a
  branch for the next daily run.
- Never commit anything local to one machine: `.venv`, `var/`, caches, or symbolic links. `tests/test_repo.py` fails
  if one is tracked; run the full test suite before every merge.
- A second checkout (git worktree) gets its own environment with `uv sync`, never a symlink to another checkout's
  `.venv`: a committed link replaces the real folder on merge.
- Research reports for Future growth > Research & ideas follow the layout and priorities at the top of
  `data/business/reports.yaml`: adjacent products and technologies first, then other opportunities, then market trend.
