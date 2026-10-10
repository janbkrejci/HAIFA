"""The hidden test gate of R10: placed only around the code test step, never seen by agents."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aifactory.testing import executor
from validation import hidden, worker


def _source(tmp_path: Path) -> Path:
    return hidden.write_hidden(tmp_path / "work")


def test_placed_puts_the_test_into_tests_and_removes_it(tmp_path: Path) -> None:
    root = tmp_path / "wt"
    (root / "tests").mkdir(parents=True)
    target = root / hidden.HIDDEN_TARGET
    with hidden.placed(root, _source(tmp_path)) as path:
        assert path == target
        assert target.read_text(encoding="utf-8") == hidden.HIDDEN_TEST
    assert not target.exists()


def test_placed_removes_the_test_after_an_exception(tmp_path: Path) -> None:
    root = tmp_path / "wt"
    (root / "tests" / "__pycache__").mkdir(parents=True)
    pyc = root / "tests" / "__pycache__" / "test_hidden_slugify.cpython-312.pyc"
    with pytest.raises(RuntimeError), hidden.placed(root, _source(tmp_path)):
        pyc.write_bytes(b"x")
        raise RuntimeError("boom")
    assert not (root / hidden.HIDDEN_TARGET).exists()
    assert not pyc.exists()


def test_placed_restores_an_existing_file(tmp_path: Path) -> None:
    root = tmp_path / "wt"
    (root / "tests").mkdir(parents=True)
    target = root / hidden.HIDDEN_TARGET
    target.write_text("mine\n", encoding="utf-8", newline="\n")
    with hidden.placed(root, _source(tmp_path)):
        assert target.read_text(encoding="utf-8") == hidden.HIDDEN_TEST
    assert target.read_text(encoding="utf-8") == "mine\n"


def test_placed_without_tests_does_nothing(tmp_path: Path) -> None:
    root = tmp_path / "wt"
    root.mkdir()
    with hidden.placed(root, _source(tmp_path)):
        assert not (root / "tests").exists()
    assert list(root.iterdir()) == []


def test_wrap_test_places_the_test_only_during_the_call(tmp_path: Path) -> None:
    root = tmp_path / "wt"
    (root / "tests").mkdir(parents=True)
    seen: list[bool] = []

    def original(run: Any, plan: Any) -> str:
        seen.append((Path(run.repo_root) / hidden.HIDDEN_TARGET).exists())
        return "result"

    wrapped = hidden.wrap_test(original, _source(tmp_path))
    assert wrapped(SimpleNamespace(repo_root=str(root)), None) == "result"
    assert seen == [True]
    assert not (root / hidden.HIDDEN_TARGET).exists()


def test_install_wraps_the_executor_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(executor, "execute", lambda run, plan: calls.append(run))
    hidden.install(_source(tmp_path))
    first = executor.execute
    assert getattr(first, "_haifa_hidden", False)
    hidden.install(_source(tmp_path))
    assert executor.execute is first


def test_worker_consumes_the_hidden_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aifactory import cli

    monkeypatch.setattr(executor, "execute", executor.execute)  # restored after the test
    installed: list[Path] = []
    monkeypatch.setattr(hidden, "install", installed.append)
    seen: list[str | None] = []

    def fake_main(argv: list[str]) -> int:
        seen.append(os.environ.get(hidden.HIDDEN_ENV))
        return 0

    monkeypatch.setattr(cli, "main", fake_main)
    monkeypatch.delenv(worker.FAKE_ENV, raising=False)
    monkeypatch.setenv(hidden.HIDDEN_ENV, str(tmp_path / "hidden"))
    assert worker.main(["version"]) == 0
    assert seen == [None]
    assert installed == [tmp_path / "hidden"]
    assert hidden.HIDDEN_ENV not in os.environ


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout


def test_exclude_hides_the_test_from_git(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    hidden.exclude(repo)
    hidden.exclude(repo)
    info = Path(_git(repo, "rev-parse", "--absolute-git-dir").strip()) / "info" / "exclude"
    lines = info.read_text(encoding="utf-8").splitlines()
    assert lines.count("/" + hidden.HIDDEN_TARGET) == 1
    (repo / "tests").mkdir()
    (repo / hidden.HIDDEN_TARGET).write_text("x\n", encoding="utf-8", newline="\n")
    assert _git(repo, "status", "--porcelain", "--untracked-files=all") == ""
