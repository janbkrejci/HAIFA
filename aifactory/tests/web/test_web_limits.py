"""Session limits of Claude and Codex for the topbar: /api/limits and its readers."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import threading
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from email.message import Message
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
    claude_token_state,
    codex_limits,
    used_harnesses,
)

BASE = "http://127.0.0.1:4700"


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


def test_claude_limits_from_usage_endpoint() -> None:
    seen: dict[str, Any] = {}

    def fetch(url: str, headers: dict[str, str]) -> Any:
        seen["url"], seen["auth"] = url, headers["Authorization"]
        return {
            "five_hour": {"utilization": 70.0, "resets_at": "2026-10-04T10:00:00+00:00"},
            "seven_day": {"utilization": 35, "resets_at": "2026-10-09T07:00:00+00:00"},
        }

    entry = claude_limits(state=lambda: ("ok", "tok"), fetch=fetch)
    assert seen == {"url": "https://api.anthropic.com/api/oauth/usage", "auth": "Bearer tok"}
    assert entry["error"] is None
    five, week = entry["windows"]
    assert (five["id"], five["used"], five["left"]) == ("5h", 70.0, 30.0)
    assert five["resets_at"] == "2026-10-04T10:00:00+00:00"
    assert (week["id"], week["used"], week["left"]) == ("1w", 35.0, 65.0)


def test_claude_limits_without_login_or_with_expired_token() -> None:
    assert claude_limits(state=lambda: ("missing", None))["error"]

    def expired(url: str, headers: dict[str, str]) -> Any:
        raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, io.BytesIO())  # type: ignore[arg-type]

    entry = claude_limits(state=lambda: ("ok", "tok"), fetch=expired)
    assert entry["windows"] == []
    assert "vypršelo" in entry["error"]


def _codex_log(root: Path, day: str, name: str, events: list[dict[str, Any]]) -> None:
    folder = root.joinpath(*day.split("/"))
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8", newline="\n"
    )


def _token_count(ts: str, primary: Any, secondary: Any) -> dict[str, Any]:
    return {
        "timestamp": ts,
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "rate_limits": {"limit_id": "codex", "primary": primary, "secondary": secondary},
        },
    }


def _offline() -> dict[str, Any]:
    raise OSError("offline")


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
    entry = codex_limits(sessions=lambda: tmp_path, now=lambda: now, rpc=_offline)
    assert entry["error"]
    assert entry["stale"] is True
    assert entry["measured_at"] == "2026-09-20T11:00:00Z"
    (five,) = entry["windows"]
    assert (five["id"], five["used"], five["left"]) == ("5h", 70.0, 30.0)
    assert five["resets_at"] is not None
    source = LimitsSource(
        {"codex": lambda: codex_limits(sessions=lambda: tmp_path, now=lambda: now, rpc=_offline)},
        now=lambda: datetime.fromtimestamp(now).astimezone(),
    )
    cached = source._read("codex")
    assert cached["stale"] and cached["measured_at"] == entry["measured_at"]
    expired = codex_limits(sessions=lambda: tmp_path, now=lambda: now + 101, rpc=_offline)
    assert expired["windows"] == [] and expired["error"]


def test_codex_limits_without_logs(tmp_path: Path) -> None:
    entry = codex_limits(sessions=lambda: tmp_path / "missing", rpc=_offline)
    assert entry["windows"] == []
    assert entry["error"]


def test_source_caches_and_survives_a_failing_reader(tmp_path: Path) -> None:
    _agents(tmp_path, "defaults:\n  harness: claude\nagents:\n  - name: b\n    harness: codex\n")
    calls: list[str] = []

    def claude() -> dict[str, Any]:
        calls.append("claude")
        return {"harness": "claude", "label": "Claude", "windows": [], "error": None}

    def codex() -> dict[str, Any]:
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


def _claude_entry(used: float, resets_at: str | None) -> dict[str, Any]:
    window = {"id": "5h", "label": "5h", "used": used, "left": 100 - used, "resets_at": resets_at}
    return {"harness": "claude", "label": "Claude", "windows": [window], "error": None}


def test_source_keeps_the_last_measured_limits_across_failures_and_restarts(
    tmp_path: Path,
) -> None:
    _agents(tmp_path, "defaults:\n  harness: claude\n")
    answers: list[dict[str, Any]] = [
        _claude_entry(70, "2026-10-04T15:00:00+00:00"),
        {"harness": "claude", "label": "Claude", "windows": [], "error": "HTTP 429"},
    ]
    clock = [0.0]
    now = [datetime.fromisoformat("2026-10-04T12:00:00+00:00")]
    last = tmp_path / "home" / "limits.json"

    def source() -> LimitsSource:
        return LimitsSource(
            {"claude": lambda: answers.pop(0)},
            ttl=60,
            clock=lambda: clock[0],
            last_file=lambda: last,
            now=lambda: now[0],
        )

    first = source()
    (fresh,) = first.get(tmp_path)["providers"]
    assert (fresh["stale"], fresh["error"]) == (False, None)
    assert fresh["measured_at"] == "2026-10-04T12:00:00+00:00"
    assert fresh["windows"][0]["used"] == 70

    # the next read fails: the last measured limits stay, with when and why
    clock[0] = 61
    (stale,) = first.get(tmp_path)["providers"]
    assert (stale["stale"], stale["error"]) == (True, "HTTP 429")
    assert stale["measured_at"] == "2026-10-04T12:00:00+00:00"
    assert stale["windows"][0]["used"] == 70

    # a restarted dashboard reads them from the file; after the reset the window is unused
    answers.append({"harness": "claude", "label": "Claude", "windows": [], "error": "offline"})
    now[0] = datetime.fromisoformat("2026-10-04T15:30:00+00:00")
    (restarted,) = source().get(tmp_path)["providers"]
    assert (restarted["stale"], restarted["error"]) == (True, "offline")
    assert (restarted["windows"][0]["used"], restarted["windows"][0]["left"]) == (0.0, 100.0)


def test_source_without_any_measurement_returns_the_error(tmp_path: Path) -> None:
    _agents(tmp_path, "defaults:\n  harness: claude\n")
    failed = {"harness": "claude", "label": "Claude", "windows": [], "error": "HTTP 429"}
    source = LimitsSource({"claude": lambda: failed}, last_file=lambda: tmp_path / "limits.json")
    assert source.get(tmp_path)["providers"] == [failed]
    assert not (tmp_path / "limits.json").exists()


def test_limits_endpoint(tmp_path: Path) -> None:
    root = git_repo(tmp_path / "repo")
    _agents(root, "defaults:\n  harness: claude\nagents:\n  - name: a\n")

    def claude() -> dict[str, Any]:
        return {"harness": "claude", "label": "Claude", "windows": [], "error": "x"}

    app = create_app(
        root, static_dir=tmp_path / "nostatic", limits_source=LimitsSource({"claude": claude})
    )
    body = TestClient(app, base_url=BASE).get("/api/limits").json()
    assert body["ok"] is True
    assert body["data"]["providers"] == [
        {"harness": "claude", "label": "Claude", "windows": [], "error": "x"}
    ]


# -- Claude token: keychain vs. file, expiry --------------------------------------------

NOW = 1_800_000_000.0


def _credentials(token: str, expires_at: float | None) -> str:
    oauth: dict[str, Any] = {"accessToken": token}
    if expires_at is not None:
        oauth["expiresAt"] = expires_at
    return json.dumps({"claudeAiOauth": oauth})


def _sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, keychain: str | None, file: str | None
) -> list[list[str]]:
    """The keychain answers ``keychain`` (macOS), ``$CLAUDE_CONFIG_DIR`` holds ``file``."""
    calls: list[list[str]] = []

    def run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        if keychain is None:
            return subprocess.CompletedProcess(cmd, 44, "", "not found")
        return subprocess.CompletedProcess(cmd, 0, keychain + "\n", "")

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(sys, "platform", "darwin")
    config = tmp_path / "claude-config"
    config.mkdir()
    if file is not None:
        (config / ".credentials.json").write_text(file, encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    return calls


def test_expired_file_token_loses_to_a_valid_keychain_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = _sources(
        monkeypatch,
        tmp_path,
        keychain=_credentials("fresh", (NOW + 3600) * 1000),
        file=_credentials("old", (NOW - 60) * 1000),
    )
    assert claude_token_state(lambda: NOW) == ("ok", "fresh")
    assert calls and calls[0][0] == "security"


def test_token_expiring_last_wins_and_missing_expiry_is_the_last_resort(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _sources(
        monkeypatch,
        tmp_path,
        keychain=_credentials("keychain", None),
        file=_credentials("file", (NOW + 60) * 1000),
    )
    assert claude_token_state(lambda: NOW) == ("ok", "file")


def test_only_expired_tokens_fail_without_a_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _sources(
        monkeypatch,
        tmp_path,
        keychain=_credentials("a", (NOW - 10) * 1000),
        file=_credentials("b", (NOW - 20) * 1000),
    )
    assert claude_token_state(lambda: NOW) == ("expired", None)

    def fetch(url: str, headers: dict[str, str]) -> Any:
        raise AssertionError("no request with an expired token")

    entry = claude_limits(state=lambda: claude_token_state(lambda: NOW), fetch=fetch)
    assert entry["windows"] == []
    assert entry["error"] == "přihlášení Claude Code vypršelo, spusť claude"


def test_no_credentials_are_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _sources(monkeypatch, tmp_path, keychain=None, file=None)
    assert claude_token_state(lambda: NOW) == ("missing", None)


# -- HTTP 429 ----------------------------------------------------------------------------


def _too_many(retry_after: str | None) -> Any:
    def fetch(url: str, headers: dict[str, str]) -> Any:
        message = Message()
        if retry_after is not None:
            message["Retry-After"] = retry_after
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", message, io.BytesIO())

    return fetch


def test_rate_limited_usage_api_says_when_to_retry() -> None:
    entry = claude_limits(state=lambda: ("ok", "tok"), fetch=_too_many("600"))
    assert entry["error"] == "Claude usage API omezuje dotazy, zkus za 10 min"
    assert entry["retry_after"] == 600.0
    plain = claude_limits(state=lambda: ("ok", "tok"), fetch=_too_many(None))
    assert plain["error"] == "Claude usage API omezuje dotazy, zkus to později"
    assert "retry_after" not in plain


def test_source_holds_a_rate_limited_answer_for_retry_after(tmp_path: Path) -> None:
    _agents(tmp_path, "defaults:\n  harness: claude\n")
    calls: list[int] = []
    answers = [
        _claude_entry(40, None),
        claude_limits(state=lambda: ("ok", "tok"), fetch=_too_many("300")),
    ]

    def claude() -> dict[str, Any]:
        calls.append(1)
        return answers[min(len(calls) - 1, 1)]

    clock = [0.0]
    source = LimitsSource({"claude": claude}, ttl=60, clock=lambda: clock[0])
    assert source.get(tmp_path)["providers"][0]["stale"] is False
    clock[0] = 61
    (limited,) = source.get(tmp_path)["providers"]
    # the last measured windows stay, with the rate limit as the error
    assert limited["stale"] is True and limited["windows"][0]["used"] == 40
    assert "nejdříve za 5 min" in limited["error"]
    clock[0] = 61 + 200  # past ttl, before Retry-After
    source.get(tmp_path)
    assert len(calls) == 2
    clock[0] = 61 + 301
    source.get(tmp_path)
    assert len(calls) == 3


# -- which providers are shown -----------------------------------------------------------


def test_missing_retry_after_backs_off_and_success_resets_delay(tmp_path: Path) -> None:
    _agents(tmp_path, "defaults:\n  harness: claude\n")
    clock = [0.0]
    calls = []
    limited = claude_limits(state=lambda: ("ok", "tok"), fetch=_too_many(None))
    answers = [limited, limited, _claude_entry(20, None), limited]

    def reader() -> dict[str, Any]:
        calls.append(1)
        return answers[len(calls) - 1]

    source = LimitsSource({"claude": reader}, clock=lambda: clock[0])
    source.get(tmp_path)
    clock[0] = 299
    source.get(tmp_path)
    assert len(calls) == 1
    clock[0] = 300
    source.get(tmp_path)
    clock[0] = 899
    source.get(tmp_path)
    assert len(calls) == 2
    clock[0] = 900
    assert source.get(tmp_path)["providers"][0]["error"] is None
    clock[0] = 961
    source.get(tmp_path)
    assert source._cache["claude"][1] == 300


def test_parallel_reads_share_one_provider_request() -> None:
    entered, release = threading.Event(), threading.Event()
    calls = []

    def reader() -> dict[str, Any]:
        calls.append(1)
        entered.set()
        assert release.wait(5)
        return _claude_entry(20, None)

    source = LimitsSource({"claude": reader})
    with ThreadPoolExecutor(max_workers=4) as pool:
        requests = [pool.submit(source._read, "claude") for _ in range(4)]
        assert entered.wait(5)
        release.set()
        assert all(r.result()["error"] is None for r in requests)
    assert len(calls) == 1


def test_disabled_provider_is_not_queried_even_when_in_roster(tmp_path: Path) -> None:
    _agents(tmp_path, "defaults:\n  harness: claude\n")

    def reader() -> dict[str, Any]:
        pytest.fail("disabled provider queried")

    source = LimitsSource({"claude": reader}, available=lambda: ["claude"], enabled=lambda _: False)
    assert source.get(tmp_path)["providers"] == []


def _entry(harness: str) -> dict[str, Any]:
    return {"harness": harness, "label": harness.title(), "windows": [], "error": "x"}


def test_codex_roster_still_shows_an_available_claude(tmp_path: Path) -> None:
    _agents(tmp_path, "defaults:\n  harness: codex\n")
    readers = {"claude": lambda: _entry("claude"), "codex": lambda: _entry("codex")}
    source = LimitsSource(readers, available=lambda: ["claude"])
    assert [p["harness"] for p in source.get(tmp_path)["providers"]] == ["claude", "codex"]
    assert [p["harness"] for p in source.get(None)["providers"]] == ["claude"]
    assert LimitsSource(readers).get(tmp_path)["providers"] == [_entry("codex")]


def test_available_harnesses(tmp_path: Path) -> None:
    sessions = tmp_path / "codex" / "sessions"

    def which(name: str) -> str | None:
        return None

    assert available_harnesses(lambda: ("missing", None), which, lambda: sessions) == []
    assert available_harnesses(lambda: ("expired", None), which, lambda: sessions) == ["claude"]
    sessions.mkdir(parents=True)
    assert available_harnesses(lambda: ("missing", None), which, lambda: sessions) == ["codex"]
    assert available_harnesses(
        lambda: ("missing", None), lambda name: f"/bin/{name}", lambda: tmp_path / "none"
    ) == ["claude", "codex"]


def test_global_limits_endpoint(tmp_path: Path) -> None:
    readers = {"claude": lambda: _entry("claude"), "codex": lambda: _entry("codex")}
    app = create_multi_app(
        home=tmp_path / "home",
        static_dir=tmp_path / "nostatic",
        limits_source=LimitsSource(readers, available=lambda: ["codex"]),
        user_home=tmp_path,
    )
    body = TestClient(app, base_url=BASE).get("/api/limits").json()
    assert body["ok"] is True
    assert body["data"]["providers"] == [_entry("codex")]
