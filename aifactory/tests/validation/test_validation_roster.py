"""`just validate --roster DIR`: the roster replaces the sandbox's agents.yaml and workflow."""

from __future__ import annotations

import datetime
import json
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from local_validation import LocalValidation, validation_env
from validation.context import Context
from validation.results import ScenarioResult
from validation.roster import apply_roster, harness_of_phase, resolve_roster, step_harnesses
from validation.sandbox import TEMPLATE_DIR, SetupError
from validation.scenarios import _roster_gap

from validation import runner, sandbox

HAIFA_ROOT = Path(__file__).resolve().parents[3]
PI_HAIKU = Path("aifactory/validation/rosters/pi-haiku")
TEMPLATE_HARNESSES = {
    "plan": "claude",
    "build": "codex",
    "test_plan": "claude",
    "fix": "codex",
    "review": "pi",
    "revise": "codex",
    "replan": "claude",
    "document": "claude",
}


def _write_roster(directory: Path, config: str, workflow: str) -> Path:
    (directory / "workflows").mkdir(parents=True, exist_ok=True)
    (directory / "agents.yaml").write_text(config, encoding="utf-8", newline="\n")
    (directory / "workflows" / "simple-sdlc.yaml").write_text(
        workflow, encoding="utf-8", newline="\n"
    )
    return directory


def _roster_without_codex(directory: Path) -> Path:
    """The template roster with codex replaced by claude (claude + pi)."""
    config = (TEMPLATE_DIR / ".factory" / "agents.yaml").read_text(encoding="utf-8")
    config = config.replace(
        "harness: codex\n    model: gpt-5.5", "harness: claude\n    model: sonnet"
    )
    workflow = (TEMPLATE_DIR / ".factory" / "workflows" / "simple-sdlc.yaml").read_text(
        encoding="utf-8"
    )
    workflow = workflow.replace("harness: codex", "harness: claude")
    assert "harness: codex" not in config and "harness: codex" not in workflow
    agents = yaml.safe_load(config)["agents"]
    assert [a["name"] for a in agents] == [
        "planner",
        "builder",
        "tester",
        "test-reviewer",
        "reviewer",
        "documenter",
    ]
    assert all(a["harness"] != "codex" for a in agents)
    return _write_roster(directory, config, workflow)


# ── unit ─────────────────────────────────────────────────────────────────────


def test_step_harnesses_of_the_template(tmp_path: Path) -> None:
    sandbox.materialize(tmp_path, "main", "local")
    harnesses = step_harnesses(tmp_path)
    assert harnesses == TEMPLATE_HARNESSES
    assert harness_of_phase(harnesses, "fix_2") == "codex"
    assert harness_of_phase(harnesses, "review_1") == "pi"
    assert harness_of_phase(harnesses, "plan") == "claude"
    assert harness_of_phase(harnesses, "retest") is None


def test_resolve_roster_requires_both_files(tmp_path: Path) -> None:
    (tmp_path / "agents.yaml").write_text("agents: []\n", encoding="utf-8", newline="\n")
    with pytest.raises(SetupError, match="workflows/simple-sdlc.yaml"):
        resolve_roster(tmp_path)
    with pytest.raises(SetupError, match="not a directory"):
        resolve_roster(tmp_path / "missing")


def test_resolve_roster_requires_the_four_agents(tmp_path: Path) -> None:
    workflow = (TEMPLATE_DIR / ".factory" / "workflows" / "simple-sdlc.yaml").read_text(
        encoding="utf-8"
    )
    config = "defaults: {harness: pi}\nagents:\n  - name: planner\n  - name: builder\n"
    _write_roster(tmp_path, config, workflow)
    with pytest.raises(SetupError, match="reviewer, documenter"):
        resolve_roster(tmp_path)


def test_resolve_roster_relative_to_haifa_root() -> None:
    rel = Path("aifactory/validation/template/.factory")
    # the template's .factory has agents.yaml and workflows/simple-sdlc.yaml
    assert resolve_roster(rel) == (HAIFA_ROOT / rel).resolve()
    assert resolve_roster(PI_HAIKU) == (HAIFA_ROOT / PI_HAIKU).resolve()


