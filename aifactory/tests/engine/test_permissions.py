"""Writes outside ``writes`` and into ``protected_files`` are rolled back and fail the phase."""

from __future__ import annotations

from pathlib import Path

import pytest
from engine_fakes import (  # noqa: F401
    EngineEnv,
    agent_phase,
    engine_env_fixture,
    events_of,
    rows,
    start,
)

from aifactory.engine import agents, permissions


def test_writes_outside_allowlist_are_rolled_back(engine_env: EngineEnv) -> None:
    env = engine_env
    run = start(env)

    def agent_work(cwd: Path) -> None:
        (cwd / "allowed").mkdir()
        (cwd / "allowed" / "a.txt").write_text("fine\n", encoding="utf-8", newline="\n")
        (cwd / "stray.txt").write_text("stray\n", encoding="utf-8", newline="\n")
        (cwd / "README.md").write_text("hijacked\n", encoding="utf-8", newline="\n")

    env.script.on("builder", agent_work)
    env.script.add_ok("builder")
    with pytest.raises(permissions.PermissionBreach) as exc:
        agent_phase(run, "builder")

    message = str(exc.value)
    assert "stray.txt" in message and "README.md" in message
    assert not (env.repo / "stray.txt").exists()
    assert (env.repo / "README.md").read_text() == "readme\n"
    assert (env.repo / "allowed" / "a.txt").read_text() == "fine\n"

    phase_id = f"{run.adw_id}_01_builder"
    assert ("error", "permission_breach") in [
        (t, n) for t, n, _ in events_of(env.db_path, phase_id)
    ]
    assert rows(env.db_path, "SELECT status FROM phases WHERE phase_id=?", phase_id) == [("fail",)]
    status = rows(env.db_path, "SELECT status FROM sessions WHERE adw_id=?", run.adw_id)
    assert status == [("fail",)]


def test_protected_file_is_rolled_back_for_unrestricted_agent(engine_env: EngineEnv) -> None:
    env = engine_env
    run = start(env)

    def agent_work(cwd: Path) -> None:
        (cwd / "protected.md").write_text("tampered\n", encoding="utf-8", newline="\n")
        (cwd / "ok.txt").write_text("ok\n", encoding="utf-8", newline="\n")

    env.script.on("free", agent_work)
    env.script.add_ok("free")
    with pytest.raises(permissions.PermissionBreach) as exc:
        agent_phase(run, "free")

    assert "protected.md" in str(exc.value)
    assert "ok.txt" not in str(exc.value)
    assert (env.repo / "protected.md").read_text() == "protected\n"
    assert (env.repo / "ok.txt").read_text() == "ok\n"


def test_naming_a_protected_file_unlocks_it(engine_env: EngineEnv) -> None:
    env = engine_env
    run = start(env)

    def agent_work(cwd: Path) -> None:
        (cwd / "protected.md").write_text("edited\n", encoding="utf-8", newline="\n")

    env.script.on("keyholder", agent_work)
    env.script.add_ok("keyholder")
    agent_phase(run, "keyholder")

    phase_id = f"{run.adw_id}_01_keyholder"
    assert rows(env.db_path, "SELECT status FROM phases WHERE phase_id=?", phase_id) == [
        ("success",)
    ]
    touched = [p for t, n, p in events_of(env.db_path, phase_id) if n == "paths_touched"]
    assert touched and "protected.md" in touched[0]["paths"]
    assert (env.repo / "protected.md").read_text() == "edited\n"


def test_read_only_agent_new_file_is_deleted(engine_env: EngineEnv) -> None:
    env = engine_env
    run = start(env)

    def agent_work(cwd: Path) -> None:
        (cwd / "x.txt").write_text("x\n", encoding="utf-8", newline="\n")

    env.script.on("reader", agent_work)
    env.script.add_ok("reader")
    with pytest.raises(permissions.PermissionBreach) as exc:
        agent_phase(run, "reader")

    assert "read-only" in str(exc.value)
    assert not (env.repo / "x.txt").exists()


def test_already_dirty_path_is_left_as_is(engine_env: EngineEnv) -> None:
    env = engine_env
    (env.repo / "README.md").write_text("operator work\n", encoding="utf-8", newline="\n")
    run = start(env)

    def agent_work(cwd: Path) -> None:
        (cwd / "README.md").write_text(
            "operator work\nagent line\n", encoding="utf-8", newline="\n"
        )

    env.script.on("builder", agent_work)
    env.script.add_ok("builder")
    with pytest.raises(permissions.PermissionBreach) as exc:
        agent_phase(run, "builder")

    assert "README.md — left as-is (was already modified)" in str(exc.value)
    assert (env.repo / "README.md").read_text() == "operator work\nagent line\n"


def test_permitted_rules(engine_env: EngineEnv) -> None:
    cfg = engine_env.cfg
    reader = agents.resolve(cfg, "reader")
    builder = agents.resolve(cfg, "builder")
    free = agents.resolve(cfg, "free")
    runtime = cfg.defaults.data_dir.rstrip("/") + "/sessions/x/out.md"
    assert permissions.permitted(runtime, reader, cfg)
    assert not permissions.permitted("README.md", reader, cfg)
    assert permissions.permitted("allowed/deep/a.txt", builder, cfg)
    assert not permissions.permitted("protected.md", free, cfg)
    assert permissions.permitted("anything.txt", free, cfg)

    assert permissions._matches("adws/adw_x.py", "adws/adw_*.py")
    assert not permissions._matches("adws/adw_data/x.py", "adws/adw_*.py")
    assert permissions._matches("a/b/c.py", "a/**")
    assert permissions._matches("dir/file", "dir/")
    assert not permissions._matches("dirx/file", "dir/")
