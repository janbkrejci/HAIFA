"""``factory try``: the sample repository (``aifactory.demo``)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from aifactory.backlog import check_backlog
from aifactory.backlog.loader import iter_tasks, load_backlog
from aifactory.check import run_check
from aifactory.demo import BASE, create_demo, default_dir
from aifactory.home import haifa_home
from aifactory.web.registry import Registry
from cli_json import run_json


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """A git identity, so the sample commit works on machines without one (CI)."""
    for kind in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{kind}_NAME", "Ada Tester")
        monkeypatch.setenv(f"GIT_{kind}_EMAIL", "ada@example.com")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_creates_a_committed_local_repo_in_the_haifa_home() -> None:
    result = create_demo()

    assert result.created and result.registered
    assert result.path == default_dir().absolute()
    root = result.path
    assert _git(root, "branch", "--show-current") == BASE
    assert _git(root, "status", "--porcelain") == ""
    assert _git(root, "remote") == ""
    config = (root / ".factory" / "config.yaml").read_text(encoding="utf-8")
    assert "git_provider: local" in config
    tracked = _git(root, "ls-files").splitlines()
    assert ".factory/config.yaml" in tracked and "textstats.py" in tracked
    assert not any("__pycache__" in path for path in tracked)
    gitignore = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".factory/worktrees/" in gitignore and ".factory/trace.db*" in gitignore
    state, _warnings = Registry(haifa_home()).snapshot()
    assert [Path(e.path).resolve() for e in state.repos] == [root.resolve()]


def test_factory_check_reports_no_repo_errors_and_the_backlog_is_valid(tmp_path: Path) -> None:
    root = create_demo(tmp_path / "sample").path

    report = run_check(root, offline=True)
    assert report.state == "installed"
    assert [f for f in report.findings if f.scope == "repo" and f.severity == "error"] == []
    backlog = load_backlog(root)
    assert check_backlog(backlog) == []
    tasks = sorted(iter_tasks(backlog), key=lambda t: t.id)
    assert [t.id for t in tasks] == ["DEMO-S01-T01", "DEMO-S01-T02", "DEMO-S01-T03"]
    assert all(t.status == "todo" for t in tasks)


def test_the_sample_tests_pass(tmp_path: Path) -> None:
    root = create_demo(tmp_path / "sample").path

    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Ran 7 tests" in proc.stderr


def test_again_changes_nothing_and_returns_the_path(tmp_path: Path) -> None:
    first = create_demo(tmp_path / "sample")
    readme = first.path / "README.md"
    readme.write_text("mine\n", encoding="utf-8")
    head = _git(first.path, "rev-parse", "HEAD")

    again = create_demo(tmp_path / "sample")

    assert again.path == first.path
    assert not again.created and again.registered
    assert again.repo_id == first.repo_id
    assert readme.read_text(encoding="utf-8") == "mine\n"
    assert _git(first.path, "rev-parse", "HEAD") == head
    state, _warnings = Registry(haifa_home()).snapshot()
    assert len(state.repos) == 1


def test_an_existing_folder_with_files_is_left_alone(tmp_path: Path) -> None:
    folder = tmp_path / "mine"
    folder.mkdir()
    (folder / "notes.txt").write_text("keep\n", encoding="utf-8")

    result = create_demo(folder)

    assert not result.created and not result.registered
    assert result.warnings
    assert [p.name for p in folder.iterdir()] == ["notes.txt"]


def test_an_empty_folder_gets_the_sample(tmp_path: Path) -> None:
    folder = tmp_path / "empty"
    folder.mkdir()

    assert create_demo(folder).created
    assert (folder / "textstats.py").is_file()


def test_cli_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "sample"

    rc, obj = run_json(capsys, ["try", str(target), "--json"])
    assert rc == 0
    assert obj["data"]["created"] is True
    assert obj["data"]["provider"] == "local"
    assert Path(obj["data"]["path"]) == target.absolute()

    rc, obj = run_json(capsys, ["try", str(target), "--json"])
    assert rc == 0
    assert obj["data"]["created"] is False


def test_cli_refuses_a_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "file"
    target.write_text("x", encoding="utf-8")

    rc, obj = run_json(capsys, ["try", str(target), "--json"])
    assert rc == 2
    assert obj["error"]["code"] == "invalid_value"


def test_env_identity_without_git_config_is_enough(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CI has no git config identity, only GIT_AUTHOR_*/GIT_COMMITTER_* in the environment."""
    empty = tmp_path / "gitconfig"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")

    result = create_demo(tmp_path / "sample")

    assert result.created
    assert _git(result.path, "log", "--format=%an <%ae>") == "Ada Tester <ada@example.com>"


def test_missing_git_identity_leaves_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "gitconfig"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for name in (
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
        "EMAIL",
    ):
        monkeypatch.delenv(name, raising=False)
    target = tmp_path / "sample"

    rc, obj = run_json(capsys, ["try", str(target), "--json"])

    assert rc == 2
    assert obj["error"]["code"] == "git_identity_missing"
    assert not target.exists()
