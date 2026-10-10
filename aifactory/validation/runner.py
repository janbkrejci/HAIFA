"""Orchestration: preflight, workdir, test repo, hidden test, scenarios, results, trace copy."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any

from validation import results as results_mod
from validation.context import SESSIONS_DIR, TRACE_DB, Context
from validation.hidden import write_hidden
from validation.results import FAILED, ScenarioResult, now_iso, write_json, write_result
from validation.roster import (
    AGENTS_CONFIG,
    WORKFLOW,
    agent_harnesses,
    resolve_roster,
    step_harnesses,
    workflow_harnesses,
)
from validation.safety import Owned, safe_rmtree
from validation.sandbox import (
    AIFACTORY_DIR,
    HAIFA_ROOT,
    TEMPLATE_DIR,
    VALIDATION_DIR,
    Sandbox,
    SetupError,
    git,
    normalize_repo,
    setup_github,
    setup_local,
)
from validation.scenarios import ORDER

EXIT_OK, EXIT_FAILED, EXIT_SETUP = 0, 1, 2
SANDBOX_ENV = "HAIFA_SANDBOX_REPO"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="just validate",
        description="Validation scenarios R1-R5, R10, RESOLVE, B1 and F2 of aifactory.",
    )
    parser.add_argument(
        "--remote",
        choices=("local", "github"),
        default="local",
        help="local: bare repo in a temp dir, fake harness, no cost; "
        "github: the HAIFA_SANDBOX_REPO sandbox with the real harnesses",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=VALIDATION_DIR / "results",
        help="where <date>/<remote>-<time>/ goes (default: aifactory/validation/results)",
    )
    parser.add_argument(
        "--workdir", type=Path, default=None, help="working directory (default: a new temp dir)"
    )
    parser.add_argument(
        "--keep-workdir", action="store_true", help="do not delete the working directory"
    )
    parser.add_argument(
        "--only", default=None, help="comma separated subset, e.g. R1,R3 (default: all)"
    )
    parser.add_argument(
        "--roster",
        type=Path,
        default=None,
        metavar="DIR",
        help="replace the template's .factory/agents.yaml and "
        ".factory/workflows/simple-sdlc.yaml with DIR/agents.yaml and "
        "DIR/workflows/simple-sdlc.yaml (relative to the HAIFA root); the roster "
        "needs the agents planner, builder, tester, test-reviewer, reviewer and documenter",
    )
    parser.add_argument(
        "--r5-samples", type=int, default=3, help="worktrees R5 creates and measures"
    )
    return parser


def _selected(only: str | None) -> list[str]:
    names = [name for name, _ in ORDER]
    if not only:
        return names
    wanted = {part.strip().upper() for part in only.split(",") if part.strip()}
    unknown = wanted - set(names)
    if unknown:
        raise SetupError(f"--only: unknown scenario(s) {sorted(unknown)}, known: {names}")
    return [n for n in names if n in wanted]


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - python-dotenv is a dependency
        return
    load_dotenv(HAIFA_ROOT / ".env", override=False)


# Computer-local harness choices (``factory harness settings``): a default harness there
# overrides the harness and model of every agent of the roster, so a run would no longer
# validate the roster. The isolated home leaves them out and links everything else.
MACHINE_HARNESS_FILES = frozenset({"harnesses.json", "harness-tests.json"})
HOME_ENV = "HAIFA_HOME"


def isolated_haifa_home(workdir: Path, source: Path | None = None) -> Path:
    """A HAIFA home in `workdir` that mirrors `source` without the machine harness choices.

    Every other entry of `source` (``env``, ``library``, ``logs`` ...) is a symlink (a
    copy where symlinks fail), so the run keeps the operator's credentials and library;
    only the roster decides which harness and model each agent uses.
    """
    from aifactory.home import haifa_home

    real = (source if source is not None else haifa_home()).expanduser()
    home = workdir / "haifa-home"
    home.mkdir(parents=True, exist_ok=True)
    if real.is_dir():
        for entry in sorted(real.iterdir()):
            if entry.name in MACHINE_HARNESS_FILES:
                continue
            link = home / entry.name
            try:
                link.symlink_to(entry.resolve(), entry.is_dir())
            except OSError:  # Windows without the symlink privilege
                if entry.is_dir():
                    shutil.copytree(entry, link, symlinks=True)
                else:
                    shutil.copy2(entry, link)
    return home


def _worker_json(argv: list[str]) -> tuple[int, dict[str, Any]]:
    """A factory command through the worker without the fake (github preflight)."""
    env = {k: v for k, v in os.environ.items() if k != "HAIFA_VALIDATE_FAKE"}
    proc = subprocess.run(
        [sys.executable, "-m", "validation.worker", *argv],
        cwd=AIFACTORY_DIR,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        data = {}
    return proc.returncode, data if isinstance(data, dict) else {}


def roster_harnesses(roster: Path | None) -> set[str]:
    """Every harness the roster's agents and its workflow steps use."""
    if roster is None:
        agents, workflow = TEMPLATE_DIR / AGENTS_CONFIG, TEMPLATE_DIR / WORKFLOW
    else:
        agents, workflow = roster / "agents.yaml", roster / "workflows" / "simple-sdlc.yaml"
    used = set(agent_harnesses(agents).values())
    return used | set(workflow_harnesses(agents, workflow).values())


