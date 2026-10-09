"""L9 plans retain per-repo digests, selection and independent blockers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from multi_repo import BASE
from starlette.testclient import TestClient
from test_web_factory import Api, api, code_of, commit_push, git, home, install, write
from test_web_factory_items import library

from aifactory.web import create_app

__all__ = ["api", "home"]


def bulk(api: Api, action: str = "add", **extra: Any) -> dict[str, Any]:
    body = {
        "action": action,
        "type": "agent",
        "name": "builder",
        "repos": list(api.ids.values()),
        **extra,
    }
    result = api.client.post("/api/library/repos-plan", json=body)
    assert result.status_code == 200, result.text
    assert result.json()["ok"]
    return dict(result.json()["data"])


def apply_rows(api: Api, data: dict[str, Any]) -> None:
    for row in data["repos"]:
        plan = row["plan"]
        result = api.client.post(
            f"/api/repos/{row['repo']['id']}/factory/apply",
            json={
                "action": plan["action"],
                "digest": plan["digest"],
                "options": plan["apply_options"],
                "target": plan["apply_target"],
            },
        )
        assert result.status_code == 200, result.text


def test_two_repos_digest_and_blocked(api: Api, tmp_path: Path) -> None:
    lib = library(api, tmp_path)
    install(api, "a")
    install(api, "b")
    heads = [git(tmp_path / k, "rev-parse", "HEAD") for k in ("a", "b")]
    library_head = git(lib, "rev-parse", "HEAD")
    data = bulk(api, options={"slot": "extra"})
    assert len(data["repos"]) == 2 and not data["partial"]
    assert heads == [git(tmp_path / k, "rev-parse", "HEAD") for k in ("a", "b")]
    assert git(lib, "rev-parse", "HEAD") == library_head
    apply_rows(api, data)
    # A dirty target in a blocks only that row.
    write(
        tmp_path / "a",
        ".factory/agents.yaml",
        (tmp_path / "a/.factory/agents.yaml").read_text() + "# local edit\n",
    )
    data = bulk(api, options={"slot": "another"}, repos="all")
    assert data["partial"]
    assert [row["status"] for row in data["repos"]] == ["blocked", "planned"]
    assert data["repos"][0]["plan"]["blockers"]
    apply_rows(api, {**data, "repos": [data["repos"][1]]})


def test_targeted_update_take(api: Api, tmp_path: Path) -> None:
    lib = library(api, tmp_path)
    install(api, "a")
    install(api, "b")
    builder = ".factory/prompts/builder/system.md"
    reviewer = ".factory/prompts/reviewer/system.md"
    old_reviewer = (tmp_path / "a" / reviewer).read_bytes()
    for key in ("a", "b"):
        write(tmp_path / key, builder, "repo conflict\n")
        commit_push(tmp_path / key, "local builder")
    write(lib, "agents/builder/system.md", "new library builder\n")
    write(lib, "agents/reviewer/system.md", "new library reviewer\n")
    commit_push(lib, "both changed")
    blocked = bulk(api, "update")
    assert all(row["plan"]["update"]["conflicts"] for row in blocked["repos"])
    data = bulk(api, "update", options={"take": ["agent/builder:system.md"]})
    assert not data["partial"], data
    assert all(row["plan"]["apply_options"]["item"] == ["agent/builder"] for row in data["repos"])
    apply_rows(api, data)
    for key in ("a", "b"):
        assert (tmp_path / key / builder).read_text() == "new library builder\n"
        assert (tmp_path / key / reviewer).read_bytes() == old_reviewer


@pytest.mark.parametrize(
    "extra",
    [
        {"repos": []},
        {"repos": ["x", "x"]},
        {"repos": "x,x"},
        {"repos": ["all"]},
        {"repos": 1},
        {"repos": ["x,y"]},
        {"repos": ["x"], "options": {"files": []}},
        {"options": {"type": "agent"}},
        {"options": {"commit": True}},
        {"options": {"item": ["agent/reviewer"]}},
        {"options": {"target": "worktree"}},
        {"options": None},
        {"action": "remove"},
        {"type": "other"},
        {"name": ""},
        {"path": "/tmp/repo"},
        {"message": "m"},
        {"digest": "d"},
    ],
)
def test_bulk_parser(api: Api, extra: dict[str, Any]) -> None:
    body = {"action": "add", "type": "agent", "name": "builder", "repos": "all", **extra}
    res = api.client.post("/api/library/repos-plan", json=body)
    assert res.status_code == 400, res.text
    assert res.json()["error"]["code"] == "usage_error"


def test_unknown_missing_and_solo(
    api: Api, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library(api, tmp_path)
    install(api, "a")
    install(api, "b")
    body = {"action": "add", "type": "agent", "name": "builder", "repos": ["unknown"]}
    res = api.client.post("/api/library/repos-plan", json=body)
    assert res.status_code == 404 and code_of(res.json()) == "unknown_repo"
    # A registered missing directory yields a partial row rather than losing the good plan.
    (tmp_path / "b").rename(tmp_path / "moved-b")
    data = bulk(api, options={"slot": "extra"})
    assert data["partial"] and data["repos"][1]["error"]["code"] == "repo_missing"
    with TestClient(create_app(tmp_path / "a"), base_url=BASE) as client:
        res = client.post("/api/library/repos-plan", json={**body, "repos": [api.ids["a"]]})
        assert res.status_code == 200, res.text
    monkeypatch.setenv("HAIFA_HOME", str(tmp_path / "no-registry"))
    with TestClient(create_app(tmp_path / "a"), base_url=BASE) as client:
        res = client.post("/api/library/repos-plan", json={**body, "repos": "all"})
        assert res.status_code == 409 and code_of(res.json()) == "registry_missing"


def test_dashboard_home_and_write_guard(
    api: Api, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library(api, tmp_path)
    monkeypatch.setenv("HAIFA_HOME", str(tmp_path / "wrong-process-home"))
    install(api, "a")
    install(api, "b")
    data = bulk(api, options={"slot": "extra", "target": "pr"})
    apply_rows(api, data)
    assert not (tmp_path / "wrong-process-home").exists()
    res = api.client.post(
        "/api/library/repos-plan",
        json={"action": "add", "type": "agent", "name": "builder", "repos": "all"},
        headers={"origin": "https://untrusted.example"},
    )
    assert res.status_code == 403
