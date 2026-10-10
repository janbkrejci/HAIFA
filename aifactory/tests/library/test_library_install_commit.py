"""``factory init --dry-run`` and ``--commit`` against a bare remote (HAIFA-S01-T12, no network)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from aifactory.config.manifest import MANIFEST_FILE
from aifactory.library import store
from aifactory.library.install import GITIGNORE_LINES
from cli_json import run_json

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "providers"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "check"))

from factory_check_repo import FakeMachine  # noqa: E402
from gh_fake import install_fake_gh, prepare_shared_gh, reply  # noqa: E402

from fake_exe import make_executable

Capsys = pytest.CaptureFixture[str]
PLANNER_PROMPT = ".factory/prompts/planner/system.md"
JUSTFILE = "test:\n    echo ok\n"


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
    claude = make_executable(claude)
    monkeypatch.setenv("CLAUDE_CODE_PATH", str(claude))
    monkeypatch.setenv("CODEX_PATH", "codex-not-installed-anywhere")
    monkeypatch.setenv("PI_PATH", "pi-not-installed-anywhere")
    return path


def make_repo(tmp_path: Path, *, remote: bool = True) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    (path / "README.md").write_text("readme\n", encoding="utf-8", newline="\n")
    (path / "justfile").write_text(JUSTFILE, encoding="utf-8", newline="\n")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "init")
    if remote:
        bare = tmp_path / "origin.git"
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
        git(path, "remote", "add", "origin", str(bare))
        git(path, "push", "-q", "-u", "origin", "main")
        git(path, "remote", "set-head", "origin", "main")
    return path.resolve()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


def bare(tmp_path: Path) -> Path:
    return tmp_path / "origin.git"


def rev(repo: Path, ref: str) -> str:
    return git(repo, "rev-parse", ref)


def snapshot(repo: Path) -> tuple[str, bytes, dict[str, bytes]]:
    refs = git(repo, "for-each-ref", "--format=%(refname) %(objectname)")
    refs += git(repo, "symbolic-ref", "HEAD")
    index = (repo / ".git" / "index").read_bytes()
    files = {
        p.relative_to(repo).as_posix(): p.read_bytes()
        for p in repo.rglob("*")
        if p.is_file() and ".git" not in p.relative_to(repo).parts
    }
    exclude = repo / ".git" / "info" / "exclude"
    files[":exclude"] = exclude.read_bytes() if exclude.exists() else b""
    return refs, index, files


def tree(path: Path) -> list[tuple[str, bytes]]:
    if not path.exists():
        return []
    return sorted(
        (p.relative_to(path).as_posix(), p.read_bytes()) for p in path.rglob("*") if p.is_file()
    )


def init(capsys: Capsys, repo: Path, *args: str) -> tuple[int, Any]:
    return run_json(capsys, ["init", "--repo", str(repo), *args, "--json"])


def preview(capsys: Capsys, repo: Path, *args: str) -> dict[str, Any]:
    rc, env = init(capsys, repo, "--dry-run", *args)
    assert rc == 0, env
    data: dict[str, Any] = env["data"]
    return data


def files_of(data: dict[str, Any]) -> dict[str, str]:
    return {f["path"]: f["content"] for f in data["files"]}


def codes(items: list[dict[str, Any]]) -> list[str]:
    return [i["code"] for i in items]


# ── preview ───────────────────────────────────────────────────────────────────


def test_preview_writes_nothing(repo: Path, home: Path, capsys: Capsys) -> None:
    before, home_before = snapshot(repo), tree(home)

    data = preview(capsys, repo)

    assert snapshot(repo) == before and tree(home) == home_before
    assert not home.exists()
    files = files_of(data)
    assert {
        ".factory/config.yaml",
        ".factory/agents.yaml",
        MANIFEST_FILE,
        ".factory/workflows/simple-sdlc.yaml",
        PLANNER_PROMPT,
        ".gitignore",
        "backlog/.gitkeep",
    } <= set(files)
    manifest = yaml.safe_load(files[MANIFEST_FILE])
    assert manifest["onboarding"]["source"] == "init" and manifest["library"] is None
    assert data["blockers"] == [] and data["validation"] == {"ok": True, "issues": []}
    assert len(data["digest"]) == 64 and data["target"] == "direct"
    assert data["dry_run"] is True and data["committed"] is False
    detected = data["detected"]
    assert detected["remote"] == "origin" and detected["base"] == "main"
    assert detected["base_source"] == "remote_head" and detected["provider"] == "local"
    assert detected["harnesses"]["claude"]["installed"] is True
    assert detected["harnesses"]["codex"]["installed"] is False
    available = data["available"]
    assert available["source"] == "seed" and available["library"] is None
    agents = {a["name"]: a for a in available["agents"]}
    assert agents["planner"]["default"] and not agents["scout"]["default"]
    assert agents["builder"]["harness"] == "claude"
    workflows = {w["name"]: w for w in available["workflows"]}
    assert workflows["simple-sdlc"]["default"]
    assert workflows["simple-sdlc"]["agents"] == [
        "planner",
        "builder",
        "tester",
        "reviewer",
        "documenter",
    ]
    config = yaml.safe_load(files[".factory/config.yaml"])
    assert config == {
        "base": "main",
        "git_provider": "local",
        "backlog_dir": "backlog",
        "specs_dir": "specs",
        "docs_dir": "app_docs",
    }
    # the time in the manifest does not change the digest
    assert preview(capsys, repo)["digest"] == data["digest"]


def test_preview_offers_the_library(repo: Path, home: Path, capsys: Capsys) -> None:
    store.init_library("team")
    lib = tree(store.library_root())

    data = preview(capsys, repo)

    assert data["available"]["source"] == "library"
    assert data["available"]["library"]["name"] == "team"
    assert yaml.safe_load(files_of(data)[MANIFEST_FILE])["library"]["name"] == "team"
    assert tree(store.library_root()) == lib


def test_option_conflicts(repo: Path, capsys: Capsys) -> None:
    before = snapshot(repo)
    for args in (
        ("--dry-run", "--force"),
        ("--commit", "--force"),
        ("--pr",),
        ("--expect", "abc"),
        ("--dry-run", "--expect", "abc"),
        ("-m", "x"),
        ("--dry-run", "--provider", "github", "--azure-org", "c"),
    ):
        rc, env = init(capsys, repo, *args)
        assert rc == 2 and env["error"]["code"] == "conflicting_options", args
    assert snapshot(repo) == before


# ── commit ────────────────────────────────────────────────────────────────────


def test_commit_and_push(repo: Path, tmp_path: Path, capsys: Capsys) -> None:
    base_sha = rev(repo, "main")
    data = preview(capsys, repo)

    rc, env = init(capsys, repo, "--commit", "--expect", data["digest"])

    assert rc == 0, env
    out = env["data"]
    assert out["committed"] and out["pushed"] and out["advanced"]
    sha = out["commit"]
    assert rev(repo, "main") == sha == rev(bare(tmp_path), "main")
    assert rev(repo, f"{sha}^") == base_sha
    names = git(repo, "show", "--name-only", "--format=", sha).split()
    assert sorted(names) == sorted(f["path"] for f in data["files"])
    assert git(repo, "log", "-1", "--format=%s", sha) == "factory: install from the seed"
    assert git(repo, "status", "--porcelain") == ""
    for path, content in files_of(data).items():
        if path != MANIFEST_FILE:
            assert (repo / path).read_text(encoding="utf-8") == content
    assert (repo / MANIFEST_FILE).is_file()
    assert not (repo / ".factory" / "trace.db").exists()

    again = preview(capsys, repo)
    assert codes(again["blockers"]) == ["already_installed"]
    assert again["blockers"][0]["fix"] == "factory update"


def test_after_install_check_and_items(repo: Path, capsys: Capsys) -> None:
    from aifactory.check import run_check

    rc, env = init(capsys, repo, "--commit")
    assert rc == 0, env

    report = run_check(repo, machine=FakeMachine())
    assert [f for f in report.findings if f.severity == "error"] == []

    rc, items = run_json(capsys, ["config", "items", "--repo", str(repo), "--json"])
    assert rc == 0, items
    states = {(i["type"], i["name"]): i["state"] for i in items["data"]["items"]}
    assert states and set(states.values()) == {"synced"}
    assert ("workflow", "simple-sdlc") in states and ("agent", "builder") in states


def test_rejected_push_changes_nothing(repo: Path, tmp_path: Path, capsys: Capsys) -> None:
    hook = bare(tmp_path) / "hooks" / "pre-receive"
    hook.parent.mkdir(exist_ok=True)
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8", newline="\n")
    hook.chmod(0o755)
    remote_before = rev(bare(tmp_path), "main")
    before = snapshot(repo)

    rc, env = init(capsys, repo, "--commit")

    assert rc == 2 and env["error"]["code"] == "push_failed"
    assert env["data"]["files"]
    assert snapshot(repo) == before
    assert not (repo / ".factory").exists()
    assert rev(bare(tmp_path), "main") == remote_before


def test_plan_changed(repo: Path, capsys: Capsys) -> None:
    old = preview(capsys, repo)["digest"]
    assert preview(capsys, repo, "--bind", "builder=claude:claude-sonnet-4-5")["digest"] != old
    (repo / "README.md").write_text("changed\n", encoding="utf-8", newline="\n")
    git(repo, "commit", "-qam", "unrelated")
    git(repo, "push", "-q", "origin", "main")
    before = snapshot(repo)

    rc, env = init(capsys, repo, "--commit", "--expect", old)

    assert rc == 2 and env["error"]["code"] == "plan_changed"
    assert snapshot(repo) == before
    new = preview(capsys, repo)["digest"]
    rc, env = init(capsys, repo, "--commit", "--expect", new, "-m", "install factory")
    assert rc == 0, env
    assert git(repo, "log", "-1", "--format=%s") == "install factory"


@pytest.fixture(scope="module")
def _shared_gh(tmp_path_factory: pytest.TempPathFactory) -> None:
    prepare_shared_gh(tmp_path_factory.mktemp("ghwarm"))


@pytest.mark.usefixtures("_shared_gh")
def test_pr_through_github(
    repo: Path, tmp_path: Path, capsys: Capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = install_fake_gh(
        tmp_path, monkeypatch, {"pr create": reply("https://github.com/o/r/pull/7\n")}
    )
    git(repo, "checkout", "-q", "-b", "side")
    base_sha = rev(repo, "main")
    data = preview(capsys, repo, "--provider", "github", "--pr")
    assert data["target"] == "pr" and data["blockers"] == []
    assert yaml.safe_load(files_of(data)[".factory/config.yaml"])["git_provider"] == "github"
    before = snapshot(repo)

    rc, env = init(
        capsys, repo, "--provider", "github", "--commit", "--pr", "--expect", data["digest"]
    )

    assert rc == 0, env
    out = env["data"]
    assert out["branch"] == "factory-init/1" and out["pushed"] and not out["advanced"]
    assert out["pr"]["url"] == "https://github.com/o/r/pull/7"
    assert rev(bare(tmp_path), "factory-init/1") == out["commit"]
    assert rev(repo, f"{out['commit']}^") == base_sha
    assert rev(repo, "main") == base_sha
    assert snapshot(repo)[1:] == before[1:]
    assert not (repo / ".factory").exists()
    creates = [a for a in log.argvs() if a[:2] == ["pr", "create"]]
    assert creates and creates[0][2:6] == ["--base", "main", "--head", "factory-init/1"]


# ── blockers ──────────────────────────────────────────────────────────────────


def test_dirty_paths(repo: Path, capsys: Capsys) -> None:
    target = repo / PLANNER_PROMPT
    target.parent.mkdir(parents=True)
    target.write_text("my own planner\n", encoding="utf-8", newline="\n")
    before = snapshot(repo)

    data = preview(capsys, repo)
    assert codes(data["blockers"]) == ["dirty_paths"]
    assert PLANNER_PROMPT in data["blockers"][0]["message"]
    rc, env = init(capsys, repo, "--commit")
    assert rc == 2 and env["error"]["code"] == "dirty_paths"
    assert snapshot(repo) == before

    target.write_text(files_of(data)[PLANNER_PROMPT], encoding="utf-8", newline="\n")
    data = preview(capsys, repo)
    assert data["blockers"] == []
    rc, env = init(capsys, repo, "--commit", "--expect", data["digest"])
    assert rc == 0, env
    assert git(repo, "status", "--porcelain") == ""


def test_dirty_gitignore_goes_to_info_exclude(repo: Path, capsys: Capsys) -> None:
    (repo / ".gitignore").write_text("node_modules/\n", encoding="utf-8", newline="\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "gitignore")
    git(repo, "push", "-q", "origin", "main")
    (repo / ".gitignore").write_text("node_modules/\n*.log\n", encoding="utf-8", newline="\n")

    data = preview(capsys, repo)

    assert ".gitignore" not in files_of(data)
    assert data["exclude"]["lines"] == list(GITIGNORE_LINES)
    assert "gitignore_dirty" in codes(data["warnings"])
    assert data["blockers"] == []
    exclude = repo / ".git" / "info" / "exclude"
    before = exclude.read_text(encoding="utf-8") if exclude.exists() else ""

    rc, env = init(capsys, repo, "--commit", "--expect", data["digest"])

    assert rc == 0, env
    text = exclude.read_text(encoding="utf-8")
    assert text.startswith(before)
    assert all(line in text.splitlines() for line in GITIGNORE_LINES)
    assert (repo / ".gitignore").read_text(encoding="utf-8") == "node_modules/\n*.log\n"
    assert git(repo, "status", "--porcelain") == "M .gitignore"


def test_clean_gitignore_is_extended(repo: Path, capsys: Capsys) -> None:
    (repo / ".gitignore").write_text("node_modules/", encoding="utf-8", newline="\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "gitignore")
    git(repo, "push", "-q", "origin", "main")

    data = preview(capsys, repo)
    planned = {f["path"]: f for f in data["files"]}[".gitignore"]
    assert planned["action"] == "modify" and data["exclude"] is None
    assert planned["content"] == "node_modules/\n" + "".join(f"{x}\n" for x in GITIGNORE_LINES)

    rc, env = init(capsys, repo, "--commit")
    assert rc == 0, env
    assert (repo / ".gitignore").read_text(encoding="utf-8") == planned["content"]
    assert git(repo, "status", "--porcelain") == ""


def test_existing_sssf_config(repo: Path, capsys: Capsys) -> None:
    sssf = repo / "adws" / "adw_sssf_config" / "sssf.config.yaml"
    sssf.parent.mkdir(parents=True)
    sssf.write_text("agents: []\n", encoding="utf-8", newline="\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "sssf")
    before = snapshot(repo)

    data = preview(capsys, repo)
    assert codes(data["blockers"])[0] == "existing_config"
    assert data["blockers"][0]["fix"] == "factory onboard"
    rc, env = init(capsys, repo, "--commit")
    assert rc == 2 and env["error"]["code"] == "existing_config"
    assert snapshot(repo) == before


def test_config_not_committed(repo: Path, capsys: Capsys) -> None:
    rc, env = init(capsys, repo)  # the working-tree init of HAIFA-S04-T01
    assert rc == 0, env

    data = preview(capsys, repo)

    assert codes(data["blockers"])[0] == "config_not_committed"
    assert data["blockers"][0]["fix"] == "factory config commit"


def test_invalid_plan(
    repo: Path, tmp_path: Path, capsys: Capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    # codex is on this machine; the engine's default model is no Codex model
    codex = tmp_path / "bin" / "codex"
    codex.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8", newline="\n")
    codex = make_executable(codex)
    monkeypatch.setenv("CODEX_PATH", str(codex))
    data = preview(capsys, repo, "--bind", "builder=codex")
    assert codes(data["blockers"]) == ["invalid_plan"]
    assert data["validation"]["ok"] is False and data["validation"]["issues"]
    rc, env = init(capsys, repo, "--commit", "--bind", "builder=codex")
    assert rc == 2 and env["error"]["code"] == "invalid_plan" and env["error"]["issues"]


def test_not_on_base_only_for_direct(repo: Path, capsys: Capsys) -> None:
    git(repo, "checkout", "-q", "-b", "side")
    assert codes(preview(capsys, repo)["blockers"]) == ["not_on_base"]
    assert preview(capsys, repo, "--pr")["blockers"] == []


# ── choices ───────────────────────────────────────────────────────────────────


def test_builder_on_codex_others_on_claude(repo: Path, capsys: Capsys) -> None:
    data = preview(capsys, repo, "--bind", "builder=codex:gpt-5.5")

    assert data["blockers"] == []
    roster = {
        a["name"]: a for a in yaml.safe_load(files_of(data)[".factory/agents.yaml"])["agents"]
    }
    assert roster["builder"]["harness"] == "codex" and roster["builder"]["model"] == "gpt-5.5"
    assert "thinking" not in roster["builder"]
    for name in ("planner", "reviewer", "documenter"):
        assert roster[name]["harness"] == "claude"
    assert data["bindings"]["builder"]["harness"] == "codex"
    missing = [w for w in data["warnings"] if w["code"] == "harness_missing"]
    assert len(missing) == 1 and "builder" in missing[0]["message"]

    rc, env = init(capsys, repo, "--commit", "--bind", "builder=codex:gpt-5.5")
    assert rc == 0, env
    assert any("codex" in w for w in env["warnings"])


def test_directories(repo: Path, capsys: Capsys) -> None:
    data = preview(
        capsys,
        repo,
        "--backlog-dir",
        "work/backlog",
        "--specs-dir",
        "docs/specs",
        "--docs-dir",
        "docs/app",
    )

    files = files_of(data)
    assert "work/backlog/.gitkeep" in files and "backlog/.gitkeep" not in files
    config = yaml.safe_load(files[".factory/config.yaml"])
    assert (config["backlog_dir"], config["specs_dir"], config["docs_dir"]) == (
        "work/backlog",
        "docs/specs",
        "docs/app",
    )
    roster = {a["name"]: a for a in yaml.safe_load(files[".factory/agents.yaml"])["agents"]}
    assert roster["planner"]["writes"] == ["docs/specs/"]
    assert roster["documenter"]["writes"] == ["docs/app/"]
    assert data["blockers"] == []

    rc, env = init(capsys, repo, "--dry-run", "--specs-dir", "../out")
    assert rc == 2 and env["error"]["code"] == "invalid_value"


def test_existing_backlog_warns_and_gets_no_gitkeep(repo: Path, capsys: Capsys) -> None:
    (repo / "backlog").mkdir()
    (repo / "backlog" / "notes.md").write_text("mine\n", encoding="utf-8", newline="\n")

    data = preview(capsys, repo)

    assert "backlog/.gitkeep" not in files_of(data)
    warnings = [w for w in data["warnings"] if w["code"] == "foreign_content"]
    assert len(warnings) == 1 and warnings[0]["message"].startswith("backlog/")
    assert data["blockers"] == []


def test_azure_from_remote_url(tmp_path: Path, capsys: Capsys) -> None:
    repo = make_repo(tmp_path, remote=False)
    # only the URL: a --pr preview neither fetches nor pushes
    git(repo, "remote", "add", "origin", "https://dev.azure.com/contoso/My%20Proj/_git/widgets")

    data = preview(capsys, repo, "--pr")

    assert data["detected"]["provider"] == "azure"
    azure = {"organization": "contoso", "project": "My Proj", "repository": "widgets"}
    assert data["detected"]["azure"] == azure and data["azure"] == azure
    config = yaml.safe_load(files_of(data)[".factory/config.yaml"])
    assert config["git_provider"] == "azure" and config["azure"] == azure
    assert "remote" not in config

    other = preview(capsys, repo, "--pr", "--azure-project", "Other")
    assert other["azure"]["project"] == "Other"


def test_azure_needs_all_fields(tmp_path: Path, capsys: Capsys) -> None:
    repo = make_repo(tmp_path, remote=False)
    rc, env = init(capsys, repo, "--dry-run", "--provider", "azure", "--azure-org", "c")
    assert rc == 2 and env["error"]["code"] == "invalid_value"
    data = preview(
        capsys,
        repo,
        "--azure-org",
        "c",
        "--azure-project",
        "p",
        "--azure-repo",
        "r",
    )
    assert data["provider"] == "azure" and data["blockers"] == []


def test_without_remote_commits_locally(tmp_path: Path, capsys: Capsys) -> None:
    repo = make_repo(tmp_path, remote=False)
    data = preview(capsys, repo)
    assert data["detected"]["remote"] is None and data["detected"]["base_source"] == "branch"

    rc, env = init(capsys, repo, "--commit", "--expect", data["digest"])

    assert rc == 0, env
    assert env["data"]["advanced"] and not env["data"]["pushed"]
    assert git(repo, "status", "--porcelain") == ""


def test_builder_on_missing_pi_only_warns(
    repo: Path, tmp_path: Path, capsys: Capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aifactory.engine import agent_pi

    # pi lists its models only through its CLI; without pi the catalog is empty
    monkeypatch.setattr(agent_pi, "_pi_catalog", lambda: [])
    bind = ("--bind", "builder=pi:openai/gpt-5.5")

    data = preview(capsys, repo, *bind)

    assert data["blockers"] == [] and data["validation"]["ok"] is True
    missing = [w for w in data["warnings"] if w["code"] == "harness_missing"]
    assert len(missing) == 1 and "builder" in missing[0]["message"]
    roster = {
        a["name"]: a for a in yaml.safe_load(files_of(data)[".factory/agents.yaml"])["agents"]
    }
    assert roster["builder"]["harness"] == "pi"
    rc, env = init(capsys, repo, "--commit", "--expect", data["digest"], *bind)
    assert rc == 0, env

    # with pi on the machine the model is checked and an unknown one blocks
    fake = tmp_path / "bin" / "pi"
    fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8", newline="\n")
    fake = make_executable(fake)
    monkeypatch.setenv("PI_PATH", str(fake))
    (tmp_path / "other").mkdir()
    other = make_repo(tmp_path / "other")
    blocked = preview(capsys, other, *bind)
    assert codes(blocked["blockers"]) == ["invalid_plan"]
