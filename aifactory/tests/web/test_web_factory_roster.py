"""Roster editor of the Factory tab: GET and POST /factory/roster (HAIFA-REFINEMENT-T01)."""

from __future__ import annotations

from pathlib import Path

import yaml
from test_web_factory import AGENTS, Api, api, git, home, install

from aifactory.config.roster import PRESETS
from aifactory.harness.override import THINKING_LEVELS

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
    workflow = root / WORKFLOW
    text = workflow.read_text(encoding="utf-8")
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
    before = (root / AGENTS).read_bytes()
    data = api.post("a", "factory/roster", {"preset": "codex", "dry_run": True})["data"]
    assert data["changed"] is True and data["dry_run"] is True
    assert "codex" in data["diff"]
    assert {a["harness"] for a in data["agents"]} == {"codex"}
    assert {a["harness"] for a in data["before"]} == {"claude"}
    assert "path" not in data
    assert (root / AGENTS).read_bytes() == before


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
    assert _agents(root)["builder"]["thinking"] == "high"
    assert git(root, "rev-parse", "HEAD") == head
    assert AGENTS in git(root, "status", "--porcelain")
    # the same change again changes nothing
    again = api.post("a", "factory/roster", {"agent": "builder", "thinking": "high"})["data"]
    assert again["changed"] is False and again["diff"] == ""


def test_invalid_roster_change_is_422(api: Api, tmp_path: Path) -> None:
    install(api, "a")
    before = (tmp_path / "a" / AGENTS).read_bytes()
    for body in (
        {"thinking": "enormous"},
        {"agent": "nobody", "model": "x"},
        {"preset": "gemini"},
        {"dry_run": True},
    ):
        error = api.post("a", "factory/roster", body, status=422)["error"]
        assert error["code"] == "invalid_config", body
    assert (tmp_path / "a" / AGENTS).read_bytes() == before


def test_roster_body_validation(api: Api, tmp_path: Path) -> None:
    install(api, "a")
    for body in (
        {"preset": "codex", "dry_run": "yes"},
        {"preset": "codex", "path": "/etc/passwd"},
        {"harness": 3},
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
