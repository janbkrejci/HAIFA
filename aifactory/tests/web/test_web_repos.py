"""The multi-repo dashboard API (``create_multi_app``): registry endpoints and per-repo mounts."""

from __future__ import annotations

import asyncio
import http.client
import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import pytest
import uvicorn
import yaml
from backlog_fixture import make_backlog_repo
from multi_repo import (
    BASE,
    SSSF_ROSTER,
    commit_all,
    git,
    init_repo,
    multi_client,
    onboard,
    register,
    rmtree,
    symlink,
    write,
)
from starlette.testclient import TestClient

from aifactory.codeprint import CodeWatch
from aifactory.skill import envelope_problems
from aifactory.web import create_multi_app

ALLOWED_GIT = {"rev-parse", "cat-file", "ls-tree", "for-each-ref", "remote"}


@pytest.fixture
def home(tmp_path: Path) -> Path:
    return tmp_path / "home"


@pytest.fixture
def client(home: Path, tmp_path: Path) -> TestClient:
    return multi_client(home, tmp_path, port=4700)


def _check(response: Any, status: int) -> Any:
    body = response.json()
    assert envelope_problems(body) == []
    assert response.status_code == status, body
    return body


def _get(client: TestClient, url: str, status: int = 200) -> Any:
    return _check(client.get(url), status)


def _post(client: TestClient, url: str, payload: Any, status: int = 200) -> Any:
    return _check(client.post(url, json=payload), status)


def _inspect(client: TestClient, path: Path | str, status: int = 200) -> Any:
    return _post(client, "/api/repos/inspect", {"path": str(path)}, status)


def _add(client: TestClient, path: Path | str, status: int = 201) -> Any:
    return _post(client, "/api/repos", {"path": str(path)}, status)


def _registry(home: Path) -> Any:
    path = home / "dashboard.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None


# -- global endpoints --------------------------------------------------------------------


def test_health(client: TestClient, home: Path) -> None:
    data = _get(client, "/api/health")["data"]
    assert data["app"] == "haifa-dashboard"
    assert data["home"] == str(home)
    assert isinstance(data["version"], str)


def test_dashboard_settings(client: TestClient, home: Path) -> None:
    data = _get(client, "/api/dashboard/settings")["data"]
    assert data["port"] == 4700 and data["restart_required"] is False
    assert data["home"] == str(home)
    data = _post(client, "/api/dashboard/settings", {"port": 4801})["data"]
    assert data["port"] == 4801 and data["restart_required"] is True
    assert _registry(home)["port"] == 4801
    for bad in (0, "x", True, 70000):
        body = _post(client, "/api/dashboard/settings", {"port": bad}, 422)
        assert body["error"]["code"] == "invalid_value"
        assert body["error"]["issues"][0]["id"] == "port"
    body = _post(client, "/api/dashboard/settings", {"colour": "red"}, 400)
    assert body["error"]["code"] == "usage_error"
    assert _registry(home)["port"] == 4801


# -- inspect -----------------------------------------------------------------------------


def test_inspect_folder_without_git(client: TestClient, tmp_path: Path, home: Path) -> None:
    folder = tmp_path / "plain"
    folder.mkdir()
    data = _inspect(client, folder)["data"]
    assert data["problem"]["code"] == "not_git"
    assert data["addable"] is False and data["factory"] is None
    assert not (folder / ".git").exists()
    body = _add(client, folder, 422)
    assert body["error"]["code"] == "not_git"
    assert not (folder / ".git").exists()
    assert _registry(home) is None


def test_inspect_subfolder_takes_root(client: TestClient, tmp_path: Path, home: Path) -> None:
    root = init_repo(tmp_path / "proj")
    (root / "src" / "deep").mkdir(parents=True)
    data = _inspect(client, root / "src" / "deep")["data"]
    assert data["root"] == str(root)
    assert data["subdir"] == "src/deep"
    assert data["addable"] is True and data["problem"] is None
    assert data["branch"] == "main" and data["remote"] is None
    assert data["registered"] is None
    assert data["factory"]["state"] == "none" and data["factory"]["action"] == "init"
    assert data["trace_db"] == str(root / ".factory" / "trace.db")
    assert _registry(home) is None


