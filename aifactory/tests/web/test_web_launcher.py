"""The dashboard's run launcher: every run is a separate ``factory`` process.

The run process is the stub ``launch_stub.py`` (it claims a row and waits, exits with an
envelope or with garbage); ``test_web_task_run`` runs a real ``factory task run`` through
``validation.worker``. No test calls a model or the network.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from aifactory import home, oscompat
from aifactory.run import TaskRunRow, TaskRunStore
from aifactory.skill import envelope_problems
from aifactory.web import create_app
from aifactory.web import launcher as launcher_module
from aifactory.web.launcher import DEFAULT_COMMAND, RunLauncher

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "run"))

from run_repo import T01, T02, git, make_run_repo  # noqa: E402

BASE = "http://127.0.0.1:4700"
STUB = Path(__file__).resolve().with_name("launch_stub.py")
STUB_COMMAND = [sys.executable, str(STUB)]
AIFACTORY = Path(__file__).resolve().parents[2]


class Stub:
    """The control file of the stub run processes."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.plans: dict[str, dict[str, Any]] = {}
        self._save()

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.plans), encoding="utf-8", newline="\n")

    def plan(self, task_id: str, mode: str, **extra: Any) -> None:
        self.plans[task_id] = {"mode": mode, **extra}
        self._save()

    def records(self, task_id: str) -> list[dict[str, Any]]:
        found = sorted(self.path.parent.glob(f"{self.path.name}.{task_id}.*.json"))
        return [json.loads(p.read_text(encoding="utf-8")) for p in found]


@pytest.fixture(name="stub")
def stub_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Stub:
    stub = Stub(tmp_path / "stub.json")
    monkeypatch.setenv("HAIFA_LAUNCH_STUB", str(stub.path))
    return stub


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


Apps = Callable[[Path], tuple[Starlette, TestClient, RunLauncher]]


@pytest.fixture(name="make_app")
def make_app_fixture(tmp_path: Path, stub: Stub) -> Iterator[Apps]:
    launchers: list[RunLauncher] = []

    def make(repo: Path) -> tuple[Starlette, TestClient, RunLauncher]:
        launcher = RunLauncher(command=STUB_COMMAND)
        launchers.append(launcher)
        app = create_app(repo, static_dir=tmp_path / "nostatic", launcher=launcher)
        return app, TestClient(app, base_url=BASE), launcher

    try:
        yield make
    finally:
        for launcher in launchers:
            for run in launcher.running():
                _kill(run.pid)
        for launcher in launchers:
            launcher.wait(30)
            assert launcher.running() == []


def _kill(pid: int) -> None:
    try:
        oscompat.kill(pid, force=True)
    except ProcessLookupError:
        pass


def _check(response: Any, status: int) -> Any:
    body = response.json()
    assert envelope_problems(body) == []
    assert response.status_code == status, body
    return body


def _run(client: TestClient, task_id: str, payload: Any, status: int = 202) -> Any:
    return _check(client.post(f"/api/backlog/tasks/{task_id}/run", json=payload), status)


def runs_of(repo: Path, task_id: str) -> list[TaskRunRow]:
    db = repo / ".factory" / "trace.db"
    if not db.is_file():
        return []
    store = TaskRunStore(db)
    try:
        return store.for_task(task_id)
    finally:
        store.close()


def _row(repo: Path, run_id: str) -> TaskRunRow | None:
    """The row as stored, without reaping dead runs."""
    store = TaskRunStore(repo / ".factory" / "trace.db")
    try:
        return store.get(run_id)
    finally:
        store.close()


def _until(condition: Callable[[], bool], timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return condition()


def _zombie_or_gone(pid: int) -> str:
    done = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)],
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
    )
    return done.stdout.strip()


