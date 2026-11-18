"""Last-HAIFA bridge on fake hosting and isolated data/tools; never touches live uv."""

from __future__ import annotations

import errno
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.testclient import TestClient

from aifactory import __version__, cli, migration_guard, oscompat, transition, upgrade
from aifactory.library.remote import library_min_factory_version
from aifactory.upgrade import UpgradeError, run_upgrade
from aifactory.web import create_multi_app, updates
from test_upgrade import make_bundle
from test_upgrade import uv_log as uv_log


@pytest.fixture
def hosting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    old = make_bundle(tmp_path / "old", version=__version__)
    new = make_bundle(tmp_path / "new", version="1.0.1", brand="giro")
    old_url = f"https://github.com/janbkrejci/HAIFA/releases/download/v{__version__}/haifa-{__version__}.zip"
    new_url = "https://github.com/janbkrejci/GIRO/releases/download/v1.0.1/giro-1.0.1.zip"
    state: dict[str, Any] = {
        "calls": [],
        "old": old,
        "new": new,
        "new_url": new_url,
        "old_url": old_url,
    }

    def urlopen(request: Any, **kwargs: Any) -> io.BytesIO:
        url = request.full_url if hasattr(request, "full_url") else request
        state["calls"].append(url)
        if url == old_url:
            return io.BytesIO(old.read_bytes())
        if url == new_url:
            return io.BytesIO(new.read_bytes())
        if url == "https://api.github.com/repos/janbkrejci/GIRO/releases/latest":
            return io.BytesIO(
                json.dumps(
                    {
                        "tag_name": "v1.0.1",
                        "assets": [{"name": "giro-1.0.1.zip", "browser_download_url": new_url}],
                    }
                ).encode()
            )
        if url == "https://api.github.com/repos/janbkrejci/HAIFA/releases/latest":
            return io.BytesIO(
                json.dumps(
                    {
                        "tag_name": f"v{__version__}",
                        "assets": [{"name": old.name, "browser_download_url": old_url}],
                    }
                ).encode()
            )
        raise AssertionError(f"Unexpected live URL: {url}")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(upgrade, "editable_install", lambda: False)
    monkeypatch.setattr(updates, "editable_install", lambda: False)
    monkeypatch.setattr(upgrade, "needs_handoff", lambda: False)
    return state


@pytest.fixture
def prepared_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "haifa"
    home.mkdir(mode=0o700)
    (home / "env").write_text("SECRET=preserved\n")
    (home / "env").chmod(0o600)
    (home / "library/.git").mkdir(parents=True)
    (home / "library/.git/HEAD").write_text("local-library-head")
    (home / "library/untracked").write_text("customizations")
    (home / "library/notes").write_text("ordinary document, not SQLite")
    for suffix in ("-wal", "-shm"):
        (home / f"library/notes{suffix}").write_bytes(b"ordinary user file")
        folder = home / f"library/folder{suffix}"
        folder.mkdir()
        (folder / "contents").write_bytes(b"ordinary user directory")
    with closing(sqlite3.connect(home / "history.db")) as connection:
        connection.execute("CREATE TABLE history(value TEXT)")
        connection.execute("INSERT INTO history VALUES ('preserved')")
        connection.commit()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("HAIFA_HOME", str(home))
    monkeypatch.delenv("HAIFA_LIBRARY", raising=False)
    monkeypatch.delenv("HAIFA_DATABASE_URL", raising=False)
    tool = tmp_path / "tool"
    (tool / "bin").mkdir(parents=True)
    (tool / "bin/python").write_text("fake interpreter: never executed")
    monkeypatch.setattr(sys, "prefix", str(tool))
    monkeypatch.setattr(sys, "executable", str(tool / "bin/python"))
    return home


