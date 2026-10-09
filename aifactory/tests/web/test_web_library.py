"""Global library workflows use real local git, with no hosting or models."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, cast

import pytest
from multi_repo import BASE, git, rmtree, symlink, write
from starlette.applications import Starlette
from starlette.datastructures import State
from starlette.testclient import TestClient

from aifactory.library import store
from aifactory.library.install import init_repo
from aifactory.skill import envelope_problems
from aifactory.web import create_multi_app, library
from fake_exe import make_executable


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    user = tmp_path / "user"
    user.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: user))
    monkeypatch.setenv("HAIFA_HOME", str(tmp_path / "process-home"))
    monkeypatch.delenv("HAIFA_LIBRARY", raising=False)
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Ada Tester")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "ada@example.com")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "commit.gpgsign")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")
    app = create_multi_app(home=user / "haifa", user_home=user)
    with TestClient(app, base_url=BASE) as result:
        yield result


def state(client: TestClient) -> State:
    return cast(Starlette, client.app).state


def response(res: Any, status: int = 200, code: str | None = None) -> dict[str, Any]:
    assert res.status_code == status, res.text
    body = res.json()
    assert not envelope_problems(body), body
    if code is None:
        assert body["ok"], body
    else:
        assert body["error"]["code"] == code, body
    return dict(body.get("data") or {})


def preview(client: TestClient, action: str, **options: Any) -> dict[str, Any]:
    return response(client.post("/api/library/plan", json={"action": action, "options": options}))


def apply(client: TestClient, action: str, plan: dict[str, Any], **options: Any) -> Any:
    return client.post(
        "/api/library/apply",
        json={
            "action": action,
            "options": options,
            "digest": plan["digest"],
        },
    )


def initialize(client: TestClient, **options: Any) -> Path:
    result = response(apply(client, "init", preview(client, "init", **options), **options))
    assert result["committed"]
    return Path(result["library"])


def test_empty_home_and_read_only_init(client: TestClient) -> None:
    home = state(client).home
    assert response(client.get("/api/library")) == {"exists": False}
    first = preview(client, "init", name="team")
    assert first == preview(client, "init", name="team")
    assert not home.exists()
    assert first["files"] and first["items"]
    assert first["metadata"]["generated"] == ["id"]
    response(client.get("/api/library/items/agent/builder"), 404, "library_missing")
    root = initialize(client, name="team")
    assert root == home / "library"
    assert not (home.parent.parent / "process-home").exists()
    data = response(client.get("/api/library"))
    assert data["exists"] and data["name"] == "team" and not data["fetched"]
    for item in data["items"]:
        assert item["repo_count"] == 0
        assert all(item[k] for k in ("version", "date", "author", "commit"))
    changed = preview(client, "init", name="team")
    assert changed["blockers"][0]["code"] == "library_exists"
    response(apply(client, "init", first, name="team"), 409, "plan_changed")
    response(apply(client, "init", changed, name="team"), 409, "library_exists")


def test_init_remote_clone_and_sync(client: TestClient, tmp_path: Path) -> None:
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", "-b", "main", str(bare))
    root = initialize(client, remote=str(bare))
    before = git(root, "rev-parse", "HEAD")
    assert git(bare, "rev-parse", "main") == before
    response(client.post("/api/library/push"))
    response(client.post("/api/library/pull", json={}))
    blocked = preview(client, "init", remote=str(bare))
    assert "remote_not_empty" in {b["code"] for b in blocked["blockers"]}
    app = create_multi_app(home=tmp_path / "clone-home", user_home=state(client).user_home)
    with TestClient(app, base_url=BASE) as other:
        planned = preview(other, "clone", url=str(bare))
        assert planned["remote_head"] == before
        assert planned["branch"] == "main" and planned["files"] == []
        assert not app.state.home.exists()
        # Advance the remote through the original library: clone must re-review.
        write(root, "note.txt", "changed\n")
        git(root, "add", "note.txt")
        git(root, "commit", "-m", "advance")
        response(client.post("/api/library/push"))
        response(apply(other, "clone", planned, url=str(bare)), 409, "plan_changed")
        planned = preview(other, "clone", url=str(bare), branch="main")
        cloned = response(apply(other, "clone", planned, url=str(bare), branch="main"))
        target = Path(cloned["library"])
        assert (target / "note.txt").read_text() == "changed\n"
        write(target, "note.txt", "next\n")
        git(target, "add", "note.txt")
        git(target, "commit", "-m", "another commit")
        response(other.post("/api/library/push"))
        pulled = response(client.post("/api/library/pull"))
        assert pulled["pulled"] == 1 and (root / "note.txt").read_text() == "next\n"


def test_clone_invalid_library_cleanup(client: TestClient, tmp_path: Path) -> None:
    repo = tmp_path / "invalid"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    write(repo, "library.yaml", "format: 999\n")
    git(repo, "add", "library.yaml")
    git(repo, "commit", "-m", "invalid")
    planned = preview(client, "clone", url=str(repo))
    response(apply(client, "clone", planned, url=str(repo)), 409, "invalid_library")
    assert not (state(client).home / "library").exists()
    response(client.post("/api/library/push"), 409, "library_missing")


def test_import_history_digest_and_noop(client: TestClient) -> None:
    root = initialize(client)
    source = state(client).user_home / "skill"
    write(source, "SKILL.md", "---\nname: demo\ndescription: Test\n---\nFirst version.\n")
    options = {"path": str(source), "type": "skill", "name": "demo"}
    planned = preview(client, "import", **options)
    assert planned["files"][0]["diff"] and planned["core_digest"] != planned["digest"]
    first = response(apply(client, "import", planned, **options))
    old = first["items"][0]["version"]
    planned = preview(client, "import", **options)
    head = git(root, "rev-parse", "HEAD")
    write(source, "SKILL.md", "---\nname: demo\ndescription: Test\n---\nSecond version.\n")
    changed = response(apply(client, "import", planned, **options), 409, "plan_changed")
    assert changed["digest"] != planned["digest"]
    assert git(root, "rev-parse", "HEAD") == head
    response(apply(client, "import", changed, **options))
    detail = response(client.get("/api/library/items/skill/demo"))
    assert len(detail["history"]) == 2 and detail["repos"] == []
    assert detail["description"] == "Test"
    listed = response(client.get("/api/library"))
    item = next(i for i in listed["items"] if i["name"] == "demo")
    assert item["n"] == 2 and item["description"] == "Test"
    assert "Second" in detail["files"][0]["content"]
    earlier = response(client.get("/api/library/items/skill/demo", params={"version": old}))
    assert "First" in earlier["files"][0]["content"]
    response(client.get("/api/library/items/skill/demo?version=ffff"), 404, "unknown_version")
    response(client.get("/api/library/items/skill/missing"), 404, "unknown_item")
    noop = response(apply(client, "import", preview(client, "import", **options), **options))
    assert not noop["committed"]
    planned = preview(client, "import", **options)
    file = source / "SKILL.md"
    file.chmod(0o755)
    response(apply(client, "import", planned, **options), 409, "plan_changed")


def test_import_boundaries(client: TestClient, tmp_path: Path) -> None:
    root = initialize(client)
    head = git(root, "rev-parse", "HEAD")
    outside = write(tmp_path / "external", "SKILL.md", "# Outside\n")
    user = state(client).user_home
    link = user / "link"
    symlink(link, outside.parent)
    inside = user / "inside"
    inside.mkdir()
    symlink(inside / "SKILL.md", outside)
    for path in (str(outside.parent), "../external", str(link), str(inside)):
        options = {"path": path, "type": "skill", "name": "demo"}
        response(
            client.post("/api/library/plan", json={"action": "import", "options": options}),
            403,
            "outside_home",
        )
        response(
            client.post(
                "/api/library/apply",
                json={
                    "action": "import",
                    "options": options,
                    "digest": "anything",
                },
            ),
            403,
            "outside_home",
        )
    assert git(root, "rev-parse", "HEAD") == head


def test_seed_and_local_blockers(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    root = initialize(client)
    noop = response(apply(client, "seed", preview(client, "seed")))
    assert not noop["committed"]
    seed = store.packaged_seed()
    original = seed[0]
    files = list(original.files)
    target = next(i for i, f in enumerate(files) if f.path.endswith("system.md"))
    changed_file = store.NewFile(
        files[target].path, False, files[target].data + b"\nSeed update.\n"
    )
    files[target] = changed_file
    # Compute the seed version with the same loader used by core.
    seed_root = state(client).user_home / "new-seed"
    for file in files:
        write(seed_root, file.path, file.data.decode())
    from aifactory.library.load import load_library_item

    version = load_library_item(seed_root, original.type, original.name).version
    changed = store.SeedItem(original.type, original.name, version, tuple(files))
    monkeypatch.setattr(store, "packaged_seed", lambda: (changed, *seed[1:]))
    data = response(client.get("/api/library"))
    assert data["seed_update_available"]
    planned = preview(client, "seed")
    assert planned["files"]
    response(apply(client, "seed", planned))
    assert not response(apply(client, "seed", preview(client, "seed")))["committed"]
    write(root, "untracked", "dirty\n")
    planned = preview(client, "seed")
    response(apply(client, "seed", planned), 409, "library_dirty")
    (root / "untracked").unlink()
    response(client.post("/api/library/pull"), 409, "no_remote")
    response(client.post("/api/library/push"), 409, "no_remote")


@pytest.mark.parametrize("route", ["plan", "apply", "pull", "push"])
def test_write_guard(client: TestClient, route: str) -> None:
    url = f"/api/library/{route}"
    response(
        client.post(url, json={}, headers={"Origin": "https://evil.example"}), 403, "cross_origin"
    )
    response(
        client.post(url, content="{}", headers={"Content-Type": "text/plain"}),
        415,
        "unsupported_media_type",
    )


@pytest.mark.parametrize(
    "body",
    [
        {"action": "unknown"},
        {"action": []},
        {"action": "init", "files": []},
        {"action": "init", "options": {"name": 1}},
        {"action": "init", "options": {"remote": ""}},
        {"action": "clone"},
        {"action": "import", "options": {"path": "x", "type": "bad"}},
        {"action": "seed", "options": {"take": [True]}},
        {"action": "init", "options": None},
        {"action": "init", "options": {"content": "x"}},
    ],
)
def test_bad_requests(client: TestClient, body: dict[str, Any]) -> None:
    response(client.post("/api/library/plan", json=body), 400, "usage_error")
    response(client.post("/api/library/apply", json={**body, "digest": "x"}), 400, "usage_error")


def test_busy_shared_lock_and_release(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    planned = preview(client, "init")
    entered, release = threading.Event(), threading.Event()
    original = store.init_library

    def paused(*args: Any, **kwargs: Any) -> Any:
        entered.set()
        assert release.wait(10)
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "init_library", paused)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(apply, client, "init", planned)
        try:
            assert entered.wait(10)
            response(apply(client, "init", planned), 409, "busy")
            response(client.post("/api/library/pull"), 409, "busy")
            response(client.post("/api/library/push"), 409, "busy")
        finally:
            release.set()
        response(future.result(timeout=10))
    response(client.post("/api/library/push"), 409, "no_remote")
    assert not state(client).library.lock.locked()


def test_rejected_push_and_cache_invalidation(client: TestClient, tmp_path: Path) -> None:
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", "-b", "main", str(bare))
    root = initialize(client, remote=str(bare))
    hook = write(bare, "hooks/pre-receive", "#!/bin/sh\nexit 1\n")
    make_executable(hook)
    source = state(client).user_home / "skill"
    write(source, "SKILL.md", "---\nname: demo\ndescription: Test\n---\nTest.\n")
    options = {"path": str(source), "type": "skill", "name": "demo"}
    head = git(root, "rev-parse", "HEAD")
    planned = preview(client, "import", **options)
    state(client).library.checks[True] = (0, {}, True, "")
    response(apply(client, "import", planned, **options), 502, "push_failed")
    assert not state(client).library.checks
    assert not state(client).library.lock.locked()
    assert git(root, "rev-parse", "HEAD") == git(bare, "rev-parse", "main") == head
    hook.unlink()
    response(apply(client, "import", planned, **options))


def test_usage_two_repositories(client: TestClient, tmp_path: Path) -> None:
    root = initialize(client)
    env = library.environment(state(client).home)
    from aifactory.library.config_edit import execute_plan, plan_config

    for name in ("first", "second"):
        repo = tmp_path / name
        repo.mkdir()
        git(repo, "init", "-b", "main")
        write(repo, "README.md", "readme\n")
        git(repo, "add", "README.md")
        git(repo, "commit", "-m", "init")
        init_repo(repo, agents=["builder"], workflows=["plan-build"], environ=env)
        if name == "first":
            execute_plan(
                plan_config("add", repo, type="agent", name="builder", slot="alias", environ=env),
                environ=env,
            )
        response(client.post("/api/repos", json={"path": str(repo)}), 201)
    data = response(client.get("/api/library"))
    item = next(i for i in data["items"] if i["type"] == "agent" and i["name"] == "builder")
    assert item["repo_count"] == 2
    assert item["n"] == 1 and item["purpose"]
    assert len(item["repos"]) == 3  # builder plus its alias in the first repo
    assert all(row["state"] == "synced" for row in item["repos"])
    detail = response(client.get("/api/library/items/agent/builder"))
    assert {r["slot"] for r in detail["repos"]} == {"builder", "alias"}
    assert all(r["state"] == "synced" for r in detail["repos"])
    assert not (root / ".git/FETCH_HEAD").exists()
    write(tmp_path / "first", ".factory/prompts/builder/system.md", "Locally modified.\n")
    detail = response(client.get("/api/library/items/agent/builder"))
    assert any(r["state"] == "modified" for r in detail["repos"])
    source = state(client).user_home / "builder-source"
    for leaf in ("agent.yaml", "system.md", "user.md"):
        text = (root / "agents/builder" / leaf).read_text()
        write(source, leaf, text + ("\nLibrary update.\n" if leaf == "system.md" else ""))
    opts = {"path": str(source), "type": "agent", "name": "builder"}
    response(apply(client, "import", preview(client, "import", **opts), **opts))
    detail = response(client.get("/api/library/items/agent/builder"))
    assert any(r["state"] == "outdated" for r in detail["repos"])
    rmtree(tmp_path / "second")
    detail = response(client.get("/api/library/items/agent/builder"))
    assert any(r["state"] == "repo_missing" for r in detail["repos"])
    data = response(client.get("/api/library"))
    item = next(i for i in data["items"] if i["type"] == "agent" and i["name"] == "builder")
    assert item["repo_count"] == 1


def test_head_and_options_digest_and_read_only_get(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = initialize(client)
    source = state(client).user_home / "skill"
    write(source, "SKILL.md", "---\nname: demo\ndescription: Test\n---\nTest.\n")
    options = {"path": "skill", "type": "skill", "name": "demo"}
    planned = preview(client, "import", **options)
    response(apply(client, "seed", planned), 409, "plan_changed")
    write(state(client).user_home / "other-skill", "SKILL.md", (source / "SKILL.md").read_text())
    response(
        apply(client, "import", planned, **{**options, "path": "other-skill"}), 409, "plan_changed"
    )
    write(root, "note", "advance\n")
    git(root, "add", "note")
    git(root, "commit", "-m", "advance local head")
    changed = response(apply(client, "import", planned, **options), 409, "plan_changed")
    response(apply(client, "import", changed, **options))
    before = git(root, "show-ref")
    from aifactory.library import remote

    def no_fetch(*args: Any, **kwargs: Any) -> None:
        pytest.fail("GET must not fetch")

    monkeypatch.setattr(remote, "fetch_remote", no_fetch)
    monkeypatch.setattr(store, "fetch_remote", no_fetch)
    response(client.get("/api/library"))
    response(client.get("/api/library/items/skill/demo"))
    assert before == git(root, "show-ref")


def test_pull_dirty_behind_diverged_and_push_failure(client: TestClient, tmp_path: Path) -> None:
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", "-b", "main", str(bare))
    root = initialize(client, remote=str(bare))
    clone = tmp_path / "writer"
    git(tmp_path, "clone", str(bare), str(clone))
    write(clone, "note", "remote\n")
    git(clone, "add", "note")
    git(clone, "commit", "-m", "remote commit")
    git(clone, "push", "origin", "main")
    response(client.post("/api/library/push"), 409, "library_behind")
    planned = preview(client, "seed")
    assert "library_behind" in {b["code"] for b in planned["blockers"]}
    write(root, "dirty", "untracked\n")
    response(client.post("/api/library/pull"), 409, "library_dirty")
    (root / "dirty").unlink()
    write(root, "local", "local\n")
    git(root, "add", "local")
    git(root, "commit", "-m", "local commit")
    response(client.post("/api/library/push"), 409, "library_diverged")
    response(client.post("/api/library/pull"), 409, "library_diverged")
    assert not state(client).library.lock.locked()


def test_init_identity_and_occupied_target(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(cwd: Path) -> None:
        raise store.LibraryStoreError("git_identity_missing", "no identity")

    monkeypatch.setattr(store, "check_identity", missing)
    planned = preview(client, "init")
    assert not state(client).home.exists()
    response(apply(client, "init", planned), 409, "git_identity_missing")
    write(state(client).home, "library/occupied", "occupied\n")
    response(apply(client, "init", planned), 409, "plan_changed")


def test_url_redaction(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    from aifactory.providers import git as git_provider

    original = git_provider.run_bytes

    def refs(cwd: Path, args: Any, **kwargs: Any) -> Any:
        if args[0] == "ls-remote":
            return subprocess.CompletedProcess(args, 0, b"a" * 40 + b"\trefs/heads/main\n", b"")
        return original(cwd, args, **kwargs)

    monkeypatch.setattr(git_provider, "run_bytes", refs)
    url = "https://user:secret@example.invalid/library.git"
    plan = preview(client, "clone", url=url, branch="main")
    assert plan["options"]["url"] == "https://example.invalid/library.git"
    assert "secret" not in str(plan)
    plan2 = preview(client, "clone", url=url.replace("secret", "another"), branch="main")
    assert plan2["digest"] != plan["digest"]


def test_seed_team_change_take(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    root = initialize(client)
    seed = store.packaged_seed()
    original = seed[0]
    source = state(client).user_home / "team-agent"
    for file in original.files:
        leaf = file.path.rsplit("/", 1)[-1]
        write(
            source, leaf, file.data.decode() + ("\nTeam change.\n" if leaf == "system.md" else "")
        )
    options = {"path": str(source), "type": original.type, "name": original.name}
    response(apply(client, "import", preview(client, "import", **options), **options))
    files = tuple(
        store.NewFile(
            f.path,
            f.executable,
            f.data + (b"\nNew seed.\n" if f.path.endswith("system.md") else b""),
        )
        for f in original.files
    )
    seed_root = state(client).user_home / "new-seed"
    for f in files:
        write(seed_root, f.path, f.data.decode())
    from aifactory.library.load import load_library_item

    version = load_library_item(seed_root, original.type, original.name).version
    updated = store.SeedItem(original.type, original.name, version, files)
    monkeypatch.setattr(store, "packaged_seed", lambda: (updated, *seed[1:]))
    plan = preview(client, "seed")
    assert next(i for i in plan["items"] if i["name"] == original.name)["action"] == "kept"
    response(apply(client, "seed", plan))
    assert "Team change" in (root / original.files[1].path).read_text()
    take = {"take": [original.key]}
    planned = preview(client, "seed", **take)
    assert next(i for i in planned["items"] if i["name"] == original.name)["action"] == "take"
    response(apply(client, "seed", planned, **take))
    assert "New seed" in (root / original.files[1].path).read_text()