def test_run_is_a_separate_process(
    make_app: Apps, repo: Path, stub: Stub, monkeypatch: pytest.MonkeyPatch
) -> None:
    _app, client, launcher = make_app(repo)
    data = _run(client, T01, {"note": "z UI"})["data"]
    assert data["pending"] is False
    run = data["run"]
    assert run["state"] == "running"
    assert run["task_id"] == T01
    [live] = launcher.running()
    [record] = stub.records(T01)
    assert run["pid"] == record["pid"] != os.getpid()
    if sys.platform == "win32":
        # the venv's python.exe is a launcher that runs the interpreter as its child
        assert live.pid in (record["pid"], record["ppid"])
        assert record["sid"] is None  # no sessions; NEW_GROUP gives it its own group
    else:
        assert record["pid"] == live.pid
        assert record["sid"] == live.pid  # its own session
    assert Path(record["cwd"]).resolve() == repo
    assert record["stdin"] == ""
    assert record["haifa_home"] == os.environ["HAIFA_HOME"]
    argv = record["argv"]
    assert argv[:3] == ["task", "run", T01]
    assert argv[3:6] == ["--repo", str(repo), "--json"]
    assert "--note=z UI" in argv
    assert "--force" not in argv
    logs = home.logs_dir()
    assert logs == Path(os.environ["HAIFA_HOME"]) / "logs"
    files = sorted(logs.iterdir())
    assert sorted(p.suffix for p in files) == [".json", ".log"]
    assert {live.envelope_path, live.log_path} == set(files)
    for path in files:
        if sys.platform != "win32":  # Windows has no POSIX modes
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert f"-{os.getpid()}-run-{T01}-" in path.name
    changed = git(repo, "status", "--porcelain", "--untracked-files=all").splitlines()
    assert all(line[3:].startswith(".factory/") for line in changed), changed
    check = _check(client.get(f"/api/backlog/tasks/{T01}/run-check"), 200)["data"]
    assert check["launcher_busy"] is False
    assert check["running"]["run_id"] == run["run_id"]


def test_run_passes_harness_override_and_auto(make_app: Apps, repo: Path, stub: Stub) -> None:
    _app, client, _launcher = make_app(repo)
    payload = {"harness": "codex", "model": "gpt-5.5", "thinking": "high", "auto": True}
    data = _run(client, T01, payload)["data"]
    assert data["auto"] is True
    [record] = stub.records(T01)
    argv = record["argv"]
    assert "--harness=codex" in argv
    assert "--model=gpt-5.5" in argv
    assert "--thinking=high" in argv
    assert "--auto" in argv


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("already_running", 409),
        ("unmet_dependencies", 409),
        ("unknown_task", 404),
        ("no_writes", 422),
        ("no_workflow", 422),
        ("task_not_in_base", 409),
    ],
)
def test_run_errors_before_claim(
    make_app: Apps, repo: Path, stub: Stub, code: str, status: int
) -> None:
    _app, client, launcher = make_app(repo)
    stub.plan(T01, "fail", code=code, message=f"stub says {code}")
    body = _run(client, T01, {"force": True}, status)
    assert (body["error"]["code"], body["error"]["message"]) == (code, f"stub says {code}")
    [record] = stub.records(T01)
    assert "--force" in record["argv"]
    launcher.wait(10)
    assert runs_of(repo, T01) == []


@pytest.mark.parametrize(
    ("action", "payload", "code", "status"),
    [
        ("return", {"note": "-x přidej test"}, "no_pr", 404),
        ("return", {"note": "x"}, "pr_not_open", 409),
        ("resolve", {}, "pr_not_open", 409),
        ("resolve", {}, "dirty_worktree", 409),
    ],
)
def test_review_errors_before_claim(
    make_app: Apps, repo: Path, stub: Stub, action: str, payload: Any, code: str, status: int
) -> None:
    _app, client, launcher = make_app(repo)
    stub.plan(T01, "fail", code=code, message="nope")
    body = _check(client.post(f"/api/review/{T01}/{action}", json=payload), status)
    assert (body["error"]["code"], body["error"]["message"]) == (code, "nope")
    [record] = stub.records(T01)
    assert record["argv"][:6] == ["task", action, T01, "--repo", str(repo), "--json"]
    if action == "return":
        assert record["argv"][6:] == [f"--note={payload['note']}"]
    launcher.wait(10)
    assert runs_of(repo, T01) == []


