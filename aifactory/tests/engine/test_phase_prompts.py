"""aifactory 2.10: every agent phase keeps its own rendered prompts in the session dir."""

from __future__ import annotations

from engine_fakes import EngineEnv, engine_env_fixture, start  # noqa: F401

from aifactory.engine.data_types import AgentCall, GenericOutput, PhaseParams
from aifactory.engine.runner import Run


def _phase(run: Run, name: str, owner: str, prompt: str) -> None:
    params = PhaseParams(
        name=name, kind="agent", owner=owner, description=f"{name} for the test", retries=0
    )
    with run.phase(params) as ph:
        ph.call(AgentCall(output_type=GenericOutput, prompt=prompt))


def test_each_phase_keeps_its_own_prompts(engine_env: EngineEnv) -> None:
    env = engine_env
    run = start(env)
    env.script.add_ok("free")
    env.script.add_ok("free")

    _phase(run, "build", "free", "build it")
    _phase(run, "revise_1", "free", "fix it")

    prompts = run.session_dir / "free" / "prompts"
    build = prompts / "phases" / "build"
    revise = prompts / "phases" / "revise_1"
    assert "build it" in (build / "user.md").read_text()
    assert "fix it" in (revise / "user.md").read_text()
    assert "fix it" not in (build / "user.md").read_text()
    assert (build / "system.md").read_text() == "system\n"
    assert (revise / "system.md").read_text() == "system\n"
    # The agent-level copy stays and holds the last phase.
    assert "fix it" in (prompts / "user.md").read_text()
    assert (prompts / "system.md").is_file()


def test_assigned_skill_index_is_saved_for_each_phase(engine_env: EngineEnv) -> None:
    env = engine_env
    run = start(env)
    agent = next(a for a in run.cfg.agents if a.name == "free")
    # Validate the roster field instead of attaching an ignored extra attribute.
    configured = agent.model_dump()
    configured["skills"] = ["team-check"]
    run.cfg.agents = [
        type(agent).model_validate(configured) if a.name == "free" else a for a in run.cfg.agents
    ]
    for name in ("team-check", "unassigned"):
        path = run.repo_root / ".claude/skills" / name / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"---\nname: {name}\ndescription: Check shared contracts.\n---\n"
            "Body must stay on disk.\n",
            encoding="utf-8",
        )
    env.script.add_ok("free")
    env.script.add_ok("free")
    _phase(run, "build", "free", "build it")
    _phase(run, "revise_1", "free", "fix it")
    prompts = run.session_dir / "free/prompts"
    for path in (
        prompts / "system.md",
        prompts / "phases/build/system.md",
        prompts / "phases/revise_1/system.md",
    ):
        system = path.read_text()
        assert "## Available skills" in system
        assert "team-check: Check shared contracts." in system
        assert ".claude/skills/team-check/SKILL.md" in system
        assert "unassigned" not in system and "Body must stay on disk." not in system
