"""Loading a workflow validates it completely; nothing runs."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from workflow_fakes import workflow

from aifactory.engine.role_registry import DEFAULT_ROLES_PATH, load_roles, parse_roles
from aifactory.workflow import (
    CodeStep,
    Repeat,
    RoleStep,
    WorkflowError,
    load_workflow,
    outline,
    parse_workflow,
)

HEADER = "name: t\ndescription: A workflow written only to exercise the loader\n"

SIMPLE_SDLC = (
    HEADER
    + """\
steps:
  - plan
  - commit:
      id: commit_plan
      description: Put the spec on record before any code exists to blur it
  - build
  - test_plan
  - repeat: {max: 3, until: test.passed}
    steps: [test, fix]
  - repeat: {max: 2, until: review.approved}
    steps:
      - review: {input: [build, fix, revise]}
      - revise
  - test:
      id: retest
      when: revise.ran and review.approved
      description: Re-run the suite after the revision changed code
accept: test.passed and review.approved
"""
)


def _load(tmp_path: Path, body: str) -> WorkflowError:
    path = tmp_path / "wf.yaml"
    path.write_text(HEADER + body, encoding="utf-8", newline="\n")
    with pytest.raises(WorkflowError) as exc:
        load_workflow(path)
    return exc.value


def test_simple_sdlc_structure() -> None:
    wf = workflow(SIMPLE_SDLC)
    loops = [s for s in wf.steps if isinstance(s, Repeat)]
    assert [loop.max for loop in loops] == [3, 2]
    assert [loop.until.source for loop in loops if loop.until] == [
        "test.passed",
        "review.approved",
    ]
    review = loops[1].steps[0]
    assert isinstance(review, RoleStep)
    assert review.inputs == ("build", "fix", "revise")
    retest = wf.steps[6]
    assert isinstance(retest, CodeStep)
    assert (retest.key, retest.phase_id) == ("test", "retest")
    assert wf.accept is not None
    kinds = [row["kind"] for row in outline(wf.steps)]
    assert kinds.count("repeat") == 2


@pytest.mark.parametrize(
    ("body", "tail"),
    [
        ("  - repeat: {max: 3, until: test.passed}\n    steps: [test, fix]\n", 0),
        ("  - repeat: {max: 2, until: review.approved}\n    steps: [review, revise]\n", 0),
        ("  - repeat: {max: 2, until: test.passed}\n    steps: [fix, test]\n", 1),
        ("  - repeat: {max: 2}\n    steps: [test, fix]\n", None),
        (
            "  - repeat: {max: 2, until: plan.status == 'success'}\n    steps: [test, fix]\n",
            None,
        ),
        (
            "  - repeat: {max: 2, until: test.passed}\n"
            "    steps:\n"
            "      - build\n"
            "      - repeat: {max: 2}\n"
            "        steps: [test]\n"
            "      - fix\n",
            1,
        ),
    ],
)
def test_until_tail(body: str, tail: int | None) -> None:
    wf = workflow(HEADER + "steps:\n  - plan\n  - test_plan\n" + body)
    loop = wf.steps[2]
    assert isinstance(loop, Repeat)
    assert loop.until_tail == tail


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ("steps: [plan, deploy]\n", "unknown_step"),
        ("steps:\n  - plan: {harness: gemini}\n", "unknown_harness"),
        (
            "steps:\n  - repeat: {max: 3, until: test.approved}\n    steps: [test, fix]\n",
            "unknown_field",
        ),
        (
            "steps:\n  - repeat: {max: 3, until: nothing.passed}\n    steps: [test, fix]\n",
            "unknown_ref",
        ),
        ("steps:\n  - repeat: {until: test.passed}\n    steps: [test, fix]\n", "missing_max"),
        ("steps:\n  - repeat: {max: 0}\n    steps: [test]\n", "invalid_max"),
        ("steps:\n  - repeat: {max: 2}\n", "empty_repeat"),
        ("steps:\n  - test: {model: opus}\n", "override_on_code_step"),
        ("steps:\n  - plan: {thinking: extreme}\n", "invalid_thinking"),
        ("steps:\n  - plan: {model: ''}\n", "invalid_model"),
        ("steps:\n  - command: {id: dotnet_test}\n", "missing_argv"),
        ("steps:\n  - command: {argv: [dotnet, test]}\n", "missing_id"),
        ("steps:\n  - command: {id: Bad-Id, argv: [x]}\n", "invalid_id"),
        ("steps:\n  - command: {id: fix, argv: [x]}\n", "invalid_id"),
        ("steps:\n  - command: {id: a, argv: [x], timeout: 0}\n", "invalid_timeout"),
        (
            "steps:\n  - command: {id: a, argv: [x]}\n  - command: {id: a, argv: [y]}\n",
            "duplicate_id",
        ),
        ("steps:\n  - commit: {id: commit_plan, description: Commit plan}\n", "bad_description"),
        ("steps:\n  - plan: {colour: red}\n", "unknown_key"),
        ("steps: [plan]\naccept: plan.status ==\n", "bad_condition"),
        ("steps: [plan]\naccept: __import__('os')\n", "bad_condition"),
        ("steps:\n  - review: {input: [nobody]}\n", "unknown_ref"),
        ("steps:\n  - plan: {when: ghost.ran}\n", "unknown_ref"),
        ("steps: []\n", "missing_steps"),
    ],
)
def test_invalid_workflow_fails_at_load(tmp_path: Path, body: str, code: str) -> None:
    error = _load(tmp_path, body)
    assert code in [issue.code for issue in error.issues], error.issues


def test_missing_name_and_description(tmp_path: Path) -> None:
    path = tmp_path / "wf.yaml"
    path.write_text("steps: [plan]\n", encoding="utf-8", newline="\n")
    with pytest.raises(WorkflowError) as exc:
        load_workflow(path)
    assert {i.code for i in exc.value.issues} == {"missing_name", "bad_description"}


def test_all_problems_reported_at_once(tmp_path: Path) -> None:
    error = _load(
        tmp_path,
        "steps:\n"
        "  - plan: {harness: gemini}\n"
        "  - deploy\n"
        "  - repeat: {until: test.approved}\n"
        "    steps: [test]\n",
    )
    codes = [issue.code for issue in error.issues]
    assert {"unknown_harness", "unknown_step", "missing_max", "unknown_field"} <= set(codes)
    paths = {issue.code: issue.path for issue in error.issues}
    assert paths["unknown_harness"] == "steps[0].plan.harness"
    assert paths["missing_max"] == "steps[2].repeat.max"


def test_overrides_and_command_are_parsed(tmp_path: Path) -> None:
    path = tmp_path / "wf.yaml"
    path.write_text(
        HEADER + "steps:\n"
        "  - build: {harness: codex, model: gpt-5.5, thinking: high}\n"
        "  - command: {id: dotnet_test, argv: [dotnet, test], timeout: 60}\n"
        "accept: dotnet_test.passed\n",
        encoding="utf-8",
        newline="\n",
    )
    wf = load_workflow(path)
    build, command = wf.steps
    assert isinstance(build, RoleStep)
    assert (build.harness, build.model, build.thinking) == ("codex", "gpt-5.5", "high")
    assert isinstance(command, CodeStep)
    assert (command.key, command.argv, command.timeout, command.action) == (
        "dotnet_test",
        ("dotnet", "test"),
        60,
        "command",
    )


def test_until_reads_a_command_by_its_id() -> None:
    wf = workflow(
        HEADER + "steps:\n"
        "  - repeat: {max: 2, until: tests_cmd.passed}\n"
        "    steps:\n"
        "      - command: {id: tests_cmd, argv: [dotnet, test]}\n"
        "      - fix\n"
    )
    loop = wf.steps[0]
    assert isinstance(loop, Repeat)
    assert loop.until_tail == 0


def test_harness_alias_is_stored_canonical() -> None:
    wf = workflow(HEADER + "steps:\n  - plan: {harness: claude_code}\n")
    plan = wf.steps[0]
    assert isinstance(plan, RoleStep)
    assert plan.harness == "claude"
    assert plan.override.harness == "claude"


def test_custom_role_registry() -> None:
    data = yaml.safe_load(DEFAULT_ROLES_PATH.read_text(encoding="utf-8"))
    data["roles"] = {
        "draft": {
            "agent": "writer",
            "output_type": "PlanOutput",
            "description": "Draft the change as a written proposal",
        }
    }
    roles = parse_roles(data)
    ok = parse_workflow(yaml.safe_load(HEADER + "steps: [draft, commit]\n"), roles)
    first = ok.steps[0]
    assert isinstance(first, RoleStep)
    assert first.role.agent == "writer"
    with pytest.raises(WorkflowError) as exc:
        parse_workflow(yaml.safe_load(HEADER + "steps: [draft, plan]\n"), roles)
    assert [i.code for i in exc.value.issues] == ["unknown_step"]
    with pytest.raises(WorkflowError):
        parse_workflow(yaml.safe_load(HEADER + "steps: [draft]\n"), load_roles())


def test_invalid_yaml(tmp_path: Path) -> None:
    error = _load(tmp_path, "steps: [plan\n")
    assert [i.code for i in error.issues] == ["invalid_yaml"]


def test_step_agent_replaces_the_role_agent() -> None:
    wf = workflow(HEADER + "steps:\n  - review: {agent: critic}\n")
    step = wf.steps[0]
    assert isinstance(step, RoleStep)
    packaged = load_roles().roles["review"]
    assert (step.agent, step.role.agent) == ("critic", "critic")
    assert step.role.output_type_name == "ReviewOutput"
    assert step.role.gate_names == packaged.gate_names
    assert packaged.agent == "reviewer"  # the registry itself is untouched
    assert outline(wf.steps)[0]["agent"] == "critic"


@pytest.mark.parametrize(
    ("body", "code", "path"),
    [
        ("steps:\n  - build: {agent: ''}\n", "invalid_agent", "steps[0].build.agent"),
        ("steps:\n  - build: {agent: 3}\n", "invalid_agent", "steps[0].build.agent"),
        (
            "steps:\n  - commit: {agent: builder}\n",
            "override_on_code_step",
            "steps[0].commit.agent",
        ),
    ],
)
def test_invalid_step_agent(tmp_path: Path, body: str, code: str, path: str) -> None:
    error = _load(tmp_path, body)
    assert [(i.code, i.path) for i in error.issues] == [(code, path)]


@pytest.mark.parametrize(
    ("steps", "path"),
    [
        ("  - test\n", "steps[0]"),
        ("  - test\n  - test_plan\n", "steps[0]"),
        ("  - repeat: {max: 2}\n    steps: [test, test_plan]\n", "steps[0].steps[0]"),
    ],
)
def test_test_without_an_earlier_test_plan_is_rejected(steps: str, path: str) -> None:
    with pytest.raises(WorkflowError) as exc:
        workflow(HEADER + "steps:\n" + steps)
    issues = [(i.code, i.path) for i in exc.value.issues]
    assert issues == [("test_without_plan", path)]


def test_a_test_plan_inside_an_earlier_repeat_counts() -> None:
    wf = workflow(HEADER + "steps:\n  - repeat: {max: 2}\n    steps: [test_plan, test]\n  - test\n")
    assert isinstance(wf.steps[1], CodeStep)


@pytest.mark.parametrize("option", ["selector: [x]", "full_argv: [x]", "allow_skip: true"])
def test_removed_test_options_are_rejected(option: str) -> None:
    with pytest.raises(WorkflowError):
        workflow(HEADER + "steps:\n  - test_plan\n  - test: {" + option + "}\n")
