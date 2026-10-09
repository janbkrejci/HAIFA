"""Remote service acceptance using two independent checkout paths, no external services."""

from __future__ import annotations

import os
import sqlite3
import threading
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from aifactory import database
from aifactory.backlog import edit_task, load_backlog
from aifactory.backlog.edit import TaskEditError
from aifactory.config import ConfigError
from aifactory.config.settings import LocalSettings
from aifactory.database.server import DatabaseServer
from aifactory.run.errors import TaskRunError
from aifactory.run.store import TaskRunRow, TaskRunStore
from aifactory.web.live import LiveWatcher
from aifactory.web.overview import _open_ro

TASK = "backlog/P/S/P-S-T.md"


@pytest.fixture
def service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setenv("HAIFA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("HAIFA_DATABASE_URL", raising=False)
    with DatabaseServer(("127.0.0.1", 0), tmp_path / "server") as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join(timeout=5)


def checkout(root: Path) -> Path:
    (root / ".git").mkdir(parents=True)
    files = {
        ".factory/config.yaml": "{}\n",
        "backlog/P/index.md": "---\nid: P\ntitle: Project\n---\n",
        "backlog/P/S/index.md": "---\nid: P-S\ntitle: Step\n---\n",
        TASK: "---\nid: P-S-T\ntitle: Task\nstatus: todo\n---\nBody\n",
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


@pytest.fixture
def repos(service: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    monkeypatch.setenv("HAIFA_DATABASE_URL", service)

    def remote(root: Path, *args: str) -> str | None:
        if args[:2] == ("remote", "get-url"):
            return (
                "git@example.org:Team/Repo.git"
                if root.name == "a"
                else "https://example.org/Team/Repo"
            )
        return None

    monkeypatch.setattr("aifactory.run.gitops.read_git", remote)
    return checkout(tmp_path / "a"), checkout(tmp_path / "b")


@pytest.mark.parametrize(
    "remote",
    [
        "git@EXAMPLE.org:Team/Repo.git",
        "ssh://git@example.org/Team/Repo.git",
        "https://example.org/Team/Repo/",
    ],
)
def test_remote_identity(remote: str) -> None:
    assert database.canonical_remote(remote) == "example.org/Team/Repo"
    assert (
        database.canonical_remote("ssh://git@example.org:2222/Team/Repo.git")
        != "example.org/Team/Repo"
    )


def test_missing_remote_fails_closed(
    service: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HAIFA_DATABASE_URL", service)
    monkeypatch.setattr("aifactory.run.gitops.read_git", lambda *args: None)
    with pytest.raises(ConfigError, match="requires Git remote"):
        LocalSettings().trace_db_path(checkout(tmp_path / "repo"))


def test_native_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAIFA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("HAIFA_DATABASE_URL", raising=False)
    path = LocalSettings().trace_db_path(tmp_path)
    path.parent.mkdir(parents=True)
    conn = database.connect(path)
    assert isinstance(conn, sqlite3.Connection)
    conn.close()


def test_transactions_rows_and_live_data_version(repos: tuple[Path, Path]) -> None:
    a, b = (LocalSettings().trace_db_path(root) for root in repos)
    writer = database.connect(a, isolation_level=None)
    reader = database.connect(b, isolation_level=None)
    try:
        writer.execute("CREATE TABLE values_test (id INTEGER PRIMARY KEY, text TEXT)")
        version = reader.execute("PRAGMA data_version").fetchone()[0]
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("INSERT INTO values_test VALUES (?, ?)", (1, "žluťoučký"))
        assert reader.execute("SELECT * FROM values_test").fetchall() == []
        writer.execute("COMMIT")
        assert reader.execute("PRAGMA data_version").fetchone()[0] != version
        reader.row_factory = sqlite3.Row
        row = reader.execute("SELECT * FROM values_test").fetchone()
        assert dict(row) == {"id": 1, "text": "žluťoučký"}
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("DELETE FROM values_test")
        writer.rollback()
        assert len(reader.execute("SELECT * FROM values_test").fetchall()) == 1
        with pytest.raises(sqlite3.IntegrityError):
            writer.execute("INSERT INTO values_test VALUES (1, 'duplicate')")
        ro = _open_ro(b)
        assert ro is not None
        try:
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                ro.execute("DELETE FROM values_test")
        finally:
            ro.close()
    finally:
        reader.close()
        writer.close()


def row(id: str) -> TaskRunRow:
    return TaskRunRow(
        id,
        "P-S-T",
        "factory/task",
        "/other-machine/worktree",
        "main",
        "abc",
        None,
        "running",
        "2026-10-07T12:00:00Z",
        pid=os.getpid(),
    )


def test_foreign_runs_are_not_reaped_or_signalled(
    repos: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    a, b = (TaskRunStore(LocalSettings().trace_db_path(root)) for root in repos)
    try:
        a.claim(row("first"))
        monkeypatch.setattr(database, "MACHINE", "another-machine")
        monkeypatch.setattr("aifactory.run.store._alive", lambda pid: False)
        assert b.live_runs()[0].state == "running"
        with pytest.raises(TaskRunError, match="already running"):
            b.claim(replace(row("second"), pid=1234))
        from aifactory.run.pause import pause_run
        from aifactory.run.stop import stop_run

        assert pause_run(repos[1], "first").pause == "pausing"
        with pytest.raises(TaskRunError, match="machine that started"):
            stop_run(repos[1], "first")
    finally:
        b.close()
        a.close()


def test_backlog_edits_and_conflicts(repos: tuple[Path, Path]) -> None:
    a, b = repos
    load_backlog(a)
    load_backlog(b)
    edit_task(a, "P-S-T", title="Shared title")
    assert load_backlog(b).by_id["P-S-T"].title == "Shared title"
    assert "Shared title" in (b / TASK).read_text()
    edit_task(a, "P-S-T", title="Remote edit")
    (b / TASK).write_text((b / TASK).read_text().replace("Shared title", "Local edit"))
    with pytest.raises(TaskEditError, match="conflict"):
        load_backlog(b)
    assert "Local edit" in (b / TASK).read_text()
    assert load_backlog(a).by_id["P-S-T"].title == "Remote edit"


def test_live_watcher_observes_remote_backlog_and_runs(repos: tuple[Path, Path]) -> None:
    a, b = repos
    load_backlog(a)
    load_backlog(b)
    writer = TaskRunStore(LocalSettings().trace_db_path(a))
    watcher = LiveWatcher(b)
    try:
        watcher.poll()
        writer.claim(row("first"))
        assert any(event.kind == "trace" for event in watcher.poll())
        edit_task(a, "P-S-T", title="Live title")
        events = watcher.poll() + watcher.poll()
        assert any(event.kind == "files" and TASK in event.data["paths"] for event in events)
    finally:
        watcher.close()
        writer.close()


def test_global_configuration_and_local_override(
    service: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "database.yaml").write_text(f"url: {service}\n")
    root = checkout(tmp_path / "repo")
    monkeypatch.setattr(
        "aifactory.run.gitops.read_git", lambda *args: "https://example.org/repo.git"
    )
    path = LocalSettings().trace_db_path(root)
    assert database.is_remote(path)
    assert database._ENDPOINTS[str(path)][0] == service
    override = LocalSettings(database_url="http://localhost:1234").trace_db_path(root)
    assert database._ENDPOINTS[str(override)][0] == "http://localhost:1234"
    (home / "database.yaml").write_text("url: 123\n")
    with pytest.raises(ConfigError, match="must be a string"):
        LocalSettings().trace_db_path(root)


def test_project_isolation(repos: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    a = database.connect(LocalSettings().trace_db_path(repos[0]), isolation_level=None)
    monkeypatch.setattr(
        "aifactory.run.gitops.read_git", lambda *args: "https://example.org/other.git"
    )
    b = database.connect(LocalSettings().trace_db_path(repos[1]), isolation_level=None)
    try:
        a.execute("CREATE TABLE private_project (id TEXT)")
        assert (
            b.execute("SELECT name FROM sqlite_master WHERE name = 'private_project'").fetchall()
            == []
        )
    finally:
        a.close()
        b.close()


def test_concurrent_claim_has_one_winner(repos: tuple[Path, Path]) -> None:
    stores = [TaskRunStore(LocalSettings().trace_db_path(root)) for root in repos]
    barrier = threading.Barrier(2)
    results: list[str] = []

    def claim(store: TaskRunStore, id: str) -> None:
        barrier.wait(timeout=5)
        try:
            store.claim(row(id))
            results.append("claimed")
        except TaskRunError as exc:
            results.append(exc.code)

    threads = [
        threading.Thread(target=claim, args=(store, str(index)))
        for index, store in enumerate(stores)
    ]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
            assert not thread.is_alive()
        assert sorted(results) == ["already_running", "claimed"]
    finally:
        for store in stores:
            store.close()


def test_expired_idle_connection_reconnects_but_transaction_is_not_replayed(tmp_path: Path) -> None:
    with DatabaseServer(("127.0.0.1", 0), tmp_path / "server") as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        conn = database.RemoteConnection(
            f"http://127.0.0.1:{server.server_port}", "a" * 64, {"isolation_level": None}
        )
        try:
            conn.execute("CREATE TABLE sample (id INTEGER)")
            old_session = conn.session
            server.sessions[old_session].used -= 121
            server.service_actions()
            conn.execute("INSERT INTO sample VALUES (1)")
            assert conn.session != old_session
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT INTO sample VALUES (2)")
            server.sessions[conn.session].used -= 121
            server.service_actions()
            with pytest.raises(sqlite3.OperationalError, match="expired"):
                conn.execute("COMMIT")
            check = database.RemoteConnection(conn.url, "a" * 64, {"isolation_level": None})
            try:
                assert check.execute("SELECT id FROM sample").fetchall() == [(1,)]
            finally:
                check.close()
        finally:
            conn.close()
            server.shutdown()
            thread.join(timeout=5)


def test_engine_trace_is_shared(repos: tuple[Path, Path], tmp_path: Path) -> None:
    from aifactory.engine.tracer import Tracer

    a, b = (LocalSettings().trace_db_path(root) for root in repos)
    tracer = Tracer(str(a), tmp_path / "events.jsonl")
    reader = database.connect(b, isolation_level=None)
    try:
        tracer.session_start("session", "engineer")
        tracer.session_request("session", "Shared request")
        tracer.session_add_usage("session", 120, 0.05)
        assert reader.execute(
            "SELECT request, total_tokens FROM sessions WHERE adw_id = ?", ("session",)
        ).fetchone() == ("Shared request", 120)
    finally:
        tracer.conn.close()
        reader.close()


def test_first_join_preserves_dirty_backlog(
    repos: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    a, b = repos
    load_backlog(a)
    edit_task(a, "P-S-T", title="Team title")
    (b / TASK).write_text((b / TASK).read_text().replace("title: Task", "title: My unsaved title"))
    from aifactory.run import gitops

    original = gitops.read_git

    def read_git(root: Path, *args: str) -> str | None:
        if args and args[0] == "status":
            return f" M {TASK}"
        result: str | None = original(root, *args)
        return result

    monkeypatch.setattr("aifactory.run.gitops.read_git", read_git)
    with pytest.raises(TaskEditError, match="before joining"):
        load_backlog(b)
    assert "My unsaved title" in (b / TASK).read_text()


def test_stale_validated_write_is_rejected(repos: tuple[Path, Path]) -> None:
    from aifactory.database.backlog import publish

    a, b = repos
    load_backlog(a)
    load_backlog(b)
    edit_task(a, "P-S-T", title="Team title")
    with pytest.raises(TaskEditError, match="changed remotely"):
        publish(b, {TASK: (b / TASK).read_text().replace("title: Task", "title: Stale title")})
    assert load_backlog(a).by_id["P-S-T"].title == "Team title"


def test_network_failure_does_not_create_local_database(
    repos: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from urllib.error import URLError

    path = LocalSettings().trace_db_path(repos[0])

    def unavailable(*args: object, **kwargs: object) -> None:
        raise URLError("offline")

    monkeypatch.setattr(database, "urlopen", unavailable)
    with pytest.raises(sqlite3.OperationalError, match="shared database unavailable"):
        database.connect(path)
    assert not path.exists()
