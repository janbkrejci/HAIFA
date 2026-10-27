"""Machine resources, safe cleanup delegation and write protection."""

from __future__ import annotations

import ctypes
import shutil
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from anyio.from_thread import start_blocking_portal
from starlette.testclient import TestClient

from aifactory import review
from aifactory.review.flow import CleanResult
from aifactory.web import create_multi_app, system
from aifactory.web.registry import Registry, RegistryState, RepoEntry
from aifactory.workflow import adaptive

BASE = "http://127.0.0.1:4700"
GB = 1024**3


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    # No lifespan: unrelated monitoring jobs must not touch real services.
    return TestClient(create_multi_app(home=tmp_path / "home"), base_url=BASE)


def entry(path: Path) -> RepoEntry:
    return RepoEntry(path.name, path.name, str(path), "")


@pytest.mark.parametrize(
    "disk_free,disk_total,memory_free,memory_total,disk_status,status",
    [
        (20 * GB, 100 * GB, 4 * GB, 16 * GB, "ok", "ok"),
        (9 * GB, 20 * GB, 4 * GB, 16 * GB, "warning", "warning"),
        (20 * GB, 300 * GB, 4 * GB, 16 * GB, "warning", "warning"),
        (20 * GB, 100 * GB, GB - 1, 4 * GB, "ok", "warning"),
        (20 * GB, 100 * GB, 2 * GB, 32 * GB, "ok", "warning"),
        (10 * GB, 100 * GB, GB, 10 * GB, "ok", "ok"),
        (20 * GB, 100 * GB, None, None, "ok", "ok"),
    ],
)
def test_system_response(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    disk_free: int,
    disk_total: int,
    memory_free: int | None,
    memory_total: int | None,
    disk_status: str,
    status: str,
) -> None:
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(
        shutil, "disk_usage", lambda _: SimpleNamespace(free=disk_free, total=disk_total)
    )
    monkeypatch.setattr(system, "_memory", lambda: (memory_free, memory_total))
    response = client.get("/api/machine/system")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"]
    data = body["data"]
    assert data["status"] == status
    assert data["disk"] == {"free": disk_free, "total": disk_total, "status": disk_status}
    assert len(data["volumes"]) == 1
    volume = data["volumes"][0]
    assert volume["free"] == disk_free and volume["total"] == disk_total
    assert set(volume["paths"]) == {str(tmp_path.resolve()), str((tmp_path / "home").resolve())}
    assert data["memory"]["free"] == memory_free
    assert data["memory"]["total"] == memory_total


@pytest.mark.parametrize("home_exists", [True, False])
@pytest.mark.parametrize("home_free,repo_free", [(20 * GB, GB), (GB, 20 * GB)])
def test_volume_paths_and_devices(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    home_exists: bool,
    home_free: int,
    repo_free: int,
) -> None:
    home, repo, temp = [tmp_path / name for name in ("home", "repo", "temp")]
    for path in (home, repo, temp):
        path.mkdir()
    if not home_exists:
        home = home / "missing" / "nested"
    original = Path.stat

    def stat(path: Path, **kwargs: Any) -> Any:
        if path == repo:
            return SimpleNamespace(st_dev=999, st_mode=original(path).st_mode)
        return original(path, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(temp))
    inspected: list[Path] = []

    def usage(path: Path) -> SimpleNamespace:
        inspected.append(path)
        return SimpleNamespace(free=repo_free if path == repo else home_free, total=100 * GB)

    monkeypatch.setattr(shutil, "disk_usage", usage)
    monkeypatch.setattr(system, "_memory", lambda: (4 * GB, 16 * GB))
    data = system.system_info(home, [entry(repo), entry(repo)])
    volumes = data["volumes"]
    assert len(volumes) == 2
    assert volumes[0]["paths"] == [str(home.resolve()), str(temp.resolve())]
    assert volumes[1]["paths"] == [str(repo.resolve())]
    assert inspected == [tmp_path / "home", repo]
    home_status = "ok" if home_free == 20 * GB else "warning"
    assert data["disk"] == {"free": home_free, "total": 100 * GB, "status": home_status}
    assert volumes[1]["free"] == repo_free
    assert volumes[1]["status"] == ("ok" if repo_free == 20 * GB else "warning")
    assert data["status"] == home_status


