"""Several backlog roots (``backlog_dirs``): config, load, check, writes, commit, run and API."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from aifactory.backlog import (
    TaskEditError,
    add_container,
    add_task,
    check_backlog,
    commit_backlog,
    edit_task,
    link_task,
    load_backlog,
)
from aifactory.backlog.roots import backlog_roots, owning_root
from aifactory.config import ConfigError, ConfigIssue
from aifactory.config.settings import parse_project_settings
from aifactory.run import gitops, run_task
from aifactory.skill import envelope_problems
from aifactory.web import create_app
from cli_json import run_json

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "run"))

from run_repo import (  # noqa: E402
    T01,
    Script,
    commit_all,
    fake_env,
    git,
    make_run_repo,
    ok,
    write,
)

Capsys = pytest.CaptureFixture[str]
ROOTS_CONFIG = "base: main\nbacklog_dirs: [backlog, moduly/*/backlog]\n"
M07 = "moduly/M07/backlog/M07-api"
M07_T01 = "M07-S01-T01"
M07_TASK = f"{M07}/S01-endpoints/M07-S01-T01-api.md"
M07_SPEC = "specs/M07-S01-T01-api.md"


def _add_second_root(repo: Path) -> None:
    write(repo, ".factory/config.yaml", ROOTS_CONFIG)
    write(repo, f"{M07}/index.md", "---\nid: M07\ntitle: API\nworkflow: plan-commit\n---\n")
    write(
        repo,
        f"{M07}/S01-endpoints/index.md",
        "---\nid: M07-S01\ntitle: Endpoints\nwrites: [src/api/]\n---\n",
    )
    write(
        repo,
        M07_TASK,
        f"---\nid: {M07_T01}\ntitle: Api\nstatus: todo\ndepends_on: [{T01}]\n---\n\n"
        "## Zadání\nEndpoint.\n",
    )


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    repo = make_run_repo(tmp_path / "repo")
    _add_second_root(repo)
    commit_all(repo, "second backlog root")
    return repo


def _settings(text: str) -> tuple[Any, list[ConfigIssue]]:
    issues: list[ConfigIssue] = []
    return parse_project_settings(text, "config.yaml", issues), issues


def test_config_accepts_backlog_dirs() -> None:
    settings, issues = _settings("backlog_dirs: [backlog, ./moduly/*/backlog/]\n")
    assert issues == []
    assert settings.backlog_patterns == ("backlog", "moduly/*/backlog")
    single, _ = _settings("backlog_dir: plans\n")
    assert single.backlog_patterns == ("plans",)


@pytest.mark.parametrize(
    "text",
    [
        "backlog_dir: backlog\nbacklog_dirs: [other]\n",
        "backlog_dirs: []\n",
        "backlog_dirs: backlog\n",
        "backlog_dirs: [../outside]\n",
        "backlog_dirs: [/abs]\n",
        "backlog_dirs: [a, a]\n",
        "backlog_dirs: ['moduly/**/backlog']\n",
    ],
)
def test_config_rejects_bad_backlog_dirs(text: str) -> None:
    settings, issues = _settings(text)
    assert settings is None and issues


def test_both_settings_is_a_config_error(repo: Path) -> None:
    write(repo, ".factory/config.yaml", "backlog_dir: backlog\nbacklog_dirs: [backlog]\n")
    with pytest.raises(ConfigError, match="not both"):
        load_backlog(repo)


def test_loads_every_root(repo: Path) -> None:
    backlog = load_backlog(repo)
    assert backlog.roots == ["backlog", "moduly/M07/backlog"]
    assert [c.id for c in backlog.containers] == ["M01", "M07"]
    assert backlog.by_id[M07_T01].path == M07_TASK
    assert check_backlog(backlog) == []
    assert owning_root(M07_TASK, backlog.settings) == "moduly/M07/backlog"
    assert owning_root("moduly/M07/other/x.md", backlog.settings) is None


def test_missing_plain_root_is_reported(repo: Path) -> None:
    write(repo, ".factory/config.yaml", "backlog_dirs: [backlog, nowhere]\n")
    issues = check_backlog(load_backlog(repo))
    assert [(i.code, i.path) for i in issues] == [("missing_backlog_dir", "nowhere")]
    with pytest.raises(TaskEditError) as info:
        add_task(repo, "M01-S01", "Další")
    assert info.value.code == "missing_backlog_dir"


def test_duplicate_id_across_roots(repo: Path, capsys: Capsys) -> None:
    write(repo, "moduly/M08/backlog/M01-copy/index.md", "---\nid: M01\ntitle: Kopie\n---\n")
    issues = check_backlog(load_backlog(repo))
    dupes = [i for i in issues if i.code == "duplicate_id"]
    assert len(dupes) == 1
    assert "backlog/M01-core/index.md" in dupes[0].message
    assert "moduly/M08/backlog/M01-copy/index.md" in dupes[0].message
    rc, data = run_json(capsys, ["backlog", "check", "--json", "--repo", str(repo)])
    assert rc == 1
    found = data["error"].get("issues") or data.get("data", {}).get("issues", [])
    messages = [e["message"] for e in found if e["code"] == "duplicate_id"]
    assert any("moduly/M08/backlog/M01-copy/index.md" in m for m in messages)


def test_list_and_task_writes_in_second_root(repo: Path, capsys: Capsys) -> None:
    rc, data = run_json(capsys, ["backlog", "list", "--json", "--repo", str(repo)])
    assert rc == 0
    assert [p["id"] for p in data["data"]["items"]] == ["M01", "M07"]
    assert data["data"]["backlog_dirs"] == ["backlog", "moduly/M07/backlog"]
    added = add_task(repo, "M07-S01", "Druhý endpoint")
    assert added.path.startswith(f"{M07}/S01-endpoints/")
    edit_task(repo, added.task.id, title="Druhý")
    linked = link_task(repo, added.task.id, depends_on=[M07_T01])
    assert linked.task.depends_on == [M07_T01]


def test_add_project_into_chosen_root(repo: Path, capsys: Capsys) -> None:
    result = add_container(repo, None, "M08", "Fakturace", backlog_dir="moduly/M08/backlog")
    assert result.path == "moduly/M08/backlog/M08-fakturace/index.md"
    assert load_backlog(repo).roots == ["backlog", "moduly/M07/backlog", "moduly/M08/backlog"]
    default = add_container(repo, None, "M09", "Sklad")
    assert default.path == "backlog/M09-sklad/index.md"
    with pytest.raises(TaskEditError) as info:
        add_container(repo, None, "M10", "Jinde", backlog_dir="elsewhere")
    assert info.value.code == "invalid_value"
    with pytest.raises(TaskEditError) as info:
        add_container(repo, "M07", "M07-S02", "Krok", backlog_dir="backlog")
    assert info.value.code == "conflicting_options"
    rc, data = run_json(
        capsys,
        [
            "backlog",
            "add",
            "--id",
            "M11",
            "--title",
            "CLI",
            "--backlog-dir",
            "moduly/M11/backlog",
            "--json",
            "--repo",
            str(repo),
        ],
    )
    assert rc == 0, data
    assert (repo / "moduly/M11/backlog/M11-cli/index.md").is_file()


def test_commit_changes_in_both_roots(repo: Path) -> None:
    first = add_task(repo, "M01-S01", "Třetí")
    second = add_task(repo, "M07-S01", "Druhý endpoint")
    project = add_container(repo, None, "M08", "Fakturace", backlog_dir="moduly/M08/backlog")
    write(repo, "README.md", "changed\n")
    result = commit_backlog(repo)
    assert result.committed
    assert sorted(result.paths) == sorted([first.path, second.path, project.path])
    committed = git(repo, "show", "--name-only", "--format=", "HEAD").splitlines()
    assert sorted(committed) == sorted(result.paths)
    assert git(repo, "status", "--porcelain").split() == ["M", "README.md"]


def test_extract_backlog_reads_every_root_from_base(repo: Path, tmp_path: Path) -> None:
    dest = tmp_path / "base"
    dest.mkdir()
    settings = load_backlog(repo).settings
    gitops.extract_backlog(repo, git(repo, "rev-parse", "HEAD"), settings.backlog_patterns, dest)
    base = load_backlog(dest, settings)
    assert base.roots == ["backlog", "moduly/M07/backlog"]
    assert M07_T01 in base.by_id


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


def test_run_task_from_second_root(repo: Path, script: Script) -> None:
    path = repo / M07_TASK
    path.write_text(
        path.read_text().replace(f"depends_on: [{T01}]\n", ""), encoding="utf-8", newline="\n"
    )
    commit_all(repo, "drop dependency")

    def plan(wt: Path) -> None:
        write(wt, M07_SPEC, "# spec\n")

    script.on("planner", plan)
    script.add("planner", ok(artifacts=[M07_SPEC], commit_message="Add api spec"))
    result = run_task(repo, M07_T01)
    row = result.run
    assert row.state == "succeeded", row.error
    assert row.branch == f"factory/{M07_T01}-1"
    assert git(repo, "show", f"{row.branch}:{M07_SPEC}") == "# spec"


def _client(repo: Path, tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(repo, static_dir=tmp_path / "nostatic"), base_url="http://127.0.0.1:4700"
    )


def _check(response: Any, status: int = 200) -> Any:
    body = response.json()
    assert envelope_problems(body) == []
    assert response.status_code == status, body
    return body


def test_backlog_api_uses_every_root(repo: Path, tmp_path: Path) -> None:
    client = _client(repo, tmp_path)
    body = _check(client.get("/api/backlog"))
    assert body["data"]["backlog_dirs"] == ["backlog", "moduly/M07/backlog"]
    assert M07_T01 in [t["id"] for t in body["data"]["tasks"]]
    detail = _check(client.get(f"/api/backlog/tasks/{M07_T01}"))
    assert detail["data"]["task"]["path"] == M07_TASK
    added = _check(
        client.post(
            "/api/backlog/containers",
            json={"id": "M08", "title": "Fakturace", "backlog_dir": "moduly/M08/backlog"},
        )
    )
    assert added["ok"] is True
    assert (repo / "moduly/M08/backlog/M08-fakturace/index.md").is_file()
    task = _check(client.post("/api/backlog/tasks", json={"step": "M07-S01", "title": "Další"}))
    assert task["ok"] is True
    check = _check(client.get(f"/api/backlog/tasks/{M07_T01}/run-check"))
    assert check["ok"] is True
    committed = _check(client.post("/api/backlog/commit", json={}))
    assert committed["ok"] is True
    files = git(repo, "show", "--name-only", "--format=", "HEAD").splitlines()
    assert any(f.startswith("moduly/M08/backlog/") for f in files)
    assert any(f.startswith(f"{M07}/") for f in files)


def test_backlog_roots_expands_patterns(repo: Path) -> None:
    write(repo, "moduly/M09/notes.txt", "x\n")
    settings = load_backlog(repo).settings
    assert backlog_roots(repo, settings) == ["backlog", "moduly/M07/backlog"]
