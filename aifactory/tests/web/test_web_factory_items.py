"""Item operations use CLI core, local bare remotes and an isolated dashboard home."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
import yaml
from multi_repo import BASE
from starlette.testclient import TestClient
from test_web_factory import (
    Api,
    api,
    bare_of,
    code_of,
    commit_push,
    git,
    home,
    install,
    reject_main,
    write,
)

from aifactory.library import store
from aifactory.library.state import repo_items
from aifactory.web import create_app
from aifactory.web import factory as factory_api
from aifactory.web.library import environment

__all__ = ["api", "home"]


def library(api: Api, tmp_path: Path) -> Path:
    bare = tmp_path / "library.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    result = store.init_library("team", environment(api.client.app.state.home), remote=str(bare))  # type: ignore[attr-defined]
    return Path(result.plan.library)


def perform(api: Api, repo: str, action: str, **options: Any) -> dict[str, Any]:
    plan = api.plan(repo, action, options=options)
    assert not plan["blockers"], plan
    return dict(api.apply(repo, plan, options=options)["data"])


def test_items_add_set_export_second_repo(api: Api, tmp_path: Path) -> None:
    lib = library(api, tmp_path)
    install(api, "a")
    install(api, "b")
    a, b = tmp_path / "a", tmp_path / "b"
    opts = {"type": "agent", "name": "builder", "slot": "extra"}
    old = git(a, "rev-parse", "HEAD")
    plan = api.plan("a", "add", options=opts)
    assert git(a, "rev-parse", "HEAD") == old
    api.apply("a", plan, options=opts)
    data = api.get("a", "factory/items")["data"]
    assert data == repo_items(a, environ=environment(api.client.app.state.home), save_cache=False)  # type: ignore[attr-defined]
    extra = next(i for i in data["items"] if i["name"] == "extra" and i["type"] == "agent")
    assert extra["item"] == "builder" and extra["state"] == "synced"
    version = extra["repo_version"]
    prompt = a / ".factory/prompts/extra/system.md"
    original = prompt.read_bytes()
    perform(api, "a", "set", type="agent", name="extra", model="opus", tools="", writes="")
    assert prompt.read_bytes() == original
    extra = next(i for i in api.get("a", "factory/items")["data"]["items"] if i["name"] == "extra")
    assert extra["repo_version"] == version
    roster = yaml.safe_load((a / ".factory/agents.yaml").read_text())
    entry = next(i for i in roster["agents"] if i["name"] == "extra")
    assert entry["model"] == "opus" and entry["tools"] == [] and entry["writes"] == []
    prompt.write_text("new exported prompt\n")
    assert (
        next(i for i in api.get("a", "factory/items")["data"]["items"] if i["name"] == "extra")[
            "state"
        ]
        == "modified"
    )
    base = api.get("a", "factory/items?base=")["data"]
    assert next(i for i in base["items"] if i["name"] == "extra")["state"] == "synced"
    commit_push(a, "custom prompt")
    result = perform(api, "a", "export", type="agent", name="extra", slot="custom-builder")
    assert result["library_commit"] == git(lib, "rev-parse", "HEAD")
    assert (
        git(tmp_path / "library.git", "show", "main:agents/custom-builder/system.md")
        == "new exported prompt"
    )
    perform(api, "b", "add", type="agent", name="custom-builder", slot="custom")
    assert (b / ".factory/prompts/custom/system.md").read_text() == "new exported prompt\n"
    assert (
        git(bare_of(tmp_path, "b"), "show", "main:.factory/prompts/custom/system.md")
        == "new exported prompt"
    )


def test_remove_revert_and_in_use(api: Api, tmp_path: Path) -> None:
    library(api, tmp_path)
    install(api, "a")
    perform(api, "a", "add", type="agent", name="builder", slot="extra")
    a = tmp_path / "a"
    prompt = a / ".factory/prompts/extra/system.md"
    original = prompt.read_bytes()
    prompt.write_text("changed\n")
    commit_push(a, "change")
    perform(api, "a", "revert", type="agent", name="extra", to="manifest")
    assert prompt.read_bytes() == original
    perform(api, "a", "remove", type="agent", name="extra", prune=True)
    assert not prompt.exists()
    result = api.post(
        "a",
        "factory/plan",
        {"action": "remove", "options": {"type": "agent", "name": "builder"}},
        409,
    )
    assert code_of(result) == "in_use"
    assert result["data"]["used_by"]


def test_item_stale_push_and_pr(api: Api, tmp_path: Path) -> None:
    library(api, tmp_path)
    install(api, "a")
    opts = {"type": "agent", "name": "builder", "slot": "extra"}
    plan = api.plan("a", "add", options=opts)
    perform(api, "a", "set", type="agent", name="builder", model="opus")
    failure = api.apply("a", plan, 409, options=opts)
    assert code_of(failure) == "plan_changed" and failure["data"]["action"] == "add"
    reject_main(bare_of(tmp_path, "a"))
    plan = api.plan("a", "add", options=opts)
    assert code_of(api.apply("a", plan, 502, options=opts)) == "push_failed"
    plan = api.plan("a", "add", options=opts, target="pr")
    result = api.apply("a", plan, options=opts, target="pr", message="review extra agent")["data"]
    assert result["pr"] and result["pushed"]
    assert git(tmp_path / "a", "log", "-1", "--format=%s", result["commit"]) == "review extra agent"


@pytest.mark.parametrize(
    "body",
    [
        {"action": "add", "options": {}},
        {"action": "add", "options": {"type": "nope", "name": "x"}},
        {"action": "set", "options": {"type": "agent", "name": "x", "tools": []}},
        {"action": "remove", "options": {"type": "agent", "name": "x", "prune": 1}},
        {"action": "update", "options": {"item": "agent/builder"}},
        {"action": "add", "options": {"type": "agent", "name": "x", "files": []}},
        {"action": "add", "path": "/tmp/repo"},
        {"action": "add", "content": "bytes"},
    ],
)
def test_strict_options(api: Api, body: dict[str, Any]) -> None:
    assert code_of(api.post("a", "factory/plan", body, 400)) == "usage_error"


@pytest.mark.parametrize("action", ["onboard", "adopt"])
def test_onboard_and_adopt_are_unknown_actions(api: Api, action: str) -> None:
    res = api.post("a", "factory/plan", {"action": action}, 400)
    assert code_of(res) == "usage_error"
    assert "action must be one of" in res["error"]["message"]
    res = api.post("a", "factory/apply", {"action": action, "digest": "x"}, 400)
    assert code_of(res) == "usage_error"


def test_library_busy_and_release(
    api: Api, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library(api, tmp_path)
    install(api, "a")
    install(api, "b")
    for key in ("a", "b"):
        write(tmp_path / key, ".factory/prompts/builder/system.md", f"custom {key}\n")
        commit_push(tmp_path / key, "modified copy")
    started, release = threading.Event(), threading.Event()
    original = factory_api._call

    def slow(root: Path, req: factory_api.Request, *, dry_run: bool, environ: Any = None) -> Any:
        if req.action == "export" and not dry_run:
            started.set()
            assert release.wait(30)
        return original(root, req, dry_run=dry_run, environ=environ)

    monkeypatch.setattr(factory_api, "_call", slow)
    opts = {"type": "agent", "name": "builder", "slot": "exported-a"}
    b_opts = {"type": "agent", "name": "builder", "slot": "exported-b"}
    plan = api.plan("a", "export", options=opts)
    with ThreadPoolExecutor() as pool:
        future = pool.submit(api.apply, "a", plan, options=opts)
        try:
            assert started.wait(30)
            assert code_of(api.apply("a", plan, 409, options=opts)) == "busy"
            b_plan = api.plan("b", "export", options=b_opts)
            assert code_of(api.apply("b", b_plan, 409, options=b_opts)) == "busy"
            result = api.client.post("/api/library/push", json={})
            assert result.status_code == 409 and result.json()["error"]["code"] == "busy"
            perform(api, "b", "set", type="agent", name="builder", model="opus")
        finally:
            release.set()
        assert future.result()["ok"]
    # A failed digest releases both locks.
    b_plan = api.plan("b", "export", options=b_opts)
    assert code_of(api.apply("b", {**b_plan, "digest": "wrong"}, 409, options=b_opts)) == (
        "plan_changed"
    )
    assert api.apply("b", api.plan("b", "export", options=b_opts), options=b_opts)["ok"]


def test_single_repo_routes(api: Api, tmp_path: Path) -> None:
    library(api, tmp_path)
    with TestClient(create_app(tmp_path / "a"), base_url=BASE) as client:
        plan = client.post("/api/factory/plan", json={"action": "init"}).json()["data"]
        assert (
            client.post(
                "/api/factory/apply", json={"action": "init", "digest": plan["digest"]}
            ).status_code
            == 200
        )
        assert client.get("/api/factory/items").json()["data"]["items"]
        for action, options in (
            ("add", {"type": "agent", "name": "builder", "slot": "extra"}),
            ("set", {"type": "agent", "name": "extra", "model": "opus"}),
            ("revert", {"type": "agent", "name": "extra", "to": "manifest"}),
            ("export", {"type": "agent", "name": "extra", "slot": "solo-extra"}),
            ("remove", {"type": "agent", "name": "extra"}),
        ):
            body = {"action": action, "options": options}
            res = client.post("/api/factory/plan", json=body)
            assert res.status_code == 200, res.text
            digest = res.json()["data"]["digest"]
            res = client.post("/api/factory/apply", json={**body, "digest": digest})
            assert res.status_code == 200, res.text


def test_export_partial_publish_error(api: Api, tmp_path: Path) -> None:
    lib = library(api, tmp_path)
    install(api, "a")
    write(tmp_path / "a", ".factory/prompts/builder/system.md", "custom export\n")
    commit_push(tmp_path / "a", "modified copy")
    opts = {"type": "agent", "name": "builder", "slot": "exported"}
    plan = api.plan("a", "export", options=opts)
    reject_main(bare_of(tmp_path, "a"))
    res = api.apply("a", plan, 502, options=opts)
    assert code_of(res) == "push_failed"
    assert res["data"]["library_commit"] == git(lib, "rev-parse", "HEAD")
    assert res["data"]["action"] == "export"
    assert (lib / "agents/exported/system.md").read_text() == "custom export\n"
    assert not api.client.app.state.library.lock.locked()  # type: ignore[attr-defined]
    install(api, "b")
    perform(api, "b", "add", type="agent", name="exported")


def test_items_all_states_and_unknown_version(api: Api, tmp_path: Path) -> None:
    lib = library(api, tmp_path)
    install(api, "a")
    a = tmp_path / "a"
    prompt = a / ".factory/prompts/builder/system.md"
    env = environment(api.client.app.state.home)  # type: ignore[attr-defined]

    def state() -> str:
        data = api.get("a", "factory/items")["data"]
        assert data == repo_items(a, environ=env, save_cache=False)
        value: str = next(i for i in data["items"] if i["name"] == "builder")["state"]
        return value

    assert state() == "synced"
    write(lib, "agents/builder/system.md", "new library prompt\n")
    commit_push(lib, "new builder")
    assert state() == "outdated"
    prompt.write_text("repo modification\n")
    assert state() == "diverged"
    prompt.unlink()
    assert state() == "missing"
    prompt.write_text("repo modification\n")
    manifest = a / ".factory/manifest.yaml"
    data = yaml.safe_load(manifest.read_text())
    data["items"]["agents"]["builder"]["version"] = "f" * 64
    manifest.write_text(yaml.safe_dump(data, sort_keys=False))
    assert state() == "unknown"
    commit_push(a, "unknown manifest version")
    res = api.post(
        "a",
        "factory/plan",
        {"action": "revert", "options": {"type": "agent", "name": "builder", "to": "manifest"}},
        422,
    )
    assert code_of(res) == "unknown_version"
    del data["items"]["agents"]["builder"]
    manifest.write_text(yaml.safe_dump(data, sort_keys=False))
    assert state() == "local"


def test_add_skill_to_agent(api: Api, tmp_path: Path) -> None:
    lib = library(api, tmp_path)
    write(lib, "skills/lint/SKILL.md", "---\nname: lint\ndescription: Lint code.\n---\nRun lint.\n")
    commit_push(lib, "add skill")
    install(api, "a")
    done = perform(api, "a", "add", type="skill", name="lint", agent="builder")
    assert done["pushed"]
    for tree in (".claude", ".agents"):
        assert (tmp_path / "a" / tree / "skills/lint/SKILL.md").is_file()
    roster = yaml.safe_load((tmp_path / "a/.factory/agents.yaml").read_text())
    builder = next(i for i in roster["agents"] if i["name"] == "builder")
    assert "lint" in builder["skills"]
    perform(api, "a", "remove", type="skill", name="lint")
    assert not (tmp_path / "a/.claude/skills/lint/SKILL.md").exists()


def test_roster_and_item_diff_are_read_only(api: Api, tmp_path: Path) -> None:
    library(api, tmp_path)
    install(api, "a")
    repo = tmp_path / "a"
    before = git(repo, "rev-parse", "HEAD")
    roster = api.get("a", "factory/roster")["data"]
    builder = next(a for a in roster["agents"] if a["name"] == "builder")
    assert builder["purpose"] and builder["harness"]
    assert isinstance(roster["workflow_tasks"], dict)
    diff = api.get("a", "factory/item-diff?type=agent&name=builder")["data"]
    assert diff["manifest"]["available"] and diff["head"]["available"]
    assert diff["manifest"]["files"] == []
    assert diff["head"]["files"] == []
    prompt = repo / ".factory/prompts/builder/system.md"
    prompt.write_text(prompt.read_text() + "\nLocal change\n")
    changed = api.get("a", "factory/item-diff?type=agent&name=builder")["data"]
    assert changed["state"] == "modified"
    assert any("Local change" in f["diff"] for f in changed["manifest"]["files"])
    assert git(repo, "rev-parse", "HEAD") == before
    assert "Local change" in prompt.read_text()