def test_review_actions_claim(make_app: Apps, repo: Path, stub: Stub) -> None:
    _app, client, _launcher = make_app(repo)
    data = _check(client.post(f"/api/review/{T01}/return", json={"note": "oprav"}), 202)["data"]
    assert data["action"] == "return"
    assert data["run"]["workflow"] == "return"
    assert data["run"]["note"] == "oprav"
    data = _check(client.post(f"/api/review/{T02}/resolve", json={}), 202)["data"]
    assert data["action"] == "resolve"
    assert data["run"]["workflow"] == "resolve"


def test_unreadable_envelope_is_internal_error(make_app: Apps, repo: Path, stub: Stub) -> None:
    _app, client, _launcher = make_app(repo)
    stub.plan(T01, "garbage")
    body = _run(client, T01, {}, 500)
    assert body["error"]["code"] == "internal_error"
    message = body["error"]["message"]
    assert "STUB-TAIL-MARKER" in message
    assert "exited with 3" in message


def test_process_that_finishes(make_app: Apps, repo: Path, stub: Stub) -> None:
    _app, client, launcher = make_app(repo)
    stub.plan(T01, "claim-exit")
    data = _run(client, T01, {})["data"]
    assert data["run"] is not None
    launcher.wait(10)
    assert launcher.running() == []
    [row] = runs_of(repo, T01)
    assert row.state == "succeeded"
    [live] = [p for p in home.logs_dir().iterdir() if p.suffix == ".json"]
    assert json.loads(live.read_text(encoding="utf-8"))["ok"] is True


def test_pending_when_not_claimed_in_time(repo: Path, stub: Stub) -> None:
    launcher = RunLauncher(command=STUB_COMMAND)
    stub.plan(T01, "claim-wait", delay=1.5)
    try:
        assert launcher.start(repo, T01, note=None, force=False, timeout=0.2) is None
        assert len(launcher.running()) == 1
        # The stub starts Python, imports aifactory and sleeps 1.5 s before it claims;
        # under a loaded parallel suite that alone can take longer than 10 s.
        assert _until(lambda: len(runs_of(repo, T01)) == 1, timeout=60)
        assert runs_of(repo, T01)[0].state == "running"
    finally:
        for run in launcher.running():
            _kill(run.pid)
        launcher.wait(30)


def test_two_tasks_of_one_repo_run_concurrently(make_app: Apps, repo: Path, stub: Stub) -> None:
    _app, client, launcher = make_app(repo)
    first = _run(client, T01, {})["data"]["run"]
    second = _run(client, T02, {"force": True})["data"]["run"]
    assert first["pid"] != second["pid"]
    listed = _check(client.get("/api/runs?state=running"), 200)["data"]["runs"]
    assert sorted(r["task_id"] for r in listed) == [T01, T02]
    assert len(launcher.running()) == 2
    check = _check(client.get(f"/api/backlog/tasks/{T01}/run-check"), 200)["data"]
    assert check["launcher_busy"] is False
    body = _run(client, T01, {}, 409)  # the stub's claim refuses a second run of T01
    assert body["error"]["code"] == "already_running"


def test_two_repos_run_concurrently(make_app: Apps, tmp_path: Path, repo: Path, stub: Stub) -> None:
    other = make_run_repo(tmp_path / "other")
    _a, client_a, launcher_a = make_app(repo)
    _b, client_b, launcher_b = make_app(other)
    _run(client_a, T01, {})
    _run(client_b, T01, {})
    assert [r.state for r in runs_of(repo, T01)] == ["running"]
    assert [r.state for r in runs_of(other, T01)] == ["running"]
    assert len(launcher_a.running()) == len(launcher_b.running()) == 1


def test_stop_from_dashboard(make_app: Apps, repo: Path, stub: Stub) -> None:
    _app, client, launcher = make_app(repo)
    run = _run(client, T01, {})["data"]["run"]
    data = _check(client.post(f"/api/runs/{run['run_id']}/stop"), 200)["data"]
    assert data["run"]["state"] == "stopped"
    assert data["signalled"] == [run["pid"]]
    launcher.wait(10)
    assert launcher.running() == []
    assert [r.state for r in runs_of(repo, T01)] == ["stopped"]


