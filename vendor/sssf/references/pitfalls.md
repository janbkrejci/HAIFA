# Operational Pitfalls

Lessons from the field — each a generalizable rule with the mechanism that makes it bite.

## Reviewer context window

A reviewer that reads the built files against the plan needs a model whose context window exceeds the file size. A free-tier model with a 262K context window (`poolside/laguna-s-2.1:free`) will die with SIGTERM when asked to read a 600+ line HTML file — the orchestrator kills it, and `raw_output.jsonl` ends with `{"error": "143"}`.

- **Rule:** For any reviewer that reads code files directly, use a model with ≥1M context window. On Nous Portal free tier, `meituan/longcat-2.0:free` (1.0M ctx) is the reliable default.
- **Symptom:** review phase fails with SIGTERM; `stdout` may be empty or contain a partial answer cut off mid-sentence; `stderr` shows the session started.
- **Mechanism:** the agent spawns, starts reading files, hits the context ceiling before it can emit its final JSON answer, and the orchestrator terminates it for exceeding its budget.

## Builder "no change" detection

A builder whose plan calls out that the existing code already satisfies the spec will report 0 changed files. The downstream `git commit` phase must handle this gracefully.

- **Rule:** `git_helper.commit_all` returns `""` (empty string) when the working tree is clean — it does NOT raise. ADW scripts log `sha` + `committed: bool` so the trace shows whether a commit actually happened.
- **Symptom:** `commit_build` or `commit_docs` showing `sha: ""` and `committed: false` — this is correct behavior, not a failure.
- **Mechanism:** when the revision loop finds nothing to change, or the initial build already matches the spec, there is nothing to stage. The run still succeeds if `test.passed` and `review.approved`.

## Spec wording drives agent behavior

Small changes in the spec text produce different code. If the spec says "Počítat svátky jako pracovní dobu" the toggle is always on; if it says "S placenými svátky" the toggle is off by default.

- **Rule:** Write the spec in the imperative, exactly as you want the behavior. The builder implements what the spec says, not what you implied. Review the rendered output against the spec, not against your intent.

## Spec file must exist before running SDLC

The SDLC workflow (`just simple-sdlc specs/tasks/task-X.Y.md`) reads a spec file at the given path. If `next-task.sh` deleted it after a previous successful run, the planner starts hunting for alternatives and may fail with SIGTERM after 30s timeout.

- **Rule:** Before re-running a task, ensure `specs/tasks/task-X.Y.md` exists. If missing, copy from the canonical spec (`specs/<hash>_*.md`) in `specs/`.
- **Symptom:** Planner phase fails with `File not found: specs/tasks/task-X.Y.md` then SIGTERM (143).
- **Mechanism:** `next-task.sh` deletes the spec file after success. Re-running `just simple-sdlc` without restoring it causes the planner to search, exceed timeout, and get killed.

## Builder needs time — run it in the background

A builder phase reading many files and running tests can take 5-10 minutes. Running it in the foreground hits the shell command timeout.

- **Rule:** Always run `just simple-sdlc` as a background command. Poll the session log or events.jsonl for progress.
- **Symptom:** The shell command times out with the builder still running.
- **Mechanism:** Builder sessions run tool calls sequentially; large tasks exceed foreground timeout.

## Year-boundary week numbering

ISO 8601 week numbering trips up naive implementations: 2025-01-01 is Wednesday of week 1; 2026-01-01 is Thursday of week 1. A week-numbering function that doesn't anchor on Thursday of the target year will produce off-by-one errors around year boundaries.

- **Rule:** When implementing ISO week numbers, test at minimum three years: one where Jan 1 is Thursday (2026), one where it's Wednesday (2025), and one where it's Thursday again (2015). Verify against an external reference (e.g., kalendar.beda.cz).

## CI requires env vars even for tests

`omnibus.config._load()` imports at module load and crashes with `ValueError: Missing required env var` if `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET`, or `LLM_PROVIDER` are absent. A CI pipeline that runs `pytest` without dummy values in the workflow YAML fails at import time, before any test runs.

- **Rule:** Every CI workflow that runs tests must set dummy values for `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET`, `LLM_PROVIDER` in the test step's `env:` block.
- **Symptom:** CI run fails immediately with `ValueError: Missing required env var: STRIPE_API_KEY`; local tests pass because `.env` has real values.
- **Mechanism:** `config.py` runs `_load()` at import; pytest collects conftest which imports `omnibus.app` → `omnibus.config`. No amount of test-time mocking helps — the crash happens before fixtures load.

## `in` on `sqlite3.Row` checks values, not keys

`"column_name" in sqlite3.Row(...)` returns `False` even when the column exists. The `in` operator on `sqlite3.Row` iterates over values, not keys.

- **Rule:** Use `"key" in row.keys()` (or wrap in `list()`: `"key" in list(row.keys())` to satisfy ruff SIM118) to check for column existence.
- **Symptom:** `assert "priority" in row` fails silently — the column is in the row but `in` looked at values.
- **Mechanism:** `sqlite3.Row.__iter__` yields values; `in` uses `__iter__`. There is no `__contains__` override for key lookup.

## `omnibus/provision` is a package, not a runnable module

`python -m omnibus.provision` raises `No module named omnibus.provision.__main__; 'omnibus.provision' is a package and cannot be directly executed`.

- **Rule:** Run the CLI directly: `python omnibus/provision/cli.py --db <path> --admin-email <email> --admin-password <pw>`.
- **Mechanism:** The package has no `__main__.py`; the entry point is `cli.py`. Same pattern for `omnibus/seed/cli.py`.

## `init_change_queue` takes `db_path`, not `conn_or_path`

`init_change_queue(conn_or_path=db_path)` raises `TypeError: init_change_queue() got an unexpected keyword argument 'conn_or_path'`. The actual signature is `init_change_queue(db_path: str)`.

- **Rule:** Call `init_change_queue(db_path)` — positional or `db_path=`, never `conn_or_path=`.
- **Mechanism:** The function is a thin DDL executor; it doesn't accept connection objects, only paths.

## `ruff.toml` is canonical, not `[tool.ruff]` in `pyproject.toml`

Ruff reads `ruff.toml` / `.ruff.toml` first. When hatch builds the wheel, it may not preserve `[tool.ruff]` from `pyproject.toml`, causing divergence between local ruff and CI ruff.

- **Rule:** Put ruff config in `ruff.toml` (or `.ruff.toml`), not `[tool.ruff]` in `pyproject.toml`. Delete the `[tool.ruff]` block from `pyproject.toml` to avoid two sources of truth.
- **Mechanism:** Hatch's `[tool.ruff]` support is inconsistent; `ruff.toml` is always read by ruff directly.

## `datetime.now(UTC)` requires importing `UTC`

`from datetime import datetime` does not export `UTC`. `datetime.now(UTC)` raises `NameError: name 'UTC' is not defined`.

- **Rule:** Use `from datetime import datetime, timezone` and `datetime.now(timezone.utc)`, OR `from datetime import UTC, datetime` and `datetime.now(UTC)`. Both work; the first is more common in this codebase.
- **Mechanism:** `UTC` is a separate class in `datetime`, not an attribute of `datetime` the class.
