"""``POST /api/backlog/tasks/{id}/follow-up`` and ``follows`` in the task detail."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backlog_fixture import A1, A2, git, make_backlog_repo
from starlette.testclient import TestClient

from aifactory.skill import envelope_problems
from aifactory.web import create_app

BASE = "http://127.0.0.1:4700"


class RecordingLauncher:
    """Records the runs the API starts; nothing is run."""

    def __init__(self) -> None:
        self.started: list[str] = []

    def busy(self) -> bool:
        return False

    def running(self) -> list[Any]:
        return []

    def start(self, repo: Path, task_id: str, **kwargs: Any) -> None:
        self.started.append(task_id)
        return None


def _client(root: Path, tmp_path: Path, launcher: RecordingLauncher) -> TestClient:
    app = create_app(root, static_dir=tmp_path / "nostatic", launcher=launcher)  # type: ignore[arg-type]
    return TestClient(app, base_url=BASE)


def _check(response: Any, status: int) -> Any:
    body = response.json()
    assert envelope_problems(body) == []
    assert response.status_code == status, body
    return body


def test_follow_up_and_detail(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    launcher = RecordingLauncher()
    client = _client(root, tmp_path, launcher)
    url = f"/api/backlog/tasks/{A1}/follow-up"
    data = _check(client.post(url, json={"body": "Rozšířit."}), 200)["data"]
    new = data["task"]
    assert new["follows"] == A1
    assert new["title"] == f"Navazuje na {A1}: Schema"
    assert data["run"] is None and data["commit"] is None
    assert launcher.started == []

    detail = _check(client.get(f"/api/backlog/tasks/{A1}"), 200)["data"]
    assert [f["id"] for f in detail["followed_by"]] == [new["id"]]
    assert detail["follows"] is None
    child = _check(client.get(f"/api/backlog/tasks/{new['id']}"), 200)["data"]
    assert child["follows"]["id"] == A1
    assert child["follows"]["title"] == "Schema"


def test_follow_up_takes_own_writes_and_workflow(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    [original] = list((root / "backlog").rglob(f"{A1}-*.md"))
    text = original.read_text(encoding="utf-8")
    original.write_text(
        text.replace("status: done\n", "status: done\nworkflow: custom\nwrites: [src/x/]\n", 1),
        encoding="utf-8",
        newline="\n",
    )
    client = _client(root, tmp_path, RecordingLauncher())
    data = _check(client.post(f"/api/backlog/tasks/{A1}/follow-up", json={"body": "x"}), 200)[
        "data"
    ]
    assert data["task"]["own_writes"] == ["src/x/"]
    assert data["task"]["writes"] == ["src/x/"]
    assert data["task"]["workflow"] == "custom"
    assert data["task"]["own_workflow"] == "custom"


def test_follow_up_keeps_inherited_workflow_inherited(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    client = _client(root, tmp_path, RecordingLauncher())
    data = _check(client.post(f"/api/backlog/tasks/{A1}/follow-up", json={"body": "x"}), 200)[
        "data"
    ]
    assert data["task"]["workflow"] == "plan-build"
    assert data["task"]["own_workflow"] is None
    assert data["task"]["own_writes"] == []
    text = (root / data["path"]).read_text(encoding="utf-8")
    assert "workflow:" not in text
    assert "writes:" not in text


def test_follow_up_refuses_task_not_done(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    client = _client(root, tmp_path, RecordingLauncher())
    body = _check(client.post(f"/api/backlog/tasks/{A2}/follow-up", json={"body": "x"}), 400)
    assert body["error"]["code"] == "not_done"
    bad = client.post(f"/api/backlog/tasks/{A1}/follow-up", json={"body": "x", "extra": 1})
    assert bad.status_code == 400


def test_follow_up_run_commits_and_starts(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    git(root, "branch", "-M", "main")
    launcher = RecordingLauncher()
    client = _client(root, tmp_path, launcher)
    payload = {"body": "Dál.", "title": "Vlastní", "run": True}
    data = _check(client.post(f"/api/backlog/tasks/{A1}/follow-up", json=payload), 202)["data"]
    new_id = data["task"]["id"]
    assert data["task"]["title"] == "Vlastní"
    assert data["commit"]["committed"] is True
    assert data["pending"] is True
    assert launcher.started == [new_id]
    assert git(root, "status", "--porcelain").strip() == ""
    assert f"follows {A1}" in git(root, "log", "-1", "--format=%s")
