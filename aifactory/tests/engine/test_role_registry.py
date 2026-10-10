from pathlib import Path
from typing import Any

import pytest
import yaml

from aifactory.engine import loader as engine
from aifactory.engine.role_registry import (
    CODE_ACTIONS,
    DEFAULT_ROLES_PATH,
    RolesError,
    load_roles,
    parse_roles,
)
from aifactory.workflow import RebaseOutput


def test_roles_match_vendor_registry() -> None:
    vendor = engine.load_engine_module("roles")
    registry = load_roles()
    for name, spec in vendor.ROLES.items():
        role = registry.roles[name]
        assert role.agent == spec.agent, name
        assert role.output_type is spec.output_type, name
        assert len(role.gates) == len(spec.gates), name
        assert all(a is b for a, b in zip(role.gates, spec.gates, strict=True)), name
        assert role.description == spec.description, name
        assert role.retries == spec.retries, name
    # aifactory 3.0 replaced the vendor's `test` and dropped `quality`.
    for name, spec in vendor.CODE_STEPS.items():
        if name not in ("test", "quality"):
            assert registry.code_steps[name].description == spec.description, name


def test_aliases_share_one_role() -> None:
    registry = load_roles()
    for alias, name in [
        ("planner", "plan"),
        ("builder", "build"),
        ("reviewer", "review"),
        ("documenter", "document"),
    ]:
        assert registry.roles[alias] is registry.roles[name]


def test_only_revise_resolve_test_plan_command_rebase_and_rebuild_are_extra() -> None:
    vendor = engine.load_engine_module("roles")
    registry = load_roles()
    assert set(registry.roles) - set(vendor.ROLES) == {"revise", "resolve", "test_plan"}
    assert set(registry.code_steps) - set(vendor.CODE_STEPS) == {"command", "rebase", "rebuild"}
    assert set(vendor.CODE_STEPS) - set(registry.code_steps) == {"quality"}
    test_plan = registry.roles["test_plan"]
    assert (test_plan.agent, test_plan.output_type_name, test_plan.gate_names) == (
        "tester",
        "TestPlanOutput",
        ("checks_runnable", "plan_keeps_checks"),
    )
    assert set(registry.code_steps) == set(CODE_ACTIONS)
    revise = registry.roles["revise"]
    assert (revise.agent, revise.output_type_name, revise.gate_names) == (
        "builder",
        "BuildOutput",
        ("diff_matches_claims",),
    )
    resolve = registry.roles["resolve"]
    assert (resolve.agent, resolve.output_type_name, resolve.gate_names) == (
        "builder",
        "BuildOutput",
        ("diff_matches_claims",),
    )


CODE_STEPS = """
code_steps:
  test: {owner: quality, description: Run the suite with a known command}
  commit: {owner: git, description: Record the work in its own words}
  changes: {owner: git, description: Diff the run against its baseline}
  command: {owner: quality, description: Run a named command as code}
  rebase: {owner: git, description: Replay the branch on top of base}
  rebuild: {owner: quality, description: Build generated outputs again}
"""


@pytest.mark.parametrize(
    ("role", "code"),
    [
        (
            "plan: {agent: planner, output_type: Nope, description: Turn asks into plans}",
            "unknown_output_type",
        ),
        (
            "plan: {agent: planner, output_type: PlanOutput, gates: [nope], "
            "description: Turn asks into plans}",
            "unknown_gate",
        ),
        (
            "plan: {agent: planner, output_type: PhaseParams, description: Turn asks into plans}",
            "invalid_output_type",
        ),
        ("plan: {agent: planner, output_type: PlanOutput, description: Plan}", "bad_description"),
        (
            "plan: {agent: planner, output_type: PlanOutput, description: Turn asks into plans, "
            "aliases: [test]}",
            "alias_conflict",
        ),
    ],
)
def test_invalid_registry(tmp_path: Path, role: str, code: str) -> None:
    path = tmp_path / "roles.yaml"
    path.write_text(f"roles:\n  {role}\n{CODE_STEPS}", encoding="utf-8", newline="\n")
    with pytest.raises(RolesError) as exc:
        load_roles(path)
    assert code in [issue.code for issue in exc.value.issues]


