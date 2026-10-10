"""Shared state of one validation run and the helpers the scenarios use.

Every ``factory`` command goes through ``python -m validation.worker`` in a
subprocess with ``cwd`` in the main checkout, ``--repo`` and ``--json``: the
JSON envelope (``{ok, data, error, warnings}``) on stdout, the narration in a
log file. In ``--remote local`` every command gets a fake script, so a real
harness can never be reached there; in ``--remote github`` only the commands
asked for with ``fake=True`` (B1) do. Every command gets ``HAIFA_VALIDATE_HIDDEN``
(the hidden test of ``validation.hidden``), which only the worker reads.
"""

from __future__ import annotations

import datetime
import json
import os
import sqlite3
import subprocess
import sys
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from validation import f2_backlog, fake_scripts, hidden
from validation.hidden import HIDDEN_ENV
from validation.results import ScenarioResult
from validation.safety import Owned, check_inside, safe_rmtree
from validation.sandbox import AIFACTORY_DIR, Sandbox, gh, git, git_ok
from validation.worker import FAKE_ENV

TASK_PATHS: dict[str, str] = {
    "M01-S01-T01": "backlog/M01-core/S01-math/M01-S01-T01-clamp.md",
    "M01-S01-T02": "backlog/M01-core/S01-math/M01-S01-T02-lerp.md",
    "M01-S01-T03": "backlog/M01-core/S01-math/M01-S01-T03-sign.md",
    "M01-S02-T01": "backlog/M01-core/S02-text/M01-S02-T01-slugify.md",
    "M01-S02-T02": "backlog/M01-core/S02-text/M01-S02-T02-truncate.md",
    "M02-S01-T01": "backlog/M02-cli/S01-commands/M02-S01-T01-greet.md",
    "M02-S01-T02": "backlog/M02-cli/S01-commands/M02-S01-T02-version.md",
    **f2_backlog.TASK_PATHS,
}
TRACE_DB = ".factory/trace.db"
SESSIONS_DIR = ".factory/data/sessions"


@dataclass
class Cmd:
    """One finished ``factory`` command: exit code and the JSON envelope it printed."""

    argv: list[str]
    code: int
    data: dict[str, Any]
    log: Path
    script: Path | None = None  # the fake script of the command, if it had one

    @property
    def ok(self) -> bool:
        return self.code == 0 and self.data.get("ok") is True

    @property
    def error(self) -> dict[str, Any]:
        err = self.data.get("error")
        return err if isinstance(err, dict) else {}

    @property
    def error_code(self) -> str | None:
        code = self.error.get("code")
        return None if code is None else str(code)

    @property
    def payload(self) -> dict[str, Any]:
        payload = self.data.get("data")
        return payload if isinstance(payload, dict) else {}

    @property
    def warnings(self) -> list[str]:
        warnings = self.data.get("warnings")
        return [str(w) for w in warnings] if isinstance(warnings, list) else []

    @property
    def run(self) -> dict[str, Any]:
        run = self.payload.get("run")
        return run if isinstance(run, dict) else {}

    @property
    def pr(self) -> dict[str, Any]:
        pr = self.payload.get("pr")
        return pr if isinstance(pr, dict) else {}

    def brief(self) -> str:
        err = self.error
        run = self.run
        text = f"exit {self.code}"
        if err:
            text += f": {err.get('code')}: {err.get('message')}"
        elif run:
            error = run.get("error") or ""
            text += f": run {run.get('run_id')} {run.get('state')} {error}".rstrip()
        return text


def parse_stdout(text: str) -> dict[str, Any]:
    """The JSON object ``--json`` printed (last top-level ``{`` line to the end)."""
    stripped = text.strip()
    if not stripped:
        return {}
    try:
        data = json.loads(stripped)
        return data if isinstance(data, dict) else {"value": data}
    except json.JSONDecodeError:
        pass
    lines = text.splitlines()
    for i in range(len(lines) - 1, -1, -1):
        if lines[i] == "{":
            try:
                data = json.loads("\n".join(lines[i:]))
            except json.JSONDecodeError:
                continue
            return data if isinstance(data, dict) else {"value": data}
    return {"unparsed_stdout": stripped[-2000:]}