def test_unavailable_resources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(*args: Any, **kwargs: Any) -> Any:
        raise OSError("unavailable")

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Path, "read_text", unavailable)
    monkeypatch.setattr(shutil, "disk_usage", unavailable)
    assert system._memory() == (None, None)
    data = system.system_info(tmp_path, [])
    assert data["disk"] == {"free": None, "total": None, "status": "ok"}
    assert data["status"] == "ok"
    assert all(v["free"] is None and v["total"] is None for v in data["volumes"])
    monkeypatch.setattr(adaptive, "cleanup_orphans", lambda: [])
    assert system.cleanup(tmp_path, [])["freed_bytes"] is None


@pytest.mark.parametrize("platform", ["linux", "darwin", "win32"])
def test_memory_platforms(monkeypatch: pytest.MonkeyPatch, platform: str) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    if platform == "linux":
        monkeypatch.setattr(
            Path,
            "read_text",
            lambda _: "MemTotal: 8192 kB\nMemFree: 10 kB\nMemAvailable: 2048 kB\n",
        )
        expected = (2048 * 1024, 8192 * 1024)
    elif platform == "darwin":

        def output(args: list[str], **kwargs: Any) -> Any:
            return (
                b"8192000\n"
                if args[0] == "sysctl"
                else (
                    "Mach Virtual Memory Statistics: (page size of 4096 bytes)\n"
                    "Pages free: 100.\nPages inactive: 200.\nPages speculative: 10.\n"
                )
            )

        monkeypatch.setattr(subprocess, "check_output", output)
        expected = (310 * 4096, 8192000)
    else:

        def memory_status(pointer: Any) -> int:
            value = pointer._obj
            assert value.length == ctypes.sizeof(value)
            value.total, value.available = 8 * GB, 2 * GB
            return 1

        monkeypatch.setattr(
            ctypes,
            "windll",
            SimpleNamespace(kernel32=SimpleNamespace(GlobalMemoryStatusEx=memory_status)),
            raising=False,
        )
        expected = (2 * GB, 8 * GB)
    assert system._memory() == expected


