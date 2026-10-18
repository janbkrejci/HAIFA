set positional-arguments
set dotenv-load

# Recipes use Git Bash on native Windows; install it on PATH (see README).
set windows-shell := ["bash", "-cu"]

default:
    @just --list

# frontend checks, then pytest (args go to pytest)
test *ARGS: web-test
    cd aifactory && uv run pytest "$@"

# pytest alone, without the frontend checks (args go to pytest)
pytest *ARGS:
    cd aifactory && uv run pytest "$@"

# browser tests of the dashboard (Playwright, system Chrome)
e2e *ARGS:
    cd aifactory && uv run pytest tests/e2e -n0 "$@"

# Playwright's Chromium for machines without Google Chrome
e2e-install:
    cd aifactory && uv run playwright install chromium

# mypy; one cache shared by every worktree of the repo (a fresh worktree would take 60 s instead of 1 s)
typecheck:
    cd aifactory && MYPY_CACHE_DIR="$(git rev-parse --path-format=absolute --git-common-dir)/haifa/mypy-cache" uv run mypy

# ruff lint and format check
lint:
    cd aifactory && uv run ruff check . && uv run ruff format --check .

# the factory CLI from source
factory *ARGS:
    uv run --project aifactory factory "$@"

# shared team database server: just shared-db --data-dir ./team-db --host 0.0.0.0
shared-db *ARGS:
    uv run --project aifactory python -m aifactory.database.server "$@"

# dashboard from source on 127.0.0.1:4700: just dash [--port N] [--no-open]
dash *ARGS:
    uv run --project aifactory factory obs "$@"

# build the frontend into aifactory/src/aifactory/web/static (needs bun)
web-build:
    cd aifactory/web && bun install --frozen-lockfile && bun run build

# frontend typecheck and unit tests (vue-tsc, vitest)
web-test:
    cd aifactory/web && bun install --frozen-lockfile && bun run typecheck && bun run test

# frontend dev server on :4701, /api proxied to a running `just dash`
web-dev:
    cd aifactory/web && bun install --frozen-lockfile && bun run dev

# distribution ZIP aifactory/dist/haifa-<version>.zip
bundle: web-build
    cd aifactory && uv run python -m bundle.build

# live-model validation scenarios: just validate --remote local|github|azure [--roster DIR]
validate *ARGS:
    cd aifactory && uv run python -m validation "$@"

# full gate: frontend, pytest, mypy, ruff
check: test typecheck lint
