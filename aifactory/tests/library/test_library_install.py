"""``factory init``: install factory into a repo from the library or the seed (HAIFA-S04-T01)."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from aifactory import __version__
from aifactory.config.manifest import MANIFEST_FILE
from aifactory.library import store
from aifactory.library.install import GITIGNORE_LINES, init_repo
from aifactory.library.seed import seed_items
from aifactory.workflow.parse import DEFAULT_WORKFLOWS_DIR
from cli_json import run_json

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "run"))

from run_repo import Script, commit_all, fake_env, ok, write  # noqa: E402
from workflow_fakes import plan_envelope  # noqa: E402

Capsys = pytest.CaptureFixture[str]
DEFAULT_AGENTS = ["planner", "builder", "tester", "test-reviewer", "reviewer", "documenter"]


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return proc.stdout.strip()


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """``$HAIFA_HOME`` with the library at its default place and a git identity."""
    path = tmp_path / "haifa-home"
    monkeypatch.setenv("HAIFA_HOME", str(path))
    monkeypatch.delenv("HAIFA_LIBRARY", raising=False)
    for kind in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{kind}_NAME", "Ada Tester")
        monkeypatch.setenv(f"GIT_{kind}_EMAIL", "ada@example.com")
    return path


@pytest.fixture
def repo(tmp_path: Path, home: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.name", "Test")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "commit.gpgsign", "false")
    (path / "README.md").write_text("readme\n", encoding="utf-8", newline="\n")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "init")
    return path.resolve()


BUILDER_PROMPT = b"You are the team builder.\n"


@pytest.fixture
def library(home: Path) -> Path:
    """A library from the seed with a team builder and a remote with credentials."""
    store.init_library("team")
    root = store.library_root()
    (root / "agents" / "builder" / "system.md").write_bytes(BUILDER_PROMPT)
    _git(root, "commit", "-q", "-am", "team builder")
    _git(root, "remote", "add", "origin", "https://user:secret@example.com/lib.git")
    return root


def snapshot(path: Path) -> list[tuple[str, bytes]]:
    if not path.exists():
        return []
    return sorted(
        (p.relative_to(path).as_posix(), p.read_bytes()) for p in path.rglob("*") if p.is_file()
    )


def factory_files(repo: Path) -> dict[str, bytes]:
    out = {
        p.relative_to(repo).as_posix(): p.read_bytes()
        for p in (repo / ".factory").rglob("*")
        if p.is_file()
    }
    out[".gitignore"] = (repo / ".gitignore").read_bytes()
    return out


def worktree_paths(repo: Path) -> list[str]:
    return sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*") if ".git/" not in str(p))


def init(capsys: Capsys, repo: Path, *args: str) -> tuple[int, Any]:
    return run_json(capsys, ["init", "--repo", str(repo), *args, "--json"])


def load(repo: Path, rel: str) -> Any:
    return yaml.safe_load((repo / rel).read_text(encoding="utf-8"))


def roster(repo: Path) -> dict[str, dict[str, Any]]:
    return {a["name"]: a for a in load(repo, ".factory/agents.yaml")["agents"]}


def test_init_from_seed_without_library(repo: Path, home: Path, capsys: Capsys) -> None:
    rc, env = init(capsys, repo)

    assert rc == 0, env
    data = env["data"]
    assert data["source"] == "seed" and data["library"] is None
    assert data["agents"] == DEFAULT_AGENTS and data["workflows"] == ["simple-sdlc"]
    assert {f["action"] for f in data["files"]} == {"created"}
    config = load(repo, ".factory/config.yaml")
    assert config["base"] == "main" and config["git_provider"] == "local"
    agents = load(repo, ".factory/agents.yaml")["agents"]
    assert [a["name"] for a in agents] == DEFAULT_AGENTS
    assert agents[0]["writes"] == ["specs/"]
    assert agents[5]["writes"] == ["app_docs/"]
    prompts = list((repo / ".factory" / "prompts").rglob("*.md"))
    assert len(prompts) == 12
    assert not any(b"haifa-validate" in p.read_bytes() for p in prompts)
    assert (repo / ".factory/workflows/simple-sdlc.yaml").read_bytes() == (
        DEFAULT_WORKFLOWS_DIR / "simple-sdlc.yaml"
    ).read_bytes()
    assert (repo / "backlog" / ".gitkeep").is_file()
    manifest = load(repo, MANIFEST_FILE)
    assert manifest["format"] == 1 and manifest["written_by"] == __version__
    assert manifest["library"] is None
    assert manifest["onboarding"]["source"] == "init"
    assert manifest["onboarding"]["source_commit"] == _git(repo, "rev-parse", "HEAD")
    versions = {(i.type, i.name): i.version for i in seed_items()}
    for name, entry in manifest["items"]["agents"].items():
        assert entry == {"item": name, "version": versions[("agent", name)]}
    assert (
        manifest["items"]["workflows"]["simple-sdlc"]["version"]
        == versions[("workflow", "simple-sdlc")]
    )
    assert _git(repo, "rev-list", "--count", "HEAD") == "1"
    status = _git(repo, "status", "--porcelain").splitlines()
    assert status and all(line.startswith("??") for line in status)
    assert not home.exists()


def test_init_from_library_with_team_builder(
    repo: Path, home: Path, library: Path, capsys: Capsys
) -> None:
    before = snapshot(home)
    rc, env = init(capsys, repo)

    assert rc == 0, env
    assert snapshot(home) == before
    assert env["data"]["source"] == "library"
    meta = yaml.safe_load((library / "library.yaml").read_text(encoding="utf-8"))
    manifest = load(repo, MANIFEST_FILE)
    assert manifest["library"] == {
        "id": meta["id"],
        "name": meta["name"],
        "remote": "https://example.com/lib.git",
    }
    assert "secret" not in (repo / MANIFEST_FILE).read_text(encoding="utf-8")
    assert manifest["onboarding"]["library_commit"] == _git(library, "rev-parse", "HEAD")
    seed_builder = next(i for i in seed_items() if (i.type, i.name) == ("agent", "builder"))
    version = manifest["items"]["agents"]["builder"]["version"]
    assert version != seed_builder.version
    assert (repo / ".factory/prompts/builder/system.md").read_bytes() == BUILDER_PROMPT

    commit_all(repo, "install factory")
    rc, env = run_json(capsys, ["config", "items", "--repo", str(repo), "--json"])
    assert rc == 0, env
    assert env["data"]["library"]["source"] == "library"
    assert {i["state"] for i in env["data"]["items"]} == {"synced"}


def test_bind_sets_harness_model_and_thinking(repo: Path, capsys: Capsys) -> None:
    rc, env = init(capsys, repo, "--bind", "builder=codex:gpt-5.5:high")

    assert rc == 0, env
    agents = roster(repo)
    builder = agents["builder"]
    assert (builder["harness"], builder["model"], builder["thinking"]) == (
        "codex",
        "gpt-5.5",
        "high",
    )
    assert all(
        agents[n]["harness"] == "claude"
        for n in ("planner", "tester", "test-reviewer", "reviewer", "documenter")
    )


@pytest.mark.parametrize("bind", ["builder=nope", "scout=claude", "builder", "builder=claude::x"])
def test_bad_bind_is_refused(repo: Path, capsys: Capsys, bind: str) -> None:
    rc, env = init(capsys, repo, "--bind", bind)

    assert rc == 2
    assert env["error"]["code"] == "invalid_value"
    assert not (repo / ".factory").exists()


def test_workflow_adds_its_agents(repo: Path, capsys: Capsys) -> None:
    rc, env = init(capsys, repo, "--workflows", "scout")

    assert rc == 0, env
    assert env["data"]["added_agents"] == ["scout"]
    assert list(roster(repo)) == [*DEFAULT_AGENTS, "scout"]
    assert (repo / ".factory/prompts/scout/system.md").is_file()
    assert (repo / ".factory/workflows/scout.yaml").is_file()
    assert not (repo / ".factory/workflows/simple-sdlc.yaml").exists()


def test_second_run_skips_everything(repo: Path, capsys: Capsys) -> None:
    assert init(capsys, repo)[0] == 0
    first = factory_files(repo)

    rc, env = init(capsys, repo)

    assert rc == 0, env
    assert {f["action"] for f in env["data"]["files"]} == {"skipped"}
    assert env["data"]["gitignore"]["added"] == []
    assert any("--force" in w for w in env["warnings"])
    assert factory_files(repo) == first


def test_force_overwrites(repo: Path, capsys: Capsys) -> None:
    assert init(capsys, repo)[0] == 0
    first = factory_files(repo)
    write(repo, ".factory/prompts/builder/system.md", "changed\n")
    write(repo, ".factory/config.yaml", "base: other\n")

    rc, env = init(capsys, repo, "--force")

    assert rc == 0, env
    assert {f["action"] for f in env["data"]["files"]} == {"overwritten"}
    after = factory_files(repo)
    for rel in (".factory/prompts/builder/system.md", ".factory/config.yaml"):
        assert after[rel] == first[rel]


def test_gitignore_lines_are_added_once(repo: Path, capsys: Capsys) -> None:
    (repo / ".gitignore").write_text(
        "node_modules\n.factory/local.yaml", encoding="utf-8", newline="\n"
    )

    rc, env = init(capsys, repo)

    assert rc == 0, env
    assert ".factory/local.yaml" not in env["data"]["gitignore"]["added"]
    lines = (repo / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "node_modules"
    for line in GITIGNORE_LINES:
        assert lines.count(line) == 1
    assert init(capsys, repo)[1]["data"]["gitignore"]["added"] == []
    assert (repo / ".gitignore").read_text(encoding="utf-8").splitlines() == lines


@pytest.mark.parametrize("force", [False, True])
def test_installed_repo_is_refused(repo: Path, capsys: Capsys, force: bool) -> None:
    assert init(capsys, repo)[0] == 0
    commit_all(repo, "install factory")

    rc, env = init(capsys, repo, *(["--force"] if force else []))

    assert rc == 2
    assert env["error"]["code"] == "already_installed"
    assert "factory update" in env["error"]["message"]
    assert _git(repo, "status", "--porcelain") == ""


@pytest.mark.parametrize(
    "existing",
    [".factory/config.yaml", ".factory/agents.yaml", "adws/adw_sssf_config/sssf.config.yaml"],
)
def test_existing_config_is_refused(repo: Path, capsys: Capsys, existing: str) -> None:
    write(repo, existing, "x: 1\n")
    before = worktree_paths(repo)

    rc, env = init(capsys, repo, "--force")

    assert rc == 2
    assert env["error"]["code"] == "existing_config"
    assert "does not take over" in env["error"]["message"]
    assert "factory onboard" not in env["error"]["message"]
    assert "fix" not in (env.get("data") or {})
    after = worktree_paths(repo)
    assert after == before


def test_result_is_valid(repo: Path, capsys: Capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    assert init(capsys, repo)[0] == 0
    commit_all(repo, "install factory")

    monkeypatch.chdir(repo)
    rc, env = run_json(capsys, ["config", "show", "--json"])
    assert rc == 0, env
    rc, env = run_json(capsys, ["backlog", "check", "--repo", str(repo), "--json"])
    assert rc == 0, env
    rc, env = run_json(capsys, ["config", "items", "--repo", str(repo), "--json"])
    assert rc == 0, env
    states = {(i["type"], i["name"]): i["state"] for i in env["data"]["items"]}
    assert set(states) == {("agent", n) for n in DEFAULT_AGENTS} | {("workflow", "simple-sdlc")}
    assert set(states.values()) == {"synced"}


def test_init_refuses_detached_head_without_base(repo: Path) -> None:
    _git(repo, "checkout", "-q", "--detach")
    with pytest.raises(store.LibraryStoreError) as caught:
        init_repo(repo)
    assert caught.value.code == "invalid_value"


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


TASK = "M01-S01-T01"
SPEC = f"specs/{TASK}-schema.md"
DOC = f"app_docs/{TASK}-schema.md"


def test_task_runs_in_an_installed_repo(repo: Path, capsys: Capsys, script: Script) -> None:
    from aifactory.run import run_task

    assert init(capsys, repo)[0] == 0
    write(repo, "backlog/M01-core/index.md", "---\nid: M01\ntitle: Core\n---\n\nJádro.\n")
    write(
        repo,
        "backlog/M01-core/S01-model/index.md",
        "---\nid: M01-S01\ntitle: Model\nworkflow: simple-sdlc\nwrites: [src/app/]\n---\n",
    )
    write(
        repo,
        f"backlog/M01-core/S01-model/{TASK}-schema.md",
        f"---\nid: {TASK}\ntitle: Schema\nstatus: todo\n---\n\n## Zadání\nNavrhnout schéma.\n",
    )
    commit_all(repo, "install factory")

    script.on("planner", lambda wt: write(wt, SPEC, "# spec\n"))
    script.add("planner", ok(artifacts=[SPEC], commit_message="Add schema spec"))
    script.on("builder", lambda wt: write(wt, "src/app/model.py", "x = 1\n"))
    script.add("builder", ok(changed_files=["src/app/model.py"], commit_message="Add model"))
    script.add("tester", plan_envelope("git", "--version"))
    script.add("test-reviewer", ok(approved=True, summary="plan fits", findings=[], blocking=[]))
    script.add("reviewer", ok(approved=True, findings=[{"requirement": "x", "met": True}]))
    script.on("documenter", lambda wt: write(wt, DOC, "# doc\n"))
    script.add("documenter", ok(artifacts=[DOC], commit_message="Document schema"))

    result = run_task(repo, TASK)

    row = result.run
    assert row.state == "succeeded", row.error
    assert result.workflow_run is not None and result.workflow_run.exit_code == 0
    assert _git(repo, "show", f"{row.branch}:src/app/model.py") == "x = 1"
    assert _git(repo, "show", f"{row.branch}:{DOC}") == "# doc"
