"""Task PR flow, provider ``local``: publish, approve, return, closed PR, base, clean."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from run_repo import SPEC, T01, T02, Script, fake_env, git, make_run_repo, ok, write

from aifactory.cli import main
from aifactory.config import load_run_config
from aifactory.providers import PullRequest
from aifactory.providers.local import LocalProvider
from aifactory.review import ReviewError, approve_task, return_task
from aifactory.run import TaskPrRow, TaskRunStore, run_task
from cli_json import run_json

Capsys = pytest.CaptureFixture[str]
TASK_FILE = "backlog/M01-core/S01-model/M01-S01-T01-schema.md"
BRANCH = f"factory/{T01}-1"


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


def trace_db(repo: Path) -> Path:
    return repo / ".factory" / "trace.db"


def succeed(script: Script, text: str = "# spec\n") -> None:
    script.on("planner", lambda wt: write(wt, SPEC, text))
    script.add("planner", ok(artifacts=[SPEC], commit_message="Add schema spec"))


def stored_pr(repo: Path, branch: str = BRANCH) -> TaskPrRow | None:
    store = TaskRunStore(trace_db(repo))
    try:
        return store.pr_for_branch(branch)
    finally:
        store.close()


def cli_json(capsys: Capsys, *argv: str) -> tuple[int, Any]:
    capsys.readouterr()
    return run_json(capsys, argv)


def close_pr(worktree: Path, branch: str = BRANCH) -> None:
    """Provider local: a PR whose branch is gone is closed."""
    git(worktree, "checkout", "-q", "--detach")
    git(worktree, "branch", "-D", branch)


def test_publish_opens_pr(repo: Path, script: Script) -> None:
    succeed(script)
    result = run_task(repo, T01)

    assert result.ok, (result.run.error, result.pr_error)
    assert result.pr is not None
    assert result.pr.state == "open"
    assert result.pr.pr_id == BRANCH
    assert result.pr.url == f"local:{BRANCH}"
    assert result.pr.base_sha == result.run.base_sha
    saved = stored_pr(repo)
    assert saved == result.pr
    for part in ("## Zadání", "Navrhnout schéma", "## Agenti", "## Gates a testy"):
        assert part in saved.body
    assert "## Review" in saved.body and "## Náklady" in saved.body
    assert f"<!-- factory: task={T01} branch={BRANCH} -->" in saved.body


def test_failed_run_has_no_pr(repo: Path, script: Script) -> None:
    script.on("planner", lambda wt: write(wt, "src/other.py", "x\n"))
    script.add("planner", ok())
    result = run_task(repo, T01)
    assert result.run.state == "failed"
    assert result.pr is None
    assert stored_pr(repo) is None


def test_approve_commits_done_and_merges(repo: Path, script: Script, capsys: Capsys) -> None:
    succeed(script)
    run = run_task(repo, T01)
    worktree = Path(run.run.worktree)

    code, data = cli_json(capsys, "task", "approve", T01, "--json", "--repo", str(repo))

    assert code == 0, data
    assert data["ok"] is True
    assert data["data"]["reviewed"] is False
    task_text = git(repo, "show", f"main:{TASK_FILE}")
    assert "status: done" in task_text
    assert f"PR local:{BRANCH}" in task_text.split("## Běhy", 1)[1]
    assert git(repo, "show", f"main:{SPEC}") == "# spec"
    saved = stored_pr(repo)
    assert saved is not None
    assert saved.state == "merged"
    assert saved.merge_sha == git(repo, "rev-parse", "main")
    assert data["data"]["merge_sha"] == saved.merge_sha
    assert not worktree.exists()
    removed = data["data"]["removed_worktrees"]
    assert isinstance(removed, list) and str(worktree) in removed
    assert git(repo, "status", "--porcelain") == ""
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert git(repo, "log", "-1", "--format=%s", BRANCH) == f"{T01}: status done"

    code, data = cli_json(capsys, "task", "approve", T01, "--json", "--repo", str(repo))
    assert code == 2
    assert data["error"]["code"] == "pr_not_open"


def test_approve_text_output(repo: Path, script: Script, capsys: Capsys) -> None:
    succeed(script)
    run_task(repo, T01)
    capsys.readouterr()
    assert main(["task", "approve", T01, "--repo", str(repo)]) == 0
    out = capsys.readouterr().out
    assert f"merged local:{BRANCH} into main" in out
    assert "approve review not sent" in out


def test_approve_help_describes_host_review(capsys: Capsys) -> None:
    with pytest.raises(SystemExit):
        main(["task", "approve", "--help"])
    out = capsys.readouterr().out
    assert "Azure sends an approval vote" in out
    assert "GitHub do not send" in out


def test_approve_text_reports_sent_review(
    repo: Path, script: Script, capsys: Capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    succeed(script)
    run_task(repo, T01)
    result = approve_task(repo, T01)
    result.reviewed = True
    monkeypatch.setattr("aifactory.review.approve_task", lambda *a, **kw: result)
    capsys.readouterr()
    assert main(["task", "approve", T01, "--repo", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "note: approve review sent" in out
    assert "review not sent" not in out


def test_return_runs_again_on_same_branch(repo: Path, script: Script, capsys: Capsys) -> None:
    succeed(script)
    first = run_task(repo, T01)
    old_worktree = Path(first.run.worktree)
    succeed(script, "# spec v2\n")

    code, data = cli_json(
        capsys, "task", "return", T01, "--note", "Přidej index", "--json", "--repo", str(repo)
    )

    assert code == 0, data
    planner_calls = [c for c in script.calls if c.agent == "planner"]
    assert len(planner_calls) == 2
    assert "Přidej index" in planner_calls[1].prompt
    run = data["data"]["run"]
    assert isinstance(run, dict)
    assert run["branch"] == BRANCH
    assert run["run_id"] != first.run.run_id
    assert run["base_sha"] == first.run.base_sha
    assert not old_worktree.exists()
    assert git(repo, "show", f"{BRANCH}:{SPEC}") == "# spec v2"

    store = TaskRunStore(trace_db(repo))
    try:
        prs = store.prs_for_task(T01)
    finally:
        store.close()
    assert len(prs) == 1
    assert prs[0].state == "open"
    assert "Přidej index" in prs[0].body
    costs = prs[0].body.split("## Náklady", 1)[1]
    assert costs.count("- běh ") == 2
    pr = data["data"]["pr"]
    assert isinstance(pr, dict) and pr["body"] == prs[0].body


def test_return_needs_note(repo: Path, script: Script) -> None:
    with pytest.raises(SystemExit):
        main(["task", "return", T01, "--repo", str(repo)])
    with pytest.raises(ReviewError) as info:
        return_task(repo, T01, "  ")
    assert info.value.code == "missing_note"


def test_closed_pr_is_recorded(repo: Path, script: Script, capsys: Capsys) -> None:
    succeed(script)
    run = run_task(repo, T01)
    close_pr(Path(run.run.worktree))

    code, data = cli_json(capsys, "task", "approve", T01, "--json", "--repo", str(repo))
    assert code == 2
    assert data["error"]["code"] == "pr_not_open"
    saved = stored_pr(repo)
    assert saved is not None and saved.state == "closed"

    code, data = cli_json(capsys, "task", "approve", T01, "--json", "--repo", str(repo))
    assert code == 2
    assert data["error"]["code"] == "pr_not_open"


def test_approve_without_pr(repo: Path, capsys: Capsys) -> None:
    code, data = cli_json(capsys, "task", "approve", T02, "--json", "--repo", str(repo))
    assert code == 2
    assert data["error"]["code"] == "no_pr"


class HostedLocal(LocalProvider):
    """Merges on the remote, like a hosting would; the local base is left behind."""

    def merge(
        self, pr: PullRequest, head_sha: str, subject: str, strategy: str | None = None
    ) -> str | None:
        remote = git(self.root, "remote", "get-url", "origin")
        clone = self.root.parent / "clone"
        if not clone.exists():
            subprocess.run(
                ["git", "clone", "-q", remote, str(clone)], check=True, capture_output=True
            )
        git(clone, "fetch", "-q", "origin")
        git(clone, "checkout", "-q", "main")
        git(clone, "reset", "-q", "--hard", "origin/main")
        git(clone, "merge", "-q", "--no-ff", f"origin/{pr.branch}", "-m", subject)
        git(clone, "push", "-q", "origin", "main")
        return git(clone, "rev-parse", "HEAD")


def test_approve_catches_up_base(repo: Path, script: Script, tmp_path: Path) -> None:
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True, capture_output=True
    )
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-q", "-u", "origin", "main")
    before = git(repo, "rev-parse", "main")
    provider = HostedLocal(repo, load_run_config(repo).config.settings)

    succeed(script)
    run = run_task(repo, T01, provider=provider)
    assert run.ok, (run.run.error, run.pr_error)
    assert git(origin, "rev-parse", BRANCH) == run.run.head_sha

    result = approve_task(repo, T01, provider=provider)

    assert result.merge_sha is not None and result.merge_sha != before
    assert git(origin, "rev-parse", "main") == result.merge_sha
    assert git(repo, "rev-parse", "main") == result.merge_sha
    assert result.base_sha == result.merge_sha
    assert result.warnings == []
    assert (repo / SPEC).is_file()
    assert "status: done" in (repo / TASK_FILE).read_text(encoding="utf-8")

    script.add("planner", ok())
    second = run_task(repo, T02, provider=provider)
    assert second.run.base_sha == result.merge_sha


def test_clean_removes_abandoned_worktree(repo: Path, script: Script, capsys: Capsys) -> None:
    script.on("planner", lambda wt: write(wt, "src/other.py", "x\n"))
    script.add("planner", ok())
    failed = run_task(repo, T01)
    assert failed.run.state == "failed"
    succeed(script)
    good = run_task(repo, T01)
    assert good.ok

    code, data = cli_json(capsys, "task", "clean", "--json", "--repo", str(repo))

    assert code == 0
    assert data["data"]["removed"] == [
        {
            "run_id": failed.run.run_id,
            "task_id": T01,
            "branch": failed.run.branch,
            "worktree": failed.run.worktree,
            "reason": "abandoned",
        }
    ]
    assert not Path(failed.run.worktree).exists()
    assert Path(good.run.worktree).is_dir()


def test_clean_removes_closed_pr_worktree(repo: Path, script: Script, capsys: Capsys) -> None:
    succeed(script)
    run = run_task(repo, T01)
    close_pr(Path(run.run.worktree))

    capsys.readouterr()
    assert main(["task", "clean", "--repo", str(repo)]) == 0
    out = capsys.readouterr().out
    assert f"removed {run.run.worktree} (closed, {T01})" in out
    assert "1 worktree(s) removed" in out
    assert not Path(run.run.worktree).exists()
    saved = stored_pr(repo)
    assert saved is not None and saved.state == "closed"


def test_clean_without_runs(repo: Path, capsys: Capsys) -> None:
    code, data = cli_json(capsys, "task", "clean", "--json", "--repo", str(repo))
    assert code == 0
    assert data == {"ok": True, "data": {"removed": []}, "error": None, "warnings": []}


def test_store_prs(tmp_path: Path) -> None:
    store = TaskRunStore(tmp_path / "trace.db")
    try:
        row = TaskPrRow(
            branch=BRANCH,
            task_id=T01,
            provider="local",
            pr_id=BRANCH,
            url=f"local:{BRANCH}",
            base="main",
            base_sha="a" * 40,
            title=f"{T01}: Schema",
            body="body",
            state="open",
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-01T00:00:00",
        )
        store.save_pr(row)
        assert store.pr_for_branch(BRANCH) == row
        assert store.latest_pr(T01) == row
        assert store.open_prs() == [row]
        assert row.request() == PullRequest(BRANCH, f"local:{BRANCH}", BRANCH, "main", row.title)

        store.update_pr(BRANCH, state="closed")
        closed = store.pr_for_branch(BRANCH)
        assert closed is not None
        assert closed.state == "closed"
        assert closed.updated_at != row.updated_at
        assert store.open_prs() == []
        assert store.open_pr(T01) is None
        assert store.latest_pr(T01) == closed
        with pytest.raises(ValueError):
            store.update_pr(BRANCH, nope=1)
        assert store.latest_pr(T02) is None
    finally:
        store.close()
