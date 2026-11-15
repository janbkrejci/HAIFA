from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.testclient import TestClient

from aifactory.upgrade import UpgradeError
from aifactory.web import create_multi_app, updates
from aifactory.web.server import RESTART_ENV, restart_command


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
        return SimpleNamespace(installed=True, handed_off=False)

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


def test_windows_handoff_leaves_instead_of_restarting(monkeypatch: pytest.MonkeyPatch) -> None:
    source = updates.Updates(repository="test/haifa", fetch=lambda _: release())
    monkeypatch.setattr(updates, "editable_install", lambda: False)
    seen: dict[str, Any] = {}

    def hand_off(bundle: str, **kw: Any) -> SimpleNamespace:
        seen.update(kw)
        return SimpleNamespace(installed=False, handed_off=True)

    monkeypatch.setattr(updates, "run_upgrade", hand_off)
    source.begin()
    events: list[str] = []
    source.install(lambda: events.append("restart"), leave=lambda: events.append("leave"))
    assert events == ["leave"] and source.installing
    assert seen["restart"] == restart_command()
    assert seen["environ"][RESTART_ENV] == "1"


def test_active_runs_prevent_update(tmp_path: Path) -> None:
    source = updates.Updates(repository="test/haifa", fetch=lambda _: release())
    app = create_multi_app(home=tmp_path)
    app.state.updates = source
    app.state.launcher = SimpleNamespace(running=lambda: [object()])
    with TestClient(app, base_url="http://127.0.0.1:4700") as client:
        response = client.post("/api/updates/install")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "runs_active"
        assert response.json()["error"]["message"].startswith("Aktualizace počká, běží 1 task.")
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


@pytest.mark.parametrize(
    ("count", "phrase"),
    [(2, "běží 2 tasky."), (4, "běží 4 tasky."), (5, "běží 5 tasků.")],
)
def test_refusal_names_active_runs_with_czech_plural(
    tmp_path: Path, count: int, phrase: str
) -> None:
    source = updates.Updates(repository="test/haifa", fetch=lambda _: release())
    app = create_multi_app(home=tmp_path)
    app.state.updates = source
    app.state.launcher = SimpleNamespace(running=lambda: [object()] * count)
    with TestClient(app, base_url="http://127.0.0.1:4700") as client:
        response = client.post("/api/updates/install")
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "runs_active"
    assert error["message"].startswith(f"Aktualizace počká, {phrase}")
    assert not source.installing


def test_runs_seen_in_overview_prevent_update(tmp_path: Path) -> None:
    class StubOverview:
        async def collect(self) -> tuple[dict[str, Any], None]:
            return {"totals": {"running": 3}}, None

    source = updates.Updates(repository="test/haifa", fetch=lambda _: release())
    app = create_multi_app(home=tmp_path)
    app.state.updates = source
    app.state.launcher = SimpleNamespace(running=lambda: [])
    with TestClient(app, base_url="http://127.0.0.1:4700") as client:
        app.state.overview = StubOverview()
        response = client.post("/api/updates/install")
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "runs_active"
    assert "běží 3 tasky" in error["message"]
    assert not source.installing


def giro_release(version: str = "1.0.1") -> dict[str, Any]:
    return {
        "tag_name": f"v{version}",
        "assets": [
            {
                "name": f"giro-{version}.zip",
                "browser_download_url": f"https://github.com/janbkrejci/GIRO/releases/download/v{version}/giro-{version}.zip",
            }
        ],
    }


def test_migration_click_uses_fixed_new_repository_and_existing_install_guard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aifactory import transition

    calls: list[str] = []
    prepared: list[tuple[Any, ...]] = []

    def fetch(repo: str) -> dict[str, Any]:
        calls.append(repo)
        return giro_release() if repo == "janbkrejci/GIRO" else release()

    monkeypatch.setenv("HAIFA_UPDATE_REPO", "test/haifa")
    monkeypatch.setattr(updates, "editable_install", lambda: False)
    monkeypatch.setattr(transition, "prepare", lambda *args: prepared.append(args))
    source = updates.Updates(current="0.1.9999", home=tmp_path, fetch=fetch)
    app = create_multi_app(home=tmp_path)
    app.state.updates = source
    # Never let a test leave its process.
    monkeypatch.setattr(
        source,
        "install",
        lambda restart: updates.Updates.install(source, restart, leave=lambda: None),
    )
    with TestClient(app, base_url="http://127.0.0.1:4700") as client:
        client.get("/api/updates")
        assert calls == ["test/haifa"] and prepared == []
        assert client.post("/api/updates/migrate").status_code == 202
        assert calls == ["test/haifa", "janbkrejci/GIRO"]
        assert prepared == [
            (tmp_path, giro_release()["assets"][0]["browser_download_url"], "0.1.9999", "1.0.1")
        ]
        assert client.post("/api/updates/migrate").json()["error"]["code"] == "update_busy"
        assert len(prepared) == 1


