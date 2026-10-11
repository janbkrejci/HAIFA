"""``factory init``: install factory into a repo; agents and workflows stay in the library."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from aifactory.library import store
from aifactory.library.install import GITIGNORE_LINES, init_repo
from cli_json import run_json

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "run"))

from run_repo import Script, commit_all, fake_env, ok, write  # noqa: E402
from workflow_fakes import plan_envelope  # noqa: E402

Capsys = pytest.CaptureFixture[str]


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


def test_init_writes_only_config_backlog_and_gitignore(repo: Path, capsys: Capsys) -> None:
    rc, env = init(capsys, repo)

    assert rc == 0, env
    paths = [f["path"] for f in env["data"]["files"]]
    assert paths == [".factory/config.yaml", "factory/backlog/.gitkeep"]
    assert {f["action"] for f in env["data"]["files"]} == {"created"}
    assert env["data"]["gitignore"]["added"] == list(GITIGNORE_LINES)
    assert sorted(factory_files(repo)) == [".factory/config.yaml", ".gitignore"]
    config = yaml.safe_load((repo / ".factory/config.yaml").read_text(encoding="utf-8"))
    assert config == {"base": "main", "git_provider": "local", "docs_root": "factory"}
    assert _git(repo, "log", "--oneline").count("\n") == 0  # nothing committed


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
    write(repo, ".factory/config.yaml", "base: other\n")

    rc, env = init(capsys, repo, "--force")

    assert rc == 0, env
    assert {f["action"] for f in env["data"]["files"]} == {"overwritten"}
    assert factory_files(repo)[".factory/config.yaml"] == first[".factory/config.yaml"]


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
    assert _git(repo, "status", "--porcelain") == ""


def test_sssf_is_refused(repo: Path, capsys: Capsys) -> None:
    write(repo, "adws/adw_sssf_config/sssf.config.yaml", "x: 1\n")
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
    assert {"planner", "builder", "tester", "reviewer"} <= set(env["data"]["agents"])
    assert "simple-sdlc" in env["data"]["workflows"]
    rc, env = run_json(capsys, ["backlog", "check", "--repo", str(repo), "--json"])
    assert rc == 0, env


def test_init_refuses_detached_head_without_base(repo: Path) -> None:
    _git(repo, "checkout", "-q", "--detach")
    with pytest.raises(store.LibraryStoreError) as caught:
        init_repo(repo)
    assert caught.value.code == "invalid_value"


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


TASK = "M01-S01-T01"
SPEC = f"factory/specs/M01-core/S01-model/{TASK}-schema.md"
DOC = f"factory/docs/M01-core/S01-model/{TASK}-schema.md"


def test_task_runs_in_an_installed_repo(repo: Path, capsys: Capsys, script: Script) -> None:
    from aifactory.run import run_task

    assert init(capsys, repo)[0] == 0
    write(repo, "factory/backlog/M01-core/index.md", "---\nid: M01\ntitle: Core\n---\n\nJádro.\n")
    write(
        repo,
        "factory/backlog/M01-core/S01-model/index.md",
        "---\nid: M01-S01\ntitle: Model\nworkflow: simple-sdlc\nwrites: [src/app/]\n---\n",
    )
    write(
        repo,
        f"factory/backlog/M01-core/S01-model/{TASK}-schema.md",
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
