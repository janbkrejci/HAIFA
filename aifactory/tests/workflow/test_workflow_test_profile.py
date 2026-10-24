"""One tester selects checks and shares project knowledge without extra model calls."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from workflow_fakes import (
    EngineEnv,
    FakeCodeRunner,
    git,
    plan_envelope,
    workflow,
    workflow_env_fixture,  # noqa: F401
)

from aifactory.testing.profile import ProfileCache
from aifactory.workflow import run_workflow
from aifactory.workflow.journal import Journal

TEXT = (
    "name: t\ndescription: Select and run checks without extra agents\nsteps: [test_plan, test]\n"
)
KNOWLEDGE = "Run Python tests with uv run pytest; API changes need tests/api and tests/web."


def configure(env: EngineEnv, tmp_path: Path) -> None:
    template = tmp_path / "tester-profile.md"
    template.write_text("{{prompt}}\nPROFILE<<{{testing_profile}}>>PROFILE\n", encoding="utf-8")
    for agent in env.cfg.agents:
        if agent.name == "tester":
            agent.prompt_engineering.user = str(template)


def context(env: EngineEnv) -> dict[str, object]:
    prompt = env.script.calls[-1].prompt
    return dict(json.loads(prompt.split("PROFILE<<")[1].split(">>PROFILE")[0]))


def test_project_profile_is_created_reused_and_refreshed(
    workflow_env: EngineEnv, tmp_path: Path
) -> None:
    env = workflow_env
    configure(env, tmp_path)
    cache = ProfileCache(tmp_path / "profiles", "repo:project-a")
    for expected in ("missing", "current", "stale"):
        if expected == "stale":
            (env.repo / "pyproject.toml").write_text(
                "[tool.pytest.ini_options]\n", encoding="utf-8"
            )
        env.script.add("tester", {**plan_envelope(), "testing_profile": KNOWLEDGE})
        result = run_workflow(
            workflow(TEXT),
            "do it",
            env.cfg,
            code=FakeCodeRunner([True]),
            test_profile=cache,
        )
        assert result.accepted
        assert context(env)["state"] == expected
        assert json.loads(cache.context(env.repo))["state"] == "current"
    assert len(env.script.calls) == 3
    assert {c.agent for c in env.script.calls} == {"tester"}
    assert context(env)["knowledge"] == KNOWLEDGE


def test_profiles_are_isolated_and_do_not_execute_stored_commands(
    workflow_env: EngineEnv, tmp_path: Path
) -> None:
    env = workflow_env
    configure(env, tmp_path)
    first = ProfileCache(tmp_path / "profiles", "repo:project-a")
    other = ProfileCache(tmp_path / "profiles", "repo:project-b")
    first.save(env.repo, "Do not run this: arbitrary untrusted command")
    assert json.loads(other.context(env.repo))["state"] == "missing"
    env.script.add("tester", {**plan_envelope(), "testing_profile": KNOWLEDGE})
    code = FakeCodeRunner([True])
    run_workflow(workflow(TEXT), "do it", env.cfg, code=code, test_profile=first)
    assert code.commands == []
    assert code.plans[0].checks[0].name == "check"


def test_profile_records_actual_check_durations(workflow_env: EngineEnv, tmp_path: Path) -> None:
    env = workflow_env
    cache = ProfileCache(tmp_path / "profiles", "project")
    env.script.add("tester", {**plan_envelope(), "testing_profile": KNOWLEDGE})
    result = run_workflow(workflow(TEXT), "do it", env.cfg, test_profile=cache)
    assert result.accepted
    measured = json.loads(cache.context(env.repo))["observed_seconds"]
    assert len(measured) == 1 and all(seconds > 0 for seconds in measured.values())


def test_corrupt_or_unwritable_cache_does_not_block_checks(
    workflow_env: EngineEnv, tmp_path: Path
) -> None:
    env = workflow_env
    configure(env, tmp_path)
    cache = ProfileCache(tmp_path / "profiles", "project")
    cache.directory.mkdir()
    cache.path.write_text("not JSON", encoding="utf-8")
    assert json.loads(cache.context(env.repo))["state"] == "missing"
    # An existing file cannot be used as the profile directory, on every OS.
    blocker = tmp_path / "blocked"
    blocker.touch()
    broken = ProfileCache(blocker, "project")
    env.script.add("tester", {**plan_envelope(), "testing_profile": KNOWLEDGE})
    result = run_workflow(
        workflow(TEXT), "do it", env.cfg, code=FakeCodeRunner([True]), test_profile=broken
    )
    assert result.accepted


@pytest.mark.parametrize(
    "name", ["justfile", "package.json", "uv.lock", ".github/workflows/ci.yml"]
)
def test_runner_configuration_changes_invalidate_profile(
    workflow_env: EngineEnv, tmp_path: Path, name: str
) -> None:
    root = workflow_env.repo
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("before", encoding="utf-8")
    cache = ProfileCache(tmp_path / "profiles", "project")
    cache.save(root, KNOWLEDGE)
    path.write_text("after", encoding="utf-8")
    assert json.loads(cache.context(root))["state"] == "stale"


@pytest.mark.parametrize("name", ["test_app.py", "app.spec.ts", "app_test.go", "Tests/AppTests.cs"])
def test_new_tests_invalidate_but_source_edits_do_not_discard_knowledge(
    workflow_env: EngineEnv, tmp_path: Path, name: str
) -> None:
    root = workflow_env.repo
    cache = ProfileCache(tmp_path / "profiles", "project")
    cache.save(root, KNOWLEDGE)
    (root / "app.py").write_text("pass", encoding="utf-8")
    assert json.loads(cache.context(root))["state"] == "current"
    added = root / name
    added.parent.mkdir(parents=True, exist_ok=True)
    added.write_text("test", encoding="utf-8")
    assert json.loads(cache.context(root))["state"] == "stale"
    assert json.loads(cache.context(root))["knowledge"] == KNOWLEDGE


def test_deleted_tracked_test_invalidates_profile(workflow_env: EngineEnv, tmp_path: Path) -> None:
    root = workflow_env.repo
    test = root / "test_app.py"
    test.write_text("pass", encoding="utf-8")
    git(root, "add", "test_app.py")
    cache = ProfileCache(tmp_path / "profiles", "project")
    cache.save(root, KNOWLEDGE)
    test.unlink()
    assert json.loads(cache.context(root))["state"] == "stale"


def test_replay_does_not_overwrite_a_newer_profile(workflow_env: EngineEnv, tmp_path: Path) -> None:
    env = workflow_env
    cache = ProfileCache(tmp_path / "profiles", "project")
    env.script.add("tester", {**plan_envelope(), "testing_profile": "old knowledge"})
    journal = Journal(None)
    run_workflow(
        workflow(TEXT),
        "do it",
        env.cfg,
        code=FakeCodeRunner([True]),
        test_profile=cache,
        journal=journal,
    )
    cache.save(env.repo, "new knowledge")
    journal.start_replay(len(journal.entries))
    run_workflow(
        workflow(TEXT),
        "do it",
        env.cfg,
        code=FakeCodeRunner([]),
        test_profile=cache,
        journal=journal,
    )
    assert json.loads(cache.context(env.repo))["knowledge"] == "new knowledge"
    assert len(env.script.calls) == 1