def check_config(harnesses: list[str]) -> dict[str, Any]:
    """A minimal roster for ``factory harness check --config``: one agent per harness.

    ``--config`` uses the public HAIFA roster loader (``.factory/agents.yaml``
    format); the check only needs agent names and harnesses.
    """
    return {"agents": [{"name": f"check-{name}", "harness": name} for name in harnesses]}


def preflight_github(sandbox_repo: str | None, roster: Path | None = None) -> str:
    """``owner/name`` of the sandbox after checking gh, just and the harnesses."""
    owner_name = normalize_repo(sandbox_repo)  # no subprocess before this check
    if shutil.which("just") is None:
        raise SetupError("`just` is not on PATH (the sandbox's test step runs `just test`)")
    from validation.sandbox import gh_executable

    auth = subprocess.run(
        [gh_executable(), "auth", "status"], capture_output=True, text=True, encoding="utf-8"
    )
    if auth.returncode != 0:
        raise SetupError(f"gh auth status failed: {(auth.stderr or auth.stdout).strip()}")
    names = sorted(roster_harnesses(roster))
    with tempfile.TemporaryDirectory(prefix="haifa-validate-check-") as tmp:
        config = Path(tmp) / "harnesses.yaml"
        config.write_text(json.dumps(check_config(names)), encoding="utf-8", newline="\n")
        code, data = _worker_json(["harness", "check", "--json", "--config", str(config)])
    if code != 0 or data.get("ok") is not True:
        raise SetupError(
            f"factory harness check ({', '.join(names)}) is not ok: {json.dumps(data)}"
        )
    return owner_name


def _haifa_head() -> str:
    try:
        return git(HAIFA_ROOT, "rev-parse", "HEAD")
    except RuntimeError:
        return ""


def copy_trace(ctx: Context, out: Path) -> None:
    trace = out / "trace"
    trace.mkdir(parents=True, exist_ok=True)
    db = ctx.repo / TRACE_DB
    if db.is_file():
        src = sqlite3.connect(str(db), timeout=10)
        dst = sqlite3.connect(str(trace / "sssf.db"))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
    for run_id in ctx.referenced_runs:
        source = ctx.repo / SESSIONS_DIR / run_id
        if source.is_dir():
            shutil.copytree(source, trace / "sessions" / run_id, dirs_exist_ok=True)
    logs = ctx.workdir / "logs"
    if logs.is_dir():
        shutil.copytree(logs, out / "logs", dirs_exist_ok=True)


def _existing(out: Path, paths: list[str]) -> list[str]:
    return [p for p in paths if (out / p).exists()]


def make_context(
    remote: str, sandbox: Sandbox, workdir: Path, owned: Owned, r5_samples: int
) -> Context:
    """The shared Context of one run over a prepared sandbox (writes the hidden test)."""
    harnesses = step_harnesses(sandbox.repo)
    return Context(
        remote,
        sandbox,
        workdir,
        owned,
        r5_samples=r5_samples,
        hidden=write_hidden(workdir),
        harnesses=harnesses,
    )


def write_results(ctx: Context, out: Path, done: list[ScenarioResult]) -> None:
    """Copy the trace into ``out`` and write one JSON per finished scenario."""
    out.mkdir(parents=True, exist_ok=True)
    copy_trace(ctx, out)
    for result in done:
        result.trace_sessions = _existing(out, result.trace_sessions)
        result.trace_files = _existing(out, result.trace_files)
        write_result(out, result)


