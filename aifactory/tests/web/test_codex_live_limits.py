"""App-server transport and normalization, with fake processes only."""

import io
import json
import os
import subprocess
import threading
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from aifactory.web.limits import LimitsSource, codex_limits, codex_rate_limits

NOW = 1_000_000.0


def window(minutes: int, used: float = 25) -> dict[str, Any]:
    return {"usedPercent": used, "windowDurationMins": minutes, "resetsAt": NOW + 100}


class FakeProcess:
    def __init__(self, messages: list[dict[str, Any]], stubborn: bool = False) -> None:
        self.stdin = io.StringIO()
        self.stdout: Any = io.StringIO("".join(json.dumps(m) + "\n" for m in messages))
        self.stubborn = stubborn
        self.terminated = False
        self.killed = False
        self.sent: list[dict[str, Any]] = []

    def poll(self) -> None:
        return None

    def terminate(self) -> None:
        self.sent = [json.loads(line) for line in self.stdin.getvalue().splitlines()]
        self.terminated = True

    def wait(self, timeout: float) -> int:
        if self.stubborn and not self.killed:
            raise subprocess.TimeoutExpired("codex", timeout)
        return 0

    def kill(self) -> None:
        self.killed = True


def test_rpc_handshake_and_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    limits = {"rateLimits": {"primary": window(300)}}
    process = FakeProcess(
        [
            {"method": "notice"},
            {"id": 1, "result": {}},
            {"method": "account/rateLimits/updated", "params": {}},
            {"id": 2, "result": limits},
        ]
    )
    seen: dict[str, Any] = {}

    def popen(cmd: list[str], **kwargs: Any) -> FakeProcess:
        seen.update(command=cmd, **kwargs)
        return process

    monkeypatch.setattr("aifactory.web.limits.subprocess.Popen", popen)
    assert codex_rate_limits() == limits
    assert [m["method"] for m in process.sent] == [
        "initialize",
        "initialized",
        "account/rateLimits/read",
    ]
    assert "mcp_servers={}" in seen["command"]
    assert seen["stderr"] == subprocess.DEVNULL
    assert seen["creationflags"] == (
        getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    )
    assert process.terminated and process.stdin.closed and process.stdout.closed


@pytest.mark.parametrize(
    "messages, timeout",
    [
        ([], 1),
        ([{"id": 1, "error": {"message": "secret"}}], 1),
        ([{"id": 1, "result": {}}], 0),
    ],
)
def test_rpc_failure_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    messages: list[dict[str, Any]],
    timeout: float,
) -> None:
    process = FakeProcess(messages, stubborn=True)
    monkeypatch.setattr("aifactory.web.limits.subprocess.Popen", lambda *a, **kw: process)
    with pytest.raises((ValueError, TimeoutError)) as error:
        codex_rate_limits(timeout=timeout)
    assert "secret" not in str(error.value)
    assert process.terminated and process.killed
    assert process.stdin.closed and process.stdout.closed


def test_rpc_silent_process_times_out_and_releases_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    stopped = threading.Event()

    class WaitingOutput:
        closed = False

        def __iter__(self) -> Iterator[str]:
            stopped.wait(2)
            return iter(())

        def close(self) -> None:
            self.closed = True

    class SilentProcess(FakeProcess):
        def terminate(self) -> None:
            super().terminate()
            stopped.set()

    process = SilentProcess([])
    process.stdout = WaitingOutput()
    monkeypatch.setattr("aifactory.web.limits.subprocess.Popen", lambda *a, **kw: process)
    with pytest.raises(TimeoutError, match="timeout"):
        codex_rate_limits(timeout=0.02)
    assert stopped.is_set() and process.terminated
    assert process.stdout.closed and process.stdin.closed


def test_live_selects_codex_bucket_and_real_durations(tmp_path: Path) -> None:
    data = {
        "rateLimits": {"primary": window(15, 90)},
        "rateLimitsByLimitId": {
            "other": {"primary": window(300, 90)},
            "codex": {"primary": window(300), "secondary": window(10080, 60)},
        },
    }
    entry = codex_limits(rpc=lambda: data, now=lambda: NOW, sessions=lambda: tmp_path)
    assert entry["error"] is None
    assert [(w["id"], w["left"]) for w in entry["windows"]] == [("5h", 75), ("1w", 40)]
    for unsupported in (15, 1440, 20000):

        def rpc(minutes: int = unsupported) -> dict[str, Any]:
            return {"rateLimits": {"primary": window(minutes)}}

        bad = codex_limits(
            rpc=rpc,
            now=lambda: NOW,
            sessions=lambda: tmp_path,
        )
        assert bad["windows"] == [] and bad["error"]


def test_missing_codex_bucket_does_not_use_another_product(tmp_path: Path) -> None:
    other = {"limitId": "other", "primary": window(300)}
    data = {"rateLimits": other, "rateLimitsByLimitId": {"other": other}}
    entry = codex_limits(rpc=lambda: data, now=lambda: NOW, sessions=lambda: tmp_path)
    assert entry["windows"] == [] and entry["error"]
    data["rateLimits"] = {"limitId": "codex", "primary": window(300)}
    assert codex_limits(rpc=lambda: data, now=lambda: NOW)["windows"][0]["left"] == 75


def test_cache_expires_codex_stale_windows_without_inventing_capacity(tmp_path: Path) -> None:
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory/agents.yaml").write_text("defaults: {harness: codex}\n")
    clock = [0.0]
    now = [datetime.fromtimestamp(NOW).astimezone()]
    calls = []

    def read() -> dict[str, Any]:
        calls.append(1)
        data = {"rateLimits": {"primary": window(300)}} if len(calls) == 1 else {}
        return codex_limits(
            rpc=lambda: data, now=lambda: now[0].timestamp(), sessions=lambda: tmp_path
        )

    source = LimitsSource({"codex": read}, clock=lambda: clock[0], now=lambda: now[0])
    fresh = source.get(tmp_path)["providers"][0]
    assert fresh["stale"] is False
    assert source.get(tmp_path)["providers"][0] == fresh and len(calls) == 1
    clock[0] = 61
    stale = source.get(tmp_path)["providers"][0]
    assert stale["stale"] and stale["windows"][0]["left"] == 75
    clock[0] = 122
    now[0] = datetime.fromtimestamp(NOW + 101).astimezone()
    expired = source.get(tmp_path)["providers"][0]
    assert expired["stale"] and expired["windows"] == [] and expired["error"]
