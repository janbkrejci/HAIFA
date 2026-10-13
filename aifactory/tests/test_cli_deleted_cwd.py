"""factory started in a working directory that no longer exists continues from home."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from aifactory.cli import main


@pytest.mark.skipif(
    sys.platform == "win32", reason="Windows cannot delete a process's working directory"
)
def test_deleted_working_directory_moves_to_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    gone = tmp_path / "unpacked-bundle"
    gone.mkdir()
    monkeypatch.chdir(gone)
    gone.rmdir()
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert Path(os.getcwd()) == home.resolve()
    assert "pracovní složka neexistuje" in capsys.readouterr().err
    # child processes work again: git no longer fails to read the working directory
    git = subprocess.run(["git", "--version"], capture_output=True, text=True, check=False)
    assert git.returncode == 0


def test_existing_working_directory_is_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        main(["--version"])
    assert Path(os.getcwd()) == tmp_path.resolve()
    assert "pracovní složka" not in capsys.readouterr().err