def _prepare(home: Path, hosting: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(subprocess, "Popen", _fake_worker)
    return transition.prepare(home, hosting["new_url"], __version__, "1.0.1")


def test_dashboard_click_downloads_giro_and_verified_rollback_only_after_click(
    prepared_home: Path,
    hosting: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = updates.Updates(home=prepared_home, fetch=updates.latest_release)
    app = create_multi_app(home=prepared_home)
    app.state.updates = source
    monkeypatch.setattr(subprocess, "Popen", _fake_worker)
    monkeypatch.setattr(
        source,
        "install",
        lambda restart: updates.Updates.install(source, restart, leave=lambda: None),
    )
    with TestClient(app, base_url="http://127.0.0.1:4700") as client:
        client.get("/api/updates")
        assert hosting["calls"] == ["https://api.github.com/repos/janbkrejci/HAIFA/releases/latest"]
        assert not list(prepared_home.parent.glob("*.pre-giro-*"))
        assert client.post("/api/updates/migrate").status_code == 202
        assert hosting["new_url"] in hosting["calls"]
        assert hosting["old_url"] in hosting["calls"]
        assert client.post("/api/updates/migrate").json()["error"]["code"] == "update_busy"
    manifest = json.loads((prepared_home / migration_guard.MARKER).read_text())
    assert manifest["state"] == "prepared"
    assert Path(manifest["backup"], "tool/bin/python").is_file()
    assert (prepared_home / "library/untracked").read_text() == "customizations"


@pytest.mark.parametrize(
    "failure",
    [
        "checksum",
        "missing_old",
        "disk",
        "spawn",
        "existing_target",
        "shared_db",
        "corrupt_db",
        "minimum",
    ],
)
def test_preparation_failures_preserve_haifa_and_can_retry(
    prepared_home: Path,
    hosting: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    home = prepared_home
    monkeypatch.setattr(subprocess, "Popen", _fake_worker)
    original = hosting["new"].read_bytes()
    original_copytree = shutil.copytree
    original_minimum = library_min_factory_version
    if failure == "checksum":
        hosting["new"].write_bytes(
            make_bundle(
                home.parent / "bad", version="1.0.1", brand="giro", tamper="constraints.txt"
            ).read_bytes()
        )
    elif failure == "missing_old":
        hosting["old"].unlink()
    elif failure == "disk":
        monkeypatch.setattr(
            shutil,
            "copytree",
            lambda *a, **kw: (_ for _ in ()).throw(OSError("no space")),
        )
    elif failure == "spawn":
        monkeypatch.setattr(
            subprocess, "Popen", lambda *a, **kw: (_ for _ in ()).throw(OSError("cannot spawn"))
        )
    elif failure == "existing_target":
        monkeypatch.delenv("HAIFA_HOME")
        (home.parent / "giro").mkdir()
    elif failure == "shared_db":
        monkeypatch.setenv("HAIFA_DATABASE_URL", "https://database.invalid")
    elif failure == "minimum":
        monkeypatch.setattr(upgrade, "library_min_factory_version", lambda env=None: "2.0.0")
    else:
        # Corruption is caught by the backup worker, after preparation.
        (home / "broken.db").write_bytes(b"invalid sqlite")
        with pytest.raises(UpgradeError, match="Invalid SQLite"):
            transition._copy(home, home.parent / "corrupt-backup")
        return
    with pytest.raises((UpgradeError, OSError)):
        transition.prepare(home, hosting["new_url"], __version__, "1.0.1")
    assert not (home / migration_guard.MARKER).exists()
    assert (home / "env").read_text() == "SECRET=preserved\n"
    assert (home / "library/untracked").read_text() == "customizations"
    hosting["new"].write_bytes(original)
    if failure == "missing_old":
        make_bundle(hosting["old"].parent, version=__version__)
    monkeypatch.setattr(shutil, "copytree", original_copytree)
    monkeypatch.setattr(upgrade, "library_min_factory_version", original_minimum)
    monkeypatch.setattr(subprocess, "Popen", _fake_worker)
    monkeypatch.setenv("HAIFA_HOME", str(home))
    monkeypatch.delenv("HAIFA_DATABASE_URL", raising=False)
    assert transition.prepare(home, hosting["new_url"], __version__, "1.0.1").is_file()


@pytest.mark.parametrize(
    ("default_home", "failure", "external_error"),
    [
        (default, failure, None)
        for default in (False, True)
        for failure in (None, "install", "restart", "both_installs")
    ]
    + [
        (True, "install", "EXDEV"),
        (True, "restart", "EXDEV"),
        (False, "install", "WinError17"),
        (False, "restart", "WinError17"),
    ],
)
def test_worker_installs_with_existing_updater_validates_and_rolls_back(
    # Build fake executables with the real interpreter before prepared_home
    # redirects sys.executable to the retained-tool fixture.
    uv_log: Path,
    prepared_home: Path,
    hosting: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    failure: str | None,
    default_home: bool,
    external_error: str | None,
) -> None:
    if default_home:
        monkeypatch.delenv("HAIFA_HOME")
    external = (prepared_home.parent / "external-library").resolve()
    if external_error:
        external.mkdir()
        (external / "customization").write_text("original external data")
        monkeypatch.setenv("HAIFA_LIBRARY", str(external))
    plan_file = _prepare(prepared_home, hosting, monkeypatch)
    plan = json.loads(plan_file.read_text())
    backup = Path(plan["backup"])
    cross_device_moves: list[Path] = []
    if external_error:
        real_rename = os.rename
        real_replace = os.replace

        def cross_device(source: str | Path, destination: str | Path) -> bool:
            if Path(source) != external or not Path(destination).is_relative_to(backup):
                return False
            cross_device_moves.append(Path(destination))
            error = OSError(errno.EXDEV, "simulated cross-device move")
            if external_error == "WinError17":
                error = OSError(errno.EACCES, "simulated different disk drive")
                monkeypatch.setattr(error, "winerror", 17, raising=False)
            raise error

        def rename(source: str | Path, destination: str | Path, **kwargs: Any) -> None:
            if not cross_device(source, destination):
                real_rename(source, destination, **kwargs)

        def replace(source: str | Path, destination: str | Path, **kwargs: Any) -> None:
            if not cross_device(source, destination):
                real_replace(source, destination, **kwargs)

        monkeypatch.setattr(os, "rename", rename)
        monkeypatch.setattr(os, "replace", replace)
    monkeypatch.setattr(oscompat, "alive", lambda pid: False)
    events: list[str] = []

    class Child:
        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            events.append("terminate failed GIRO")

        def wait(self, **kw: Any) -> int:
            return 0

    def spawn(argv: list[str], **kw: Any) -> Any:
        if argv[0] == "powershell":
            return REAL_POPEN(argv, **kw)
        events.append("restart")
        assert kw["env"]["HAIFA_HOME"] == kw["env"]["GIRO_HOME"]
        return Child()

    monkeypatch.setattr(subprocess, "Popen", spawn)
    real_upgrade = run_upgrade
    if failure == "both_installs":
        monkeypatch.setenv("UV_EXIT", "1")
    installs: list[str] = []

    def install(source: str, **kw: Any) -> Any:
        installs.append(kw["expected_version"])
        assert kw["refresh"] is False and kw["handoff"] is False
        if external_error and kw["expected_version"] == "1.0.1":
            (external / "customization").write_text("failed GIRO external data")
            (external / "giro-created").write_text("keep in failed snapshot")
        if failure == "install" and kw["expected_version"] == "1.0.1":
            raise UpgradeError("upgrade_failed", "fake uv failed")
        # Popen is stubbed only for dashboards, run the real updater through its
        # isolated fake uv by temporarily restoring the real Popen.
        with monkeypatch.context() as patch:
            patch.setattr(subprocess, "Popen", REAL_POPEN)
            return real_upgrade(source, **kw)

    monkeypatch.setattr(transition, "run_upgrade", install)
    monkeypatch.setattr(
        transition,
        "_health",
        lambda plan, app, version, home: app == "haifa-dashboard" or failure != "restart",
    )
    if failure == "restart":
        ticks = iter([0.0, 0.0, 1000.0, 1001.0])
        monkeypatch.setattr(time, "monotonic", lambda: next(ticks))
    transition.execute(plan_file)
    active = prepared_home.parent / "giro" if default_home and not failure else prepared_home
    assert (active / "library/untracked").read_text() == "customizations"
    assert (prepared_home / "library/.git/HEAD").read_text() == "local-library-head"
    assert (prepared_home / "library/untracked").read_text() == "customizations"
    saved_home = backup / "data" / str(plan["paths"].index(str(prepared_home.resolve())))
    for root in (active, saved_home):
        for suffix in ("-wal", "-shm"):
            assert (root / f"library/notes{suffix}").read_bytes() == b"ordinary user file"
            assert (root / f"library/folder{suffix}/contents").read_bytes() == (
                b"ordinary user directory"
            )
    with sqlite3.connect(prepared_home / "history.db") as connection:
        assert connection.execute("SELECT value FROM history").fetchone() == ("preserved",)
    if failure:
        assert installs == ["1.0.1", __version__]
        assert not (prepared_home / migration_guard.MARKER).exists()
        assert (prepared_home / transition.ERROR_FILE).is_file()
        assert events[-1] == "restart"
        if external_error:
            assert len(cross_device_moves) == 1
            assert (external / "customization").read_text() == "original external data"
            assert not (external / "giro-created").exists()
            retained = cross_device_moves[0]
            assert (retained / "customization").read_text() == "failed GIRO external data"
            assert (retained / "giro-created").read_text() == "keep in failed snapshot"
    else:
        assert installs == ["1.0.1"] and events == ["restart"]
        if default_home:
            assert json.loads((active / migration_guard.MARKER).read_text())["target"] == str(
                active
            )
        assert (
            json.loads((prepared_home / migration_guard.MARKER).read_text())["state"] == "committed"
        )
    assert "seed --all" not in uv_log.read_text()


REAL_POPEN = subprocess.Popen


def _fake_worker(argv: list[str], **kwargs: Any) -> Any:
    if "aifactory.transition" in argv:
        return SimpleNamespace()
    return REAL_POPEN(argv, **kwargs)


@pytest.mark.parametrize("state", ["prepared", "committed", "invalid"])
def test_last_haifa_refuses_cli_and_dashboard_writes_after_marker(
    prepared_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    state: str,
) -> None:
    app = create_multi_app(home=prepared_home)
    with TestClient(app, base_url="http://127.0.0.1:4700") as client:
        (prepared_home / migration_guard.MARKER).write_text(json.dumps({"state": state}))
        assert client.post("/api/restart").json()["error"]["code"] == "migration_pending"
        assert cli.main(["library", "init", "--json"]) == 2
        assert json.loads(capsys.readouterr().out)["error"]["code"] == "migration_pending"


def test_another_process_lease_blocks_transition(
    prepared_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with migration_guard.process_lease(prepared_home):
        monkeypatch.setattr(os, "getpid", lambda: -1)
        with pytest.raises(UpgradeError) as error:
            migration_guard.require_quiet(prepared_home)
        assert error.value.code == "runs_active"


def test_giro_guard_accepts_only_matching_completed_or_authorized_transaction(
    prepared_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backup = prepared_home.parent / "retained"
    backup.mkdir()
    plan = {
        "format": 1,
        "id": "operation",
        "source": str(prepared_home),
        "target": str(prepared_home),
        "backup": str(backup),
        "state": "prepared",
    }
    (backup / "plan.json").write_text(json.dumps(plan))
    migration_guard.write_manifest(prepared_home, plan)
    monkeypatch.setattr(migration_guard, "__version__", "1.0.1")
    with pytest.raises(UpgradeError):
        migration_guard.check_home(prepared_home)
    monkeypatch.setenv("GIRO_MIGRATION_ID", "operation")
    migration_guard.check_home(prepared_home)
    with pytest.raises(UpgradeError):
        migration_guard.check_home(prepared_home, writing=True)
    plan["state"] = "committed"
    (backup / "plan.json").write_text(json.dumps(plan))
    migration_guard.write_manifest(prepared_home, plan)
    migration_guard.check_home(prepared_home, writing=True)


@pytest.mark.parametrize("fails", [False, True])
def test_windows_backup_preserves_acl_or_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fails: bool
) -> None:
    source, target = tmp_path / "env", tmp_path / "backup-env"
    source.write_text("secret")
    calls: list[dict[str, Any]] = []

    def acl(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(kwargs)
        assert "SetAccessRuleProtection($true,$true)" in argv[-1]
        assert "Backup ACL verification failed" in argv[-1]
        if fails:
            raise subprocess.CalledProcessError(1, argv, stderr="ACL access denied")
        return subprocess.CompletedProcess(argv, 0, "")

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "run", acl)
    if fails:
        with pytest.raises(UpgradeError, match="ACL access denied") as error:
            transition._copy(source, target)
        assert error.value.code == "migration_unsafe"
    else:
        transition._copy(source, target)
        assert target.read_text() == "secret"
    assert calls[0]["check"] is True
    assert calls[0]["env"]["GIRO_ACL_SOURCE"] == str(source)
    assert calls[0]["env"]["GIRO_ACL_TARGET"] == str(target)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows ACL round trip")
@pytest.mark.parametrize("tamper", [None, "inheritance", "rights"])
def test_real_windows_backup_acl_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tamper: str | None
) -> None:
    source, target = tmp_path / "source", tmp_path / "backup"
    source.write_text("preserved")
    if tamper:
        script = transition._BACKUP_ACL
        if tamper == "inheritance":
            # Simulate a successful write that leaves the inherited target DACL.
            script = script.replace("ApplyAcl $copy", "")
        else:
            # Simulate reading back a protected DACL with an extra grant.
            script = script.replace(
                "$actual=Get-Acl -LiteralPath $env:GIRO_ACL_TARGET",
                "$actual=Get-Acl -LiteralPath $env:GIRO_ACL_TARGET\n"
                "$sid=[System.Security.Principal.SecurityIdentifier]::new('S-1-1-0')\n"
                "$rule=[System.Security.AccessControl.FileSystemAccessRule]::new("
                "$sid,'FullControl','Allow')\n"
                "$actual.AddAccessRule($rule)",
            )
        monkeypatch.setattr(
            transition,
            "_BACKUP_ACL",
            script,
        )
        with pytest.raises(UpgradeError, match="Backup ACL verification failed"):
            transition._copy(source, target)
    else:
        transition._copy(source, target)
        assert target.read_text() == "preserved"


def test_unwritable_migration_guard_refuses_cli_with_json_error(
    prepared_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from collections.abc import Iterator
    from contextlib import contextmanager

    @contextmanager
    def denied(home: Path) -> Iterator[None]:
        raise PermissionError("home is read-only")
        yield

    monkeypatch.setattr(migration_guard, "migration_lock", denied)
    assert cli.main(["library", "init", "--json"]) == 2
    error = json.loads(capsys.readouterr().out)["error"]
    assert error["code"] == "migration_unavailable"
    assert "read-only" in error["message"]


def test_giro_guard_rejects_a_conflicting_source_pointer(
    prepared_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backup, source = prepared_home.parent / "retained", prepared_home.parent / "legacy"
    backup.mkdir()
    source.mkdir()
    plan = {
        "format": 1,
        "id": "operation",
        "source": str(source),
        "target": str(prepared_home),
        "backup": str(backup),
        "state": "committed",
    }
    (backup / "plan.json").write_text(json.dumps(plan))
    migration_guard.write_manifest(prepared_home, plan)
    migration_guard.write_manifest(source, {**plan, "id": "different operation"})
    monkeypatch.setattr(migration_guard, "__version__", "1.0.1")
    with pytest.raises(UpgradeError):
        migration_guard.check_home(prepared_home, writing=True)


def test_sqlite_backup_incorporates_real_wal_without_copying_sidecars(tmp_path: Path) -> None:
    source, target = tmp_path / "source", tmp_path / "saved"
    source.mkdir()
    database = source / "history"
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("CREATE TABLE history(value TEXT)")
        connection.execute("INSERT INTO history VALUES ('committed in WAL')")
        connection.commit()
        assert (source / "history-wal").is_file()
        assert (source / "history-shm").is_file()
        transition._copy(source, target)
        assert not (target / "history-wal").exists()
        assert not (target / "history-shm").exists()
        with closing(sqlite3.connect(target / "history")) as saved:
            assert saved.execute("SELECT value FROM history").fetchone() == ("committed in WAL",)
