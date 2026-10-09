"""The Settings API and the config status (D4) over a temporary git repo."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from backlog_fixture import git, make_backlog_repo
from starlette.testclient import TestClient

from aifactory.config import config_changes, load_local, resolve_commit
from aifactory.config.errors import ConfigIssue
from aifactory.config.settings import parse_project_settings
from aifactory.skill import envelope_problems
from aifactory.web import create_app

BASE = "http://127.0.0.1:4700"
CONFIG = ".factory/config.yaml"
LOCAL = ".factory/local.yaml"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    repo = make_backlog_repo(tmp_path / "repo")
    git(repo, "branch", "-M", "main")
    return repo


@pytest.fixture
def client(root: Path, tmp_path: Path) -> TestClient:
    return TestClient(create_app(root, static_dir=tmp_path / "nostatic"), base_url=BASE)


def _check(response: Any, status: int) -> Any:
    body = response.json()
    assert envelope_problems(body) == []
    assert response.status_code == status, body
    return body


def _get(client: TestClient, url: str, status: int = 200) -> Any:
    return _check(client.get(url), status)


def _post(client: TestClient, payload: Any, status: int = 200) -> Any:
    return _check(client.post("/api/settings", json=payload), status)


def _bytes(root: Path, rel: str) -> bytes | None:
    path = root / rel
    return path.read_bytes() if path.is_file() else None


def test_get_settings(client: TestClient) -> None:
    data = _get(client, "/api/settings")["data"]
    shared = data["shared"]
    assert shared["backlog_dir"] == "backlog"
    assert shared["workdir"] == "."
    assert shared["base"] == "main"
    assert shared["git_provider"] == "local"
    assert shared["merge_strategy"] == "squash"
    assert shared["test_command"] is None
    assert shared["protected_files"] == [".factory/"]
    assert shared["max_parallel_runs"] == 1
    assert data["local"] == {"trace_db": ".factory/trace.db"}
    assert data["options"] == {
        "git_provider": ["local", "github", "azure"],
        "merge_strategy": ["squash", "merge"],
    }
    assert data["files"] == {"shared": CONFIG, "local": LOCAL}
    assert data["shared_issues"] == [] and data["local_issues"] == []
    assert data["status"]["clean"] is True


def test_save_shared(client: TestClient, root: Path) -> None:
    payload = {
        "shared": {
            "base": "develop",
            "test_command": "uv run pytest -q",
            "protected_files": [" .factory/ ", "justfile"],
        }
    }
    body = _post(client, payload)
    assert body["data"]["saved"] == ["shared"]
    assert body["data"]["shared"]["base"] == "develop"
    assert body["data"]["shared"]["test_command"] == "uv run pytest -q"
    raw = yaml.safe_load((root / CONFIG).read_text(encoding="utf-8"))
    assert raw["levels"] == ["module", "step", "task"]
    assert raw["protected_files"] == [".factory/", "justfile"]
    issues: list[ConfigIssue] = []
    settings = parse_project_settings((root / CONFIG).read_text(), CONFIG, issues)
    assert issues == [] and settings is not None
    assert settings.test_command == ("uv", "run", "pytest", "-q")
    assert settings.base == "develop"
    # the status still compares with the committed base (main): config.yaml is modified
    git(root, "branch", "develop")
    status = _get(client, "/api/config/status")["data"]
    assert status["clean"] is False
    assert {"path": CONFIG, "status": "modified"} in status["changes"]
    assert git(root, "diff", "--cached", "--name-only") == ""


def test_save_local_is_never_committed(client: TestClient, root: Path) -> None:
    body = _post(client, {"local": {"trace_db": "var/t.db"}})
    assert body["data"]["saved"] == ["local"]
    assert body["data"]["local"] == {"trace_db": "var/t.db"}
    assert load_local(root).trace_db == "var/t.db"
    assert ".factory/local.yaml" not in git(root, "status", "--porcelain", "--untracked=all")
    assert git(root, "diff", "--cached", "--name-only") == ""
    assert _get(client, "/api/config/status")["data"]["clean"] is True
    # a second save does not add the exclude line twice
    _post(client, {"local": {"trace_db": "var/u.db"}})
    exclude = (root / ".git" / "info" / "exclude").read_text(encoding="utf-8")
    assert exclude.splitlines().count(LOCAL) == 1


@pytest.mark.parametrize(
    ("section", "values", "field"),
    [
        ("shared", {"backlog_dir": "."}, "backlog_dir"),
        ("shared", {"workdir": "../x"}, "workdir"),
        ("shared", {"specs_dir": "/abs"}, "specs_dir"),
        ("shared", {"base": "  "}, "base"),
        ("shared", {"git_provider": "gitlab"}, "git_provider"),
        ("shared", {"merge_strategy": "rebase"}, "merge_strategy"),
        ("shared", {"git_provider": "azure"}, "git_provider"),
        ("shared", {"test_command": "a 'b"}, "test_command"),
        ("shared", {"protected_files": ["", "../x"]}, "protected_files"),
        ("shared", {"max_parallel_runs": 0}, "max_parallel_runs"),
        ("shared", {"max_parallel_runs": "2"}, "max_parallel_runs"),
        ("local", {"port": 4800}, "port"),
        ("local", {"port": 0}, "port"),
        ("local", {"port": 4800, "trace_db": "x.db"}, "port"),
        ("local", {"trace_db": ""}, "trace_db"),
    ],
)
def test_invalid_values_are_not_saved(
    client: TestClient, root: Path, section: str, values: dict[str, Any], field: str
) -> None:
    before = {CONFIG: _bytes(root, CONFIG), LOCAL: _bytes(root, LOCAL)}
    body = _post(client, {section: values}, 422)
    assert body["error"]["code"] == "invalid_value"
    issues = body["error"]["issues"]
    assert issues and {i["id"] for i in issues} == {field}
    assert all(i["code"] == "invalid_value" and i["message"] for i in issues)
    assert {CONFIG: _bytes(root, CONFIG), LOCAL: _bytes(root, LOCAL)} == before


def test_nothing_saved_when_one_section_is_invalid(client: TestClient, root: Path) -> None:
    before = _bytes(root, CONFIG)
    body = _post(client, {"shared": {"base": "develop"}, "local": {"port": 0}}, 422)
    assert [i["id"] for i in body["error"]["issues"]] == ["port"]
    assert _bytes(root, CONFIG) == before
    assert _bytes(root, LOCAL) is None


def test_null_removes_a_key(client: TestClient, root: Path) -> None:
    _post(client, {"shared": {"test_command": "make test"}})
    assert "test_command" in yaml.safe_load((root / CONFIG).read_text())
    body = _post(client, {"shared": {"test_command": None}})
    assert body["data"]["shared"]["test_command"] is None
    assert "test_command" not in yaml.safe_load((root / CONFIG).read_text())


@pytest.mark.parametrize(
    "payload",
    [
        {"shared": {"levels": ["a", "b"]}},
        {"foo": {}},
        {"shared": {"port": 4700}},
        {"local": {"base": "main"}},
        {"shared": "base: main"},
        [1, 2],
    ],
)
def test_bad_requests(client: TestClient, root: Path, payload: Any) -> None:
    before = _bytes(root, CONFIG)
    body = _post(client, payload, 400)
    assert body["error"]["code"] == "usage_error"
    assert _bytes(root, CONFIG) == before


def test_invalid_file_on_disk(client: TestClient, root: Path) -> None:
    (root / CONFIG).write_text("base: main\nmerge_strategy: nope\n", encoding="utf-8", newline="\n")
    (root / LOCAL).write_text("trace_db: ''\n", encoding="utf-8", newline="\n")
    data = _get(client, "/api/settings")["data"]
    assert data["shared"]["merge_strategy"] == "nope"
    assert data["shared_issues"]
    assert data["local"]["trace_db"] == ""
    assert data["local_issues"]
    # fixing the value makes the file valid again
    _post(client, {"shared": {"merge_strategy": "merge"}, "local": {"trace_db": "t.db"}})
    data = _get(client, "/api/settings")["data"]
    assert data["shared_issues"] == [] and data["local_issues"] == []


def test_old_local_port_is_ignored_and_kept(client: TestClient, root: Path) -> None:
    (root / LOCAL).write_text("port: 4811\n", encoding="utf-8", newline="\n")
    body = _get(client, "/api/settings")
    assert body["data"]["local"] == {"trace_db": ".factory/trace.db"}
    assert body["data"]["local_issues"] == []
    assert any(w.startswith("local_port_ignored") for w in body["warnings"])
    body = _post(client, {"local": {"trace_db": "var/t.db"}})
    assert body["data"]["local"] == {"trace_db": "var/t.db"}
    assert any(w.startswith("local_port_ignored") for w in body["warnings"])
    # only the sent key changes; the old port line stays for the operator to delete
    assert yaml.safe_load((root / LOCAL).read_text()) == {"port": 4811, "trace_db": "var/t.db"}


def test_unreadable_file_is_not_overwritten(client: TestClient, root: Path) -> None:
    (root / CONFIG).write_text("base: [\n", encoding="utf-8", newline="\n")
    before = _bytes(root, CONFIG)
    body = _post(client, {"shared": {"base": "main"}}, 422)
    assert body["error"]["issues"][0]["id"] is None
    assert _bytes(root, CONFIG) == before


def test_config_status(client: TestClient, root: Path) -> None:
    data = _get(client, "/api/config/status")["data"]
    assert data["clean"] is True and data["changes"] == []
    assert data["base"] == "main"
    (root / ".factory/workflows/new.yaml").write_text(
        "name: new\nsteps: [plan]\n", encoding="utf-8", newline="\n"
    )
    body = _get(client, "/api/config/status")
    data = body["data"]
    assert data["clean"] is False
    assert data["changes"] == [{"path": ".factory/workflows/new.yaml", "status": "untracked"}]
    sha = resolve_commit(root, "main")
    assert data["commit"] == sha
    assert data["changes"] == [c.to_dict() for c in config_changes(root, sha)]
    assert body["warnings"]


def test_config_status_unknown_base(client: TestClient, root: Path) -> None:
    (root / CONFIG).write_text("base: nowhere\n", encoding="utf-8", newline="\n")
    body = _get(client, "/api/config/status", 500)
    assert body["error"]["code"] == "invalid_config"


def test_save_max_parallel_runs(client: TestClient, root: Path) -> None:
    body = _post(client, {"shared": {"max_parallel_runs": 3}})
    assert body["data"]["shared"]["max_parallel_runs"] == 3
    assert yaml.safe_load((root / CONFIG).read_text())["max_parallel_runs"] == 3


def test_settings_lists_top_level_projects_and_path_origins(client: TestClient) -> None:
    data = _get(client, "/api/settings")["data"]
    projects = {p["id"]: p for p in data["projects"]}
    assert "M01" in projects and "M02" in projects
    assert "M01-S01" not in projects
    assert data["repository"]
    for project in projects.values():
        assert project["parent"] is None
        for key in ("specs_dir", "docs_dir", "workdir"):
            assert project["effective"][key]["value"] == data["shared"][key]
            assert project["effective"][key]["origin"]["path"] == CONFIG


def test_project_settings_save_clear_isolate_and_remain_versionable(
    client: TestClient, root: Path
) -> None:
    before = _get(client, "/api/settings")["data"]
    other = next(p for p in before["projects"] if p["id"] == "M02")
    payload = {
        "specs_dir": "projects/core/specs",
        "docs_dir": "projects/core/docs",
        "workdir": "projects/core",
    }
    response = client.post("/api/backlog/containers/M01/edit", json=payload)
    _check(response, 200)
    data = _get(client, "/api/settings")["data"]
    first = next(p for p in data["projects"] if p["id"] == "M01")
    for key, value in payload.items():
        assert first["own"][key] == value
        assert first["effective"][key]["origin"]["source"] == "own"
    assert next(p for p in data["projects"] if p["id"] == "M02") == other
    assert first["index_path"] in git(root, "ls-files", first["index_path"])
    _check(
        client.post("/api/backlog/containers/M01/edit", json={key: None for key in payload}), 200
    )
    restored = next(
        p for p in _get(client, "/api/settings")["data"]["projects"] if p["id"] == "M01"
    )
    for key in payload:
        assert key not in restored["own"]
        assert restored["effective"][key]["origin"]["source"] == "config"