def run_scenarios(ctx: Context, names: list[str], out: Path) -> list[ScenarioResult]:
    done: list[ScenarioResult] = []
    for name, func in ORDER:
        if name not in names:
            continue
        print(f"[validate] {name} ...", file=sys.stderr, flush=True)
        try:
            result = func(ctx)
        except Exception:
            result = ScenarioResult(name, ctx.remote)
            result.forced = FAILED
            result.observe(f"scénář skončil výjimkou:\n{traceback.format_exc()}")
        result.finish()
        done.append(result)
        print(f"[validate] {name}: {result.outcome}", file=sys.stderr, flush=True)
    return done


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _load_env()

    started = now_iso()
    try:
        names = _selected(args.only)
        roster = resolve_roster(args.roster) if args.roster is not None else None
        owner_name = (
            preflight_github(os.environ.get(SANDBOX_ENV), roster)
            if args.remote == "github"
            else None
        )
        if args.remote == "local" and shutil.which("just") is None:
            raise SetupError("`just` is not on PATH (the sandbox's test step runs `just test`)")
    except SetupError as exc:
        print(f"validate: {exc}", file=sys.stderr)
        return EXIT_SETUP

    owned = Owned()
    if args.workdir is None:
        workdir = owned.add(Path(tempfile.mkdtemp(prefix="haifa-validate-")))
    else:
        existed = args.workdir.exists()
        args.workdir.mkdir(parents=True, exist_ok=True)
        workdir = args.workdir.resolve()
        if not existed:
            owned.add(workdir)
        elif any(workdir.iterdir()):
            print(f"validate: --workdir {workdir} is not empty", file=sys.stderr)
            return EXIT_SETUP
        else:
            owned.add(workdir)

    previous_home = os.environ.get(HOME_ENV)
    os.environ[HOME_ENV] = str(isolated_haifa_home(workdir))
    try:
        return _run(args, names, roster, owner_name, started, owned, workdir)
    finally:
        if previous_home is None:
            os.environ.pop(HOME_ENV, None)
        else:
            os.environ[HOME_ENV] = previous_home


def _run(
    args: argparse.Namespace,
    names: list[str],
    roster: Path | None,
    owner_name: str | None,
    started: str,
    owned: Owned,
    workdir: Path,
) -> int:

    moment = datetime.datetime.now()
    out = results_mod.output_dir(args.results_dir.resolve(), args.remote, moment)
    try:
        sandbox: Sandbox
        if args.remote == "local":
            sandbox = setup_local(workdir, roster)
        else:
            assert owner_name is not None
            sandbox = setup_github(workdir, owner_name, moment, roster)
        ctx = make_context(args.remote, sandbox, workdir, owned, args.r5_samples)
    except (SetupError, RuntimeError) as exc:
        print(f"validate: cannot prepare the test repo: {exc}", file=sys.stderr)
        if not args.keep_workdir and owned.owns(workdir):
            safe_rmtree(workdir, workdir, owned)
        return EXIT_SETUP

    harnesses = ctx.harnesses
    where = f"repo {sandbox.repo}, base {sandbox.base}" + (f", roster {roster}" if roster else "")
    print(f"[validate] {args.remote}: {where}", file=sys.stderr)
    done = run_scenarios(ctx, names, out)

    write_results(ctx, out, done)
    kept = args.keep_workdir or not owned.owns(workdir)
    summary = {
        "remote": args.remote,
        "sandbox_repo": sandbox.github_repo or sandbox.remote_url,
        "base": sandbox.base,
        "haifa_commit": _haifa_head(),
        "started_at": started,
        "ended_at": now_iso(),
        "roster": str(roster) if roster else None,
        "harness_per_step": harnesses,
        "results": {r.scenario: r.outcome for r in done},
        "workdir": str(workdir),
        "workdir_kept": kept,
        "commands": ctx.commands,
    }
    write_json(out / "summary.json", summary)
    if not kept:
        safe_rmtree(workdir, workdir, owned)
    for result in done:
        print(f"{result.scenario:>7}  {result.outcome}", file=sys.stderr)
    print(f"results: {out}", file=sys.stderr)
    return EXIT_FAILED if any(r.outcome == FAILED for r in done) else EXIT_OK
