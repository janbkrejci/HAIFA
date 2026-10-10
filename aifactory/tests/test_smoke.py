"""Smoke test: the package imports and `factory --help` runs."""

import subprocess
import sys

import pytest

import aifactory
from aifactory.cli import SUBCOMMANDS, main

NAMES = [name for name, _ in SUBCOMMANDS]


def test_import() -> None:
    assert isinstance(aifactory.__version__, str)


def test_factory_help_subprocess() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aifactory", "--help"],
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert "factory" in result.stdout
    for name in ["task", "backlog", "workflow", "config", "harness", "--skill"]:
        assert name in result.stdout


def test_subcommands_not_implemented(capsys: pytest.CaptureFixture[str]) -> None:
    for name in NAMES:
        implemented = ("check", "harness", "config", "backlog", "task", "workflow", "skills")
        setup = ("init", "update", "library", "obs", "upgrade")
        if name in (*implemented, *setup):
            continue
        assert main([name]) == 2
        assert "not implemented yet" in capsys.readouterr().err
    assert main([]) == 0
    assert main(["harness"]) == 0
    assert main(["config"]) == 0
    assert main(["backlog"]) == 0
    assert main(["task"]) == 0
    assert main(["workflow"]) == 0
    assert main(["library"]) == 0
