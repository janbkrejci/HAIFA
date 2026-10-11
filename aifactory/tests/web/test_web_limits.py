"""Session limits of Claude and Codex for the topbar: /api/limits and its readers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from web_repo import git_repo

from aifactory.web import create_app, create_multi_app
from aifactory.web.limits import (
    LimitsSource,
    available_harnesses,
    claude_limits,
    codex_limits,
    used_harnesses,
)

BASE = "http://127.0.0.1:4700"
NOW = 1_800_000_000.0


def _agents(repo: Path, text: str) -> None:
    (repo / ".factory").mkdir(parents=True, exist_ok=True)
    (repo / ".factory" / "agents.yaml").write_text(text, encoding="utf-8", newline="\n")


def test_used_harnesses_reads_agents_and_workflows(tmp_path: Path) -> None:
    _agents(tmp_path, "defaults:\n  harness: claude\nagents:\n  - name: a\n    harness: pi\n")
    assert used_harnesses(tmp_path) == ["claude"]
    (tmp_path / ".factory" / "workflows").mkdir()
    (tmp_path / ".factory" / "workflows" / "w.yaml").write_text(
        "steps:\n  - agent: a\n    harness: codex\n", encoding="utf-8", newline="\n"
    )
    assert used_harnesses(tmp_path) == ["claude", "codex"]


def test_used_harnesses_without_config(tmp_path: Path) -> None:
    assert used_harnesses(tmp_path) == []


# -- Claude: rate_limit_event in the agent outputs of HAIFA runs ---------------------------


def _rate_event(five: float, week: float, five_resets: float, week_resets: float) -> str:
    return json.dumps(
        {
            "type": "rate_limit_event",
            "rate_limit_info": {
                "status": "allowed",
                "unifiedWindows": {
                    "five_hour": {"utilization": five, "resetsAt": five_resets},
                    "seven_day": {"utilization": week, "resetsAt": week_resets},
                },
            },
        }
    )


def _claude_output(root: Path, run: str, lines: list[str], mtime: float) -> Path:
    path = root / ".factory" / "data" / "sessions" / run / "builder" / "raw_output.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def test_claude_limits_take_the_last_event_of_the_last_written_run(tmp_path: Path) -> None:
    one, two = tmp_path / "one", tmp_path / "two"
    _claude_output(one, "r1", [_rate_event(0.9, 0.9, NOW + 10, NOW + 10)], NOW - 300)
    _claude_output(
        two,
        "r2",
        [
            _rate_event(0.1, 0.2, NOW + 100, NOW + 1000),
            '{"type":"assistant"}',
            _rate_event(0.4, 0.22, NOW + 100, NOW - 1),
            '{"type":"result"}',
        ],
        NOW - 60,
    )
    # a newer output without any event does not hide the older numbers
    _claude_output(one, "r3", ['{"type":"result"}'], NOW - 10)
    entry = claude_limits([one, two], now=lambda: NOW)
    assert entry["error"] is None
    five, week = entry["windows"]
    assert (five["id"], round(five["used"]), round(five["left"])) == ("5h", 40, 60)
    assert five["resets_at"] is not None
    # the weekly window reset since the run: nothing of it is used now
    assert (week["id"], week["used"], week["resets_at"]) == ("1w", 0.0, None)
    assert entry["measured_at"].startswith("2027-01-15")


def test_claude_limits_without_runs(tmp_path: Path) -> None:
    entry = claude_limits([tmp_path / "missing"], now=lambda: NOW)
    assert entry["windows"] == []
    assert entry["error"]


# -- Codex: rate_limits in Codex's own session logs ----------------------------------------


def _token_count(timestamp: str, primary: Any, secondary: Any) -> str:
    limits = {"limit_id": "codex", "primary": primary, "secondary": secondary}
    return json.dumps(
        {
            "timestamp": timestamp,
            "type": "event_msg",
            "payload": {"type": "token_count", "rate_limits": limits},
        }
    )


def _codex_log(root: Path, day: str, name: str, lines: list[str]) -> None:
    directory = root / day
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_codex_limits_take_the_last_window_and_drop_passed_resets(tmp_path: Path) -> None:
    now = 1_000_000.0
    _codex_log(
        tmp_path,
        "2026/09/20",
        "rollout-a.jsonl",
        [
            _token_count(
                "2026-09-20T10:00:00Z",
                {"used_percent": 10.0, "window_minutes": 300, "resets_at": now + 100},
                None,
            ),
            _token_count(
                "2026-09-20T11:00:00Z",
                {"used_percent": 70.0, "window_minutes": 300, "resets_at": now + 100},
                {"used_percent": 36.0, "window_minutes": 10080, "resets_at": now - 1},
            ),
        ],
    )
    # a newer log whose limits carry no window does not hide the older numbers
    _codex_log(
        tmp_path,
        "2026/09/26",
        "rollout-b.jsonl",
        [_token_count("2026-09-26T10:00:00Z", None, None)],
    )
    entry = codex_limits(sessions=lambda: tmp_path, now=lambda: now)
    assert entry["error"] is None
    assert entry["measured_at"].startswith("2026-09-20")
    (five,) = entry["windows"]
    assert (five["id"], five["used"], five["left"]) == ("5h", 70.0, 30.0)
    assert five["resets_at"] is not None
    expired = codex_limits(sessions=lambda: tmp_path, now=lambda: now + 101)
    assert expired["windows"] == [] and expired["error"]


def test_codex_limits_without_logs(tmp_path: Path) -> None:
    entry = codex_limits(sessions=lambda: tmp_path / "missing")
    assert entry["windows"] == []
    assert entry["error"]


# -- the cached source ---------------------------------------------------------------------


def _entry(harness: str) -> dict[str, Any]:
    return {"harness": harness, "label": harness.title(), "windows": [], "error": "x"}


def test_source_caches_and_survives_a_failing_reader(tmp_path: Path) -> None:
    _agents(tmp_path, "defaults:\n  harness: claude\nagents:\n  - name: b\n    harness: codex\n")
    calls: list[str] = []

    def claude(roots: list[Path]) -> dict[str, Any]:
        calls.append("claude")
        return {"harness": "claude", "label": "Claude", "windows": [], "error": None}

    def codex(roots: list[Path]) -> dict[str, Any]:
        raise RuntimeError("boom")

    clock = [0.0]
    source = LimitsSource({"claude": claude, "codex": codex}, ttl=60, clock=lambda: clock[0])
    first = source.get(tmp_path)
    assert [p["harness"] for p in first["providers"]] == ["claude", "codex"]
    assert first["providers"][1]["error"] == "boom"
    source.get(tmp_path)
    assert calls == ["claude"]
    clock[0] = 61
    source.get(tmp_path)
    assert calls == ["claude", "claude"]


def test_source_searches_the_registered_repositories_and_the_one_asked(tmp_path: Path) -> None:
    one, two = tmp_path / "one", tmp_path / "two"
    _agents(two, "defaults:\n  harness: claude\n")
    seen: list[list[Path]] = []

    def claude(roots: list[Path]) -> dict[str, Any]:
        seen.append(roots)
        return _entry("claude")

    source = LimitsSource({"claude": claude}, available=lambda: ["claude"], roots=lambda: [one])
    source.get(None)
    source.get(two)
    assert seen == [[one.resolve()], sorted([one.resolve(), two.resolve()])]


def test_disabled_provider_is_not_queried_even_when_in_roster(tmp_path: Path) -> None:
    _agents(tmp_path, "defaults:\n  harness: claude\n")

    def reader(roots: list[Path]) -> dict[str, Any]:
        pytest.fail("disabled provider queried")

    source = LimitsSource({"claude": reader}, available=lambda: ["claude"], enabled=lambda _: False)
    assert source.get(tmp_path)["providers"] == []


def test_codex_roster_still_shows_an_available_claude(tmp_path: Path) -> None:
    _agents(tmp_path, "defaults:\n  harness: codex\n")
    readers = {"claude": lambda _: _entry("claude"), "codex": lambda _: _entry("codex")}
    source = LimitsSource(readers, available=lambda: ["claude"])
    assert [p["harness"] for p in source.get(tmp_path)["providers"]] == ["claude", "codex"]
    assert [p["harness"] for p in source.get(None)["providers"]] == ["claude"]
    assert LimitsSource(readers).get(tmp_path)["providers"] == [_entry("codex")]


def test_available_harnesses(tmp_path: Path) -> None:
    sessions = tmp_path / "codex" / "sessions"

    def which(name: str) -> str | None:
        return None

    assert available_harnesses(which, lambda: sessions) == []
    sessions.mkdir(parents=True)
    assert available_harnesses(which, lambda: sessions) == ["codex"]
    assert available_harnesses(lambda name: f"/bin/{name}", lambda: tmp_path / "none") == [
        "claude",
        "codex",
    ]


def test_limits_endpoint(tmp_path: Path) -> None:
    root = git_repo(tmp_path / "repo")
    _agents(root, "defaults:\n  harness: claude\nagents:\n  - name: a\n")
    app = create_app(
        root,
        static_dir=tmp_path / "nostatic",
        limits_source=LimitsSource({"claude": lambda _: _entry("claude")}),
    )
    body = TestClient(app, base_url=BASE).get("/api/limits").json()
    assert body["ok"] is True
    assert body["data"]["providers"] == [_entry("claude")]


def test_global_limits_endpoint(tmp_path: Path) -> None:
    readers = {"claude": lambda _: _entry("claude"), "codex": lambda _: _entry("codex")}
    app = create_multi_app(
        home=tmp_path / "home",
        static_dir=tmp_path / "nostatic",
        limits_source=LimitsSource(readers, available=lambda: ["codex"]),
        user_home=tmp_path,
    )
    body = TestClient(app, base_url=BASE).get("/api/limits").json()
    assert body["ok"] is True
    assert body["data"]["providers"] == [_entry("codex")]