@pytest.mark.parametrize(
    "failure",
    ["network", "missing", "draft", "legacy_zip", "foreign_url", "major", "duplicate_asset"],
)
def test_migration_rejects_unavailable_or_wrong_release_and_can_retry(
    failure: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = giro_release()
    if failure == "missing":
        data["assets"] = []
    elif failure == "draft":
        data["draft"] = True
    elif failure == "legacy_zip":
        data["assets"][0]["name"] = "haifa-1.0.1.zip"
    elif failure == "foreign_url":
        data["assets"][0]["browser_download_url"] = (
            "https://github.com/janbkrejci/HAIFA/releases/download/v1.0.1/giro-1.0.1.zip"
        )
    elif failure == "major":
        data = giro_release("0.1.9999")
    elif failure == "duplicate_asset":
        data["assets"] *= 2

    def fetch(repo: str) -> dict[str, Any]:
        assert repo == "janbkrejci/GIRO"
        if failure == "network":
            raise OSError("hosting offline")
        return data

    monkeypatch.setattr(updates, "editable_install", lambda: False)
    source = updates.Updates(fetch=fetch)
    with pytest.raises(UpgradeError, match="."):
        source.begin(migration=True)
    assert not source.installing
    assert source.check()["status"] == "error"
    source.fetch = lambda _: giro_release()
    assert source.begin(migration=True)["status"] == "installing"
    with pytest.raises(UpgradeError) as busy:
        source.begin(migration=True)
    assert busy.value.code == "update_busy"


@pytest.mark.parametrize("race", [False, True])
def test_migration_respects_active_run_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, race: bool
) -> None:
    monkeypatch.setattr(updates, "editable_install", lambda: False)
    source = updates.Updates(fetch=lambda _: giro_release())
    app = create_multi_app(home=tmp_path)
    app.state.updates = source
    results = iter([[], [object()]] if race else [[object()]])
    app.state.launcher = SimpleNamespace(running=lambda: next(results))
    with TestClient(app, base_url="http://127.0.0.1:4700") as client:
        assert client.post("/api/updates/migrate").json()["error"]["code"] == "runs_active"
    assert not source.installing


@pytest.mark.parametrize(
    ("legacy", "new", "expected"),
    [
        ("janbkrejci/HAIFA", "", "janbkrejci/GIRO"),
        ("company/releases", "", "company/releases"),
        ("janbkrejci/HAIFA", "company/giro", "company/giro"),
    ],
)
def test_giro_subsequent_updates_ignore_only_old_default(
    monkeypatch: pytest.MonkeyPatch, legacy: str, new: str, expected: str
) -> None:
    monkeypatch.setenv("HAIFA_UPDATE_REPO", legacy)
    monkeypatch.setenv("GIRO_UPDATE_REPO", new)
    source = updates.Updates(current="1.0.1", fetch=lambda repo: giro_release("1.0.2"))
    assert source.repository == expected
    if expected == "janbkrejci/GIRO":
        assert source.check()["status"] == "available"


@pytest.mark.parametrize("saved", ['{"error": "GIRO restart failed; HAIFA restored"}', "{"])
def test_restored_haifa_keeps_recovery_diagnostic_and_allows_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    saved: str,
) -> None:
    from aifactory.transition import ERROR_FILE

    (tmp_path / ERROR_FILE).write_text(saved)
    source = updates.Updates(home=tmp_path, fetch=lambda _: giro_release())
    assert source.check()["status"] == "error"
    assert source.check()["error"]
    monkeypatch.setattr(updates, "editable_install", lambda: False)
    assert source.begin(migration=True)["status"] == "installing"


def test_other_process_discovered_during_preparation_keeps_waiting_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aifactory import transition

    def busy(*args: Any, **kwargs: Any) -> Any:
        raise UpgradeError("runs_active", "Another library writer is active")

    monkeypatch.setattr(transition, "prepare", busy)
    monkeypatch.setattr(updates, "editable_install", lambda: False)
    source = updates.Updates(home=tmp_path, fetch=lambda _: giro_release())
    source.begin(migration=True)
    source.install(
        lambda: pytest.fail("Must not restart"), leave=lambda: pytest.fail("Must not exit")
    )
    assert not source.installing
    assert source.check()["error_code"] == "runs_active"
