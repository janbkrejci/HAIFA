"""``run_task``: worktree, branch, ``task_runs``, write guard and task-named outputs."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from run_repo import (
    DOC,
    SPEC,
    T01,
    T02,
    Script,
    commit_all,
    fake_env,
    git,
    make_run_repo,
    ok,
    write,
)

from aifactory.cli import main
from aifactory.harness.override import StepOverride, effective_agent
from aifactory.run import TaskRunError, TaskRunRow, TaskRunStore, run_task
from aifactory.run import task as task_mod
from aifactory.run.store import ABORTED, RUNNING
from cli_json import read_envelope

Capsys = pytest.CaptureFixture[str]


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


def trace_db(repo: Path) -> Path:
    return repo / ".factory" / "trace.db"


def factory_branches(repo: Path) -> list[str]:
    out = git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/factory/")
    return [line for line in out.splitlines() if line]


def assert_nothing_created(repo: Path) -> None:
    worktrees = repo / ".factory" / "worktrees"
    assert not worktrees.exists() or not any(worktrees.iterdir())
    assert factory_branches(repo) == []


def test_run_creates_worktree_branch_and_row(repo: Path, script: Script) -> None:
    def plan(wt: Path) -> None:
        write(wt, SPEC, "# spec\n")
        write(wt, "src/app/model.py", "x = 1\n")

    script.on("planner", plan)
    script.add("planner", ok(artifacts=[SPEC], commit_message="Add schema spec"))

    result = run_task(repo, T01)

    row = result.run
    assert row.state == "succeeded", row.error
    worktree = Path(row.worktree)
    assert worktree == repo / ".factory" / "worktrees" / row.run_id
    assert worktree.is_dir()
    assert row.branch == f"factory/{T01}-1"
    assert git(repo, "show", f"{row.branch}:{SPEC}") == "# spec"
    assert git(repo, "log", "-1", "--format=%s", row.branch) == "Add schema spec"
    assert git(repo, "status", "--porcelain") == ""
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert result.workflow_run is not None and result.workflow_run.exit_code == 0

    store = TaskRunStore(trace_db(repo))
    try:
        stored = store.get(row.run_id)
    finally:
        store.close()
    assert stored is not None
    assert stored.state == "succeeded"
    assert stored.head_sha == git(repo, "rev-parse", row.branch)

    script.add("planner", ok())
    second = run_task(repo, T01)
    assert second.run.state == "succeeded", second.run.error
    assert second.run.branch == f"factory/{T01}-2"


def test_outputs_are_named_by_task(repo: Path, script: Script) -> None:
    script.on("planner", lambda wt: write(wt, SPEC, "# spec\n"))
    script.add("planner", ok(artifacts=[SPEC]))
    result = run_task(repo, T01)
    assert result.run.state == "succeeded", result.run.error
    run_id = result.run.run_id
    worktree = result.run.worktree
    session = str(repo / ".factory" / "data" / "sessions" / run_id)

    prompt = script.calls[0].prompt
    assert SPEC in prompt and DOC in prompt
    assert f"spec={SPEC}" in prompt
    assert f"doc={DOC}" in prompt
    assert "{{spec_path}}" not in prompt and "{{doc_path}}" not in prompt
    # The run id appears only inside the worktree and session paths, never as a name.
    assert run_id not in prompt.replace(worktree, "").replace(session, "")
    assert git(repo, "log", "-1", "--format=%s", result.run.branch) == f"{T01}: done"

    script.on("planner", lambda wt: write(wt, f"specs/{wt.name}_plan.md", "plan\n"))
    script.add("planner", ok())
    failed = run_task(repo, T01)
    assert failed.run.state == "failed"
    wrong = f"specs/{failed.run.run_id}_plan.md"
    assert not (Path(failed.run.worktree) / wrong).exists()
    assert failed.run.error is not None and wrong in failed.run.error


@pytest.mark.parametrize("harness", ["claude", "codex", "pi"])
def test_write_to_main_checkout_is_reverted(tmp_path: Path, script: Script, harness: str) -> None:
    repo = make_run_repo(tmp_path / "repo", harness)

    def stray(wt: Path) -> None:
        write(repo, "app_docs/x.md", "stray\n")
        write(repo, "README.md", "hijacked\n")

    script.on("planner", stray)
    script.add("planner", ok())

    result = run_task(repo, T01)

    assert result.run.state == "failed"
    error = result.run.error or ""
    assert "main checkout" in error
    assert "app_docs/x.md" in error and "README.md" in error
    assert not (repo / "app_docs" / "x.md").exists()
    assert (repo / "README.md").read_text(encoding="utf-8") == "readme\n"
    assert git(repo, "status", "--porcelain") == ""
    assert [call.harness for call in script.calls] == [harness]
    assert Path(script.calls[0].cwd).resolve() == Path(result.run.worktree)


def test_agent_reverting_main_checkout_work_is_restored(repo: Path, script: Script) -> None:
    write(repo, "README.md", "engineer wip\n")
    write(repo, "notes/wip.txt", "draft\n")

    def wipe(wt: Path) -> None:
        git(repo, "checkout", "--", ".")
        git(repo, "clean", "-fd")

    script.on("planner", wipe)
    script.add("planner", ok())

    result = run_task(repo, T01)

    assert result.run.state == "failed"
    assert (repo / "README.md").read_text(encoding="utf-8") == "engineer wip\n"
    assert (repo / "notes" / "wip.txt").read_text(encoding="utf-8") == "draft\n"
    error = result.run.error or ""
    assert "main checkout: README.md" in error
    assert "main checkout: notes/wip.txt" in error
    assert "cannot restore" not in error
    assert "guard_backup" in error


def test_write_outside_writes_is_reverted(repo: Path, script: Script) -> None:
    script.on("planner", lambda wt: write(wt, "src/other.py", "x\n"))
    script.add("planner", ok())

    result = run_task(repo, T01)

    assert result.run.state == "failed"
    assert not (Path(result.run.worktree) / "src" / "other.py").exists()
    error = result.run.error or ""
    assert "worktree: src/other.py" in error
    assert f"task {T01} may only change" in error


def test_agent_commit_outside_writes_is_reverted(repo: Path, script: Script) -> None:
    base = git(repo, "rev-parse", "HEAD")

    def commit(wt: Path) -> None:
        write(wt, "src/other.py", "x\n")
        git(wt, "add", "-A")
        git(wt, "commit", "-q", "-m", "sneaky")

    script.on("planner", commit)
    script.add("planner", ok())

    result = run_task(repo, T01)

    assert result.run.state == "failed"
    worktree = Path(result.run.worktree)
    assert git(worktree, "rev-parse", "HEAD") == base
    assert not (worktree / "src" / "other.py").exists()
    assert git(worktree, "status", "--porcelain") == ""
    error = result.run.error or ""
    assert "HEAD" in error and "src/other.py" in error


def test_breach_is_reverted_even_when_gate_fails(repo: Path, script: Script) -> None:
    script.on("planner", lambda wt: write(repo, "app_docs/x.md", "stray\n"))
    script.add("planner", ok(artifacts=["specs/missing.md"]))

    result = run_task(repo, T01)

    assert result.run.state == "failed"
    assert not (repo / "app_docs" / "x.md").exists()
    assert "app_docs/x.md" in (result.run.error or "")


def test_artifact_in_main_checkout_is_rejected(repo: Path, script: Script) -> None:
    """Z1 from the prototype report: a plan written into the main checkout used to pass."""
    script.on("planner", lambda wt: write(repo, SPEC, "# spec\n"))
    script.add("planner", ok(artifacts=[str(repo / SPEC)]))

    result = run_task(repo, T01)

    assert result.run.state == "failed"
    error = result.run.error or ""
    assert f"main checkout: {SPEC}" in error
    assert not (repo / SPEC).exists()


def test_empty_commit_does_not_fail(repo: Path, script: Script) -> None:
    script.add("planner", ok(artifacts=[]))

    result = run_task(repo, T01)

    assert result.run.state == "succeeded", result.run.error
    assert result.workflow_run is not None
    assert result.workflow_run.results["commit"]["committed"] is False
    assert git(repo, "rev-parse", result.run.branch) == git(repo, "rev-parse", "main")


def _row(run_id: str, pid: int) -> TaskRunRow:
    return TaskRunRow(
        run_id=run_id,
        task_id=T01,
        branch=f"factory/{T01}-9",
        worktree="/nowhere",
        base="main",
        base_sha="0" * 40,
        head_sha=None,
        state=RUNNING,
        started_at="2026-01-01T00:00:00.000+00:00",
        pid=pid,
    )


def test_second_start_of_running_task_fails(repo: Path, script: Script, capsys: Capsys) -> None:
    store = TaskRunStore(trace_db(repo))
    try:
        store.claim(_row("busy0001", os.getpid()))
    finally:
        store.close()

    for force in (False, True):
        with pytest.raises(TaskRunError) as exc:
            run_task(repo, T01, force=force)
        assert exc.value.code == "already_running"

    capsys.readouterr()
    assert main(["task", "run", T01, "--json", "--repo", str(repo)]) == 2
    data = read_envelope(capsys)
    assert data["ok"] is False
    assert data["error"]["code"] == "already_running"
    assert script.calls == []
    assert factory_branches(repo) == []


def test_running_row_of_dead_process_is_aborted(repo: Path, script: Script) -> None:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    store = TaskRunStore(trace_db(repo))
    try:
        store.claim(_row("dead0001", child.pid))
    finally:
        store.close()
    script.add("planner", ok())

    result = run_task(repo, T01)

    assert result.run.state == "succeeded", result.run.error
    store = TaskRunStore(trace_db(repo))
    try:
        dead = store.get("dead0001")
    finally:
        store.close()
    assert dead is not None and dead.state == ABORTED
    # the dead run's branch number still counts
    assert result.run.branch == f"factory/{T01}-10"


def test_prompt_paths_stay_in_worktree_or_session(tmp_path: Path, script: Script) -> None:
    repo = make_run_repo(tmp_path / "repo")
    script.add("planner", ok())
    result = run_task(repo, T01, note="mind the schema")
    assert result.run.state == "succeeded", result.run.error
    worktree = result.run.worktree
    session = str(repo / ".factory" / "data" / "sessions" / result.run.run_id)

    roots = {str(repo), str(tmp_path / "repo")}
    texts = [text for call in script.calls for text in (call.prompt, call.system)]
    assert script.calls and "mind the schema" in script.calls[0].prompt
    for root in roots:
        pattern = re.compile(re.escape(root) + r"[^\s`'\"<>)]*")
        for text in texts:
            for found in pattern.findall(text):
                resolved = found.replace(str(tmp_path / "repo"), str(repo), 1)
                assert resolved.startswith((worktree, session)), found


@pytest.mark.parametrize(
    ("task_id", "setup", "code"),
    [
        (T02, None, "unmet_dependencies"),
        ("NOPE", None, "unknown_task"),
        ("M01-S01-T03", "working_tree_task", "task_not_in_base"),
        ("M01-S02-T01", "no_writes", "no_writes"),
        ("M01-S01-T04", "unknown_workflow", "unknown_workflow"),
        ("M01-S01-T04", "task_workflow_null", "no_workflow"),
        ("M01-S02-T01", "step_workflow_null", "no_workflow"),
    ],
)
def test_checks_before_start(
    repo: Path, script: Script, task_id: str, setup: str | None, code: str
) -> None:
    step = "backlog/M01-core/S01-model"
    if setup == "working_tree_task":
        write(repo, f"{step}/M01-S01-T03-new.md", "---\nid: M01-S01-T03\ntitle: New\n---\n")
    elif setup == "no_writes":
        write(repo, "backlog/M01-core/S02-api/index.md", "---\nid: M01-S02\ntitle: Api\n---\n")
        write(
            repo,
            "backlog/M01-core/S02-api/M01-S02-T01-endpoint.md",
            "---\nid: M01-S02-T01\ntitle: Endpoint\nstatus: todo\nwrites: []\n---\n",
        )
        commit_all(repo, "no writes")
    elif setup == "unknown_workflow":
        write(
            repo,
            f"{step}/M01-S01-T04-odd.md",
            "---\nid: M01-S01-T04\ntitle: Odd\nstatus: todo\nworkflow: nope\n---\n",
        )
        commit_all(repo, "odd workflow")
    elif setup == "task_workflow_null":
        write(
            repo,
            f"{step}/M01-S01-T04-open.md",
            "---\nid: M01-S01-T04\ntitle: Open\nstatus: todo\nworkflow: null\n---\n",
        )
        commit_all(repo, "task without workflow")
    elif setup == "step_workflow_null":
        write(
            repo,
            "backlog/M01-core/S02-api/index.md",
            "---\nid: M01-S02\ntitle: Api\nworkflow: null\nwrites: [src/api/]\n---\n",
        )
        write(
            repo,
            "backlog/M01-core/S02-api/M01-S02-T01-endpoint.md",
            "---\nid: M01-S02-T01\ntitle: Endpoint\nstatus: todo\n---\n",
        )
        commit_all(repo, "step without workflow")

    with pytest.raises(TaskRunError) as exc:
        run_task(repo, task_id)

    assert exc.value.code == code
    assert_nothing_created(repo)
    assert script.calls == []


def test_task_without_writes_runs_with_the_default(repo: Path, script: Script) -> None:
    """No level sets `writes`: the task may write the whole repo and its workflow runs."""
    write(repo, "backlog/M01-core/S02-api/index.md", "---\nid: M01-S02\ntitle: Api\n---\n")
    write(
        repo,
        "backlog/M01-core/S02-api/M01-S02-T01-endpoint.md",
        "---\nid: M01-S02-T01\ntitle: Endpoint\nstatus: todo\n---\n",
    )
    commit_all(repo, "no writes key")
    script.on("planner", lambda wt: write(wt, "docs/endpoint.md", "# endpoint\n"))
    script.add("planner", ok())
    result = run_task(repo, "M01-S02-T01")
    assert result.run.state == "succeeded", result.run.error
    assert [call.agent for call in script.calls] == ["planner"]
    assert git(repo, "show", f"{result.run.branch}:docs/endpoint.md") == "# endpoint"


def no_run_rows(repo: Path, task_id: str) -> bool:
    if not trace_db(repo).exists():
        return True
    store = TaskRunStore(trace_db(repo))
    try:
        return store.for_task(task_id) == []
    finally:
        store.close()


def _task_without_workflow(repo: Path) -> str:
    """A task with `workflow: null`, unmet `depends_on` and no own writes (step S02 has none)."""
    write(repo, "backlog/M01-core/S02-api/index.md", "---\nid: M01-S02\ntitle: Api\n---\n")
    write(
        repo,
        "backlog/M01-core/S02-api/M01-S02-T01-endpoint.md",
        f"---\nid: M01-S02-T01\ntitle: Endpoint\nstatus: todo\nworkflow: null\n"
        f"depends_on: [{T01}]\n---\n",
    )
    commit_all(repo, "task without workflow")
    return "M01-S02-T01"


def test_no_workflow_even_with_force(repo: Path, script: Script) -> None:
    task_id = _task_without_workflow(repo)
    for force in (False, True):
        with pytest.raises(TaskRunError) as exc:
            run_task(repo, task_id, force=force)
        assert exc.value.code == "no_workflow"
    assert_nothing_created(repo)
    assert no_run_rows(repo, task_id)
    assert script.calls == []


@pytest.mark.parametrize("flags", [[], ["--force"], ["--auto"], ["--force", "--auto"]])
def test_cli_run_without_workflow_fails(
    repo: Path, script: Script, capsys: Capsys, flags: list[str]
) -> None:
    task_id = _task_without_workflow(repo)
    capsys.readouterr()
    assert main(["task", "run", task_id, *flags, "--json", "--repo", str(repo)]) == 2
    data = read_envelope(capsys)
    assert data["ok"] is False
    assert data["error"]["code"] == "no_workflow"
    assert_nothing_created(repo)
    assert no_run_rows(repo, task_id)
    assert script.calls == []


def test_force_runs_despite_unmet_dependencies(repo: Path, script: Script) -> None:
    script.add("planner", ok())
    result = run_task(repo, T02, force=True)
    assert result.run.state == "succeeded", result.run.error
    assert result.run.branch == f"factory/{T02}-1"


def test_config_comes_from_base(repo: Path, script: Script) -> None:
    write(repo, ".factory/prompts/planner/user.md", "CHANGED {{prompt}}\n")
    script.add("planner", ok())

    result = run_task(repo, T01)

    assert result.run.state == "succeeded", result.run.error
    assert "CHANGED" not in script.calls[0].prompt
    assert result.warnings
    # the operator's uncommitted change in the main checkout is left alone
    assert (repo / ".factory/prompts/planner/user.md").read_text(
        encoding="utf-8"
    ) == "CHANGED {{prompt}}\n"


# ── per-run roster override (task run --harness/--model/--thinking) ─────────


def test_agents_override_changes_every_role(repo: Path) -> None:
    rc = task_mod._load(repo)
    changed = task_mod.apply_agents_override(rc, {"harness": "codex", "thinking": "high"})
    assert {a.harness for a in changed.config.agents.agents} == {"codex"}
    # a harness switch without a model takes that harness's preset model
    assert {a.model for a in changed.config.agents.agents} == {"gpt-6.1-sol"}
    assert {a.thinking for a in changed.config.agents.agents} == {"high"}
    # in memory only: the loaded config is untouched
    assert {a.harness for a in rc.config.agents.agents} == {"claude"}
    same = task_mod.apply_agents_override(rc, {"model": "opus"})
    assert {(a.harness, a.model) for a in same.config.agents.agents} == {("claude", "opus")}
    assert task_mod.apply_agents_override(rc, None) is rc


def test_override_with_a_model_the_harness_rejects(repo: Path) -> None:
    rc = task_mod._load(repo)
    with pytest.raises(TaskRunError) as err:
        task_mod.apply_agents_override(rc, {"harness": "codex", "model": "a/b/c"})
    assert err.value.code == "invalid_override"


def test_step_override_still_wins_over_the_run_override(repo: Path) -> None:
    rc = task_mod.apply_agents_override(task_mod._load(repo), {"harness": "codex"})
    agent = rc.config.agents.agents[0]
    stepped = effective_agent(agent, StepOverride(harness="claude", model="sonnet"))
    assert (stepped.harness, stepped.model) == ("claude", "sonnet")


@pytest.mark.parametrize(
    "override",
    [{"harness": "nope"}, {"thinking": "loud"}, {"colour": "red"}],
)
def test_invalid_override_does_not_start(
    repo: Path, script: Script, override: dict[str, str]
) -> None:
    with pytest.raises(TaskRunError) as err:
        run_task(repo, T01, agents_override=override)
    assert err.value.code == "invalid_override"
    assert_nothing_created(repo)


def test_override_is_noted_on_the_run(repo: Path, script: Script) -> None:
    script.on("planner", lambda wt: write(wt, SPEC, "# spec\n"))
    script.add("planner", ok(artifacts=[SPEC]))
    result = run_task(repo, T01, note="pozor", agents_override={"model": "opus"})
    assert result.run.note == "pozor [přepis rosteru: model=opus]"


def test_task_harness_switch_uses_machine_model_instead_of_project_model(repo: Path) -> None:
    from aifactory import backlog as core

    project = repo / "backlog/M01-core/index.md"
    project.write_text(
        project.read_text().replace(
            "workflow: plan-commit", "workflow: plan-commit\nharness: claude\nmodel: opus"
        )
    )
    task_path = repo / "backlog/M01-core/S01-model/M01-S01-T01-schema.md"
    task_path.write_text(
        task_path.read_text().replace("status: todo", "status: todo\nharness: codex")
    )
    task = core.load_for_edit(repo).by_id[T01]
    assert isinstance(task, core.Task)
    assert task_mod.task_harness_values(task) == {"harness": "codex"}


def test_project_and_task_model_choices_reach_run(repo: Path, script: Script) -> None:
    project = repo / "backlog/M01-core/index.md"
    project.write_text(
        project.read_text().replace(
            "workflow: plan-commit", "workflow: plan-commit\nharness: claude\nmodel: sonnet"
        )
    )
    task_path = repo / "backlog/M01-core/S01-model/M01-S01-T01-schema.md"
    task_path.write_text(task_path.read_text().replace("status: todo", "status: todo\nmodel: opus"))
    commit_all(repo, "Task model")
    script.on("planner", lambda wt: write(wt, SPEC, "# spec\n"))
    script.add("planner", ok(artifacts=[SPEC]))
    result = run_task(repo, T01)
    assert result.run.note == "[přepis rosteru: harness=claude, model=opus]"
