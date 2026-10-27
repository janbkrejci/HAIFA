"""Claude transcript cleanup stays within owned cwd prefixes."""

import os
import shutil
from pathlib import Path

import pytest

from aifactory.harness import agent_dirs


@pytest.fixture(autouse=True)
def claude_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "CLAUDE_CONFIG_DIR", ("\\\\?\\" if os.name == "nt" else "") + str(tmp_path / "claude")
    )


def project(cwd: str | Path) -> Path:
    path = next(iter(agent_dirs.claude_project_dirs(cwd)))
    path.mkdir(parents=True, exist_ok=True)
    (path / "session.jsonl").write_text("transcript")
    return path


def test_encoding_and_config_override(tmp_path: Path) -> None:
    cwd = r"C:\Users\JAN~1.KRE\.factory\worktrees\run-1"
    dirs = agent_dirs.claude_project_dirs(cwd)
    assert (
        Path(os.environ["CLAUDE_CONFIG_DIR"])
        / "projects/C--Users-JAN-1-KRE--factory-worktrees-run-1"
        in dirs
    )
    assert all(p.parent == Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" for p in dirs)
    relative = Path("relative.cwd")
    assert {p.name for p in agent_dirs.claude_project_dirs(relative)} == {
        "relative-cwd",
        agent_dirs._encode(relative.resolve()),
    }


def test_default_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert all(
        p.parent == tmp_path / ".claude/projects"
        for p in agent_dirs.claude_project_dirs(tmp_path / "cwd")
    )


def test_remove_handles_readonly_and_missing(tmp_path: Path) -> None:
    cwd = tmp_path / "cwd"
    path = project(cwd)
    (path / "session.jsonl").chmod(0o444)
    agent_dirs.remove_agent_dirs(cwd)
    assert not path.exists()
    agent_dirs.remove_agent_dirs(cwd)


def test_cleanup_failure_is_best_effort(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = project(tmp_path / "cwd")

    def denied(*args: object, **kwargs: object) -> None:
        raise PermissionError("locked")

    monkeypatch.setattr(shutil, "rmtree", denied)
    agent_dirs.remove_agent_dirs(tmp_path / "cwd")
    agent_dirs.sweep_orphans([tmp_path / "cwd"], [])
    assert path.exists()


def test_sweep_preserves_existing_live_and_unrelated(tmp_path: Path) -> None:
    prefix = tmp_path / "worktrees"
    existing = prefix / "existing/subdir"
    existing.mkdir(parents=True)
    kept = [
        project(existing),
        project(prefix / "existing"),
        project(prefix / "being-created"),
        project(tmp_path / "personal"),
        project(tmp_path / "other-worktrees/project"),
    ]
    orphan = project(prefix / "gone")
    agent_dirs.sweep_orphans([prefix], [prefix / "being-created"])
    assert not orphan.exists()
    assert all(p.exists() for p in kept)


def test_sweep_advice_prefix(tmp_path: Path) -> None:
    live = tmp_path / "factory-advice-live/repo"
    live.mkdir(parents=True)
    kept = project(live)
    orphan = project(tmp_path / "factory-advice-gone/repo")
    outside = project(tmp_path / "personal/repo")
    agent_dirs.sweep_orphans([tmp_path / "factory-advice-"], [])
    assert not orphan.exists()
    assert kept.exists() and outside.exists()


def test_remove_worktree_cleans_transcripts_only_after_success(tmp_path: Path) -> None:
    from aifactory.providers import git
    from aifactory.providers.base import ProviderError

    repo = tmp_path / "repo"
    repo.mkdir()
    git.git(repo, "init", "-q")
    git.git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "--allow-empty",
        "-qm",
        "initial",
    )
    cwd = tmp_path / "worktree"
    git.git(repo, "worktree", "add", "--detach", str(cwd))
    transcript = project(cwd)
    main_transcript = project(repo)
    with pytest.raises(ProviderError):
        git.remove_worktree(repo, repo)
    assert main_transcript.exists()
    assert git.remove_worktree(repo, cwd)
    assert not transcript.exists()
    assert not git.remove_worktree(repo, cwd)


def test_worktree_clean_sweeps_historical_projects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import MagicMock

    from aifactory.review import flow

    ctx = MagicMock()
    ctx.main = tmp_path
    ctx.rc.config.settings.worktrees_dir = "worktrees"
    existing = tmp_path / "worktrees/existing"
    existing.mkdir(parents=True)
    active = tmp_path / "worktrees/active"
    row = MagicMock(worktree=str(active), state="running")
    ctx.store.all_runs.return_value = [row]
    monkeypatch.setattr(flow, "_clean_locked", lambda *_: flow.CleanResult())
    kept = [project(existing), project(active / "subdir")]
    orphan = project(tmp_path / "worktrees/gone")
    assert flow._clean(ctx).warnings == []
    assert not orphan.exists()
    assert all(path.exists() for path in kept)


def test_sweep_preserves_existing_directory_links(tmp_path: Path) -> None:
    prefix = tmp_path / "worktrees"
    prefix.mkdir()
    target = tmp_path / "personal"
    (target / "subdir").mkdir(parents=True)
    link = prefix / "linked"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")
    kept = [project(link), project(link / "subdir")]
    agent_dirs.sweep_orphans([prefix], [])
    assert all(path.exists() for path in kept)