def test_factory_task_stop_from_terminal(make_app: Apps, repo: Path, stub: Stub) -> None:
    _app, client, launcher = make_app(repo)
    run = _run(client, T01, {})["data"]["run"]
    done = subprocess.run(
        [sys.executable, "-m", "aifactory", "task", "stop", T01, "--repo", str(repo), "--json"],
        cwd=AIFACTORY,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        encoding="utf-8",
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert json.loads(done.stdout)["ok"] is True
    launcher.wait(10)
    assert launcher.running() == []
    assert _check(client.get("/api/health"), 200)["ok"] is True
    [row] = runs_of(repo, T01)
    assert row.run_id == run["run_id"]
    assert row.state == "stopped"


def test_new_app_instance_sees_the_run(make_app: Apps, repo: Path, stub: Stub) -> None:
    _a, client_a, launcher_a = make_app(repo)
    run = _run(client_a, T01, {})["data"]["run"]
    _b, client_b, launcher_b = make_app(repo)
    listed = _check(client_b.get(f"/api/runs?task={T01}"), 200)["data"]["runs"]
    assert [(r["state"], r["run_id"]) for r in listed] == [("running", run["run_id"])]
    [row] = runs_of(repo, T01)
    assert row.pid == run["pid"]
    assert launcher_b.running() == []
    data = _check(client_b.post(f"/api/runs/{run['run_id']}/stop"), 200)["data"]
    assert data["run"]["state"] == "stopped"
    launcher_a.wait(10)
    assert launcher_a.running() == []


def test_killed_process_is_reaped(make_app: Apps, repo: Path, stub: Stub) -> None:
    _app, client, launcher = make_app(repo)
    run = _run(client, T01, {})["data"]["run"]
    pid = run["pid"]
    oscompat.kill(pid, force=True)
    assert _until(lambda: launcher.running() == [])
    if sys.platform == "win32":  # no zombies there: the process is just gone
        assert _until(lambda: not oscompat.alive(pid))
    else:
        assert _until(lambda: not _zombie_or_gone(pid).startswith("Z")), _zombie_or_gone(pid)

    def aborted() -> bool:
        row = _row(repo, run["run_id"])
        return row is not None and row.state == "aborted"

    assert _until(aborted)  # the launcher reaped the store itself


def test_command_prefix_is_configurable(repo: Path, stub: Stub) -> None:
    assert launcher_module.command_prefix() == DEFAULT_COMMAND
    stub.plan(T01, "claim-exit")
    launcher_module.set_command_prefix(STUB_COMMAND)
    try:
        assert launcher_module.command_prefix() == tuple(STUB_COMMAND)
        launcher = RunLauncher()
        row = launcher.start(repo, T01, note=None, force=False)
        assert row is not None
        launcher.wait(10)
        [record] = stub.records(T01)
        assert record["argv"][:3] == ["task", "run", T01]
    finally:
        launcher_module.set_command_prefix(None)
    assert launcher_module.command_prefix() == DEFAULT_COMMAND


def test_haifa_home_resolution(tmp_path: Path) -> None:
    assert home.haifa_home({"HAIFA_HOME": "/x/h", "XDG_CONFIG_HOME": "/x/c"}) == Path("/x/h")
    assert home.haifa_home({"HAIFA_HOME": "", "XDG_CONFIG_HOME": "/x/c"}) == Path("/x/c/haifa")
    assert home.haifa_home({"XDG_CONFIG_HOME": "", "HOME": "/u"}) == Path("/u/.config/haifa")
    assert home.haifa_home({"HOME": "/u"}) == Path("/u/.config/haifa")
    assert home.haifa_home() == Path(os.environ["HAIFA_HOME"])
    logs = home.logs_dir({"HAIFA_HOME": str(tmp_path / "h")})
    assert logs == tmp_path / "h" / "logs"
    if sys.platform != "win32":  # Windows has no POSIX modes
        assert stat.S_IMODE(logs.stat().st_mode) == 0o700
    with home.create_private(logs / "a.json") as out:
        out.write(b"{}")
    if sys.platform != "win32":
        assert stat.S_IMODE((logs / "a.json").stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        home.create_private(logs / "a.json")