def test_inspect_linked_worktree(client: TestClient, tmp_path: Path) -> None:
    root = init_repo(tmp_path / "proj")
    linked = tmp_path / "linked"
    git(root, "worktree", "add", "-q", str(linked), "-b", "side")
    data = _inspect(client, linked)["data"]
    assert data["problem"]["code"] == "linked_worktree"
    assert data["problem"]["main_checkout"] == str(root)
    body = _add(client, linked, 422)
    assert body["error"]["code"] == "linked_worktree"
    assert body["data"]["main_checkout"] == str(root)


def test_inspect_run_worktree(client: TestClient, tmp_path: Path) -> None:
    root = init_repo(tmp_path / "proj")
    worktree = root / ".factory" / "worktrees" / "abc"
    git(root, "worktree", "add", "-q", str(worktree), "-b", "factory/x-1")
    assert _inspect(client, worktree)["data"]["problem"]["code"] == "run_worktree"
    (worktree / "src").mkdir()
    assert _inspect(client, worktree / "src")["data"]["problem"]["code"] == "run_worktree"
    assert _add(client, worktree, 422)["error"]["code"] == "run_worktree"


def test_inspect_bare_and_empty_repos(client: TestClient, tmp_path: Path) -> None:
    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    assert _inspect(client, bare)["data"]["problem"]["code"] == "bare_repo"
    empty = init_repo(tmp_path / "empty", commit=False)
    data = _inspect(client, empty)["data"]
    assert data["problem"]["code"] == "no_commits"
    assert data["root"] == str(empty)
    assert _add(client, empty, 422)["error"]["code"] == "no_commits"
    assert _inspect(client, empty / ".git")["data"]["problem"]["code"] == "not_git"


def test_inspect_bad_paths(client: TestClient, tmp_path: Path) -> None:
    data = _inspect(client, tmp_path / "missing")["data"]
    assert data["problem"]["code"] == "path_not_found" and data["root"] is None
    assert _add(client, tmp_path / "missing", 404)["error"]["code"] == "path_not_found"
    file = write(tmp_path, "file.txt", "x")
    assert _inspect(client, file)["data"]["problem"]["code"] == "not_a_directory"
    assert _add(client, file, 422)["error"]["code"] == "not_a_directory"
    assert _inspect(client, "relative/path", 400)["error"]["code"] == "usage_error"
    assert _post(client, "/api/repos/inspect", {}, 400)["error"]["code"] == "usage_error"
    body = _post(client, "/api/repos/inspect", {"path": str(tmp_path), "x": 1}, 400)
    assert body["error"]["code"] == "usage_error"


def test_inspect_expands_home(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = tmp_path / "user"
    root = init_repo(fake_home / "code" / "proj")
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))  # what expanduser reads on Windows
    data = _inspect(client, "~/code/proj")["data"]
    assert data["root"] == str(root) and data["addable"] is True
    added = _add(client, "~/code/proj")["data"]["repo"]
    assert added["path"] == str(root)


def test_inspect_factory_states(client: TestClient, tmp_path: Path) -> None:
    sssf = init_repo(tmp_path / "sssf")
    write(sssf, SSSF_ROSTER, "name: sssf\n")
    commit_all(sssf)
    data = _inspect(client, sssf)["data"]
    assert (data["factory"]["state"], data["factory"]["action"]) == ("sssf", "onboard")

    pre = init_repo(tmp_path / "pre")
    write(pre, ".factory/config.yaml", "base: main\n")
    commit_all(pre)
    data = _inspect(client, pre)["data"]
    assert (data["factory"]["state"], data["factory"]["action"]) == ("pre_library", "onboard")
    assert data["factory"]["onboarding"] is None

    done = init_repo(tmp_path / "done")
    onboard(done)
    git(done, "remote", "add", "origin", "https://example.com/done.git")
    data = _inspect(client, done)["data"]
    assert (data["factory"]["state"], data["factory"]["action"]) == ("onboarded", "adopt")
    assert data["factory"]["onboarding"]["by"] == "Ada Tester"
    assert data["remote"] == {"name": "origin", "url": "https://example.com/done.git"}


