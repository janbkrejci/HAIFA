from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.testclient import TestClient

from aifactory.upgrade import UpgradeError
from aifactory.web import create_multi_app, updates


def release(version: str = "0.2.0") -> dict[str, Any]:
    return {
        "tag_name": f"v{version}",
        "assets": [
            {
                "name": f"haifa-{version}.zip",
                "browser_download_url": f"https://github.com/test/haifa/releases/download/v{version}/haifa-{version}.zip",
            }
        ],
    }


def test_cached_check_and_manual_retry() -> None:
    calls: list[str] = []

    def fetch(repo: str) -> dict[str, Any]:
        calls.append(repo)
        return release()

    source = updates.Updates(repository="test/haifa", fetch=fetch)
    assert source.check()["status"] == "available"
    assert source.check()["status"] == "available"
    assert len(calls) == 1
    source.check(fresh=True)
    assert len(calls) == 2
    source = updates.Updates(repository="test/haifa", current="0.2.0", fetch=lambda _: release())
    assert source.check()["status"] == "current"


def test_error_can_be_retried_and_foreign_asset_is_rejected() -> None:
    data = release()
    data["assets"][0]["browser_download_url"] = "https://other.example/install.zip"
    source = updates.Updates(repository="test/haifa", fetch=lambda _: data)
    assert source.check()["status"] == "error"
    data["assets"][0]["browser_download_url"] = release()["assets"][0]["browser_download_url"]
    assert source.check(fresh=True)["status"] == "available"


def test_install_verifies_target_restarts_and_blocks_other_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    restarts: list[str] = []
    source = updates.Updates(repository="test/haifa", fetch=lambda _: release())
    monkeypatch.setattr(updates, "editable_install", lambda: False)

    def install(bundle: str, **kw: Any) -> SimpleNamespace:
        assert bundle == release()["assets"][0]["browser_download_url"]
        assert kw["expected_version"] == "0.2.0"
        return SimpleNamespace(installed=True)

    monkeypatch.setattr(updates, "run_upgrade", install)
    app = create_multi_app(home=tmp_path, restart=lambda: restarts.append("restart"))
    app.state.updates = source
    with TestClient(app, base_url="http://127.0.0.1:4700") as client:
        assert client.get("/api/updates").json()["data"]["status"] == "available"
        assert client.post("/api/updates/install").status_code == 202
        assert restarts == ["restart"]
        assert (
            client.post("/api/machine/harnesses", json={}).json()["error"]["code"] == "update_busy"
        )
        assert client.post("/api/restart").json()["error"]["code"] == "update_busy"
        assert restarts == ["restart"]


def test_failed_install_preserves_dashboard_without_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = updates.Updates(repository="test/haifa", fetch=lambda _: release())
    monkeypatch.setattr(updates, "editable_install", lambda: False)

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise UpgradeError("checksum_mismatch", "bad checksum")

    monkeypatch.setattr(updates, "run_upgrade", fail)
    source.begin()
    restarts: list[str] = []
    source.install(lambda: restarts.append("restart"))
    assert not source.installing and restarts == []
    assert source.check()["status"] == "error"


def test_active_runs_prevent_update(tmp_path: Path) -> None:
    source = updates.Updates(repository="test/haifa", fetch=lambda _: release())
    app = create_multi_app(home=tmp_path)
    app.state.updates = source
    app.state.launcher = SimpleNamespace(running=lambda: [object()])
    with TestClient(app, base_url="http://127.0.0.1:4700") as client:
        response = client.post("/api/updates/install")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "runs_active"
        assert not source.installing


def test_run_started_during_release_check_prevents_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = updates.Updates(repository="test/haifa", fetch=lambda _: release())
    monkeypatch.setattr(updates, "editable_install", lambda: False)
    results = iter([[], [object()]])
    app = create_multi_app(home=tmp_path)
    app.state.updates = source
    app.state.launcher = SimpleNamespace(running=lambda: next(results))
    with TestClient(app, base_url="http://127.0.0.1:4700") as client:
        assert client.post("/api/updates/install").json()["error"]["code"] == "runs_active"
    assert not source.installing
    assert source.check()["status"] == "available"
