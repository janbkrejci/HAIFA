"""``specs_dir``/``docs_dir`` of the backlog: where the outputs of a task run go.

The nearest value (task, step, project) wins over ``.factory/config.yaml``; an
agent with a non-empty `writes` may write the two outputs even outside its
`writes`, ``writes: []`` may not. Fake harnesses only, no model.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from run_repo import T01, Script, commit_all, fake_env, git, make_run_repo, ok, write

from aifactory.run import TaskRunError, run_task

PROJECT_INDEX = "backlog/M01-core/index.md"
STEP_INDEX = "backlog/M01-core/S01-model/index.md"
TASK_FILE = "backlog/M01-core/S01-model/M01-S01-T01-schema.md"
M07_SPEC = "docs/M07/specs/M01-S01-T01-schema.md"
M07_DOC = "docs/M07/app/M01-S01-T01-schema.md"


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


def project_index(extra: str = "") -> str:
    return f"---\nid: M01\ntitle: Core\nworkflow: plan-commit\n{extra}---\n\nJádro.\n"


def step_index(extra: str = "", writes: str = "[src/app/]") -> str:
    return f"---\nid: M01-S01\ntitle: Model\nwrites: {writes}\n{extra}---\n\nModel.\n"


def task_file(extra: str = "") -> str:
    return f"---\nid: {T01}\ntitle: Schema\nstatus: todo\n{extra}---\n\n## Zadání\nSchéma.\n"


def planner_writes(repo: Path, writes: str) -> None:
    write(
        repo,
        ".factory/agents.yaml",
        "defaults:\n  harness: claude\n  model: sonnet\n"
        f"agents:\n  - name: planner\n    writes: {writes}\n"
        "  - name: builder\n  - name: documenter\n",
    )


def project_m07(repo: Path, *, step_writes: str = "[src/app/]", planner: str = "[specs/]") -> None:
    write(repo, PROJECT_INDEX, project_index("specs_dir: docs/M07/specs\ndocs_dir: docs/M07/app\n"))
    write(repo, STEP_INDEX, step_index(writes=step_writes))
    planner_writes(repo, planner)
    commit_all(repo, "project output dirs")


def factory_branches(repo: Path) -> list[str]:
    out = git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/factory/")
    return [line for line in out.splitlines() if line]


def test_project_specs_dir_receives_spec(repo: Path, script: Script) -> None:
    project_m07(repo)
    script.on("planner", lambda wt: write(wt, M07_SPEC, "# spec\n"))
    script.add("planner", ok(artifacts=[M07_SPEC]))

    result = run_task(repo, T01)

    assert result.run.state == "succeeded", result.run.error
    assert git(repo, "show", f"{result.run.branch}:{M07_SPEC}") == "# spec"
    prompt = script.calls[0].prompt
    assert f"spec={M07_SPEC}" in prompt
    assert f"doc={M07_DOC}" in prompt
    assert f"- spec file: {M07_SPEC}" in prompt
    assert f"- documentation file: {M07_DOC}" in prompt


def test_step_and_task_override_project(repo: Path, script: Script) -> None:
    write(repo, PROJECT_INDEX, project_index("specs_dir: docs/M07/specs\n"))
    write(repo, STEP_INDEX, step_index("specs_dir: docs/S01\n"))
    commit_all(repo, "step specs_dir")
    script.add("planner", ok())

    first = run_task(repo, T01)

    assert first.run.state == "succeeded", first.run.error
    prompt = script.calls[0].prompt
    assert "spec=docs/S01/M01-S01-T01-schema.md" in prompt
    assert "doc=app_docs/M01-S01-T01-schema.md" in prompt

    write(repo, TASK_FILE, task_file("specs_dir: docs/T\n"))
    commit_all(repo, "task specs_dir")
    script.add("planner", ok())

    second = run_task(repo, T01)

    assert second.run.state == "succeeded", second.run.error
    assert "spec=docs/T/M01-S01-T01-schema.md" in script.calls[1].prompt


def test_planner_write_outside_writes_and_outputs_is_reverted(repo: Path, script: Script) -> None:
    project_m07(repo, step_writes="[src/app/, docs/M07/]")
    other = "docs/M07/specs/other.md"

    def plan(wt: Path) -> None:
        write(wt, M07_SPEC, "# spec\n")
        write(wt, other, "x\n")

    script.on("planner", plan)
    script.add("planner", ok(artifacts=[M07_SPEC]))

    result = run_task(repo, T01)

    assert result.run.state == "failed"
    worktree = Path(result.run.worktree)
    assert not (worktree / other).exists()
    assert (worktree / M07_SPEC).exists()
    error = result.run.error or ""
    assert f"worktree: {other}" in error
    assert f"worktree: {M07_SPEC}" not in error


def test_planner_write_outside_scope_is_reverted(repo: Path, script: Script) -> None:
    project_m07(repo)

    def plan(wt: Path) -> None:
        write(wt, M07_SPEC, "# spec\n")
        write(wt, "src/other.py", "x\n")

    script.on("planner", plan)
    script.add("planner", ok(artifacts=[M07_SPEC]))

    result = run_task(repo, T01)

    assert result.run.state == "failed"
    assert not (Path(result.run.worktree) / "src" / "other.py").exists()
    assert "src/other.py" in (result.run.error or "")


def test_agent_with_empty_writes_cannot_write_outputs(repo: Path, script: Script) -> None:
    project_m07(repo, planner="[]")
    script.on("planner", lambda wt: write(wt, M07_SPEC, "# spec\n"))
    script.add("planner", ok(artifacts=[M07_SPEC]))

    result = run_task(repo, T01)

    assert result.run.state == "failed"
    assert not (Path(result.run.worktree) / M07_SPEC).exists()
    assert M07_SPEC in (result.run.error or "")


@pytest.mark.parametrize(
    ("where", "value"),
    [("project", "../x"), ("project", "/abs"), ("task", "5"), ("task", "''")],
)
def test_invalid_output_dir_stops_before_start(
    repo: Path, script: Script, where: str, value: str
) -> None:
    if where == "project":
        write(repo, PROJECT_INDEX, project_index(f"specs_dir: {value}\n"))
    else:
        write(repo, TASK_FILE, task_file(f"docs_dir: {value}\n"))
    commit_all(repo, "invalid output dir")

    with pytest.raises(TaskRunError) as caught:
        run_task(repo, T01)

    assert caught.value.code == "invalid_output_dir"
    assert script.calls == []
    worktrees = repo / ".factory" / "worktrees"
    assert not worktrees.exists() or not any(worktrees.iterdir())
    assert factory_branches(repo) == []


@pytest.mark.parametrize("project_override", [True, False])
@pytest.mark.parametrize("forbidden", [True, False])
def test_agent_workdir_preserves_root_outputs_and_scope(
    repo: Path, script: Script, project_override: bool, forbidden: bool
) -> None:

    write(repo, "packages/core/README.md", "Core\n")
    project_m07(repo)
    if project_override:
        write(
            repo,
            PROJECT_INDEX,
            project_index(
                "workdir: packages/core\nspecs_dir: docs/M07/specs\ndocs_dir: docs/M07/app\n"
            ),
        )
    else:
        config = repo / ".factory/config.yaml"
        config.write_text(config.read_text() + "workdir: packages/core\n")
    commit_all(repo, "project cwd")
    # Uncommitted changes must not alter the cwd read from base.
    write(repo, PROJECT_INDEX, project_index("workdir: missing\n"))

    def plan(cwd: Path) -> None:
        assert cwd.name == "core" and cwd.parent.name == "packages"
        wt = cwd.parent.parent
        write(wt, M07_SPEC, "# spec\n")
        if forbidden:
            write(wt, "src/other.py", "forbidden\n")

    script.on("planner", plan)
    script.add("planner", ok(artifacts=[M07_SPEC]))
    result = run_task(repo, T01)
    assert Path(script.calls[0].cwd) == Path(result.run.worktree) / "packages/core"
    assert result.run.state == ("failed" if forbidden else "succeeded"), result.run.error
    assert (Path(result.run.worktree) / M07_SPEC).exists()
    assert not (Path(result.run.worktree) / "src/other.py").exists()
    assert "Repository root:" in script.calls[0].prompt


@pytest.mark.parametrize("value", ["../x", "/abs", "C:/abs", "missing", "src/app/model.py"])
def test_invalid_workdir_stops_before_start(repo: Path, script: Script, value: str) -> None:
    write(repo, PROJECT_INDEX, project_index(f"workdir: {value}\n"))
    commit_all(repo, "invalid cwd")
    with pytest.raises(TaskRunError) as caught:
        run_task(repo, T01)
    assert caught.value.code == "invalid_config"
    assert script.calls == []
    assert factory_branches(repo) == []


def test_two_projects_run_with_distinct_workdirs_and_outputs(repo: Path, script: Script) -> None:
    for project in ("M01", "M02"):
        write(repo, f"packages/{project}/README.md", project)
        index = PROJECT_INDEX if project == "M01" else "backlog/M02-ui/index.md"
        write(
            repo,
            index,
            f"---\nid: {project}\ntitle: {project}\nworkflow: plan-commit\n"
            f"workdir: packages/{project}\nspecs_dir: out/{project}/specs\n"
            f"docs_dir: out/{project}/docs\nwrites: [src/app/]\n---\n",
        )
    second = "M02-S01-T01"
    write(repo, "backlog/M02-ui/S01-view/index.md", "---\nid: M02-S01\ntitle: View\n---\n")
    write(
        repo,
        f"backlog/M02-ui/S01-view/{second}-view.md",
        f"---\nid: {second}\ntitle: View\nstatus: todo\n---\n",
    )
    commit_all(repo, "two projects")
    from aifactory.engine import agents

    original_adapters = dict(agents.INTERFACES)

    for task_id, project, slug in ((T01, "M01", "schema"), (second, "M02", "view")):
        spec = f"out/{project}/specs/{task_id}-{slug}.md"

        def plan(cwd: Path, spec: str = spec, project: str = project) -> None:
            assert cwd.name == project
            write(cwd.parent.parent, spec, "# spec\n")

        script.on("planner", plan)
        script.add("planner", ok(artifacts=[spec]))
        result = run_task(repo, task_id)
        assert result.run.state == "succeeded", result.run.error
        assert Path(script.calls[-1].cwd) == Path(result.run.worktree) / f"packages/{project}"
        assert (Path(result.run.worktree) / spec).exists()
        assert f"doc=out/{project}/docs/{task_id}-{slug}.md" in script.calls[-1].prompt
    assert agents.INTERFACES == original_adapters


def test_workdir_symlink_in_base_is_rejected(repo: Path, script: Script) -> None:
    (repo / "linked").symlink_to("src/app", target_is_directory=True)
    write(repo, PROJECT_INDEX, project_index("workdir: linked\n"))
    commit_all(repo, "symlink cwd")
    with pytest.raises(TaskRunError) as caught:
        run_task(repo, T01)
    assert caught.value.code == "invalid_config"
    assert script.calls == []
    assert factory_branches(repo) == []