def test_shared_trace_db(client: TestClient, tmp_path: Path, home: Path) -> None:
    a = init_repo(tmp_path / "a")
    b = init_repo(tmp_path / "b")
    _add(client, a)
    write(b, ".factory/local.yaml", f"trace_db: {a / '.factory' / 'trace.db'}\n")
    data = _inspect(client, b)["data"]
    assert data["problem"]["code"] == "trace_db_shared"
    assert data["problem"]["repo"] == "a"
    assert data["factory"]["state"] == "none"
    body = _add(client, b, 409)
    assert body["error"]["code"] == "trace_db_shared"
    assert [r["id"] for r in _registry(home)["repos"]] == ["a"]
    # The same repo again is not a conflict with itself.
    assert _add(client, a, 200)["data"]["created"] is False


def test_inspect_runs_only_read_git(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = init_repo(tmp_path / "proj")
    onboard(root)
    git(root, "remote", "add", "origin", "https://example.com/proj.git")
    (root / "sub").mkdir()
    other = init_repo(tmp_path / "other")
    _add(client, other)
    index = root / ".git" / "index"
    before = index.stat().st_mtime_ns
    calls: list[list[str]] = []
    real_run = subprocess.run

    def spy(argv: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(argv, list | tuple) and argv and argv[0] == "git":
            calls.append([str(a) for a in argv[1:]])
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)
    assert _inspect(client, root / "sub")["data"]["addable"] is True
    assert calls

    def subcommand(args: list[str]) -> list[str]:
        rest = list(args)
        while rest and rest[0] in ("-c", "-C"):
            rest = rest[2:]
        return rest

    for args in calls:
        rest = subcommand(args)
        assert rest[0] in ALLOWED_GIT, args
        if rest[0] == "remote":
            assert rest[1] == "get-url", args
    assert index.stat().st_mtime_ns == before


# -- add, list, delete -------------------------------------------------------------------


def _porcelain(root: Path) -> str:
    return git(root, "status", "--porcelain", "--ignored")


def test_add_installs_and_is_idempotent(client: TestClient, tmp_path: Path, home: Path) -> None:
    root = init_repo(tmp_path / "proj")
    (root / "sub").mkdir()
    write(root, "sub/keep.txt", "x")
    head = commit_all(root)
    body = _add(client, root / "sub")
    assert body["data"]["created"] is True
    repo = body["data"]["repo"]
    assert (repo["id"], repo["name"], repo["path"]) == ("proj", "proj", str(root))
    assert repo["status"] == "ok"
    install = body["data"]["install"]
    assert install["committed"] is True and install["pushed"] is False
    assert git(root, "rev-parse", "HEAD~1") == head
    assert install["commit"] == git(root, "rev-parse", "HEAD")
    assert ".factory/manifest.yaml" in {f["path"] for f in install["files"]}
    installed = _porcelain(root)
    again = _add(client, root, 200)["data"]
    assert again["created"] is False and again["repo"]["id"] == "proj"
    assert again["install"]["committed"] is False and again["install"]["files"] == []
    link = tmp_path / "link"
    symlink(link, root)
    assert _add(client, link, 200)["data"]["repo"]["id"] == "proj"
    assert len(_registry(home)["repos"]) == 1
    assert _porcelain(root) == installed
    assert git(root, "rev-parse", "HEAD") == install["commit"]


def test_refused_install_leaves_no_registry_entry(
    client: TestClient, tmp_path: Path, home: Path
) -> None:
    root = init_repo(tmp_path / "proj")
    write(root, ".factory/config.yaml", "base: main\n")  # uncommitted, would be overwritten
    body = _add(client, root, 409)
    assert body["error"]["code"] == "dirty_paths"
    assert _get(client, "/api/repos")["data"]["repos"] == []
    assert not _registry(home)["repos"]
    # an already registered repo stays registered when the install is refused
    register(client, root)
    assert _add(client, root, 409)["error"]["code"] == "dirty_paths"
    assert [r["id"] for r in _get(client, "/api/repos")["data"]["repos"]] == ["proj"]


def test_list_statuses(client: TestClient, tmp_path: Path) -> None:
    done = init_repo(tmp_path / "done")
    onboard(done)
    wt = init_repo(tmp_path / "wt")
    write(wt, ".factory/config.yaml", "base: main\n")
    dirty = init_repo(tmp_path / "dirty")
    write(dirty, ".factory/config.yaml", "base: main\n")
    commit_all(dirty)
    write(dirty, ".factory/config.yaml", "base: main\nmax_parallel_runs: 2\n")
    plain = init_repo(tmp_path / "plain")
    sssf = init_repo(tmp_path / "sssf")
    write(sssf, SSSF_ROSTER, "name: sssf\n")
    commit_all(sssf)
    gone = init_repo(tmp_path / "gone")
    nogit = init_repo(tmp_path / "nogit")
    for root in (done, wt, dirty, plain, sssf, gone, nogit):
        register(client, root)
    rmtree(gone)
    rmtree(nogit / ".git")
    data = _get(client, "/api/repos")["data"]
    by_id = {r["id"]: r for r in data["repos"]}
    assert {k: r["status"] for k, r in by_id.items()} == {
        "done": "ok",
        "wt": "uncommitted",
        "dirty": "uncommitted",
        "plain": "not_installed",
        "sssf": "not_installed",
        "gone": "missing",
        "nogit": "not_git",
    }
    assert by_id["done"]["factory"]["state"] == "onboarded"
    assert by_id["sssf"]["factory"]["state"] == "sssf"
    assert by_id["dirty"]["factory"]["state"] == "pre_library"
    assert by_id["gone"]["factory"] is None
    assert set(by_id["done"]) >= {"id", "name", "path", "added_at", "status", "factory"}


def _delete(client: TestClient, repo_id: str, payload: Any, status: int = 200) -> Any:
    return _check(client.request("DELETE", f"/api/repos/{repo_id}", json=payload), status)


def test_delete_without_uninstall_removes_only_the_entry(
    client: TestClient, tmp_path: Path, home: Path
) -> None:
    root = init_repo(tmp_path / "proj")
    _add(client, root)
    before = _porcelain(root)
    head = git(root, "rev-parse", "HEAD")
    body = _delete(client, "proj", {"uninstall": False})
    assert body["data"]["removed"]["path"] == str(root)
    assert body["data"]["uninstall"] is None
    assert _registry(home)["repos"] == []
    assert root.is_dir() and _porcelain(root) == before
    assert git(root, "rev-parse", "HEAD") == head
    assert _check(client.delete("/api/repos/proj"), 404)["error"]["code"] == "unknown_repo"
    assert _get(client, "/api/repos/proj/backlog", 404)["error"]["code"] == "unknown_repo"


def test_delete_uninstalls_and_exports(tmp_path: Path) -> None:
    from aifactory.library import store
    from aifactory.web.library import environment

    # the install and export use the process HAIFA_HOME; the dashboard home is the same here
    home = Path(os.environ["HAIFA_HOME"])
    client = multi_client(home, tmp_path)
    bare = tmp_path / "library.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    lib = store.init_library("team", environment(home), remote=str(bare))
    root = init_repo(tmp_path / "proj")
    _add(client, root)
    prompt = root / ".factory/prompts/builder/system.md"
    prompt.write_text(prompt.read_text(encoding="utf-8") + "Repo rule.\n", encoding="utf-8")
    commit_all(root, "own builder")
    removal = _get(client, "/api/repos/proj/removal")["data"]
    own = {(i["type"], i["name"]) for i in removal["own_items"]}
    assert ("agent", "builder") in own
    assert ".factory/agents.yaml" in {f["path"] for f in removal["files"]}
    payload = {"export": [{"type": "agent", "name": "builder"}]}
    body = _delete(client, "proj", payload)
    assert body["data"]["uninstall"]["commit"] == git(root, "rev-parse", "HEAD")
    assert not (root / ".factory").exists()
    assert not git(root, "ls-files", ".factory")
    assert _registry(home)["repos"] == []
    assert _get(client, "/api/repos/proj/removal", 404)["error"]["code"] == "unknown_repo"
    assert body["data"]["uninstall"]["exported"] == [{"type": "agent", "name": "builder"}]
    library_root = Path(lib.plan.library)
    exported = (library_root / "agents/builder/system.md").read_text(encoding="utf-8")
    assert exported.endswith("Repo rule.\n")


def test_delete_body_validation(client: TestClient, tmp_path: Path) -> None:
    root = init_repo(tmp_path / "proj")
    register(client, root)
    for payload in ({"uninstall": "yes"}, {"export": ["agent/x"]}, {"export": [{"type": 1}]}):
        assert _delete(client, "proj", payload, 400)["error"]["code"] == "usage_error"
    assert [r["id"] for r in _get(client, "/api/repos")["data"]["repos"]] == ["proj"]


def test_unknown_and_missing_repo(client: TestClient, tmp_path: Path) -> None:
    assert _get(client, "/api/repos/nope/runs", 404)["error"]["code"] == "unknown_repo"
    root = make_backlog_repo(tmp_path / "proj")
    git(root, "branch", "-M", "main")
    _add(client, root)
    assert _get(client, "/api/repos/proj/nothing-here", 404)["error"]["code"] == "not_found"
    assert _get(client, "/api/repos/proj/health", 404)["error"]["code"] == "not_found"
    _get(client, "/api/repos/proj/backlog")
    rmtree(root)
    body = _get(client, "/api/repos/proj/runs", 404)
    assert body["error"]["code"] == "repo_missing"


def test_corrupt_registry_keeps_serving(client: TestClient, tmp_path: Path, home: Path) -> None:
    root = init_repo(tmp_path / "proj")
    _add(client, root)
    (home / "dashboard.yaml").write_text("repos: [\n", encoding="utf-8", newline="\n")
    body = _get(client, "/api/repos")
    assert [r["id"] for r in body["data"]["repos"]] == ["proj"]
    assert "last valid registry" in body["warnings"][0]
    other = init_repo(tmp_path / "other")
    assert _add(client, other, 409)["error"]["code"] == "registry_invalid"
    assert (home / "dashboard.yaml").read_text(encoding="utf-8") == "repos: [\n"


# -- isolation of two repos --------------------------------------------------------------


def _two_repos(client: TestClient, tmp_path: Path) -> tuple[Path, Path]:
    a = make_backlog_repo(tmp_path / "a", with_trace=True)
    git(a, "branch", "-M", "main")
    b = make_backlog_repo(tmp_path / "b", levels=["area", "task"])
    git(b, "branch", "-M", "main")
    register(client, a)
    register(client, b)
    return a, b


def test_two_repos_are_isolated(client: TestClient, tmp_path: Path) -> None:
    a, b = _two_repos(client, tmp_path)
    tasks_a = {t["id"] for t in _get(client, "/api/repos/a/backlog")["data"]["tasks"]}
    tasks_b = {t["id"] for t in _get(client, "/api/repos/b/backlog")["data"]["tasks"]}
    assert "M01-S01-T01" in tasks_a and "A1-T01" not in tasks_a
    assert tasks_b == {"A1-T01", "A1-T02"}
    runs_a = _get(client, "/api/repos/a/runs")["data"]["runs"]
    runs_b = _get(client, "/api/repos/b/runs")["data"]["runs"]
    assert {r["run_id"] for r in runs_a} == {"r-b2", "r-b3"}
    assert runs_b == []

    _post(client, "/api/repos/a/settings", {"shared": {"merge_strategy": "merge"}})
    assert "merge_strategy: merge" in (a / ".factory" / "config.yaml").read_text(encoding="utf-8")
    assert "merge_strategy: merge" not in (b / ".factory" / "config.yaml").read_text(
        encoding="utf-8"
    )
    shared_b = _get(client, "/api/repos/b/settings")["data"]
    assert shared_b["shared"]["merge_strategy"] == "squash"

    added = _post(client, "/api/repos/b/backlog/tasks", {"step": "A1", "title": "Nový"})["data"]
    assert (b / added["path"]).is_file()
    assert not (a / added["path"]).exists()
    assert added["task"]["id"].startswith("A1-")
    status_a = _get(client, "/api/repos/a/backlog/status")["data"]
    assert status_a["changes"] == []


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
    return port


def _read_event(response: http.client.HTTPResponse, kind: str, deadline: float) -> Any:
    current: str | None = None
    while time.monotonic() < deadline:
        line = response.fp.readline().decode("utf-8").rstrip("\r\n")
        if line.startswith("event: "):
            current = line[len("event: ") :]
        elif line.startswith("data: ") and current == kind:
            return json.loads(line[len("data: ") :])
        elif line == "":
            current = None
    raise AssertionError(f"no {kind} event in time")


def _append(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


@pytest.mark.xdist_group("live")
def test_live_events_per_repo(tmp_path: Path, home: Path) -> None:
    setup = multi_client(home, tmp_path)
    a, b = _two_repos(setup, tmp_path)
    port = _free_port()
    app = create_multi_app(home=home, static_dir=tmp_path / "nostatic", live_interval=0.1)
    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=port, log_level="warning", timeout_graceful_shutdown=1
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert time.monotonic() < deadline, "server did not start"
            time.sleep(0.02)
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/api/repos/a/live", headers={"Host": "127.0.0.1"})
        response = conn.getresponse()
        assert response.status == 200
        assert _read_event(response, "hello", time.monotonic() + 5)["interval"] == 0.1
        time.sleep(0.3)  # the watcher takes its baseline
        b_task = "backlog/A1/A1-T01-first.md"
        _append(b / b_task, "\nJen B.\n")
        a_task = "backlog/M01-core/S01-model/M01-S01-T01-schema.md"
        time.sleep(0.5)  # B's change would have been reported by now
        _append(a / a_task, "\nJen A.\n")
        event = _read_event(response, "files", time.monotonic() + 5)
        assert event["paths"] == [a_task]
        # Removing the repo closes its hub, which ends the stream.
        remover = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        remover.request(
            "DELETE",
            "/api/repos/a",
            body=json.dumps({"uninstall": False}),
            headers={"Host": "127.0.0.1", "Content-Type": "application/json"},
        )
        assert remover.getresponse().status == 200
        remover.close()
        end = time.monotonic() + 5
        while time.monotonic() < end:
            if response.fp.readline() in (b"", b"0\r\n"):  # closed or the last chunk
                break
        else:
            raise AssertionError("the stream did not end")
        conn.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
    assert not thread.is_alive()


# -- write guard (M1) and stale code ------------------------------------------------------


def _writes(root: Path) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        ("POST", "/api/repos", {"path": str(root)}),
        ("POST", "/api/repos/inspect", {"path": str(root)}),
        ("DELETE", "/api/repos/proj", {}),
        ("POST", "/api/dashboard/settings", {"port": 4800}),
        ("POST", "/api/repos/proj/backlog/tasks", {"step": "M01-S01", "title": "X"}),
    ]


def test_write_guard_on_new_endpoints(client: TestClient, tmp_path: Path, home: Path) -> None:
    root = make_backlog_repo(tmp_path / "proj")
    git(root, "branch", "-M", "main")
    _add(client, root)
    registry_before = (home / "dashboard.yaml").read_text(encoding="utf-8")
    status_before = _porcelain(root)
    for method, url, payload in _writes(root):
        content = json.dumps(payload) if payload else None
        for headers, code, status in (
            ({"Origin": "http://evil.example"}, "cross_origin", 403),
            ({"Sec-Fetch-Site": "cross-site"}, "cross_origin", 403),
        ):
            sent = {**headers, "Content-Type": "application/json"}
            response = client.request(method, url, content=content, headers=sent)
            assert response.status_code == status, (method, url)
            assert response.json()["error"]["code"] == code
        response = client.request(
            method, url, content="x=1", headers={"Content-Type": "text/plain"}
        )
        assert response.status_code == 415, (method, url)
        assert response.json()["error"]["code"] == "unsupported_media_type"
    assert (home / "dashboard.yaml").read_text(encoding="utf-8") == registry_before
    assert _porcelain(root) == status_before


def test_stale_code_blocks_new_writes_but_not_restart(tmp_path: Path, home: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    (package / "mod.py").write_text("x = 1\n", encoding="utf-8", newline="\n")
    restarts: list[str] = []
    client = multi_client(
        home,
        tmp_path,
        code_watch=CodeWatch(package, ttl=0.0),
        restart=lambda: restarts.append("restart"),
    )
    root = init_repo(tmp_path / "proj")
    _add(client, root)
    # code and restart are global only, not per repository
    assert client.get("/api/repos/proj/code").status_code == 404
    (package / "mod.py").write_text("x = 22\n", encoding="utf-8", newline="\n")
    other = init_repo(tmp_path / "other")
    response = client.post("/api/repos", json={"path": str(other)})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "stale_code"
    assert client.post("/api/repos/proj/restart").status_code == 409
    assert _post(client, "/api/restart", None)["data"] == {"restarting": True}
    assert restarts == ["restart"]
    assert _get(client, "/api/repos")["ok"] is True


def test_code_and_restart_need_no_repository(tmp_path: Path, home: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    (package / "mod.py").write_text("x = 1\n", encoding="utf-8", newline="\n")
    restarts: list[str] = []
    client = multi_client(
        home,
        tmp_path,
        code_watch=CodeWatch(package, ttl=0.0),
        restart=lambda: restarts.append("restart"),
    )
    assert _get(client, "/api/code")["data"]["stale"] is False
    (package / "mod.py").write_text("x = 22\n", encoding="utf-8", newline="\n")
    assert _get(client, "/api/code")["data"]["stale"] is True
    assert _post(client, "/api/restart", None)["data"] == {"restarting": True}
    assert restarts == ["restart"]


def test_single_repo_app_has_no_registry_endpoints(tmp_path: Path) -> None:
    from aifactory.web import create_app

    root = init_repo(tmp_path / "proj")
    client = TestClient(create_app(root, static_dir=tmp_path / "nostatic"), base_url=BASE)
    assert _get(client, "/api/health")["data"]["repo"] == str(root)
    assert _get(client, "/api/repos", 404)["error"]["code"] == "not_found"


def test_live_hub_closes_twice(tmp_path: Path) -> None:
    from aifactory.web.live import LiveHub

    async def scenario() -> None:
        hub = LiveHub(init_repo(tmp_path / "proj"), interval=0.05)
        await hub.aclose()  # never subscribed
        queue = await hub.subscribe()
        await hub.aclose()
        await hub.aclose()
        assert await queue.get() is None

    asyncio.run(scenario())
