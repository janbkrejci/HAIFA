"""Local settings are shared by worktrees, never by clones or stale caches."""

from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path
from typing import Any

import pytest

from aifactory.repo_settings import RepositorySettings, SettingsError
from aifactory.run.gitops import git


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init")
    git(
        root,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.test",
        "commit",
        "--allow-empty",
        "-m",
        "init",
    )
    return root


def test_read_is_pure_and_defaults_are_safe(repo: Path, tmp_path: Path) -> None:
    home = tmp_path / "home"
    service = RepositorySettings(repo, home)
    assert service.read().model_dump() == {
        "version": 1,
        "auto_merge": False,
        "auto_continue": False,
        "harness": None,
    }
    assert service.show()["effective_harness"] is None
    assert not home.exists()
    with service.automatic_start() as allowed:
        assert allowed is False


def test_worktrees_clones_homes_and_restart(repo: Path, tmp_path: Path) -> None:
    home = tmp_path / "home"
    service = RepositorySettings(repo, home)
    before = git(repo, "status", "--porcelain", "--untracked-files=all")
    service.update({"auto_merge": True, "auto_continue": True, "harness": "codex"})
    worktree = tmp_path / "worktree"
    git(repo, "worktree", "add", "--detach", str(worktree))
    assert RepositorySettings(worktree, home).path == service.path
    assert RepositorySettings(worktree, home).read() == service.read()
    clone = tmp_path / "clone"
    git(tmp_path, "clone", str(repo), str(clone))
    assert RepositorySettings(clone, home).path != service.path
    assert RepositorySettings(clone, home).read().auto_merge is False
    assert RepositorySettings(repo, tmp_path / "other-home").read().auto_continue is False
    assert git(repo, "status", "--porcelain", "--untracked-files=all") == before
    assert RepositorySettings(repo, home).read().auto_continue is True
    service.update({"auto_continue": False})
    assert service.read().auto_merge is True
    assert service.read().auto_continue is False
    if os.name == "nt":
        assert RepositorySettings(Path(str(repo).upper()), home).path == service.path


@pytest.mark.parametrize(
    "raw,code",
    [
        ("{", "repo_settings_invalid"),
        ("[]", "repo_settings_invalid"),
        ('{"version": true}', "repo_settings_invalid"),
        ('{"version": "1"}', "repo_settings_invalid"),
        ('{"version": 2}', "repo_settings_version"),
        ('{"version": 1}', "repo_settings_invalid"),
        (
            json.dumps(
                {"version": 1, "auto_merge": "false", "auto_continue": True, "harness": None}
            ),
            "repo_settings_invalid",
        ),
        (
            json.dumps({"version": 1, "auto_merge": False, "auto_continue": 1, "harness": None}),
            "repo_settings_invalid",
        ),
        (
            json.dumps(
                {"version": 1, "auto_merge": False, "auto_continue": True, "harness": "invalid"}
            ),
            "repo_settings_invalid",
        ),
    ],
)
def test_invalid_file_never_uses_old_enabled_cache(
    repo: Path,
    tmp_path: Path,
    raw: str,
    code: str,
) -> None:
    service = RepositorySettings(repo, tmp_path / "home")
    service.update({"auto_continue": True})
    assert service.read().auto_continue
    service.path.write_text(raw, encoding="utf-8")
    for operation in (service.read, lambda: service.update({"auto_merge": True})):
        with pytest.raises(SettingsError) as error:
            operation()
        assert error.value.code == code
    with pytest.raises(SettingsError), service.automatic_start():
        pytest.fail("invalid settings allowed a start")
    assert service.path.read_text(encoding="utf-8") == raw


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"version": 2},
        {"auto_merge": "false"},
        {"auto_continue": None},
        {"harness": "unknown"},
        {"harness": False},
    ],
)
def test_invalid_patch_is_not_saved(
    repo: Path,
    tmp_path: Path,
    changes: dict[str, object],
) -> None:
    service = RepositorySettings(repo, tmp_path / "home")
    with pytest.raises(SettingsError) as error:
        service.update(changes)
    assert error.value.code == "invalid_value"
    assert not service.path.exists()