@dataclass
class Pending:
    ctx: Context
    argv: list[str]
    proc: subprocess.Popen[str]
    log: Path
    script: Path | None = None

    def wait(self) -> Cmd:
        out, err = self.proc.communicate()
        self.log.write_text(err or "", encoding="utf-8", newline="\n")
        cmd = Cmd(self.argv, self.proc.returncode, parse_stdout(out or ""), self.log, self.script)
        self.ctx.commands.append(
            {"argv": self.argv, "exit": cmd.code, "log": self.log.name, "brief": cmd.brief()}
        )
        return cmd


@dataclass
class Context:
    remote: str
    sandbox: Sandbox
    workdir: Path
    owned: Owned
    r5_samples: int = 3
    # the directory of the hidden test; passed to validation.worker as HAIFA_VALIDATE_HIDDEN,
    # which the worker consumes (agents never get it) to place the test for code test steps
    hidden: Path | None = None
    harnesses: dict[str, str] = field(default_factory=dict)  # effective harness per step
    state: dict[str, Any] = field(default_factory=dict)
    referenced_runs: list[str] = field(default_factory=list)
    commands: list[dict[str, Any]] = field(default_factory=list)
    _n: int = 0

    @property
    def repo(self) -> Path:
        return self.sandbox.repo

    @property
    def base(self) -> str:
        return self.sandbox.base

    @property
    def logs(self) -> Path:
        path = self.workdir / "logs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def local(self) -> bool:
        return self.remote == "local"

    # -- HAIFA commands --

    def _spawn(
        self, argv: list[str], task: str | None, variant: str, fake: bool, repo_args: bool
    ) -> Pending:
        self._n += 1
        name = "-".join(a for a in argv[:2] if not a.startswith("-"))
        label = f"{self._n:02d}-{name}" + (f"-{task}" if task else "")
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            p for p in (str(AIFACTORY_DIR), env.get("PYTHONPATH", "")) if p
        )
        env.pop(FAKE_ENV, None)
        if self.hidden is not None:
            env[HIDDEN_ENV] = str(self.hidden)
        else:
            env.pop(HIDDEN_ENV, None)
        script_path: Path | None = None
        if self.local or fake:
            script: dict[str, Any] = (
                fake_scripts.script_for(task, variant, repo=self.repo)
                if task is not None
                else {"agents": {}}
            )
            path = self.logs / f"{label}.script.json"
            path.write_text(json.dumps(script, indent=2), encoding="utf-8", newline="\n")
            env[FAKE_ENV] = str(path)
            script_path = path
        full = [*argv, "--repo", str(self.repo), "--json"] if repo_args else [*argv, "--json"]
        proc = subprocess.Popen(
            [sys.executable, "-m", "validation.worker", *full],
            cwd=self.repo,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        return Pending(self, full, proc, self.logs / f"{label}.log", script_path)

    def haifa(
        self, *argv: str, task: str | None = None, variant: str = "happy", fake: bool = False
    ) -> Cmd:
        """Run one ``factory`` command; `task` picks the fake script (local mode or `fake`)."""
        return self._spawn(list(argv), task, variant, fake, True).wait()

    def factory_plain(self, *argv: str) -> Cmd:
        """A ``factory`` command without ``--repo`` (e.g. ``workflow check``), still in the repo."""
        return self._spawn(list(argv), None, "happy", False, False).wait()

    def haifa_async(self, *argv: str, task: str | None = None, variant: str = "happy") -> Pending:
        return self._spawn(list(argv), task, variant, False, True)

    def run_task(
        self, task_id: str, *extra: str, variant: str = "happy", fake: bool = False
    ) -> Cmd:
        return self.haifa("task", "run", task_id, *extra, task=task_id, variant=variant, fake=fake)

    # -- git and base --

    def fetch_base(self) -> str | None:
        git(self.repo, "fetch", "-q", "origin", self.base, check=False)
        sha = git(self.repo, "rev-parse", "--verify", "-q", f"origin/{self.base}", check=False)
        return sha or None

    def catch_up_base(self) -> None:
        """Fast-forward the main checkout's base to origin (github: HAIFA does not do it)."""
        if self.fetch_base() is None:
            return
        git_ok(self.repo, "merge", "--ff-only", "-q", f"origin/{self.base}")

    def base_commits(self) -> int:
        sha = self.fetch_base()
        if sha is None:
            return 0
        return int(git(self.repo, "rev-list", "--count", sha))

    def task_in_base(self, task_id: str) -> tuple[dict[str, Any], str]:
        """Header and full text of the task file in ``origin/<base>`` (fetched now)."""
        self.fetch_base()
        text = git(self.repo, "show", f"origin/{self.base}:{TASK_PATHS[task_id]}", check=False)
        header: dict[str, Any] = {}
        if text.startswith("---"):
            parts = text.split("\n---", 1)
            loaded = yaml.safe_load(parts[0].removeprefix("---")) if parts else None
            header = loaded if isinstance(loaded, dict) else {}
        return header, text

    def status_in_base(self, task_id: str) -> str:
        return str(self.task_in_base(task_id)[0].get("status", ""))

    def base_suite(self, dirname: str = "resolve-check") -> tuple[bool, str]:
        """`just test` in a clean checkout of ``origin/<base>`` (local only)."""
        path = self.workdir / dirname
        check_inside(path, self.workdir, self.owned)
        git(self.repo, "worktree", "add", "-q", "--detach", str(path), f"origin/{self.base}")
        try:
            env = dict(os.environ)
            env.pop(HIDDEN_ENV, None)
            with hidden.placed(path, self.hidden) if self.hidden is not None else nullcontext():
                proc = subprocess.run(
                    ["just", "test"],
                    cwd=path,
                    capture_output=True,
                    text=True,
                    env=env,
                    encoding="utf-8",
                )
            tail = (proc.stdout + proc.stderr).strip().splitlines()[-1:] or [""]
            return proc.returncode == 0, f"exit {proc.returncode} {tail[0]}".strip()
        finally:
            git(self.repo, "worktree", "remove", "--force", str(path), check=False)
            safe_rmtree(path, self.workdir, self.owned)

    def gh(self, *args: str, check: bool = True) -> str:
        return gh(self.repo, *args, check=check)

    # -- trace --

    def db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.repo / TRACE_DB), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def query(self, sql: str, *args: Any) -> list[sqlite3.Row]:
        path = self.repo / TRACE_DB
        if not path.is_file():
            return []
        conn = self.db()
        try:
            return list(conn.execute(sql, args).fetchall())
        finally:
            conn.close()

    def phases(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.query(
            "SELECT name, kind, owner, status, seq FROM phases WHERE adw_id = ? ORDER BY seq",
            run_id,
        )
        return [dict(r) for r in rows]

    def agent_starts(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.query(
            "SELECT p.name AS phase, e.payload_json FROM events e "
            "JOIN phases p ON p.phase_id = e.phase_id "
            "WHERE e.adw_id = ? AND e.type = 'agent_start' ORDER BY p.seq, e.rowid",
            run_id,
        )
        out = []
        for r in rows:
            payload = json.loads(r["payload_json"] or "{}")
            out.append(
                {
                    "phase": r["phase"],
                    "coding_agent": payload.get("coding_agent"),
                    "session_id": payload.get("session_id"),
                    "model": payload.get("model"),
                    "thinking": payload.get("thinking"),
                }
            )
        return out

    def phase_rows(self, run_id: str) -> dict[str, dict[str, Any]]:
        """The last phase of every name of `run_id`, by name."""
        return {p["name"]: p for p in self.phases(run_id)}

    def _quality(self, run_id: str, phase: str) -> dict[str, Any] | None:
        rows = self.query(
            "SELECT e.payload_json FROM events e JOIN phases p ON p.phase_id = e.phase_id "
            "WHERE e.adw_id = ? AND p.name = ? AND e.type = 'tool_call' "
            "AND e.name LIKE 'quality:%' ORDER BY e.rowid DESC LIMIT 1",
            run_id,
            phase,
        )
        if not rows:
            return None
        payload = json.loads(rows[0]["payload_json"] or "{}")
        return payload if isinstance(payload, dict) else None

    def test_passed(self, run_id: str, phase: str) -> bool | None:
        """Whether test phase `phase` passed (its last ``quality:<check>`` event), or None.

        The test step stops at the first failing check, so the last check decides.
        """
        payload = self._quality(run_id, phase)
        if payload is None or "passed" not in payload:
            return None
        return bool(payload["passed"])

    def test_output(self, run_id: str, phase: str) -> str:
        """The ``command.log`` of the last check of test phase `phase` (verbatim), or ''."""
        payload = self._quality(run_id, phase) or {}
        path = Path(str(payload.get("output_artifact") or ""))
        if not payload.get("output_artifact") or not path.is_file():
            return ""
        return path.read_text(encoding="utf-8", errors="replace")

    def envelope(self, run_id: str, phase: str) -> dict[str, Any]:
        """The last valid envelope an agent returned in phase `phase` of `run_id`, or {}."""
        rows = self.query(
            "SELECT v.payload_json FROM envelopes v JOIN phases p ON p.phase_id = v.phase_id "
            "WHERE v.adw_id = ? AND p.name = ? ORDER BY v.valid DESC, v.created_at DESC, "
            "v.rowid DESC LIMIT 1",
            run_id,
            phase,
        )
        if not rows:
            return {}
        payload = json.loads(rows[0]["payload_json"] or "{}")
        return payload if isinstance(payload, dict) else {}

    def events(self, run_id: str, type_: str, name: str) -> list[dict[str, Any]]:
        rows = self.query(
            "SELECT payload_json FROM events WHERE adw_id = ? AND type = ? AND name = ? "
            "ORDER BY rowid",
            run_id,
            type_,
            name,
        )
        return [json.loads(r["payload_json"] or "{}") for r in rows]

    def session_usage(self, run_id: str) -> dict[str, Any]:
        rows = self.query(
            "SELECT status, total_tokens, total_cost FROM sessions WHERE adw_id = ?", run_id
        )
        return dict(rows[0]) if rows else {}

    def phase_tokens(self, run_id: str) -> dict[str, int]:
        rows = self.query(
            "SELECT p.name AS phase, SUM(e.tokens) AS tokens FROM events e "
            "JOIN phases p ON p.phase_id = e.phase_id "
            "WHERE e.adw_id = ? AND e.tokens IS NOT NULL GROUP BY p.name ORDER BY MIN(p.seq)",
            run_id,
        )
        return {r["phase"]: int(r["tokens"] or 0) for r in rows}

    def task_run(self, run_id: str) -> dict[str, Any]:
        rows = self.query("SELECT * FROM task_runs WHERE run_id = ?", run_id)
        return dict(rows[0]) if rows else {}

    def task_pr(self, branch: str) -> dict[str, Any]:
        rows = self.query("SELECT * FROM task_prs WHERE branch = ?", branch)
        return dict(rows[0]) if rows else {}

    def session_dir(self, run_id: str) -> Path:
        return self.repo / SESSIONS_DIR / run_id

    # -- evidence --

    def reference(self, result: ScenarioResult, cmd_or_run: Cmd | str | None) -> str | None:
        """Record a run as evidence of `result`; its session dir is copied into trace/."""
        run_id = cmd_or_run if isinstance(cmd_or_run, str) or cmd_or_run is None else None
        if isinstance(cmd_or_run, Cmd):
            run_id = cmd_or_run.run.get("run_id")
        if not run_id:
            return None
        result.add_run(str(run_id))
        if run_id not in self.referenced_runs:
            self.referenced_runs.append(str(run_id))
        rel = f"trace/sessions/{run_id}"
        if rel not in result.trace_sessions:
            result.trace_sessions.append(rel)
        return str(run_id)

    def add_pr(self, result: ScenarioResult, task_id: str, pr: dict[str, Any]) -> None:
        if not pr:
            return
        state = self.task_pr(str(pr.get("branch", ""))).get("state", pr.get("state"))
        result.prs.append(
            {
                "task_id": task_id,
                "branch": pr.get("branch"),
                "url": pr.get("url"),
                "pr_id": pr.get("pr_id"),
                "state": state,
            }
        )


def parse_time(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    try:
        moment = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=datetime.UTC)


def run_seconds(row: dict[str, Any]) -> float | None:
    start, end = parse_time(row.get("started_at")), parse_time(row.get("ended_at"))
    if start is None or end is None:
        return None
    return round((end - start).total_seconds(), 3)
