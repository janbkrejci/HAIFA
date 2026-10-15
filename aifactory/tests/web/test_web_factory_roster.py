"""Roster editor of the Factory tab: GET and POST /factory/roster (HAIFA-REFINEMENT-T01)."""

from __future__ import annotations

from pathlib import Path

import yaml
from test_web_factory import AGENTS, Api, api, git, home, install

from aifactory.config.roster import PRESETS
from aifactory.harness.override import THINKING_LEVELS
from aifactory.workflow import DEFAULT_WORKFLOWS_DIR

__all__ = ["api", "home"]

WORKFLOW = ".factory/workflows/simple-sdlc.yaml"
BUILD = "  - build:\n      description: Implement the plan exactly\n"


def _agents(root: Path) -> dict[str, dict[str, object]]:
    data = yaml.safe_load((root / AGENTS).read_text(encoding="utf-8"))
    return {a["name"]: a for a in data["agents"]}


def test_roster_lists_presets_thinking_levels_and_step_overrides(api: Api, tmp_path: Path) -> None:
    install(api, "a")
    root = tmp_path / "a"
    plain = api.get("a", "factory/roster")["data"]
    assert plain["presets"] == PRESETS
    assert plain["thinking_levels"] == list(THINKING_LEVELS)
    assert plain["workflow_overrides"] == []
    # the repo's own copy of the library workflow, with step overrides
    workflow = root / WORKFLOW
    workflow.parent.mkdir(parents=True, exist_ok=True)
    text = (DEFAULT_WORKFLOWS_DIR / "simple-sdlc.yaml").read_text(encoding="utf-8")
    assert BUILD in text
    workflow.write_text(
        text.replace(BUILD, BUILD + "      harness: codex\n      thinking: high\n"),
        encoding="utf-8",
        newline="\n",
    )
    rows = api.get("a", "factory/roster")["data"]["workflow_overrides"]
    assert rows == [
        {
            "workflow": "simple-sdlc",
            "step": "build",
            "agent": "builder",
            "harness": "codex",
            "model": None,
            "thinking": "high",
        }
    ]


def test_roster_preview_writes_nothing(api: Api, tmp_path: Path) -> None:
    install(api, "a")
    root = tmp_path / "a"
    assert not (root / AGENTS).exists()  # every agent comes from the library
    data = api.post("a", "factory/roster", {"preset": "codex", "dry_run": True})["data"]
    assert data["changed"] is True and data["dry_run"] is True
    assert "codex" in data["diff"]
    assert {a["harness"] for a in data["agents"]} == {"codex"}
    assert {a["harness"] for a in data["before"]} == {"claude"}
    assert {a["origin"] for a in data["agents"]} == {"library"}
    assert "path" not in data
    assert not (root / AGENTS).exists()


def test_roster_change_writes_the_working_tree_only(api: Api, tmp_path: Path) -> None:
    install(api, "a")
    root = tmp_path / "a"
    head = git(root, "rev-parse", "HEAD")
    data = api.post(
        "a", "factory/roster", {"agent": "builder", "thinking": "high", "dry_run": False}
    )["data"]
    assert data["changed"] is True
    builder = next(a for a in data["agents"] if a["name"] == "builder")
    assert builder["thinking"] == "high"
    assert _agents(root)["builder"] == {"name": "builder", "thinking": "high"}
    assert git(root, "rev-parse", "HEAD") == head
    assert AGENTS in git(root, "status", "--porcelain")
    # the same change again changes nothing
    again = api.post("a", "factory/roster", {"agent": "builder", "thinking": "high"})["data"]
    assert again["changed"] is False and again["diff"] == ""


def test_invalid_roster_change_is_422(api: Api, tmp_path: Path) -> None:
    install(api, "a")
    for body in (
        {"thinking": "enormous"},
        {"agent": "nobody", "model": "x"},
        {"preset": "gemini"},
        {"dry_run": True},
    ):
        error = api.post("a", "factory/roster", body, status=422)["error"]
        assert error["code"] == "invalid_config", body
    assert not (tmp_path / "a" / AGENTS).exists()


def test_roster_body_validation(api: Api, tmp_path: Path) -> None:
    install(api, "a")
    for body in (
        {"preset": "codex", "dry_run": "yes"},
        {"preset": "codex", "path": "/etc/passwd"},
        {"harness": 3},
        {"agent": "builder", "reset": "model"},
        {"agent": "builder", "reset": ["tools"]},
    ):
        error = api.post("a", "factory/roster", body, status=400)["error"]
        assert error["code"] == "usage_error", body


def test_roster_write_passes_the_write_guard(api: Api, tmp_path: Path) -> None:
    install(api, "a")
    url = api.url("a", "factory/roster")
    body = {"preset": "codex", "dry_run": True}
    cross = api.client.post(url, json=body, headers={"Origin": "http://evil.example"})
    assert cross.status_code == 403
    assert cross.json()["error"]["code"] == "cross_origin"
    plain = api.client.post(url, content="x=1", headers={"Content-Type": "text/plain"})
    assert plain.status_code == 415


def test_roster_reset_returns_an_override_to_the_inherited_value(api: Api, tmp_path: Path) -> None:
    install(api, "a")
    root = tmp_path / "a"
    api.post("a", "factory/roster", {"agent": "builder", "thinking": "high", "dry_run": False})
    builder = next(
        a for a in api.get("a", "factory/roster")["data"]["agents"] if a["name"] == "builder"
    )
    assert builder["overridden"] == ["thinking"]
    assert builder["inherited"]["thinking"] != "high"
    inherited = builder["inherited"]
    body = {"agent": "builder", "reset": ["thinking"], "dry_run": True}
    preview = api.post("a", "factory/roster", body)["data"]
    assert preview["changed"] is True and "high" in preview["diff"]
    assert _agents(root)["builder"] == {"name": "builder", "thinking": "high"}
    api.post("a", "factory/roster", {**body, "dry_run": False})
    assert "builder" not in _agents(root)
    after = next(
        a for a in api.get("a", "factory/roster")["data"]["agents"] if a["name"] == "builder"
    )
    assert after["overridden"] == [] and after["thinking"] == inherited["thinking"]