def test_failed_save_keeps_previous_record(
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RepositorySettings(repo, tmp_path / "home")
    service.update({"auto_continue": False})
    previous = service.path.read_bytes()

    def fail(*args: object) -> None:
        raise OSError("disk unavailable")

    monkeypatch.setattr("aifactory.repo_settings.os.replace", fail)
    with pytest.raises(SettingsError) as error:
        service.update({"auto_continue": True})
    assert error.value.code == "repo_settings_io"
    assert service.path.read_bytes() == previous
    assert not list(service.directory.glob(".*"))
    with service.automatic_start() as allowed:
        assert allowed is False


def test_unreadable_and_invalid_encoding_are_observable(repo: Path, tmp_path: Path) -> None:
    service = RepositorySettings(repo, tmp_path / "home")
    service.update({"auto_continue": True})
    service.path.write_bytes(b"\xff")
    with pytest.raises(SettingsError) as error:
        service.read()
    assert error.value.code == "repo_settings_invalid"
    service.path.unlink()
    service.path.mkdir()
    with pytest.raises(SettingsError) as error:
        service.read()
    assert error.value.code == "repo_settings_io"


def _patch_process(
    repo: Path, home: Path, changes: dict[str, object], ready: Any, proceed: Any, done: Any
) -> None:
    service = RepositorySettings(repo, home)
    ready.set()
    assert proceed.wait(15)
    service.update(changes)
    done.set()


def test_process_updates_preserve_different_fields(repo: Path, tmp_path: Path) -> None:
    ctx = multiprocessing.get_context("spawn")
    proceed = ctx.Event()
    home = tmp_path / "home"
    processes = []
    try:
        for changes in ({"auto_merge": True}, {"harness": "pi"}):
            ready, done = ctx.Event(), ctx.Event()
            process = ctx.Process(
                target=_patch_process, args=(repo, home, changes, ready, proceed, done)
            )
            process.start()
            processes.append(process)
            assert ready.wait(15)
        proceed.set()
        for process in processes:
            process.join(20)
            assert process.exitcode == 0
        result = RepositorySettings(repo, home).read()
        assert result.auto_merge is True and result.harness == "pi"
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join(5)


def test_disable_waits_for_accepted_start_then_blocks_next(repo: Path, tmp_path: Path) -> None:
    ctx = multiprocessing.get_context("spawn")
    home = tmp_path / "home"
    service = RepositorySettings(repo, home)
    service.update({"auto_continue": True})
    ready, proceed, done = ctx.Event(), ctx.Event(), ctx.Event()
    process = ctx.Process(
        target=_patch_process, args=(repo, home, {"auto_continue": False}, ready, proceed, done)
    )
    try:
        with service.automatic_start() as allowed:
            assert allowed is True
            process.start()
            assert ready.wait(15)
            proceed.set()
            assert not done.wait(0.2)
        assert done.wait(15)
        process.join(10)
        assert process.exitcode == 0
        with service.automatic_start() as allowed:
            assert allowed is False
    finally:
        if process.is_alive():
            process.terminate()
        if process.pid is not None:
            process.join(5)


def test_move_has_new_identity_and_deleted_clone_is_not_resolved(
    repo: Path, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    service = RepositorySettings(repo, home)
    service.update({"auto_merge": True})
    moved = tmp_path / "moved"
    repo.rename(moved)
    assert RepositorySettings(moved, home).read().auto_merge is False
    assert service.path.exists()  # orphan retained; reads never clean or migrate
    with pytest.raises(SettingsError):
        RepositorySettings(repo, home)


def test_inherits_only_machine_harness(repo: Path, tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "harnesses.json").write_text(
        json.dumps(
            {
                "version": 1,
                "default_harness": "codex",
                "harnesses": {
                    "codex": {"enabled": True, "model": "gpt-6.1-sol"},
                    "claude": {"enabled": False},
                    "pi": {"enabled": False},
                },
            }
        ),
        encoding="utf-8",
    )
    service = RepositorySettings(repo, home)
    assert service.show()["effective_harness"] == "codex"
    service.update({"harness": "pi"})
    assert service.show()["effective_harness"] == "pi"
    service.update({"harness": None})
    assert service.show()["effective_harness"] == "codex"


def test_legacy_true_never_becomes_a_default(repo: Path, tmp_path: Path) -> None:
    (repo / "factory" / "backlog").mkdir(parents=True)
    (repo / "factory" / "backlog" / "index.md").write_text(
        "---\nauto_merge: true\nauto_continue: true\nharness: claude\n---\n",
        encoding="utf-8",
    )
    service = RepositorySettings(repo, tmp_path / "home")
    assert not service.read().auto_merge
    assert not service.read().auto_continue
    assert service.read().harness is None
    service.update({"auto_merge": False, "auto_continue": False})
    assert not service.read().auto_merge
    assert not service.read().auto_continue
    service.path.write_text("broken", encoding="utf-8")
    with pytest.raises(SettingsError):
        service.read()


@pytest.mark.parametrize("auto_continue", [False, True])
def test_merge_submission_serializes_disable(
    repo: Path, tmp_path: Path, auto_continue: bool
) -> None:
    ctx = multiprocessing.get_context("spawn")
    home = tmp_path / "home"
    service = RepositorySettings(repo, home)
    service.update({"auto_merge": True, "auto_continue": auto_continue})
    ready, proceed, done = ctx.Event(), ctx.Event(), ctx.Event()
    process = ctx.Process(
        target=_patch_process, args=(repo, home, {"auto_merge": False}, ready, proceed, done)
    )
    try:
        with service.automatic_merge() as allowed:
            assert allowed is True
            process.start()
            assert ready.wait(15)
            proceed.set()
            assert not done.wait(0.2)
        assert done.wait(15)
        process.join(10)
        assert process.exitcode == 0
        with service.automatic_merge() as allowed:
            assert allowed is False
        assert service.read().auto_continue is auto_continue
        service.path.write_text("broken", encoding="utf-8")
        with pytest.raises(SettingsError):
            with service.automatic_merge():
                pytest.fail("invalid policy must never permit a submission")
    finally:
        if process.is_alive():
            process.terminate()
        if process.pid is not None:
            process.join(5)
