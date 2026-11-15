"""GIRO resolution and offline migration: isolated homes and fake software only."""

from __future__ import annotations

import io
import json
import os
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

from aifactory import cli, home_migration, migration_guard, upgrade
from aifactory.engine.utils import agent_environment, operator_env
from aifactory.environment import SUFFIXES, child_environment, resolve, value
from aifactory.home import haifa_home, load_env_file
from aifactory.upgrade import UpgradeError
from aifactory.web.server import APP_NAME
from test_upgrade import make_bundle


@pytest.mark.parametrize("suffix", SUFFIXES)
def test_alias_precedence_and_child_normalization(suffix: str) -> None:
    new, old = f"GIRO_{suffix}", f"HAIFA_{suffix}"
    err = io.StringIO()
    result = resolve({new: "new", old: "legacy"}, stderr=err)
    assert result[new] == result[old] == "new"
    assert new in err.getvalue() and old in err.getvalue()
    assert "legacy" not in err.getvalue()
    assert value(suffix, {new: "", old: "legacy"}) == "legacy"
    if suffix != "HOME":
        result = resolve({old: "shell"}, {new: "file"})
        assert result[new] == result[old] == "shell"
        result = resolve({new: ""}, {new: "file", old: "old-file"}, stderr=err)
        assert result[new] == result[old] == "file"
    result = child_environment({new: "parent", old: "old-parent"}, **{old: "child"})
    assert result[new] == result[old] == "child"


def test_env_file_keeps_shell_origin_and_cannot_redirect_home(tmp_path: Path) -> None:
    selected = tmp_path / "selected"
    selected.mkdir()
    (selected / "env").write_text(
        "GIRO_LIBRARY=file\nGIRO_HOME=/wrong\nHAIFA_HOME=/wrong\nHOME=/wrong\n"
    )
    (selected / "env").chmod(0o600)
    env = {"HAIFA_HOME": str(selected), "HAIFA_LIBRARY": "shell"}
    load_env_file(env)
    assert env["GIRO_HOME"] == env["HAIFA_HOME"] == str(selected)
    assert env["GIRO_LIBRARY"] == env["HAIFA_LIBRARY"] == "shell"
    assert haifa_home(env) == selected


def test_worker_environment_overrides_both_run_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIRO_RUN_ID", "parent")
    with agent_environment({"HAIFA_RUN_ID": "worker"}):
        env = operator_env()
    assert env["GIRO_RUN_ID"] == env["HAIFA_RUN_ID"] == "worker"


@pytest.mark.parametrize("platform", ["darwin", "linux", "win32"])
def test_default_paths_and_explicit_aliases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    assert haifa_home({"HOME": str(tmp_path)}) == tmp_path / ".config/giro"
    assert (
        haifa_home({"HOME": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path / "xdg")})
        == tmp_path / "xdg/giro"
    )
    assert haifa_home({"HAIFA_HOME": str(tmp_path / "legacy")}) == tmp_path / "legacy"
    assert haifa_home({"GIRO_HOME": str(tmp_path / "new"), "HAIFA_HOME": "old"}) == tmp_path / "new"


def test_legacy_only_and_empty_collision_do_not_write(tmp_path: Path) -> None:
    source = tmp_path / "haifa"
    source.mkdir()
    env = {"XDG_CONFIG_HOME": str(tmp_path)}
    with pytest.raises(UpgradeError, match="--confirm"):
        haifa_home(env)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["haifa"]
    (tmp_path / "giro").mkdir()
    with pytest.raises(UpgradeError) as caught:
        haifa_home(env)
    assert caught.value.code == "migration_collision"
    assert list(source.iterdir()) == []


@pytest.mark.skipif(sys.platform == "win32", reason="symlink privilege is optional on Windows")
def test_same_directory_via_symlink_is_not_a_collision(tmp_path: Path) -> None:
    (tmp_path / "haifa").mkdir()
    (tmp_path / "giro").symlink_to(tmp_path / "haifa", target_is_directory=True)
    assert haifa_home({"XDG_CONFIG_HOME": str(tmp_path)}) == tmp_path / "giro"


