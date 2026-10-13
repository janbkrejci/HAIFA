from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from aifactory.engine import git_helper


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_diff_of_a_non_utf8_file_is_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # legacy VB6 sources are cp1250: their diff is no valid UTF-8
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    legacy = tmp_path / "ROBEST.FRM"
    legacy.write_bytes("Příjmení\n".encode("cp1250"))
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()
    legacy.write_bytes("Příjmení a jméno\n".encode("cp1250"))
    monkeypatch.chdir(tmp_path)

    text = git_helper.diff_text(base)

    assert "ROBEST.FRM" in text
    assert "�" in text
