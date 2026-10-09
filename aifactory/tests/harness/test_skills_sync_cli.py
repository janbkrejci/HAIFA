"""`factory skills sync`: the mirror written through the CLI."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from aifactory.cli import main
from aifactory.harness.repo_skills import MIRROR, SOURCE
from cli_json import run_json


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    skill = repo / SOURCE / "a" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("skill a\n", encoding="utf-8", newline="\n")
    return repo


def test_sync_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    rc, obj = run_json(capsys, ["skills", "sync", "--repo", str(repo), "--json"])
    assert rc == 0
    assert obj["data"]["added"] == ["a"]
    assert obj["data"]["updated"] == []
    assert obj["data"]["removed"] == []
    assert obj["data"]["mirror"] == MIRROR
    assert (repo / MIRROR / "a" / "SKILL.md").read_text() == "skill a\n"


def test_sync_text(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    assert main(["skills", "sync", "--repo", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "added a" in out.splitlines()
    assert main(["skills", "sync", "--repo", str(repo)]) == 0
    assert "up to date" in capsys.readouterr().out


def test_sync_outside_a_repo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc, obj = run_json(capsys, ["skills", "sync", "--repo", str(tmp_path), "--json"])
    assert rc == 2
    assert obj["ok"] is False


def test_sync_write_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from aifactory.harness import repo_skills

    def fail(root: Path) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(repo_skills, "sync", fail)
    rc, obj = run_json(capsys, ["skills", "sync", "--repo", str(_repo(tmp_path)), "--json"])
    assert rc == 2
    assert obj["error"]["code"] == "skills_sync_failed"


def test_skills_without_subcommand_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["skills"]) == 0
    assert "sync" in capsys.readouterr().out