@pytest.fixture
def legacy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    source, target = tmp_path / "haifa", tmp_path / "giro"
    (source / "library/.git").mkdir(parents=True)
    (source / "library/.git/HEAD").write_text("local commit")
    (source / "library/untracked").write_text("local changes")
    (source / "env").write_text("HAIFA_UPDATE_REPO=janbkrejci/HAIFA\n")
    (source / "assistant").mkdir()
    (source / "assistant/draft").write_text("unfinished work")
    monkeypatch.setattr(upgrade, "editable_install", lambda: False)
    for suffix in ("LIBRARY", "DATABASE_URL"):
        for prefix in ("GIRO_", "HAIFA_"):
            monkeypatch.delenv(prefix + suffix, raising=False)
    bundle = make_bundle(tmp_path / "software", "0.1.9999")
    return source, target, bundle


@pytest.mark.parametrize("same_home", [False, True])
def test_migration_preserves_dirty_library_drafts_and_is_repeatable(
    legacy: tuple[Path, Path, Path], same_home: bool
) -> None:
    source, target, bundle = legacy
    target = source if same_home else target
    result = home_migration.migrate(source, target, bundle)
    assert result["state"] == "committed"
    assert (target / "library/untracked").read_text() == "local changes"
    assert (target / "library/.git/HEAD").read_text() == "local commit"
    assert (target / "assistant/draft").read_text() == "unfinished work"
    assert (source / "env").is_file()
    assert (Path(result["backup"]) / "data/0/env").is_file()
    migration_guard.check_home(target, writing=True)
    assert home_migration.migrate(source, target, bundle)["id"] == result["id"]
    if not same_home:
        assert haifa_home({"XDG_CONFIG_HOME": str(source.parent)}) == target
    if os.name != "nt":
        assert target.stat().st_mode & 0o777 == 0o700
        assert (target / "env").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "failure", ["permission", "interrupted", "collision", "active", "invalid_bundle"]
)
def test_failure_keeps_source_recoverable(
    legacy: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    source, target, bundle = legacy
    original = home_migration._copy

    def fail_copy(src: Path, dst: Path) -> None:
        if failure == "permission" or dst.name == "staging":
            raise PermissionError("simulated read-only destination")
        original(src, dst)

    if failure in {"permission", "interrupted"}:
        monkeypatch.setattr(home_migration, "_copy", fail_copy)
    elif failure == "collision":
        target.mkdir()
        (target / "keep").write_text("existing")
    elif failure == "active":

        def active(home: Path) -> None:
            raise UpgradeError("runs_active", "another process is active")

        monkeypatch.setattr(home_migration, "require_quiet", active)
    else:
        bundle.write_bytes(b"damaged")
    with pytest.raises((UpgradeError, OSError)):
        home_migration.migrate(source, target, bundle)
    assert (source / "library/untracked").read_text() == "local changes"
    assert (source / "assistant/draft").read_text() == "unfinished work"
    if failure == "interrupted":
        with pytest.raises(UpgradeError):
            home_migration.migrate(source, target, bundle)
        manifest = json.loads((source / migration_guard.MARKER).read_text())
        assert (Path(manifest["backup"]) / "data/0/env").is_file()
    if failure == "collision":
        assert (target / "keep").read_text() == "existing"


def test_missing_source_pointer_blocks_committed_target(legacy: tuple[Path, Path, Path]) -> None:
    source, target, bundle = legacy
    home_migration.migrate(source, target, bundle)
    (source / migration_guard.MARKER).unlink()
    with pytest.raises(UpgradeError):
        migration_guard.check_home(target, writing=True)


def test_entry_points_share_implementation_and_health_identity() -> None:
    project = Path(__file__).resolve().parents[1]
    data = tomllib.loads((project / "pyproject.toml").read_text())
    assert data["project"]["scripts"] == {
        "giro": "aifactory.cli:main",
        "factory": "aifactory.cli:main",
    }
    assert cli.build_parser().prog == "giro"
    assert "GIRO" in cli.build_parser().format_help()
    assert APP_NAME == "giro-dashboard"


def test_giro_publication_is_gated_to_new_repository() -> None:
    root = Path(__file__).resolve().parents[2]
    workflow: dict[str, Any] = yaml.safe_load(
        (root / ".github/workflows/giro-release.yml").read_text()
    )
    job = workflow["jobs"]["release"]
    assert "github.repository == 'janbkrejci/GIRO'" in job["if"]
    assert "GIRO_RELEASE_ENABLED == 'true'" in job["if"]
    steps = "\n".join(step.get("run", "") for step in job["steps"])
    assert "dist/giro-$VERSION.zip" in steps
    assert "dist/haifa-$VERSION.zip" not in steps


def test_new_default_only_does_not_create_legacy(tmp_path: Path) -> None:
    (tmp_path / "giro").mkdir()
    assert haifa_home({"XDG_CONFIG_HOME": str(tmp_path)}) == tmp_path / "giro"
    assert not (tmp_path / "haifa").exists()


def test_external_library_is_backed_up_without_moving_it(
    legacy: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target, bundle = legacy
    external = source.parent / "team-library"
    external.mkdir()
    (external / "dirty").write_text("uncommitted")
    monkeypatch.setenv("GIRO_LIBRARY", str(external))
    manifest = home_migration.migrate(source, target, bundle)
    index = manifest["paths"].index(str(external))
    assert (Path(manifest["backup"]) / "data" / str(index) / "dirty").read_text() == "uncommitted"
    assert (external / "dirty").read_text() == "uncommitted"


def test_registered_repository_and_runtime_identities_survive_home_migration(
    legacy: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    from aifactory.web.registry import Registry

    source, target, bundle = legacy
    root = source.parent / "renamed-checkout"
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    (root / ".factory/data/sessions/historical-id").mkdir(parents=True)
    (root / ".factory/data/sessions/historical-id/transcript").write_text("conversation")
    (root / ".factory/worktrees").mkdir()
    entry, _ = Registry(source).add(root)
    registry_before = (source / "dashboard.yaml").read_bytes()
    manifest = home_migration.migrate(source, target, bundle)
    assert (target / "dashboard.yaml").read_bytes() == registry_before
    registered = Registry(target).snapshot()[0].by_id(entry.id)
    assert registered is not None and registered.path == str(root)
    assert (root / ".factory/data/sessions/historical-id/transcript").read_text() == "conversation"
    saved = Path(manifest["backup"]) / "data" / str(manifest["paths"].index(str(root / ".factory")))
    assert (saved / "data/sessions/historical-id/transcript").read_text() == "conversation"


def test_update_source_from_migrated_env_cannot_return_to_haifa(tmp_path: Path) -> None:
    (tmp_path / "env").write_text("HAIFA_UPDATE_REPO=janbkrejci/HAIFA\n")
    env = {"HAIFA_HOME": str(tmp_path)}
    load_env_file(env)
    assert env["GIRO_UPDATE_REPO"] == env["HAIFA_UPDATE_REPO"] == "janbkrejci/GIRO"
    explicit = resolve({"GIRO_UPDATE_REPO": "janbkrejci/HAIFA"})
    assert explicit["GIRO_UPDATE_REPO"] == "janbkrejci/HAIFA"


def test_agents_do_not_inherit_either_validation_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    names = [
        f"{prefix}_VALIDATE_{kind}" for prefix in ("GIRO", "HAIFA") for kind in ("FAKE", "HIDDEN")
    ]
    for name in names:
        monkeypatch.setenv(name, "private-test-path")
    env = operator_env()
    assert all(name not in env for name in names)


def test_version_is_giro_and_does_not_open_data(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import aifactory.home

    def forbidden(*args: Any) -> Path:
        raise AssertionError("version must not open the data home")

    monkeypatch.setattr(aifactory.home, "haifa_home", forbidden)
    with pytest.raises(SystemExit) as exited:
        cli.main(["--version"])
    assert exited.value.code == 0
    assert capsys.readouterr().out.startswith("GIRO 1.")


def test_migration_usage_errors_keep_the_json_envelope(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["migrate", "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "usage_error"


@pytest.mark.skipif(sys.platform == "win32", reason="symlink privilege is optional on Windows")
def test_migration_locks_share_canonical_home_identity(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(source, target_is_directory=True)
    with migration_guard.migration_lock(source):
        with pytest.raises(UpgradeError) as caught:
            with migration_guard.migration_lock(alias):
                raise AssertionError("second lock unexpectedly acquired")
    assert caught.value.code == "update_busy"


def test_registered_active_run_blocks_offline_migration(legacy: tuple[Path, Path, Path]) -> None:
    import sqlite3
    import subprocess

    from aifactory.web.registry import Registry

    source, target, bundle = legacy
    root = source.parent / "active-repo"
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    (root / ".factory").mkdir()
    with sqlite3.connect(root / ".factory/trace.db") as database:
        database.execute("CREATE TABLE task_runs(state TEXT)")
        database.execute("INSERT INTO task_runs VALUES ('running')")
    Registry(source).add(root)
    with pytest.raises(UpgradeError) as caught:
        home_migration.migrate(source, target, bundle)
    assert caught.value.code == "runs_active"
    assert not target.exists()
    assert not (source / migration_guard.MARKER).exists()


def test_invalid_new_library_url_does_not_fall_back_to_legacy() -> None:
    from aifactory.library.share import default_library_url
    from aifactory.library.store import LibraryStoreError

    with pytest.raises(LibraryStoreError):
        default_library_url(
            {"GIRO_LIBRARY_URL": " ", "HAIFA_LIBRARY_URL": "https://valid.example/library"}
        )


@pytest.mark.parametrize("other_source", ["another-home", "giro"])
def test_default_collision_rejects_completed_migration_of_another_source(
    legacy: tuple[Path, Path, Path], other_source: str
) -> None:
    legacy_home, target, bundle = legacy
    source = legacy_home.parent / other_source
    source.mkdir()
    (source / "settings").write_text("separate factory")
    home_migration.migrate(source, target, bundle)
    # Both transactions are valid explicitly, but neither authorizes ignoring the
    # unrelated sibling legacy default (including an in-place explicit migration).
    migration_guard.check_home(target, writing=True)
    assert haifa_home({"GIRO_HOME": str(target)}) == target
    before = {str(p): p.read_bytes() for p in legacy_home.parent.rglob("*") if p.is_file()}
    with pytest.raises(UpgradeError) as error:
        haifa_home({"XDG_CONFIG_HOME": str(legacy_home.parent)})
    assert error.value.code == "migration_pending"
    assert {str(p): p.read_bytes() for p in legacy_home.parent.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize(
    "field",
    [
        "format",
        "id",
        "state",
        "source",
        "target",
        "backup",
        "original_version",
        "target_version",
        "haifa_bundle",
        "bundle_hashes",
        "paths",
        "data_hashes",
    ],
)
@pytest.mark.parametrize("damage", ["missing", "wrong_type"])
def test_incomplete_committed_manifest_blocks_access_and_repetition(
    legacy: tuple[Path, Path, Path], field: str, damage: str
) -> None:
    source, target, bundle = legacy
    manifest = home_migration.migrate(source, target, bundle)
    if damage == "missing":
        del manifest[field]
    else:
        manifest[field] = None
    # Corrupt every copy equally: equality alone must not authorize access.
    retained = Path(json.loads((target / migration_guard.MARKER).read_text())["backup"])
    migration_guard.write_manifest(source, manifest)
    migration_guard.write_manifest(target, manifest)
    (retained / "plan.json").write_text(json.dumps(manifest))
    before = {str(p): p.read_bytes() for p in source.parent.rglob("*") if p.is_file()}
    for writing in (False, True):
        with pytest.raises(UpgradeError):
            migration_guard.check_home(target, writing=writing)
    with pytest.raises(UpgradeError):
        home_migration.migrate(source, target, bundle)
    assert {str(p): p.read_bytes() for p in source.parent.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize(
    "damage",
    ["missing_bundle", "missing_data", "empty_records", "invalid_hash", "different_version"],
)
def test_committed_manifest_requires_consistent_recovery_records(
    legacy: tuple[Path, Path, Path], damage: str
) -> None:
    source, target, bundle = legacy
    manifest = home_migration.migrate(source, target, bundle)
    backup = Path(manifest["backup"])
    if damage == "missing_bundle":
        Path(manifest["haifa_bundle"]).unlink()
    elif damage == "missing_data":
        (backup / "data/0/env").unlink()
    elif damage == "empty_records":
        manifest["data_hashes"] = {}
    elif damage == "invalid_hash":
        manifest["bundle_hashes"][manifest["haifa_bundle"]] = "invalid"
    else:
        retained = {**manifest, "original_version": "0.1.1"}
        (backup / "plan.json").write_text(json.dumps(retained))
    if damage != "different_version":
        migration_guard.write_manifest(source, manifest)
        migration_guard.write_manifest(target, manifest)
        (backup / "plan.json").write_text(json.dumps(manifest))
    before = {str(p): p.read_bytes() for p in source.parent.rglob("*") if p.is_file()}
    with pytest.raises(UpgradeError):
        migration_guard.check_home(target, writing=True)
    with pytest.raises(UpgradeError):
        home_migration.migrate(source, target, bundle)
    assert {str(p): p.read_bytes() for p in source.parent.rglob("*") if p.is_file()} == before