def test_cleanup_delegates_and_continues(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repos = [entry(tmp_path / name) for name in ("bad", "good", "last")]
    calls: list[Path | str] = []
    free = [20 * GB]

    def orphans() -> list[Path]:
        calls.append("advice")
        free[0] += 123
        return [tmp_path / "factory-advice-dead"]

    def clean(path: Path) -> CleanResult:
        calls.append(path)
        if path.name == "bad":
            raise RuntimeError("unreachable")
        return CleanResult(
            removed=[{"worktree": str(path / "finished")}],
            deleted_branches=["factory/finished"],
            warnings=["kept dirty tree"],
        )

    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(
        shutil, "disk_usage", lambda _: SimpleNamespace(free=free[0], total=100 * GB)
    )
    monkeypatch.setattr(adaptive, "cleanup_orphans", orphans)
    monkeypatch.setattr(review, "clean_worktrees", clean)
    data = system.cleanup(tmp_path, repos)
    assert calls == ["advice", *(Path(repo.path) for repo in repos)]
    assert data["advice_directories"] == [str(tmp_path / "factory-advice-dead")]
    assert data["freed_bytes"] == 123  # shared volume is counted once
    assert [r["repo"] for r in data["repos"]] == [repo.path for repo in repos[1:]]
    assert data["repos"][0]["deleted_branches"] == ["factory/finished"]
    assert data["repos"][0]["removed"] == [{"worktree": str(tmp_path / "good" / "finished")}]
    assert any("bad" in warning and "unreachable" in warning for warning in data["warnings"])
    assert len(data["warnings"]) == 3


@pytest.mark.parametrize(
    "kwargs,status",
    [
        ({"json": {}}, 403),
        ({"json": {}, "headers": {"Sec-Fetch-Site": "same-origin"}}, 403),
        ({"json": {}, "headers": {"Origin": ""}}, 403),
        ({"json": {}, "headers": {"Origin": "http://evil.example"}}, 403),
        ({"json": {}, "headers": {"Origin": "null"}}, 403),
        ({"json": {}, "headers": {"Origin": BASE, "Sec-Fetch-Site": "cross-site"}}, 403),
        ({"content": "{}", "headers": {"Origin": BASE, "Content-Type": "text/plain"}}, 415),
    ],
)
def test_cleanup_write_guard(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, kwargs: dict[str, Any], status: int
) -> None:
    def forbidden(*args: Any) -> Any:
        pytest.fail("rejected writes cannot clean anything")

    monkeypatch.setattr(system, "cleanup", forbidden)
    response = client.post("/api/machine/cleanup", **kwargs)
    assert response.status_code == status
    assert response.json()["error"]["code"] == (
        "cross_origin" if status == 403 else "unsupported_media_type"
    )


def test_cleanup_endpoint_busy_and_recovers(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    started, release = threading.Event(), threading.Event()

    def clean(home: Path, repos: Any) -> dict[str, Any]:
        started.set()
        assert release.wait(10)
        return {"advice_directories": [], "repos": [], "freed_bytes": 42, "warnings": ["kept"]}

    monkeypatch.setattr(system, "cleanup", clean)
    with start_blocking_portal() as portal, ThreadPoolExecutor() as pool:
        # Share one event loop between requests, without starting monitoring services.
        client.portal = portal
        pending = pool.submit(
            client.post, "/api/machine/cleanup", json={}, headers={"Origin": BASE}
        )
        try:
            assert started.wait(5)
            # Also proves that cleanup does not block the event loop.
            assert client.get("/api/machine/system").status_code == 200
            response = client.post("/api/machine/cleanup", json={}, headers={"Origin": BASE})
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "busy"
        finally:
            release.set()
        response = pending.result(timeout=10)
        client.portal = None
    assert response.status_code == 200
    assert response.json()["data"]["freed_bytes"] == 42
    assert response.json()["warnings"] == ["kept"]
    assert client.post("/api/machine/cleanup", json={}, headers={"Origin": BASE}).status_code == 200


@pytest.mark.parametrize("content", ["{", "[]", "null", ""])
def test_cleanup_requires_json_object(client: TestClient, content: str) -> None:
    response = client.post(
        "/api/machine/cleanup",
        content=content,
        headers={"Origin": BASE, "Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "usage_error"


def test_endpoints_use_registered_repos(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repos = (entry(tmp_path / "one"), entry(tmp_path / "two"))
    snapshot = RegistryState(version=1, port=4700, repos=repos)
    monkeypatch.setattr(Registry, "snapshot", lambda _: (snapshot, ["registry warning"]))
    calls: list[tuple[Path, Any]] = []

    def action(home: Path, registered: Any) -> dict[str, Any]:
        calls.append((home, registered))
        return {"warnings": []}

    monkeypatch.setattr(system, "system_info", action)
    monkeypatch.setattr(system, "cleanup", action)
    for response in (
        client.get("/api/machine/system"),
        client.post("/api/machine/cleanup", json={}, headers={"Origin": BASE}),
    ):
        assert response.status_code == 200
        assert response.json()["warnings"] == ["registry warning"]
    assert calls == [(tmp_path / "home", repos)] * 2


def test_cleanup_exception_releases_lock(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: Any) -> Any:
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr(system, "cleanup", broken)
    with pytest.raises(RuntimeError, match="unexpected failure"):
        client.post("/api/machine/cleanup", json={}, headers={"Origin": BASE})
    monkeypatch.setattr(system, "cleanup", lambda *args: {"warnings": []})
    assert client.post("/api/machine/cleanup", json={}, headers={"Origin": BASE}).status_code == 200


def test_advice_failure_does_not_skip_repos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken() -> list[Path]:
        raise OSError("locked advice")

    calls: list[Path] = []

    def clean(repo: Path) -> CleanResult:
        calls.append(repo)
        return CleanResult()

    monkeypatch.setattr(adaptive, "cleanup_orphans", broken)
    monkeypatch.setattr(review, "clean_worktrees", clean)
    data = system.cleanup(tmp_path, [entry(tmp_path / "repo")])
    assert calls == [tmp_path / "repo"]
    assert data["warnings"] == ["advice cleanup: locked advice"]
