"""Where the outputs of a task run go: ``<docs_root>/specs|docs/<project>/<step>/``.

The spec and the documentation mirror the task's place in the backlog; an agent
with a non-empty `writes` may write the two outputs even outside its `writes`,
``writes: []`` may not. Fake harnesses only, no model.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from run_repo import DOC, SPEC, T01, Script, commit_all, fake_env, git, make_run_repo, ok, write

from aifactory.run import TaskRunError, run_task

CONFIG = ".factory/config.yaml"
PROJECT_INDEX = "backlog/M01-core/index.md"
STEP_INDEX = "backlog/M01-core/S01-model/index.md"
TASK_FILE = "backlog/M01-core/S01-model/M01-S01-T01-schema.md"


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


def project_index(extra: str = "") -> str:
    return f"---\nid: M01\ntitle: Core\nworkflow: plan-commit\n{extra}---\n\nJádro.\n"


def planner_writes(repo: Path, writes: str) -> None:
    write(
        repo,
        ".factory/agents.yaml",
        "defaults:\n  harness: claude\n  model: sonnet\n"
        f"agents:\n  - name: planner\n    writes: {writes}\n"
        "  - name: builder\n  - name: documenter\n",
    )
    commit_all(repo, "planner writes")


def add_config(repo: Path, text: str) -> None:
    config = repo / CONFIG
    config.write_text(config.read_text() + text)


def factory_branches(repo: Path) -> list[str]:
    out = git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/factory/")
    return [line for line in out.splitlines() if line]


def test_outputs_mirror_project_and_step(repo: Path, script: Script) -> None:
    assert SPEC == "specs/M01-core/S01-model/M01-S01-T01-schema.md"
    script.on("planner", lambda wt: write(wt, SPEC, "# spec\n"))
    script.add("planner", ok(artifacts=[SPEC]))

    result = run_task(repo, T01)

    assert result.run.state == "succeeded", result.run.error
    assert git(repo, "show", f"{result.run.branch}:{SPEC}") == "# spec"
    prompt = script.calls[0].prompt
    assert f"spec={SPEC}" in prompt
    assert f"doc={DOC}" in prompt
    assert f"- spec file: {SPEC}" in prompt
    assert f"- documentation file: {DOC}" in prompt


def test_outputs_live_under_docs_root(repo: Path, script: Script) -> None:
    config = repo / CONFIG
    config.write_text(config.read_text().replace("docs_root: .\n", "docs_root: factory\n"))
    shutil.move(repo / "backlog", repo / "factory" / "backlog")
    commit_all(repo, "docs root factory")
    spec = "factory/specs/M01-core/S01-model/M01-S01-T01-schema.md"
    script.on("planner", lambda wt: write(wt, spec, "# spec\n"))
    script.add("planner", ok(artifacts=[spec]))

    result = run_task(repo, T01)

    assert result.run.state == "succeeded", result.run.error
    prompt = script.calls[0].prompt
    assert f"spec={spec}" in prompt
    assert "doc=factory/docs/M01-core/S01-model/M01-S01-T01-schema.md" in prompt


def test_old_folder_keys_are_ignored(repo: Path, script: Script) -> None:
    add_config(repo, "specs_dir: old/specs\ndocs_dir: old/docs\nbacklog_dir: backlog\n")
    write(repo, PROJECT_INDEX, project_index("specs_dir: docs/M07\nworkdir: missing\n"))
    write(
        repo,
        TASK_FILE,
        f"---\nid: {T01}\ntitle: Schema\nstatus: todo\ndocs_dir: ../x\n---\n\n## Zadání\nS.\n",
    )
    commit_all(repo, "old keys")
    script.add("planner", ok())

    result = run_task(repo, T01)

    assert result.run.state == "succeeded", result.run.error
    prompt = script.calls[0].prompt
    assert f"spec={SPEC}" in prompt
    assert f"doc={DOC}" in prompt


def test_planner_write_outside_writes_and_outputs_is_reverted(repo: Path, script: Script) -> None:
    write(repo, STEP_INDEX, "---\nid: M01-S01\ntitle: Model\nwrites: [src/app/, specs/]\n---\n")
    planner_writes(repo, "[src/]")
    other = "specs/M01-core/other.md"

    def plan(wt: Path) -> None:
        write(wt, SPEC, "# spec\n")
        write(wt, other, "x\n")

    script.on("planner", plan)
    script.add("planner", ok(artifacts=[SPEC]))

    result = run_task(repo, T01)

    assert result.run.state == "failed"
    worktree = Path(result.run.worktree)
    assert not (worktree / other).exists()
    assert (worktree / SPEC).exists()
    error = result.run.error or ""
    assert f"worktree: {other}" in error
    assert f"worktree: {SPEC}" not in error


def test_planner_write_outside_scope_is_reverted(repo: Path, script: Script) -> None:
    planner_writes(repo, "[specs/, src/]")

    def plan(wt: Path) -> None:
        write(wt, SPEC, "# spec\n")
        write(wt, "src/other.py", "x\n")

    script.on("planner", plan)
    script.add("planner", ok(artifacts=[SPEC]))

    result = run_task(repo, T01)

    assert result.run.state == "failed"
    assert not (Path(result.run.worktree) / "src" / "other.py").exists()
    assert "src/other.py" in (result.run.error or "")


def test_agent_with_empty_writes_cannot_write_outputs(repo: Path, script: Script) -> None:
    planner_writes(repo, "[]")
    script.on("planner", lambda wt: write(wt, SPEC, "# spec\n"))
    script.add("planner", ok(artifacts=[SPEC]))

    result = run_task(repo, T01)

    assert result.run.state == "failed"
    assert not (Path(result.run.worktree) / SPEC).exists()
    assert SPEC in (result.run.error or "")


@pytest.mark.parametrize("forbidden", [True, False])
def test_agent_workdir_preserves_root_outputs_and_scope(
    repo: Path, script: Script, forbidden: bool
) -> None:
    write(repo, "packages/core/README.md", "Core\n")
    planner_writes(repo, "[specs/]")
    add_config(repo, "workdir: packages/core\n")
    commit_all(repo, "project cwd")
    # Uncommitted changes must not alter the cwd read from base.
    add_config(repo, "workdir: missing\n")

    def plan(cwd: Path) -> None:
        assert cwd.name == "core" and cwd.parent.name == "packages"
        wt = cwd.parent.parent
        write(wt, SPEC, "# spec\n")
        if forbidden:
            write(wt, "src/other.py", "forbidden\n")

    script.on("planner", plan)
    script.add("planner", ok(artifacts=[SPEC]))
    result = run_task(repo, T01)
    assert Path(script.calls[0].cwd) == Path(result.run.worktree) / "packages/core"
    assert result.run.state == ("failed" if forbidden else "succeeded"), result.run.error
    assert (Path(result.run.worktree) / SPEC).exists()
    assert not (Path(result.run.worktree) / "src/other.py").exists()
    assert "Repository root:" in script.calls[0].prompt


@pytest.mark.parametrize("value", ["missing", "src/app/model.py"])
def test_invalid_workdir_stops_before_start(repo: Path, script: Script, value: str) -> None:
    add_config(repo, f"workdir: {value}\n")
    commit_all(repo, "invalid cwd")
    with pytest.raises(TaskRunError) as caught:
        run_task(repo, T01)
    assert caught.value.code == "invalid_config"
    assert script.calls == []
    assert factory_branches(repo) == []


def test_workdir_symlink_in_base_is_rejected(repo: Path, script: Script) -> None:
    add_config(repo, "workdir: linked\n")
    git(repo, "add", "-A")
    # Staged as a symlink entry: the check reads base, and os.symlink needs a privilege on Windows.
    target = repo.parent / "link-target"
    target.write_bytes(b"src/app")
    blob = git(repo, "hash-object", "-w", str(target))
    git(repo, "update-index", "--add", "--cacheinfo", f"120000,{blob},linked")
    git(repo, "commit", "-q", "-m", "symlink cwd")
    git(repo, "checkout", "--", "linked")
    with pytest.raises(TaskRunError) as caught:
        run_task(repo, T01)
    assert caught.value.code == "invalid_config"
    assert script.calls == []
    assert factory_branches(repo) == []
