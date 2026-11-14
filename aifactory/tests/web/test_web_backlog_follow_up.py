"""``POST /api/backlog/tasks/{id}/follow-up`` and ``follows`` in the task detail."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from backlog_fixture import A1, A2, git, make_backlog_repo
from starlette.testclient import TestClient

from aifactory.skill import envelope_problems
from aifactory.web import create_app
from cli_json import run_json

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


def _same_original(root: Path) -> None:
    [original] = list((root / "backlog").rglob(f"{A1}-*.md"))
    text = original.read_text(encoding="utf-8")
    original.write_text(
        text.replace("status: done\n", "status: done\nworkflow: custom\nwrites: [src/x/]\n", 1),
        encoding="utf-8",
        newline="\n",
    )


@pytest.mark.parametrize("title", [None, "Vlastní titulek"])
def test_cli_and_endpoint_give_the_same_follow_up(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], title: str | None
) -> None:
    cli_root = make_backlog_repo(tmp_path / "cli")
    web_root = make_backlog_repo(tmp_path / "web")
    for root in (cli_root, web_root):
        _same_original(root)
    argv = ["task", "follow-up", A1, "--body", "Rozšířit.", "--json", "--repo", str(cli_root)]
    if title is not None:
        argv += ["--title", title]
    rc, envelope = run_json(capsys, argv)
    assert rc == 0
    cli = envelope["data"]
    payload: dict[str, Any] = {"body": "Rozšířit."}
    if title is not None:
        payload["title"] = title
    client = _client(web_root, tmp_path, RecordingLauncher())
    web = _check(client.post(f"/api/backlog/tasks/{A1}/follow-up", json=payload), 200)["data"]

    for key in ("action", "changed", "path", "issues"):
        assert web[key] == cli[key], key
    # the dashboard's task carries the CLI's keys plus its board fields
    assert {k: web["task"][k] for k in cli["task"]} == cli["task"]
    assert cli["task"]["follows"] == A1
    assert cli["task"]["own_writes"] == ["src/x/"] and cli["task"]["workflow"] == "custom"
    assert (web_root / web["path"]).read_text(encoding="utf-8") == (
        cli_root / cli["path"]
    ).read_text(encoding="utf-8")


def test_cli_and_endpoint_refuse_a_task_that_is_not_done(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    before = git(root, "status", "--porcelain")
    argv = ["task", "follow-up", A2, "--body", "x", "--json", "--repo", str(root)]
    rc, envelope = run_json(capsys, argv)
    assert rc != 0 and envelope["error"]["code"] == "not_done"
    client = _client(root, tmp_path, RecordingLauncher())
    body = _check(client.post(f"/api/backlog/tasks/{A2}/follow-up", json={"body": "x"}), 400)
    assert body["error"]["code"] == "not_done"
    assert body["error"]["message"] == envelope["error"]["message"]
    assert git(root, "status", "--porcelain") == before


def test_follow_up_repeated_request_reuses_task_and_start(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    git(root, "branch", "-M", "main")
    launcher = RecordingLauncher()
    client = _client(root, tmp_path, launcher)
    payload = {"body": "Retry safe", "run": True, "request_id": "same-request-id-123"}
    url = f"/api/backlog/tasks/{A1}/follow-up"
    first = _check(client.post(url, json=payload), 202)["data"]
    second = _check(client.post(url, json=payload), 202)["data"]
    assert first["task"]["id"] == second["task"]["id"]
    assert launcher.started == [first["task"]["id"]]
    assert second["pending"]
    assert len(_check(client.get(f"/api/backlog/tasks/{A1}"), 200)["data"]["followed_by"]) == 1


@pytest.mark.parametrize("stage", ["commit", "start"])
def test_follow_up_partial_failure_returns_existing_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    from aifactory import backlog as core
    from aifactory.run.errors import TaskRunError

    root = make_backlog_repo(tmp_path / "repo")
    git(root, "branch", "-M", "main")
    launcher = RecordingLauncher()

    def fail(*args: Any, **kwargs: Any) -> None:
        raise TaskRunError("test_failure", "Try again from task detail")

    if stage == "commit":
        monkeypatch.setattr(core, "commit_backlog", fail)
    else:
        monkeypatch.setattr(launcher, "start", fail)
    client = _client(root, tmp_path, launcher)
    payload = {"body": "Retry safe", "run": True, "request_id": "failed-request-123"}
    url = f"/api/backlog/tasks/{A1}/follow-up"
    first = _check(client.post(url, json=payload), 202)["data"]
    second = _check(client.post(url, json=payload), 202)["data"]
    assert first["error"]["code"] == "test_failure"
    assert first["stage"] == stage
    assert second["task"]["id"] == first["task"]["id"]
    assert len(_check(client.get(f"/api/backlog/tasks/{A1}"), 200)["data"]["followed_by"]) == 1


def test_follow_up_with_missing_start_journal_does_not_replay_start(tmp_path: Path) -> None:
    from aifactory import backlog as core

    root = make_backlog_repo(tmp_path / "repo")
    launcher = RecordingLauncher()
    created = core.follow_up_task(root, A1, "Saved before crash", request_id="crashed-request-123")
    client = _client(root, tmp_path, launcher)
    data = _check(
        client.post(
            f"/api/backlog/tasks/{A1}/follow-up",
            json={
                "body": "Saved before crash",
                "run": True,
                "request_id": "crashed-request-123",
            },
        ),
        202,
    )["data"]
    assert data["task"]["id"] == created.task.id
    assert data["error"]["code"] == "follow_up_incomplete"
    assert launcher.started == []


def test_follow_up_request_identity_cannot_be_reused_for_different_content(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    client = _client(root, tmp_path, RecordingLauncher())
    url = f"/api/backlog/tasks/{A1}/follow-up"
    _check(client.post(url, json={"body": "First", "request_id": "identity-request-123"}), 200)
    failed = _check(
        client.post(url, json={"body": "Different", "request_id": "identity-request-123"}), 409
    )
    assert failed["error"]["code"] == "edit_conflict"


def test_follow_up_releases_backlog_lock_before_launch(tmp_path: Path) -> None:
    from threading import Event, Thread

    from aifactory import backlog as core

    root = make_backlog_repo(tmp_path / "repo")
    git(root, "branch", "-M", "main")
    completed = Event()

    class ConcurrentLauncher(RecordingLauncher):
        def start(self, repo: Path, task_id: str, **kwargs: Any) -> None:
            def edit_another_task() -> None:
                core.edit_task(repo, A2, title="Concurrent edit")
                completed.set()

            worker = Thread(target=edit_another_task, daemon=True)
            worker.start()
            assert completed.wait(5), "launcher must not hold the backlog mutation lock"
            worker.join(timeout=5)
            super().start(repo, task_id, **kwargs)

    launcher = ConcurrentLauncher()
    client = _client(root, tmp_path, launcher)
    data = _check(
        client.post(
            f"/api/backlog/tasks/{A1}/follow-up",
            json={
                "body": "Follow up",
                "run": True,
                "request_id": "separate-lock-123",
            },
        ),
        202,
    )["data"]
    assert launcher.started == [data["task"]["id"]]
