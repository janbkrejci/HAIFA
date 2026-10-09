set positional-arguments
set dotenv-load

# Recipes use Git Bash on native Windows; install it on PATH (see README).
set windows-shell := ["bash", "-cu"]

default:
    @just --list

# ── aifactory ───────────────────────────────────────────────────────────────

# run the aifactory test suite incl. the F3 browser test: just test  (args go to pytest; frontend checks run first)
test *ARGS: web-test
    cd aifactory && uv run pytest "$@"

# browser acceptance test of F3 (Playwright over `factory obs`, system Chrome): just e2e
e2e *ARGS:
    cd aifactory && uv run pytest tests/e2e -n0 "$@"

# install Playwright's bundled chromium for machines without Google Chrome
e2e-install:
    cd aifactory && uv run playwright install chromium

# type-check aifactory with mypy
# one mypy cache for every checkout of the repo (main and run worktrees): a fresh worktree
# would otherwise type-check from scratch (60 s instead of 1 s)
typecheck:
    cd aifactory && MYPY_CACHE_DIR="$(git rev-parse --path-format=absolute --git-common-dir)/haifa/mypy-cache" uv run mypy

# lint aifactory with ruff
lint:
    cd aifactory && uv run ruff check . && uv run ruff format --check .

# run the factory CLI: just factory --help
factory *ARGS:
    uv run --project aifactory factory "$@"

# serve a public read/write team database: just shared-db --data-dir ./team-db --host 0.0.0.0
shared-db *ARGS:
    uv run --project aifactory python -m aifactory.database.server "$@"

# open the HAIFA dashboard on 127.0.0.1: just dash [--port N] [--no-open]
dash *ARGS:
    uv run --project aifactory factory obs "$@"

# build the dashboard frontend into the aifactory package (needs bun)
web-build:
    cd aifactory/web && bun install --frozen-lockfile && bun run build

# typecheck and unit-test the dashboard frontend (vue-tsc, vitest)
web-test:
    cd aifactory/web && bun install --frozen-lockfile && bun run typecheck && bun run test

# frontend dev server on :4701, /api proxied to a running `just dash`
web-dev:
    cd aifactory/web && bun install --frozen-lockfile && bun run dev

# distribution bundle aifactory/dist/haifa-<version>.zip: frontend, wheel, pinned deps, install.sh
bundle: web-build
    cd aifactory && uv run python -m bundle.build

# validation scenarios R1–R5, R10, RESOLVE, B1: just validate --remote local|github [--roster DIR]
validate *ARGS:
    cd aifactory && uv run python -m validation "$@"


check: test typecheck lint

check-scoped:
    just check

# the whole suite (`just check`) over a fresh checkout of main. Green is remembered in the git common
# dir; red adds a fix task to step STEP with the failing tests and the commits since the last green
# check, tested with the whole suite (test: just check)
[script("bash")]
full-check step="HAIFA-S03":
    set -uo pipefail
    state="$(git rev-parse --path-format=absolute --git-common-dir)/haifa"
    mkdir -p "$state" || exit 1
    sha=$(git rev-parse main) || exit 1
    work=$(mktemp -d "${TMPDIR:-/tmp}/haifa-full-check.XXXXXX") || exit 1
    if ! git worktree add -q --detach "$work/repo" "$sha"; then
        echo "full-check: cannot prepare checkout; green stamp unchanged" >&2
        rm -rf "$work"
        exit 1
    fi
    echo "full check of main ${sha:0:7} in $work/repo"
    (cd "$work/repo" && just check) > "$work/check.log" 2>&1
    rc=$?
    git worktree remove --force "$work/repo" > /dev/null 2>&1 || true
    if [ "$rc" -eq 0 ]; then
        echo "$sha" > "$state/full-check-green"
        rm -rf "$work"
        echo "full check green at ${sha:0:7}"
        exit 0
    fi
    green=$(cat "$state/full-check-green" 2>/dev/null || true)
    plain=$(sed 's/\x1b\[[0-9;]*m//g' "$work/check.log")
    failed=$(grep -E '^(FAILED|ERROR) ' <<<"$plain" | head -30 || true)
    [ -n "$failed" ] || failed=$(tail -15 <<<"$plain")
    if [ -n "$green" ]; then
        commits=$(git log --oneline --no-decorate "$green..$sha" | head -40)
        since="od posledního zeleného stavu ${green:0:7}"
    else
        commits=$(git log --oneline --no-decorate -15 "$sha")
        since="(poslední zelený stav neznámý, posledních 15)"
    fi
    fence='```'
    body="\`just full-check\` (celá sada nad main) selhal na ${sha:0:7}. Log: $work/check.log

    Selhání:

    $fence
    $failed
    $fence

    Commity $since:

    $fence
    $commits
    $fence

    Where: podle selhání.

    Done means:
    - Celá sada (\`just check\`) nad main projde.
    - Každé selhání má opravenou příčinu v kódu nebo v testu, ne obejitou.

    Pevná omezení:
    - \`vendor/\` a \`prototype/\` se nemění.
    - Testy nevolají model ani síť."
    body=$(sed 's/^    //' <<<"$body")
    just factory task add "{{step}}" "Celá sada je červená na ${sha:0:7}" --test just check --body "$body"
    just factory backlog commit -m "backlog: celá sada červená na ${sha:0:7}"
    echo "full check red at ${sha:0:7}: fix task added to {{step}}, log $work/check.log"
    exit 1
