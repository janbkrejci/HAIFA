"""GET /api/guide: the guide chapters on the single- and multi-repo dashboards."""

from __future__ import annotations

from pathlib import Path

import pytest
from multi_repo import multi_client
from starlette.testclient import TestClient
from web_repo import git_repo

from aifactory import guide
from aifactory.skill import envelope_problems
from aifactory.web import create_app

BASE = "http://127.0.0.1:4700"


def _check(body: dict[str, object]) -> list[dict[str, str]]:
    assert envelope_problems(body) == []
    assert body["ok"] is True
    data = body["data"]
    assert isinstance(data, dict)
    chapters: list[dict[str, str]] = data["chapters"]
    assert [c["id"] for c in chapters] == [c.id for c in guide.chapters()]
    assert all(c["title"] and c["markdown"].startswith("# ") for c in chapters)
    return chapters


def test_guide_on_the_repo_dashboard(tmp_path: Path) -> None:
    root = git_repo(tmp_path / "repo")
    client = TestClient(create_app(root, static_dir=tmp_path / "nostatic"), base_url=BASE)
    response = client.get("/api/guide")
    assert response.status_code == 200
    assert _check(response.json())[0]["id"] == guide.chapters()[0].id


def test_guide_on_the_multi_repo_dashboard(tmp_path: Path) -> None:
    client = multi_client(tmp_path / "home", tmp_path)
    response = client.get("/api/guide")
    assert response.status_code == 200
    ids = [c["id"] for c in _check(response.json())]
    assert guide.INSTALL_CHAPTER in ids


@pytest.mark.parametrize("multi", [False, True])
def test_guide_locale_is_per_request_and_keeps_legacy_default(tmp_path: Path, multi: bool) -> None:
    app = (
        multi_client(tmp_path / "home", tmp_path).app
        if multi
        else create_app(git_repo(tmp_path / "repo"), static_dir=tmp_path / "nostatic")
    )
    english_browser = TestClient(app, base_url=BASE)
    czech_browser = TestClient(app, base_url=BASE)
    for client, locale in [
        (english_browser, "en"),
        (czech_browser, "cs"),
        (english_browser, "en"),
        (czech_browser, "cs"),
    ]:
        response = client.get(f"/api/guide?locale={locale}")
        assert response.status_code == 200
        assert _check(response.json()) == [c.as_dict() for c in guide.chapters(locale=locale)]
    assert _check(english_browser.get("/api/guide").json()) == [
        c.as_dict() for c in guide.chapters(locale="cs")
    ]
    assert _check(czech_browser.get("/api/guide?locale=de").json()) == [
        c.as_dict() for c in guide.chapters(locale="en")
    ]