def test_pi_haiku_roster_harnesses(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    sandbox.materialize(repo, "main", "local")
    apply_roster(repo, resolve_roster(PI_HAIKU))
    harnesses = step_harnesses(repo)
    assert harnesses["plan"] == "claude"
    assert {harnesses[s] for s in ("build", "fix", "revise", "review")} == {"pi"}
    assert "codex" not in harnesses.values()


def test_apply_roster_replaces_both_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    sandbox.materialize(repo, "main", "local")
    roster = _roster_without_codex(tmp_path / "roster")
    written = apply_roster(repo, roster)
    assert written == [".factory/agents.yaml", ".factory/workflows/simple-sdlc.yaml"]
    for src, target in zip(("agents.yaml", "workflows/simple-sdlc.yaml"), written, strict=True):
        assert (repo / target).read_bytes() == (roster / src).read_bytes()
    harnesses = step_harnesses(repo)
    assert "codex" not in harnesses.values()
    assert harnesses["build"] == "claude" and harnesses["review"] == "pi"


def test_roster_gap_is_inconclusive_only_when_kept_checks_pass() -> None:
    ok = ScenarioResult("R1", "local")
    ok.check("run_ok", True)
    assert _roster_gap(ok, "no codex").outcome == "inconclusive"
    bad = ScenarioResult("R1", "local")
    bad.check("run_ok", True)
    bad.check("pr_opened", False)
    result = _roster_gap(bad, "no codex")
    assert result.outcome == "failed"
    assert "no codex" in result.observations


@pytest.mark.skipif(shutil.which("just") is None, reason="just is not on PATH")
def test_failed_exits_nonzero_inconclusive_does_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing(ctx: Context) -> ScenarioResult:
        res = ScenarioResult("RF", ctx.remote)
        res.check("broken", False)
        return res

    def unsure(ctx: Context) -> ScenarioResult:
        return ScenarioResult("RI", ctx.remote).inconclusive("cannot tell")

    def argv(name: str) -> list[str]:
        return [
            "--remote",
            "local",
            "--results-dir",
            str(tmp_path / name / "results"),
            "--workdir",
            str(tmp_path / name / "work"),
        ]

    monkeypatch.setattr(runner, "ORDER", (("RF", failing), ("RI", unsure)))
    monkeypatch.setattr(runner, "_selected", lambda only: ["RF", "RI"])
    assert runner.main(argv("mixed")) == runner.EXIT_FAILED
    monkeypatch.setattr(runner, "ORDER", (("RI", unsure),))
    monkeypatch.setattr(runner, "_selected", lambda only: ["RI"])
    assert runner.main(argv("unsure")) == runner.EXIT_OK


# ── end to end ───────────────────────────────────────────────────────────────


@pytest.fixture
def marker(tmp_path: Path) -> Iterator[Path]:
    with validation_env(tmp_path / "env") as path:
        yield path


@pytest.mark.skipif(shutil.which("just") is None, reason="just is not on PATH")
def test_validate_local_pi_haiku_roster(tmp_path: Path, marker: Path) -> None:
    """`just validate --roster` itself; R1 and R10 over the roster are the tests below."""
    results = tmp_path / "results"
    work = tmp_path / "work"
    proc = subprocess.run(
        [
            "just",
            "validate",
            "--remote",
            "local",
            "--roster",
            str(PI_HAIKU),
            "--only",
            "R5",
            "--results-dir",
            str(results),
            "--workdir",
            str(work),
        ],
        cwd=HAIFA_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr[-4000:]
    today = datetime.date.today().isoformat()
    runs = list((results / today).glob("local-*"))
    assert len(runs) == 1, runs
    out = runs[0]

    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["results"] == {"R5": "passed"}, proc.stderr[-4000:]
    assert summary["roster"] == str((HAIFA_ROOT / PI_HAIKU).resolve())
    assert summary["harness_per_step"]["build"] == "pi"
    assert "codex" not in summary["harness_per_step"].values()
    assert not marker.exists()


def _roster_scenario(tmp_path: Path, name: str) -> dict[str, Any]:
    """R1 or R10 over the pi-haiku roster: inconclusive (no codex), every check passes."""
    run = LocalValidation(tmp_path / "run", roster=resolve_roster(PI_HAIKU))
    assert step_harnesses(run.ctx.repo)["build"] == "pi"
    data = run.scenario(name)
    assert data["outcome"] == "inconclusive", data
    assert data["checks"], data["scenario"]
    assert all(c["ok"] for c in data["checks"]), data["checks"]
    # the forced review round still runs: the rule is in the template's prompts
    assert {c["name"] for c in data["checks"]} >= {"revise_ran", "review_2_approved"}
    assert any("codex" in text for text in data["observations"])
    return data


@pytest.mark.skipif(shutil.which("just") is None, reason="just is not on PATH")
def test_pi_haiku_roster_r1(tmp_path: Path, marker: Path) -> None:
    r1 = _roster_scenario(tmp_path, "R1")
    assert "harness_per_phase" not in [c["name"] for c in r1["checks"]]
    assert not marker.exists()


@pytest.mark.skipif(shutil.which("just") is None, reason="just is not on PATH")
def test_pi_haiku_roster_r10(tmp_path: Path, marker: Path) -> None:
    r10 = _roster_scenario(tmp_path, "R10")
    assert "fix_ran_on_codex" not in [c["name"] for c in r10["checks"]]
    assert not marker.exists()


@pytest.mark.parametrize(
    ("roster", "expected"),
    [(None, {"claude", "codex", "pi"}), (PI_HAIKU, {"claude", "pi"})],
    ids=["template", "pi-haiku"],
)
def test_github_preflight_checks_the_roster_harnesses(
    tmp_path: Path, roster: Path | None, expected: set[str]
) -> None:
    from aifactory.config.loader import load_roster_file
    from aifactory.harness.check import harnesses_in_config

    harnesses = runner.roster_harnesses(resolve_roster(roster) if roster is not None else None)
    assert harnesses == expected
    config = runner.check_config(sorted(harnesses))
    assert config == {
        "agents": [{"name": f"check-{name}", "harness": name} for name in sorted(expected)]
    }
    path = tmp_path / "harnesses.yaml"
    path.write_text(json.dumps(config), encoding="utf-8", newline="\n")
    assert set(harnesses_in_config(load_roster_file(path))) == expected
