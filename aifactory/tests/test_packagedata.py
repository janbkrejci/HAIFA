"""Packaged roles and workflows keep the content they had when the process started."""

from __future__ import annotations

from pathlib import Path

import pytest

from aifactory import packagedata
from aifactory.engine import role_registry
from aifactory.packagedata import PackageData


def _defaults(tmp_path: Path) -> Path:
    base = tmp_path / "defaults"
    base.mkdir()
    return base


def test_covered_file_keeps_its_start_time_text(tmp_path: Path) -> None:
    roles = _defaults(tmp_path) / "roles.yaml"
    roles.write_text("a: 1\n", encoding="utf-8", newline="\n")
    data = PackageData([roles.parent])
    roles.write_text("a: 2\n", encoding="utf-8", newline="\n")
    assert data.read_text(roles) == "a: 1\n"


def test_covered_file_added_after_start_is_missing(tmp_path: Path) -> None:
    base = _defaults(tmp_path)
    data = PackageData([base])
    late = base / "late.yaml"
    late.write_text("x: 1\n", encoding="utf-8", newline="\n")
    with pytest.raises(FileNotFoundError):
        data.read_text(late)


def test_other_files_are_read_from_disk(tmp_path: Path) -> None:
    data = PackageData([_defaults(tmp_path)])
    other = tmp_path / "repo-roles.yaml"
    other.write_text("a: 1\n", encoding="utf-8", newline="\n")
    assert data.read_text(other) == "a: 1\n"
    other.write_text("a: 2\n", encoding="utf-8", newline="\n")
    assert data.read_text(other) == "a: 2\n"


def test_names_lists_the_snapshot(tmp_path: Path) -> None:
    base = _defaults(tmp_path)
    (base / "b.yaml").write_text("{}\n", encoding="utf-8", newline="\n")
    (base / "a.yaml").write_text("{}\n", encoding="utf-8", newline="\n")
    data = PackageData([base])
    (base / "c.yaml").write_text("{}\n", encoding="utf-8", newline="\n")
    assert data.names(base) == ["a", "b"]


def test_load_roles_keeps_the_registry_a_run_started_with(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roles = _defaults(tmp_path) / "roles.yaml"
    roles.write_text(
        role_registry.DEFAULT_ROLES_PATH.read_text(encoding="utf-8"), encoding="utf-8", newline="\n"
    )
    monkeypatch.setattr(packagedata, "DATA", PackageData([roles.parent]))
    monkeypatch.setattr(role_registry, "DEFAULT_ROLES_PATH", roles)
    before = role_registry.load_roles()
    # a merge replaces the packaged file with one this code cannot read
    roles.write_text("code_steps:\n  rebuild_from_the_future: {}\n", encoding="utf-8", newline="\n")
    after = role_registry.load_roles()
    assert sorted(after.roles) == sorted(before.roles)
    assert sorted(after.code_steps) == sorted(before.code_steps)