def test_minimal_registry_loads(tmp_path: Path) -> None:
    path = tmp_path / "roles.yaml"
    path.write_text(
        "roles:\n  plan: {agent: planner, output_type: PlanOutput, "
        "description: Turn asks into plans}\n" + CODE_STEPS,
        encoding="utf-8",
        newline="\n",
    )
    registry = load_roles(path)
    assert registry.roles["plan"].gates == ()
    assert "passed" in registry.result_fields("test")
    assert registry.result_fields("commit") == {"sha", "committed", "message", "ran"}
    assert registry.result_fields("rebase") == frozenset(RebaseOutput.model_fields) | {"ran"}


AUDIT = {
    "agent": "auditor",
    "output_type": "ReviewOutput",
    "gates": ["artifacts_exist"],
    "description": "Audit the change against the security checklist",
}


def _row(role: Any) -> tuple[Any, ...]:
    return (
        role.name,
        role.agent,
        role.output_type_name,
        role.gate_names,
        role.description,
        role.retries,
    )


def test_overlay_changes_one_role_and_adds_one() -> None:
    packaged = load_roles()
    registry = parse_roles({"roles": {"review": {"agent": "critic"}, "audit": AUDIT}})
    review = registry.roles["review"]
    assert review.agent == "critic"
    assert review.output_type_name == "ReviewOutput"
    assert review.gate_names == packaged.roles["review"].gate_names
    assert review.description == packaged.roles["review"].description
    assert registry.roles["reviewer"] is review
    assert registry.roles["audit"].agent == "auditor"
    assert registry.roles["audit"].gate_names == ("artifacts_exist",)
    assert _row(registry.roles["plan"]) == _row(packaged.roles["plan"])
    assert set(registry.code_steps) == set(CODE_ACTIONS)
    assert set(registry.roles) == set(packaged.roles) | {"audit"}


def test_overlay_file_loads(tmp_path: Path) -> None:
    path = tmp_path / "roles.yaml"
    path.write_text(yaml.safe_dump({"roles": {"audit": AUDIT}}), encoding="utf-8", newline="\n")
    registry = load_roles(path)
    assert registry.is_role("audit")
    assert registry.is_role("plan")
    assert registry.is_code("commit")


def test_empty_overlay_is_the_packaged_registry() -> None:
    packaged = load_roles()
    registry = parse_roles({})
    assert {n: _row(r) for n, r in registry.roles.items()} == {
        n: _row(r) for n, r in packaged.roles.items()
    }


def test_full_file_replaces_as_before() -> None:
    data = yaml.safe_load(DEFAULT_ROLES_PATH.read_text(encoding="utf-8"))
    packaged = load_roles()
    registry = parse_roles(data)
    assert {n: _row(r) for n, r in registry.roles.items()} == {
        n: _row(r) for n, r in packaged.roles.items()
    }
    del data["roles"]["scout"]
    assert not parse_roles(data).is_role("scout")


@pytest.mark.parametrize(
    ("data", "code", "path"),
    [
        (
            {"roles": {"audit": {k: v for k, v in AUDIT.items() if k != "gates"}}},
            "missing_key",
            "roles.audit.gates",
        ),
        ({"roles": {"review": {"colour": "red"}}}, "unknown_key", "roles.review.colour"),
        ({"roles": {"planner": {"agent": "x"}}}, "alias_conflict", "roles.planner"),
        ({"roles": {"plan": {"aliases": ["test"]}}}, "alias_conflict", "roles.plan.aliases"),
        (
            {"roles": {"review": {"output_type": "Nope"}}},
            "unknown_output_type",
            "roles.review.output_type",
        ),
        ({"roles": []}, "missing_roles", "roles"),
        ({"roles": {"review": 3}}, "invalid_role", "roles.review"),
        ({"role": {}}, "unknown_key", "role"),
    ],
)
def test_invalid_overlay(data: dict[str, Any], code: str, path: str) -> None:
    with pytest.raises(RolesError) as exc:
        parse_roles(data)
    assert (code, path) in [(i.code, i.path) for i in exc.value.issues]
