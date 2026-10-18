"""Preflight of `just validate --remote`: the roster's harness+model pairs are checked too."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from validation.sandbox import TEMPLATE_DIR, SetupError

from validation import runner, sandbox

REVIEWER_PI = "harness: pi\n    model: nous-portal/stealth/space-bunny-alpha"


def _offline_roster(directory: Path, builder_model: str = "gpt-5.5") -> Path:
    """The template roster without pi (claude and codex resolve models offline)."""
    config = (TEMPLATE_DIR / ".factory" / "agents.yaml").read_text(encoding="utf-8")
    assert REVIEWER_PI in config
    config = config.replace(REVIEWER_PI, "harness: claude\n    model: sonnet")
    config = config.replace("model: gpt-5.5", f"model: {builder_model}")
    workflow = (TEMPLATE_DIR / ".factory" / "workflows" / "simple-sdlc.yaml").read_text(
        encoding="utf-8"
    )
    workflow = workflow.replace("harness: pi", "harness: claude")
    assert "harness: pi" not in config and "harness: pi" not in workflow
    (directory / "workflows").mkdir(parents=True, exist_ok=True)
    (directory / "agents.yaml").write_text(config, encoding="utf-8", newline="\n")
    (directory / "workflows" / "simple-sdlc.yaml").write_text(
        workflow, encoding="utf-8", newline="\n"
    )
    return directory


def test_roster_files_default_to_the_template(tmp_path: Path) -> None:
    assert runner.roster_files(None) == (
        TEMPLATE_DIR / ".factory" / "agents.yaml",
        TEMPLATE_DIR / ".factory" / "workflows" / "simple-sdlc.yaml",
    )
    assert runner.roster_files(tmp_path) == (
        tmp_path / "agents.yaml",
        tmp_path / "workflows" / "simple-sdlc.yaml",
    )


def test_preflight_models_accepts_known_models(tmp_path: Path) -> None:
    assert runner.roster_model_problems(_offline_roster(tmp_path)) == []
    runner._preflight_models(_offline_roster(tmp_path))


def test_preflight_models_rejects_a_model_the_harness_cannot_run(tmp_path: Path) -> None:
    roster = _offline_roster(tmp_path, builder_model="nous-portal/stealth/space-bunny-alpha")
    problems = runner.roster_model_problems(roster)
    assert problems and all("invalid_agent" in p and "'builder'" in p for p in problems)
    with pytest.raises(SetupError) as exc:
        runner._preflight_models(roster)
    assert "harness 'codex' cannot run model 'nous-portal/stealth/space-bunny-alpha'" in str(
        exc.value
    )


def test_preflight_models_reports_an_unreadable_roster(tmp_path: Path) -> None:
    roster = _offline_roster(tmp_path)
    (roster / "agents.yaml").write_text("agents: [", encoding="utf-8", newline="\n")
    with pytest.raises(SetupError, match="cannot check the models"):
        runner._preflight_models(roster)


def test_preflight_github_stops_on_an_unknown_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The model check runs in the preflight, before the sandbox is touched."""
    seen: list[str] = []
    monkeypatch.setattr(runner, "_require_just", lambda: seen.append("just"))
    monkeypatch.setattr(runner, "_preflight_harnesses", lambda roster: seen.append("harness"))

    def fail(roster: Path | None) -> None:
        seen.append("models")
        raise SetupError("unknown model")

    monkeypatch.setattr(runner, "_preflight_models", fail)
    monkeypatch.setattr(sandbox, "gh_executable", lambda: "gh")

    class Done:
        returncode = 0
        stdout = stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Done())
    with pytest.raises(SetupError, match="unknown model"):
        runner.preflight_github("owner/name", tmp_path)
    assert seen[-2:] == ["harness", "models"]
