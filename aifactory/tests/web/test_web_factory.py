"""API of the Factory tab: check, plan, apply and base pull (HAIFA-S01-T17).

Two repositories with local bare remotes (provider ``local``, so a PR goes through
``LocalProvider``), a fake machine for the check: no model and no network.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
import yaml
from multi_repo import BASE, multi_client
from starlette.testclient import TestClient

from aifactory.config import load_local
from aifactory.library import store
from aifactory.run.store import RUNNING, TaskRunRow, TaskRunStore
from aifactory.skill import envelope_problems
from aifactory.web import create_app
from aifactory.web import factory as web_factory
from aifactory.web.repos import trace_db_of
from fake_exe import make_executable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "check"))

from factory_check_repo import FakeMachine  # noqa: E402

CONFIG = ".factory/config.yaml"
AGENTS = ".factory/agents.yaml"
SYSTEM = ".factory/prompts/builder/system.md"
LIB_SYSTEM = "agents/builder/system.md"


def git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return proc.stdout.strip()


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """``$HAIFA_HOME`` without a library, a git identity, and only claude on this machine."""
    path = tmp_path / "haifa-home"
    monkeypatch.setenv("HAIFA_HOME", str(path))
    monkeypatch.delenv("HAIFA_LIBRARY", raising=False)
    for kind in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{kind}_NAME", "Ada Tester")
        monkeypatch.setenv(f"GIT_{kind}_EMAIL", "ada@example.com")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "commit.gpgsign")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")
    claude = tmp_path / "bin" / "claude"
    claude.parent.mkdir()
    claude.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8", newline="\n")
    monkeypatch.setenv("CLAUDE_CODE_PATH", str(make_executable(claude)))
    monkeypatch.setenv("CODEX_PATH", "codex-not-installed-anywhere")
    monkeypatch.setenv("PI_PATH", "pi-not-installed-anywhere")
    return path


def make_repo(tmp_path: Path, name: str, *, remote: bool = True) -> Path:
    path = tmp_path / name
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    write(path, "README.md", "readme\n")
    write(path, "justfile", "test:\n    echo ok\n")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "init")
    if remote:
        bare = bare_of(tmp_path, name)
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
        git(path, "remote", "add", "origin", str(bare))
        git(path, "push", "-q", "-u", "origin", "main")
        git(path, "remote", "set-head", "origin", "main")
    return path.resolve()


def bare_of(tmp_path: Path, name: str) -> Path:
    return tmp_path / f"{name}-origin.git"


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def commit_push(root: Path, message: str) -> str:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
    git(root, "push", "-q", "origin", "main")
    return git(root, "rev-parse", "HEAD")


def reject_main(bare: Path) -> None:
    hook = bare / "hooks" / "pre-receive"
    hook.parent.mkdir(exist_ok=True)
    hook.write_text(
        '#!/bin/sh\nwhile read old new ref; do [ "$ref" = refs/heads/main ] && exit 1; done\n'
        "exit 0\n",
        encoding="utf-8",
        newline="\n",
    )
    hook.chmod(0o755)


def status_clean(root: Path) -> bool:
    return git(root, "status", "--porcelain") == ""


class Api:
    """The multi-repo client with one prefix per repository."""

    def __init__(self, client: TestClient, ids: dict[str, str]) -> None:
        self.client = client
        self.ids = ids

    def url(self, repo: str, path: str) -> str:
        return f"/api/repos/{self.ids[repo]}/{path}"

    def get(self, repo: str, path: str, status: int = 200) -> dict[str, Any]:
        return check_body(self.client.get(self.url(repo, path)), status)

    def post(self, repo: str, path: str, body: Any = None, status: int = 200) -> dict[str, Any]:
        resp = self.client.post(self.url(repo, path), json=body if body is not None else {})
        return check_body(resp, status)

    def plan(self, repo: str, action: str, **body: Any) -> dict[str, Any]:
        data: dict[str, Any] = self.post(repo, "factory/plan", {"action": action, **body})["data"]
        return data

    def apply(self, repo: str, plan: dict[str, Any], status: int = 200, **body: Any) -> Any:
        return self.post(
            repo,
            "factory/apply",
            {"action": plan["action"], "digest": plan["digest"], **body},
            status,
        )


def check_body(resp: Any, status: int) -> dict[str, Any]:
    body: dict[str, Any] = resp.json()
    assert resp.status_code == status, body
    assert envelope_problems(body) == []
    return body


@pytest.fixture
def api(tmp_path: Path) -> Api:
    client = multi_client(Path(os.environ["HAIFA_HOME"]), tmp_path)
    client.app.state.check_machine = FakeMachine()  # type: ignore[attr-defined]
    ids: dict[str, str] = {}
    for name in ("a", "b"):
        root = make_repo(tmp_path, name)
        resp = client.post("/api/repos", json={"path": str(root)})
        assert resp.status_code == 201, resp.json()
        ids[name] = resp.json()["data"]["repo"]["id"]
    return Api(client, ids)


def install(api: Api, repo: str, **options: Any) -> dict[str, Any]:
    plan = api.plan(repo, "init", options=options)
    data: dict[str, Any] = api.apply(repo, plan, options=options)["data"]
    return data


def code_of(body: dict[str, Any]) -> str:
    code: str = body["error"]["code"]
    return code


# ── install ───────────────────────────────────────────────────────────────────


def test_install_builder_on_other_harness(api: Api, tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    b_before = (git(b, "rev-parse", "main"), git(b, "status", "--porcelain"))
    options = {"bind": {"builder": {"harness": "codex", "model": "gpt-5.5"}}}

    body = api.post("a", "factory/plan", {"action": "init", "options": options})
    plan = body["data"]
    assert plan["digest"] and plan["blockers"] == []
    assert "detected" in plan and "available" in plan
    assert plan["bindings"]["builder"]["harness"] == "codex"
    assert plan["bindings"]["builder"]["model"] == "gpt-5.5"
    assert any("codex" in w for w in body["warnings"])
    assert not (a / ".factory").exists()

    done = api.apply("a", plan, options=options)["data"]
    assert done["commit"] and done["pushed"] is True and done["pr"] is None
    assert set(done) >= {"commit", "pushed", "pr", "warnings"}
    assert git(bare_of(tmp_path, "a"), "rev-parse", "main") == done["commit"]
    roster = yaml.safe_load(git(a, "show", f"{done['commit']}:{AGENTS}"))
    by_name = {e["name"]: e for e in roster["agents"]}
    assert by_name["builder"]["harness"] == "codex"
    default = roster.get("defaults", {}).get("harness")
    others = {n: e.get("harness", default) for n, e in by_name.items() if n != "builder"}
    assert others and set(others.values()) == {"claude"}
    assert (git(b, "rev-parse", "main"), git(b, "status", "--porcelain")) == b_before
    assert not (b / ".factory").exists()


def test_install_plan_has_no_test_command(api: Api) -> None:
    plain = api.plan("a", "init")
    assert "test_command" not in plain
    bad = api.post("a", "factory/plan", {"action": "init", "options": {"test_command": "x"}}, 400)
    assert code_of(bad) == "usage_error"


def test_rejected_push_then_pr_with_same_digest(api: Api, tmp_path: Path) -> None:
    a = tmp_path / "a"
    bare = bare_of(tmp_path, "a")
    reject_main(bare)
    main_before = git(a, "rev-parse", "main")
    plan = api.plan("a", "init")

    failed = api.apply("a", plan, status=502)
    assert code_of(failed) == "push_failed"
    assert failed["data"]["files"]
    assert git(a, "rev-parse", "main") == main_before
    assert git(bare, "rev-parse", "main") == main_before
    assert not (a / ".factory" / "config.yaml").exists()

    done = api.apply("a", plan, target="pr")["data"]
    assert done["pushed"] is True
    assert done["pr"]["branch"] == "factory-init/1"
    assert git(bare, "rev-parse", "factory-init/1") == done["commit"]
    assert git(a, "rev-parse", "main") == main_before


def test_plan_changed(api: Api, tmp_path: Path) -> None:
    a = tmp_path / "a"
    old = api.plan("a", "init")
    write(a, "justfile", "test:\n    echo ok\n\nlint:\n    echo lint\n")
    before = commit_push(a, "another recipe")

    changed = api.apply("a", old, status=409)
    assert code_of(changed) == "plan_changed"
    new_digest = changed["data"]["digest"]
    assert new_digest and new_digest != old["digest"]
    assert git(bare_of(tmp_path, "a"), "rev-parse", "main") == before

    done = api.apply("a", {"action": "init", "digest": new_digest})["data"]
    assert done["commit"] != before


# ── busy and runs ─────────────────────────────────────────────────────────────


def test_busy(api: Api, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    started, release = threading.Event(), threading.Event()
    original = web_factory._call

    def slow(root: Path, req: web_factory.Request, *, dry_run: bool, environ: Any = None) -> Any:
        if not dry_run and root == (tmp_path / "a").resolve():
            started.set()
            assert release.wait(30)
        return original(root, req, dry_run=dry_run, environ=environ)

    monkeypatch.setattr(web_factory, "_call", slow)
    plan = api.plan("a", "config_commit")
    result: dict[str, Any] = {}

    def first() -> None:
        resp = api.client.post(
            api.url("a", "factory/apply"),
            json={"action": "config_commit", "digest": plan["digest"]},
        )
        result["status"], result["body"] = resp.status_code, resp.json()

    other_digest = api.get("b", "config/pull/plan")["data"]["digest"]
    thread = threading.Thread(target=first)
    thread.start()
    try:
        assert started.wait(30)
        busy = api.apply("a", plan, status=409)
        assert code_of(busy) == "busy"
        assert (
            code_of(
                api.post(
                    "a",
                    "config/pull",
                    {"digest": plan["digest"]},
                    status=409,
                )
            )
            == "busy"
        )
        other = api.client.post(
            api.url("b", "config/pull"),
            json={"digest": other_digest},
        )
        assert other.status_code == 200, other.json()
    finally:
        release.set()
        thread.join(30)
    assert result["status"] == 200, result["body"]
    assert result["body"]["data"]["committed"] is False


def _claim(repo: Path) -> None:
    runs = TaskRunStore(load_local(repo).trace_db_path(repo))
    try:
        runs.claim(
            TaskRunRow(
                run_id="r1",
                task_id="T1",
                branch="factory/T1-1",
                worktree=str(repo),
                base="main",
                base_sha=git(repo, "rev-parse", "main"),
                head_sha=None,
                state=RUNNING,
                started_at="2026-01-01T00:00:00Z",
                pid=os.getpid(),
            )
        )
    finally:
        runs.close()


def test_run_in_progress(api: Api, tmp_path: Path) -> None:
    a = tmp_path / "a"
    install(api, "a")
    write(a, CONFIG, (a / CONFIG).read_text(encoding="utf-8") + "# tuned\n")
    _claim(a)

    plan = api.plan("a", "config_commit")
    assert "run_in_progress" in [b["code"] for b in plan["blockers"]]
    refused = api.apply("a", plan, status=409)
    assert code_of(refused) == "run_in_progress"

    clone = tmp_path / "a-clone"
    git(tmp_path, "clone", "-q", str(bare_of(tmp_path, "a")), str(clone))
    write(clone, "notes.md", "notes\n")
    commit_push(clone, "remote ahead")
    git(a, "checkout", "--", CONFIG)
    assert (
        code_of(
            api.post(
                "a",
                "config/pull",
                {"digest": api.get("a", "config/pull/plan")["data"]["digest"]},
                status=409,
            )
        )
        == "run_in_progress"
    )


# ── update ────────────────────────────────────────────────────────────────────


def _units(plan: dict[str, Any], kind: str, name: str) -> dict[str, dict[str, Any]]:
    item = next(i for i in plan["update"]["items"] if (i["type"], i["name"]) == (kind, name))
    return {f["file"]: f for f in item["files"]}


def test_update_with_take_and_migrate(api: Api, tmp_path: Path) -> None:
    library_bare = tmp_path / "library-origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(library_bare))
    store.init_library("team", remote=str(library_bare))
    a = tmp_path / "a"
    install(api, "a")

    # take: the repo and the library both changed builder's system.md
    write(a, SYSTEM, "repo text\n")
    commit_push(a, "repo change")
    lib = store.library_root()
    write(lib, LIB_SYSTEM, "library text\n")
    git(lib, "add", "-A")
    git(lib, "commit", "-q", "-m", "library change")
    git(lib, "push", "-q", "origin", "main")
    plan = api.plan("a", "update")
    assert plan["update"]["conflicts"] == ["agent/builder:system.md"]
    options = {"take": ["agent/builder:system.md"]}
    plan = api.plan("a", "update", options=options)
    assert _units(plan, "agent", "builder")["system.md"]["status"] == "taken"
    done = api.apply("a", plan, options=options)["data"]
    assert done["committed"] and done["pushed"]
    bare = bare_of(tmp_path, "a")
    assert git(bare, "show", f"main:{SYSTEM}") == "library text"

    # migrate: an old levels key in the committed config
    git(a, "pull", "-q", "--ff-only", "origin", "main")
    write(a, CONFIG, (a / CONFIG).read_text(encoding="utf-8") + "levels: [module, step, task]\n")
    commit_push(a, "old levels")
    plan = api.plan("a", "update")
    found = plan["update"]["migrations"][0]
    assert found["id"] == "m001" and not found["applied"]
    options = {"migrate": ["m001"]}
    plan = api.plan("a", "update", options=options)
    assert plan["update"]["migrations"][0]["applied"]
    api.apply("a", plan, options=options)
    assert "levels: [project, step, task]" in git(bare, "show", f"main:{CONFIG}")

    bad = api.post("a", "factory/plan", {"action": "update", "options": {"migrate": ["m999"]}}, 422)
    assert code_of(bad) == "invalid_value"


# ── config commit and pull ────────────────────────────────────────────────────


def test_config_commit(api: Api, tmp_path: Path) -> None:
    a = tmp_path / "a"
    install(api, "a")
    write(a, CONFIG, (a / CONFIG).read_text(encoding="utf-8") + "# tuned\n")

    plan = api.plan("a", "config_commit")
    assert [f["path"] for f in plan["files"]] == [CONFIG]
    assert plan["digest"]
    done = api.apply("a", plan, message="tune config")["data"]
    assert done["committed"] and done["pushed"]
    bare = bare_of(tmp_path, "a")
    assert git(bare, "log", "-1", "--format=%s", "main") == "tune config"
    assert status_clean(a)


def test_config_pull(api: Api, tmp_path: Path) -> None:
    a = tmp_path / "a"
    clone = tmp_path / "a-clone"
    git(tmp_path, "clone", "-q", str(bare_of(tmp_path, "a")), str(clone))
    write(clone, "notes.md", "notes\n")
    remote = commit_push(clone, "remote ahead")
    b_before = git(tmp_path / "b", "rev-parse", "main")

    data = api.post(
        "a", "config/pull", {"digest": api.get("a", "config/pull/plan")["data"]["digest"]}
    )["data"]
    assert data["updated"] is True and data["after"] == remote
    assert git(a, "rev-parse", "main") == remote
    assert (
        api.post(
            "a", "config/pull", {"digest": api.get("a", "config/pull/plan")["data"]["digest"]}
        )["data"]["updated"]
        is False
    )
    assert git(tmp_path / "b", "rev-parse", "main") == b_before


# ── check ─────────────────────────────────────────────────────────────────────


def test_check_cache_and_trace_db_shared(
    api: Api, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = [1000.0]
    monkeypatch.setattr(web_factory, "_clock", lambda: now[0])
    first = api.get("a", "factory/check?offline=1")
    # not installed yet: the check answers HTTP 200 with checks_failed (factory_missing)
    assert first["ok"] is False and code_of(first) == "checks_failed"
    data = first["data"]
    assert "state" in data and "findings" in data and data["cached"] is False
    again = api.get("a", "factory/check?offline=1")["data"]
    assert again["cached"] is True and again["checked_at"] == data["checked_at"]
    assert api.get("a", "factory/check?offline=1&fresh=1")["data"]["cached"] is False
    now[0] += 61
    assert api.get("a", "factory/check?offline=1")["data"]["cached"] is False
    assert api.get("a", "factory/check?offline=1")["data"]["cached"] is True

    write(tmp_path / "b", ".factory/local.yaml", f"trace_db: {trace_db_of(tmp_path / 'a')}\n")
    shared = api.get("b", "factory/check?offline=1")
    assert shared["ok"] is False and code_of(shared) == "checks_failed"
    found = [f for f in shared["data"]["findings"] if f["code"] == "trace_db_shared"]
    assert found and found[0]["severity"] == "error" and found[0]["scope"] == "machine"
    fresh_a = api.get("a", "factory/check?offline=1&fresh=1")["data"]
    assert "trace_db_shared" in [f["code"] for f in fresh_a["findings"]]

    bad = api.client.get(api.url("a", "factory/check?offline=maybe"))
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "usage_error"


def test_check_carries_manifest_and_version(api: Api, tmp_path: Path) -> None:
    from aifactory import __version__

    store.init_library("team")
    install(api, "a")
    data = api.get("a", "factory/check?offline=1&fresh=1")["data"]
    assert data["state"] == "onboarded"
    assert data["library"]["name"]
    assert isinstance(data["manifest"]["format"], int)
    assert data["manifest"]["written_by"]
    assert data["manifest_error"] is None
    assert data["version"] == __version__

    write(tmp_path / "b", ".factory/config.yaml", "base: main\n")
    commit_push(tmp_path / "b", "pre-library config")
    old = api.get("b", "factory/check?offline=1&fresh=1")["data"]
    assert old["state"] == "pre_library"
    assert old["manifest"] is None and old["version"] == __version__


# ── validation ────────────────────────────────────────────────────────────────


def test_validation(api: Api) -> None:
    def usage(path: str, body: dict[str, Any]) -> None:
        assert code_of(api.post("a", path, body, 400)) == "usage_error"

    usage("factory/apply", {"action": "init", "digest": "x", "files": [{"path": "a"}]})
    usage("factory/apply", {"action": "init", "digest": "x", "path": "/tmp"})
    usage("factory/plan", {"action": "install"})
    usage("factory/apply", {"action": "init"})
    usage("factory/plan", {"action": "update", "options": {"agents": ["builder"]}})
    usage("factory/plan", {"action": "config_commit", "options": {"take": []}})
    usage("factory/plan", {"action": "init", "target": "elsewhere"})
    usage("factory/plan", {"action": "init", "options": {"agents": "builder"}})
    bad_harness = {"action": "init", "options": {"bind": {"builder": {"harness": "nope"}}}}
    assert code_of(api.post("a", "factory/plan", bad_harness, 422)) == "invalid_value"
    conflict = {
        "action": "init",
        "options": {"provider": "github", "azure": {"organization": "o"}},
    }
    assert code_of(api.post("a", "factory/plan", conflict, 422)) == "conflicting_options"


# ── one repository ────────────────────────────────────────────────────────────


def test_single_repo_app(tmp_path: Path) -> None:
    root = make_repo(tmp_path, "solo", remote=False)
    app = create_app(root, static_dir=tmp_path / "nostatic")
    app.state.check_machine = FakeMachine()
    client = TestClient(app, base_url=BASE)

    check = check_body(client.get("/api/factory/check?offline=1"), 200)
    assert "trace_db_shared" not in [f["code"] for f in check["data"]["findings"]]
    plan = check_body(client.post("/api/factory/plan", json={"action": "init"}), 200)
    assert plan["data"]["digest"]
    digest = check_body(client.get("/api/config/pull/plan"), 200)["data"]["digest"]
    pulled = check_body(client.post("/api/config/pull", json={"digest": digest}), 409)
    assert code_of(pulled) == "no_remote"


def test_pull_requires_review_and_rejects_changed_remote(api: Api, tmp_path: Path) -> None:
    a = tmp_path / "a"
    before = git(a, "rev-parse", "main")
    assert code_of(api.post("a", "config/pull", {}, 400)) == "usage_error"
    preview = api.get("a", "config/pull/plan")["data"]
    clone = tmp_path / "remote-writer"
    git(tmp_path, "clone", "-q", str(bare_of(tmp_path, "a")), str(clone))
    write(clone, "remote.txt", "remote change\n")
    after = commit_push(clone, "remote moved")
    refused = api.post("a", "config/pull", {"digest": preview["digest"]}, 409)
    assert code_of(refused) == "plan_changed"
    assert git(a, "rev-parse", "main") == before
    assert not (a / "remote.txt").exists()
    next_plan = api.get("a", "config/pull/plan")["data"]
    assert next_plan["after"] == after
    assert next_plan["files"][0]["content"] == "remote change\n"
    api.post("a", "config/pull", {"digest": next_plan["digest"]})
    assert git(a, "rev-parse", "main") == after


def test_dashboard_onboarding_hint_uses_known_refs(api: Api, tmp_path: Path) -> None:
    install(api, "a")
    repo = tmp_path / "b"
    write(repo, ".factory/config.yaml", "base: main\n")
    commit_push(repo, "pre-library")
    assert web_factory.onboarding_hint(repo)["onboarding_state"] is None
    git(repo, "branch", "factory-config/onboarding")
    assert web_factory.onboarding_hint(repo)["onboarding_state"] == "onboarding_pending"
    git(repo, "fetch", str(bare_of(tmp_path, "a")), "+main:refs/remotes/origin/main")
    before = git(repo, "rev-parse", "main")
    assert web_factory.onboarding_hint(repo)["onboarding_state"] == "onboarded_in_remote"
    assert git(repo, "rev-parse", "main") == before


def test_onboarding_preview_links_pending_pr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from types import SimpleNamespace

    from aifactory.config.settings import ProjectSettings
    from aifactory.providers.base import PullRequest
    from aifactory.providers.publish import Blocker

    result = SimpleNamespace(
        to_json=lambda: {"digest": "d", "files": [], "blockers": []},
        warnings=[],
        plan=SimpleNamespace(
            blockers=[Blocker("onboarding_pending", "pending")], settings=ProjectSettings()
        ),
    )
    monkeypatch.setattr(web_factory, "_call", lambda *args, **kwargs: result)
    pr = PullRequest(
        "42", "https://example.test/pull/42", "factory-config/onboarding", "main", "Onboard"
    )
    monkeypatch.setattr(
        "aifactory.providers.get_provider",
        lambda *args: SimpleNamespace(find_open_pr=lambda branch: pr),
    )
    req = web_factory.parse_plan_body({"action": "onboard", "options": {}, "target": "base"})
    data, _ = web_factory.plan(tmp_path, req)
    assert data["pending_pr"] == {"id": "42", "url": "https://example.test/pull/42"}
