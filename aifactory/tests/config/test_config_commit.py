"""A run reads `.factory/` from the base commit's tree, never from the working tree."""

from __future__ import annotations

from pathlib import Path

import pytest
from config_repo import AGENTS_YAML, FILES, commit_all, git, make_repo, write

from aifactory.config import CommitSource, ConfigError, load_run_config

PLANNER_SYSTEM = ".factory/prompts/planner/system.md"


def _model(run_agents: list[object], name: str) -> str:
    for agent in run_agents:
        if getattr(agent, "name", None) == name:
            return str(getattr(agent, "model", ""))
    raise KeyError(name)


def test_uncommitted_prompt_and_agents_stay_out_of_the_run(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write(repo, PLANNER_SYSTEM, "EDITED, not committed\n")
    write(repo, ".factory/agents.yaml", AGENTS_YAML.replace("model: opus", "model: haiku"))

    run = load_run_config(repo)

    assert run.config.prompts["planner"].system == FILES[PLANNER_SYSTEM]
    assert _model(list(run.config.agents.agents), "planner") == "opus"
    changed = {c.path: c.status for c in run.changes}
    assert changed == {".factory/agents.yaml": "modified", PLANNER_SYSTEM: "modified"}
    assert any(PLANNER_SYSTEM in w for w in run.warnings)
    assert any(".factory/agents.yaml" in w for w in run.warnings)
    assert run.to_json()["warnings"] == list(run.warnings)


def test_two_runs_from_one_commit_get_the_same_config(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    a = load_run_config(repo)
    write(repo, PLANNER_SYSTEM, "changed between runs\n")
    write(repo, ".factory/workflows/plan-build.yaml", "name: plan-build\nsteps: [build]\n")
    write(repo, ".factory/workflows/extra.yaml", "name: extra\nsteps: [scout]\n")
    b = load_run_config(repo)

    assert a.commit == b.commit
    assert a.config.digest == b.config.digest
    assert a.config.agents == b.config.agents
    assert a.config.prompts == b.config.prompts
    assert a.config.workflows == b.config.workflows
    assert a.config.settings == b.config.settings
    assert "extra" not in b.config.workflows
    assert a.warnings == ()
    statuses = {c.path: c.status for c in b.changes}
    assert statuses[".factory/workflows/extra.yaml"] == "untracked"
    assert statuses[PLANNER_SYSTEM] == "modified"


def test_loading_does_not_touch_the_checkout(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write(repo, PLANNER_SYSTEM, "dirty\n")
    git(repo, "add", ".factory/agents.yaml")
    head = git(repo, "rev-parse", "HEAD")
    status = git(repo, "status", "--porcelain")

    load_run_config(repo)

    assert git(repo, "rev-parse", "HEAD") == head
    assert git(repo, "status", "--porcelain") == status
    assert (repo / PLANNER_SYSTEM).read_text() == "dirty\n"
    assert len(git(repo, "worktree", "list").splitlines()) == 1


def test_local_yaml_is_never_read_from_base(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write(repo, ".factory/local.yaml", "trace_db: one.db\n")
    git(repo, "add", "-f", ".factory/local.yaml")
    commit_all(repo, "local.yaml committed by mistake")
    write(repo, ".factory/local.yaml", "trace_db: two.db\nport: 2222\n")

    run = load_run_config(repo)

    assert run.local.trace_db == "two.db"
    assert "port" not in run.to_json()["local"]
    assert any(w.startswith("local_port_ignored") for w in run.warnings)
    assert run.changes == ()
    source = CommitSource(repo.resolve(), "main", run.commit)
    with pytest.raises(ValueError, match="never read from a commit"):
        source.read_text(".factory/local.yaml")


def test_base_other_than_head(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    git(repo, "checkout", "-q", "-b", "feature")
    write(repo, PLANNER_SYSTEM, "feature prompt\n")
    commit_all(repo, "prompt on feature")

    run = load_run_config(repo)
    assert run.base == "main"
    assert run.config.prompts["planner"].system == FILES[PLANNER_SYSTEM]
    assert any(PLANNER_SYSTEM in w for w in run.warnings)

    feature = load_run_config(repo, base="feature")
    assert feature.config.prompts["planner"].system == "feature prompt\n"
    # config.yaml still says `base: main`, which is reported
    assert feature.changes == ()
    assert feature.warnings == ("committed base is 'main' but the run uses 'feature'",)


def test_errors_carry_the_commit_label(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write(repo, ".factory/agents.yaml", "agents: [\n")
    commit_all(repo, "broken")
    sha = git(repo, "rev-parse", "HEAD").strip()
    with pytest.raises(ConfigError) as info:
        load_run_config(repo)
    assert info.value.issues[0].path == f"main@{sha[:7]}:.factory/agents.yaml"


def test_unknown_base(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write(repo, ".factory/config.yaml", "base: develop\n")
    commit_all(repo, "base develop")
    with pytest.raises(ConfigError, match="develop"):
        load_run_config(repo)


def test_outside_a_git_repository(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not a git repository"):
        load_run_config(tmp_path)
