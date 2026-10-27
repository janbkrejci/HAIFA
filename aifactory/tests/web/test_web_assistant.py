"""The dashboard guide (``web/assistant.py``, ``web/assistant_gate.py``) with a fake harness."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from multi_repo import BASE, git, init_repo, install, multi_client, register, write
from starlette.testclient import TestClient

from aifactory.engine import agent_cc
from aifactory.engine.data_types import AgentResult
from aifactory.home import haifa_home
from aifactory.web import assistant_gate as gate

SECRET = "s3cr3t-value-0042"
HOME_SECRET = "home-secret-9876"
ENV_SECRET = "ghp_environmentsecret123"

Fake = Callable[..., AgentResult]


def machine_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from aifactory.harness import settings

    monkeypatch.setattr("aifactory.harness.settings.shutil.which", lambda name: f"/bin/{name}")
    value = settings.HarnessSettings(
        default_harness="claude",
        harnesses={
            "claude": settings.HarnessChoice(model="sonnet", thinking="medium"),
            "codex": settings.HarnessChoice(model="gpt-5.5"),
            "pi": settings.HarnessChoice(enabled=False),
        },
    )
    home = haifa_home()
    home.mkdir(parents=True, exist_ok=True)
    (home / settings.FILE).write_text(value.model_dump_json())


@pytest.fixture
def setup(tmp_path: Path) -> tuple[TestClient, Path, str]:
    repo = init_repo(tmp_path / "alpha")
    install(repo)
    client = multi_client(haifa_home(), tmp_path)
    repo_id = register(client, repo)["id"]
    return client, repo, repo_id


def fake_harness(
    monkeypatch: pytest.MonkeyPatch, act: Callable[[Any], str] | None = None
) -> list[Any]:
    """claude's adapter replaced: records every request, ``act`` plays the agent."""
    seen: list[Any] = []

    def run(request: Any, **kwargs: Any) -> AgentResult:
        seen.append(request)
        on_event = kwargs.get("on_event")
        text = act(request) if act else f"answer {len(seen)}"
        if on_event:
            block = {"type": "text", "text": text}
            on_event({"type": "assistant", "message": {"content": [block]}})
        return AgentResult(text=text, returncode=0, tokens=10, cost=0.01)

    monkeypatch.setattr(agent_cc, "run", run)
    return seen


def new_thread(client: TestClient) -> str:
    response = client.post("/api/assistant/threads", json={})
    assert response.status_code == 201, response.text
    thread_id: str = response.json()["data"]["id"]
    return thread_id


def ask(client: TestClient, thread_id: str, text: str, **extra: Any) -> dict[str, Any]:
    response = client.post(
        f"/api/assistant/threads/{thread_id}/messages", json={"text": text, **extra}
    )
    assert response.status_code == 202, response.text
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        data: dict[str, Any] = client.get(f"/api/assistant/threads/{thread_id}").json()["data"]
        if not data["busy"]:
            return data
        time.sleep(0.05)
    raise AssertionError("the guide did not answer")


def test_second_message_continues_the_session(
    setup: tuple[TestClient, Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, repo, repo_id = setup
    machine_settings(monkeypatch)
    seen = fake_harness(monkeypatch)
    thread_id = new_thread(client)
    first = ask(client, thread_id, "Co běží?")
    second = ask(client, thread_id, "A co čeká na review?")

    assert [m["role"] for m in second["messages"]] == ["user", "assistant"] * 2
    assert first["messages"][1]["text"] == "answer 1"
    assert second["messages"][3]["text"] == "answer 2"
    one, two = seen
    assert one.session_id == two.session_id == f"guide-{thread_id}"
    assert one.session_dir == two.session_dir
    assert one.model == two.model == "sonnet"
    # The context goes with the first message of the session only.
    assert "# HAIFA skill" in one.prompt and "# HAIFA skill" not in two.prompt
    assert "A co čeká na review?" in two.prompt
    assert repo_id in one.system_prompt and str(repo) in one.system_prompt
    # Read-only: the guide command only, in a directory outside every repository.
    assert one.allowed_commands == ["./guide", "./guide *"]
    assert not Path(one.cwd).resolve().is_relative_to(repo)
    assert (Path(one.cwd) / "guide").is_file()
    listed = client.get("/api/assistant/threads").json()["data"]["threads"]
    assert [t["id"] for t in listed] == [thread_id]
    assert listed[0]["title"] == "Co běží?"


def test_thread_without_settings_uses_the_guide_agent(
    setup: tuple[TestClient, Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _repo, _repo_id = setup
    seen = fake_harness(monkeypatch)
    thread_id = new_thread(client)
    data = ask(client, thread_id, "Ahoj")
    assert data["harness"] == "claude"
    assert seen[0].model == "claude-opus-5-5"
    assert "# Guide Agent" in seen[0].system_prompt


def test_commands_outside_the_allowlist_are_refused(setup: tuple[TestClient, Path, str]) -> None:
    _client, _repo, repo_id = setup
    for command in (
        ["task", "run", "P01-S01-T01"],
        ["task", "approve", "P01-S01-T01"],
        ["config", "set", "base", "x"],
        ["backlog", "commit"],
        ["library", "import", "x"],
        ["init"],
    ):
        code, out = gate.execute(["factory", repo_id, *command])
        assert code == 2, command
        assert json.loads(out)["error"]["code"] == "refused"
    for argv in (
        ["factory", repo_id, "task", "list", "--repo", "/tmp"],
        ["factory", repo_id, "config", "show", "--base", ".env"],
        ["factory", "unknown", "task", "list"],
        ["factory", "-", "task", "list"],
        ["shell", "rm", "-rf", "/"],
    ):
        assert gate.execute(argv)[0] == 2, argv
    for allowed in gate.ALLOWED:
        assert gate.check_command([*allowed, "X"]) == allowed


def test_workflow_show_and_repos(setup: tuple[TestClient, Path, str]) -> None:
    _client, repo, repo_id = setup
    code, out = gate.execute(["repos"])
    assert code == 0
    assert json.loads(out)["data"] == [{"id": repo_id, "path": str(repo)}]
    code, out = gate.execute(["factory", repo_id, "workflow", "show", "build"])
    assert code == 0
    assert json.loads(out)["data"]["source"] == "package"
    assert gate.execute(["factory", repo_id, "workflow", "show", "../x"])[0] == 2


def test_sql_reads_only(setup: tuple[TestClient, Path, str]) -> None:
    _client, repo, repo_id = setup
    db = repo / ".factory/trace.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE task_runs (run_id TEXT, status TEXT)")
        conn.execute("INSERT INTO task_runs VALUES ('r1', 'running')")
    conn.close()
    code, out = gate.execute(["sql", repo_id, "SELECT run_id, status FROM task_runs"])
    assert code == 0
    assert json.loads(out)["data"]["rows"] == [["r1", "running"]]
    for query in (
        "DELETE FROM task_runs",
        "UPDATE task_runs SET status = 'x'",
        "INSERT INTO task_runs VALUES ('r2', 'x')",
        "DROP TABLE task_runs",
        "PRAGMA journal_mode = DELETE",
        f"ATTACH DATABASE '{repo / 'other.db'}' AS other",
        "SELECT 1; DELETE FROM task_runs",
    ):
        assert gate.execute(["sql", repo_id, query])[0] == 2, query
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT * FROM task_runs").fetchall() == [("r1", "running")]
    conn.close()
    assert not (repo / "other.db").exists()


def test_concurrent_edits_are_reported_without_rolling_them_back(
    setup: tuple[TestClient, Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, repo, _repo_id = setup
    head_before = git(repo, "rev-parse", "HEAD")

    def act(request: Any) -> str:
        def edit() -> None:
            (repo / "README.md").write_text("concurrent edit\n", encoding="utf-8")
            (repo / "new.txt").write_text("new\n", encoding="utf-8")

        editor = threading.Thread(target=edit)
        editor.start()
        editor.join()
        return "hotovo"

    fake_harness(monkeypatch, act)
    thread_id = new_thread(client)
    data = ask(client, thread_id, "Uprav README")
    answer = data["messages"][-1]
    assert "error" in answer
    assert "README.md" in answer["error"]
    assert "Změny byly zachovány" in answer["error"]
    assert (repo / "README.md").read_text(encoding="utf-8") == "concurrent edit\n"
    assert (repo / "new.txt").read_text(encoding="utf-8") == "new\n"
    assert git(repo, "rev-parse", "HEAD") == head_before


def test_repo_thread_limits_context_commands_and_observation_to_its_repo(
    setup: tuple[TestClient, Path, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aifactory.web.assistant import AssistantManager

    client, repo, repo_id = setup
    other = init_repo(tmp_path / "beta")
    install(other)
    other_id = register(client, other)["id"]
    response = client.post("/api/assistant/threads", json={"screen": {"repo": repo_id}})
    thread_id = response.json()["data"]["id"]

    def act(request: Any) -> str:
        assert str(repo) in request.system_prompt
        assert str(other) not in request.system_prompt

        def command(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ["bash", str(Path(request.cwd) / "guide"), *args],
                cwd=request.cwd,
                capture_output=True,
                text=True,
                check=False,
            )

        listed = command("repos")
        assert listed.returncode == 0, listed.stderr
        assert json.loads(listed.stdout)["data"] == [{"id": repo_id, "path": str(repo)}]
        assert command("factory", other_id, "workflow", "show", "build").returncode == 2
        assert command("sql", other_id, "SELECT 1").returncode == 2
        assert command("factory", repo_id, "workflow", "show", "build").returncode == 0
        # Work outside this thread's repository must not fail the answer or be reverted.
        (other / "README.md").write_text("another editor\n", encoding="utf-8")
        return "hotovo"

    fake_harness(monkeypatch, act)
    data = ask(client, thread_id, "Co běží?")
    assert data["messages"][-1]["text"] == "hotovo", data["messages"][-1]
    assert "error" not in data["messages"][-1]
    assert (other / "README.md").read_text(encoding="utf-8") == "another editor\n"
    restarted = AssistantManager(haifa_home(), lambda: [(repo_id, repo), (other_id, other)])
    assert restarted.get(thread_id)["repo_id"] == repo_id
    restarted.close()
    rejected = client.post(
        f"/api/assistant/threads/{thread_id}/messages",
        json={"text": "Jiné repo", "screen": {"repo": other_id}},
    )
    assert rejected.status_code == 400


def test_dashboard_thread_sees_all_registered_repositories(
    setup: tuple[TestClient, Path, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, repo, repo_id = setup
    other = init_repo(tmp_path / "beta")
    install(other)
    other_id = register(client, other)["id"]
    seen = fake_harness(monkeypatch)
    thread_id = new_thread(client)
    data = ask(client, thread_id, "Co běží?", screen={"repo": repo_id})
    assert data["repo_id"] is None
    assert str(repo) in seen[0].system_prompt and str(other) in seen[0].system_prompt
    result = subprocess.run(
        ["bash", str(Path(seen[0].cwd) / "guide"), "repos"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert {r["id"] for r in json.loads(result.stdout)["data"]} == {repo_id, other_id}


def test_legacy_repo_thread_drops_its_global_session(
    setup: tuple[TestClient, Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from aifactory.web.assistant import AssistantManager

    client, repo, repo_id = setup
    fake_harness(monkeypatch)
    thread_id = new_thread(client)
    ask(client, thread_id, "Co běží?", screen={"repo": repo_id})
    path = haifa_home() / "assistant" / "threads" / thread_id / "thread.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    stored.pop("repo_id")
    path.write_text(json.dumps(stored), encoding="utf-8")
    restarted = AssistantManager(haifa_home(), lambda: [(repo_id, repo)])
    assert restarted.get(thread_id)["repo_id"] == repo_id
    migrated = json.loads(path.read_text(encoding="utf-8"))
    assert migrated["session_id"] != stored["session_id"]
    assert migrated["context_sent"] is False
    restarted.close()


def test_secrets_never_reach_the_agent(
    setup: tuple[TestClient, Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, repo, repo_id = setup
    write(repo, ".env", f"API_TOKEN={SECRET}\n")
    (haifa_home() / ".env").write_text(f"OTHER={HOME_SECRET}\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_TOKEN", ENV_SECRET)
    # A workflow that happens to contain the secret: the gate's output is redacted.
    write(repo, ".factory/workflows/leaky.yaml", f"# {SECRET} {ENV_SECRET}\nsteps: []\n")
    outputs: list[str] = []

    def act(request: Any) -> str:
        outputs.append(gate.execute(["factory", repo_id, "workflow", "show", "leaky"])[1])
        outputs.append(gate.execute(["factory", repo_id, "config", "show", ".env"])[1])
        return f"the token is {SECRET}"

    seen = fake_harness(monkeypatch, act)
    thread_id = new_thread(client)
    data = ask(client, thread_id, f"Co je {SECRET}?", screen={"repo": repo_id})
    sent = " ".join([seen[0].system_prompt, seen[0].prompt, *outputs])
    for value in (SECRET, HOME_SECRET, ENV_SECRET):
        assert value not in sent
    assert gate.REDACTED in outputs[0]
    assert "refused" in outputs[1]
    assert SECRET not in data["messages"][-1]["text"]


def test_screen_context_reaches_the_prompt(
    setup: tuple[TestClient, Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, repo, repo_id = setup
    seen = fake_harness(monkeypatch)
    thread_id = new_thread(client)
    screen = {"repo": repo_id, "task": "P01-S01-T01", "run": "run-1234"}
    data = ask(client, thread_id, "Proč tento běh selhal?", screen=screen)
    prompt = seen[0].prompt
    assert "Screen the user is looking at" in prompt
    assert f"`{repo_id}` ({repo})" in prompt
    assert "`P01-S01-T01`" in prompt and "`run-1234`" in prompt
    assert data["messages"][0]["screen"] == screen
    bad = client.post(
        f"/api/assistant/threads/{thread_id}/messages",
        json={"text": "x", "screen": {"file": "/etc/passwd"}},
    )
    assert bad.status_code == 400


def test_stream_and_request_guard(
    setup: tuple[TestClient, Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _repo, _repo_id = setup
    fake_harness(monkeypatch)
    thread_id = new_thread(client)
    ask(client, thread_id, "Ahoj")
    with client.stream("GET", f"/api/assistant/threads/{thread_id}/stream") as response:
        body = "".join(response.iter_text())
    kinds = [line.split(": ", 1)[1] for line in body.splitlines() if line.startswith("event:")]
    assert kinds == ["start", "text", "done", "idle"]
    # Writes go through the dashboard's write guard.
    assert (
        client.post(
            "/api/assistant/threads", json={}, headers={"Origin": "http://evil.example"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/assistant/threads/{thread_id}/messages",
            content="text=x",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ).status_code
        == 415
    )
    assert client.get("/api/assistant/threads/nothread").status_code == 404
    assert BASE.startswith("http://")


@pytest.mark.skipif(sys.platform == "win32", reason="the guide script is a POSIX sh script")
def test_guide_script_runs_the_gate(
    setup: tuple[TestClient, Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _repo, repo_id = setup
    seen = fake_harness(monkeypatch)
    ask(client, new_thread(client), "Ahoj")
    work = Path(seen[0].cwd)
    done = subprocess.run(
        ["./guide", "factory", repo_id, "task", "run", "X"],
        cwd=work,
        capture_output=True,
        text=True,
    )
    assert done.returncode == 2
    assert "not allowed" in done.stdout
    done = subprocess.run(["./guide", "repos"], cwd=work, capture_output=True, text=True)
    assert done.returncode == 0
    assert repo_id in done.stdout


def default_harness_settings(
    monkeypatch: pytest.MonkeyPatch, harness: str, claude_enabled: bool = True
) -> None:
    from aifactory.harness import settings

    monkeypatch.setattr("aifactory.harness.settings.shutil.which", lambda name: f"/bin/{name}")
    value = settings.HarnessSettings(
        default_harness=harness,
        harnesses={
            "claude": settings.HarnessChoice(enabled=claude_enabled, model="sonnet"),
            "codex": settings.HarnessChoice(model="gpt-5.5"),
            "pi": settings.HarnessChoice(model="pi-model"),
        },
    )
    home = haifa_home()
    home.mkdir(parents=True, exist_ok=True)
    (home / settings.FILE).write_text(value.model_dump_json())


def fake_unlimited(monkeypatch: pytest.MonkeyPatch, harness: str) -> list[Any]:
    """The codex or pi adapter replaced: records every request it would run."""
    from aifactory.harness import load

    seen: list[Any] = []

    def run(request: Any, **_kwargs: Any) -> AgentResult:
        seen.append(request)
        return AgentResult(text="unlimited", returncode=0, tokens=1, cost=0.0)

    monkeypatch.setattr(load(harness), "run", run)
    return seen


@pytest.mark.parametrize("harness", ["codex", "pi"])
def test_harness_without_command_limit_falls_back_to_claude(
    setup: tuple[TestClient, Path, str], monkeypatch: pytest.MonkeyPatch, harness: str
) -> None:
    client, _repo, _repo_id = setup
    default_harness_settings(monkeypatch, harness)
    claude = fake_harness(monkeypatch)
    unlimited = fake_unlimited(monkeypatch, harness)
    thread_id = new_thread(client)
    data = ask(client, thread_id, "Ahoj")
    assert data["harness"] == "claude"
    assert data["messages"][1]["text"] == "answer 1"
    assert not unlimited
    assert claude[0].model == "sonnet"
    assert claude[0].allowed_commands == ["./guide", "./guide *"]


@pytest.mark.parametrize("harness", ["codex", "pi"])
def test_harness_without_command_limit_is_refused_without_claude(
    setup: tuple[TestClient, Path, str], monkeypatch: pytest.MonkeyPatch, harness: str
) -> None:
    client, _repo, _repo_id = setup
    default_harness_settings(monkeypatch, harness, claude_enabled=False)
    unlimited = fake_unlimited(monkeypatch, harness)
    response = client.post("/api/assistant/threads", json={})
    assert response.status_code == 409, response.text
    error = response.json()["error"]
    assert error["code"] == "harness_unavailable"
    assert harness in error["message"] and "claude" in error["message"]
    assert not unlimited


@pytest.mark.parametrize("harness", ["codex", "pi"])
def test_thread_stored_on_unlimited_harness_is_refused(
    setup: tuple[TestClient, Path, str], monkeypatch: pytest.MonkeyPatch, harness: str
) -> None:
    client, _repo, _repo_id = setup
    machine_settings(monkeypatch)
    fake_harness(monkeypatch)
    unlimited = fake_unlimited(monkeypatch, harness)
    thread_id = new_thread(client)
    # A thread created before the guide refused codex and pi.
    client.app.state.assistant.threads[thread_id].harness = harness  # type: ignore[attr-defined]
    answer = ask(client, thread_id, "Ahoj")["messages"][1]
    assert "cannot run on " + harness in answer["error"]
    assert not unlimited


TASK_FILE = "backlog/P01/S01/P01-S01-T01-first.md"


def with_task(repo: Path) -> None:
    write(repo, "backlog/P01/index.md", "---\nid: P01\ntitle: Project\n---\n")
    write(repo, "backlog/P01/S01/index.md", "---\nid: P01-S01\ntitle: Step\n---\n")
    write(repo, TASK_FILE, "---\nid: P01-S01-T01\ntitle: First\nstatus: todo\n---\nBody\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "backlog")


def proposal(**fields: Any) -> str:
    return "```haifa-action\n" + json.dumps(fields) + "\n```"


def test_proposed_actions_write_nothing_until_confirmed(
    setup: tuple[TestClient, Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, repo, repo_id = setup
    with_task(repo)
    status_before = git(repo, "status", "--porcelain")
    head_before = git(repo, "rev-parse", "HEAD")
    task_before = (repo / TASK_FILE).read_text(encoding="utf-8")

    def act(request: Any) -> str:
        return "\n\n".join(
            [
                "Navrhuji:",
                proposal(
                    kind="edit_task",
                    repo=repo_id,
                    task="P01-S01-T01",
                    writes=["src/"],
                    reason="Task píše do src.",
                ),
                proposal(kind="cancel_task", repo=repo_id, task="P01-S01-T01"),
                proposal(kind="delete_repo", repo=repo_id),
                proposal(kind="run_task", repo="nope", task="P01-S01-T01"),
                "Potvrď kartu.",
            ]
        )

    seen = fake_harness(monkeypatch, act)
    thread_id = new_thread(client)
    data = ask(client, thread_id, "Uprav writes")
    answer = data["messages"][-1]
    edit, cancel = answer["actions"]
    assert edit["kind"] == "edit_task" and edit["writes"] == ["src/"]
    assert edit["reason"] == "Task píše do src."
    assert {edit["status"], cancel["status"]} == {"proposed"}
    assert "haifa-action" not in answer["text"]
    assert "Navrhuji:" in answer["text"] and "Potvrď kartu." in answer["text"]
    assert "unknown kind 'delete_repo'" in answer["text"]
    assert "'nope' is not a registered repository" in answer["text"]
    # Nothing is written without the user's confirmation.
    assert (repo / TASK_FILE).read_text(encoding="utf-8") == task_before
    assert git(repo, "status", "--porcelain") == status_before
    assert git(repo, "rev-parse", "HEAD") == head_before

    # The panel executes a confirmed action through the dashboard's write API...
    url = f"/api/repos/{repo_id}/backlog/tasks/P01-S01-T01/edit"
    response = client.post(url, json={"writes": edit["writes"]})
    assert response.status_code == 200, response.text
    assert "src/" in (repo / TASK_FILE).read_text(encoding="utf-8")
    # ... and records the outcome, which writes nothing to the repository.
    after_edit = (repo / TASK_FILE).read_text(encoding="utf-8")
    actions = f"/api/assistant/threads/{thread_id}/actions"
    recorded = client.post(f"{actions}/{edit['id']}", json={"status": "done", "message": "ok"})
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["data"]["action"]["status"] == "done"
    dismissed = client.post(f"{actions}/{cancel['id']}", json={"status": "dismissed"})
    assert dismissed.status_code == 200, dismissed.text
    assert (repo / TASK_FILE).read_text(encoding="utf-8") == after_edit
    again = client.post(f"{actions}/{edit['id']}", json={"status": "done"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "action_decided"
    assert client.post(f"{actions}/000000000000", json={"status": "done"}).status_code == 404
    bad = client.post(f"{actions}/{edit['id']}", json={"status": "proposed"})
    assert bad.status_code == 400

    thread = client.get(f"/api/assistant/threads/{thread_id}").json()["data"]
    roles = [m["role"] for m in thread["messages"]]
    assert roles == ["user", "assistant", "action", "action"]
    assert [a["status"] for a in thread["messages"][1]["actions"]] == ["done", "dismissed"]
    # The outcomes go to the agent with the next message, once.
    ask(client, thread_id, "Díky")
    assert "Outcome of your proposed actions" in seen[1].prompt
    assert "edit_task P01-S01-T01 in " + repo_id + ": executed: ok" in seen[1].prompt
    assert "cancel_task P01-S01-T01 in " + repo_id + ": dismissed" in seen[1].prompt
    ask(client, thread_id, "A dál?")
    assert "Outcome of your proposed actions" not in seen[2].prompt


def test_follow_up_proposal_writes_nothing_until_confirmed(
    setup: tuple[TestClient, Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, repo, repo_id = setup
    with_task(repo)
    done = (repo / TASK_FILE).read_text(encoding="utf-8").replace("status: todo", "status: done")
    write(repo, TASK_FILE, done)
    git(repo, "commit", "-qam", "done")
    status_before = git(repo, "status", "--porcelain")
    head_before = git(repo, "rev-parse", "HEAD")
    files_before = sorted(p.name for p in (repo / "backlog").rglob("*.md"))

    def act(request: Any) -> str:
        block = proposal(
            kind="follow_up", repo=repo_id, task="P01-S01-T01", body="Dodělat.", run=False
        )
        return "Navrhuji navázat:\n\n" + block

    fake_harness(monkeypatch, act)
    thread_id = new_thread(client)
    [action] = ask(client, thread_id, "Naváž")["messages"][-1]["actions"]
    assert action["kind"] == "follow_up" and action["status"] == "proposed"
    assert action["task"] == "P01-S01-T01" and action["body"] == "Dodělat."
    assert action["run"] is False and "title" not in action
    # Nothing is written without the user's confirmation.
    assert sorted(p.name for p in (repo / "backlog").rglob("*.md")) == files_before
    assert git(repo, "status", "--porcelain") == status_before
    assert git(repo, "rev-parse", "HEAD") == head_before

    # Confirmed, the panel calls the dashboard's follow-up endpoint.
    url = f"/api/repos/{repo_id}/backlog/tasks/P01-S01-T01/follow-up"
    response = client.post(url, json={"body": action["body"], "run": action["run"]})
    assert response.status_code == 200, response.text
    created = response.json()["data"]["task"]
    assert created["follows"] == "P01-S01-T01"
    assert created["title"] == "Navazuje na P01-S01-T01: First"
    actions = f"/api/assistant/threads/{thread_id}/actions"
    recorded = client.post(f"{actions}/{action['id']}", json={"status": "done", "message": "ok"})
    assert recorded.status_code == 200, recorded.text


def test_parse_actions_validates_fields() -> None:
    from aifactory.web.assistant import parse_actions

    text, actions = parse_actions(
        "a\n" + proposal(kind="create_task", repo="r", step="P01-S01", title="T", writes=["x/"]),
        {"r"},
    )
    assert text == "a" and actions[0]["kind"] == "create_task"
    for bad in (
        proposal(kind="edit_task", repo="r", task="T1"),
        proposal(kind="run_task", repo="r"),
        proposal(kind="approve_pr", repo="r", task="T1", extra=1),
        proposal(kind="create_task", repo="r", step="S", title="T", writes="src/"),
        proposal(kind="follow_up", repo="r", task="T1"),
        proposal(kind="follow_up", repo="r", task="T1", body="x", run="yes"),
        proposal(kind="follow_up", repo="r", task="T1", body="x", writes=["src/"]),
        "```haifa-action\nnot json\n```",
    ):
        text, actions = parse_actions(bad, {"r"})
        assert actions == [] and text.startswith("> Návrh akce nejde nabídnout")


def test_delete_removes_the_thread_for_good(
    setup: tuple[TestClient, Path, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, _repo, _repo_id = setup
    fake_harness(monkeypatch)
    kept = new_thread(client)
    gone = new_thread(client)
    ask(client, gone, "Ahoj")
    folder = haifa_home() / "assistant" / "threads" / gone
    assert (folder / "thread.json").is_file()
    from aifactory.harness.agent_dirs import claude_project_dirs

    monkeypatch.setenv(
        "CLAUDE_CONFIG_DIR", ("\\\\?\\" if os.name == "nt" else "") + str(tmp_path / "claude")
    )
    claude_dirs = claude_project_dirs(folder / "work")
    for path in claude_dirs:
        path.mkdir(parents=True, exist_ok=True)

    # Git objects in the guide's work repo are read-only on Windows. Include one
    # explicitly so deletion keeps covering this even if repo setup changes.
    readonly = folder / "readonly-object"
    readonly.write_bytes(b"object")
    readonly.chmod(0o444)

    # The write guard applies to DELETE as to every other write.
    refused = client.delete(
        f"/api/assistant/threads/{gone}", headers={"Origin": "http://evil.example"}
    )
    assert refused.status_code == 403
    assert folder.is_dir()

    response = client.delete(f"/api/assistant/threads/{gone}")
    assert response.status_code == 200, response.text
    assert response.json()["data"] == {"deleted": gone}
    assert not folder.exists()
    assert all(not path.exists() for path in claude_dirs)
    listed = client.get("/api/assistant/threads").json()["data"]["threads"]
    assert [t["id"] for t in listed] == [kept]
    missing = client.get(f"/api/assistant/threads/{gone}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "unknown_thread"
    # A restarted dashboard reads the threads from disk: the deleted one stays gone.
    restarted = multi_client(haifa_home(), tmp_path)
    listed = restarted.get("/api/assistant/threads").json()["data"]["threads"]
    assert [t["id"] for t in listed] == [kept]
    assert restarted.get(f"/api/assistant/threads/{gone}").status_code == 404

    for unknown in (gone, "nothread", "NOT-a-thread"):
        again = client.delete(f"/api/assistant/threads/{unknown}")
        assert again.status_code == 404
        assert again.json()["error"]["code"] == "unknown_thread"


def test_delete_refuses_a_thread_that_answers(
    setup: tuple[TestClient, Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    client, _repo, _repo_id = setup
    started = threading.Event()
    release = threading.Event()

    def act(_request: Any) -> str:
        started.set()
        release.wait(30)
        return "hotovo"

    fake_harness(monkeypatch, act)
    thread_id = new_thread(client)
    sent = client.post(f"/api/assistant/threads/{thread_id}/messages", json={"text": "Ahoj"})
    assert sent.status_code == 202, sent.text
    assert started.wait(30)
    try:
        response = client.delete(f"/api/assistant/threads/{thread_id}")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "busy"
    finally:
        release.set()
    folder = haifa_home() / "assistant" / "threads" / thread_id
    assert (folder / "thread.json").is_file()
    deadline = time.monotonic() + 60
    while client.get(f"/api/assistant/threads/{thread_id}").json()["data"]["busy"]:
        assert time.monotonic() < deadline, "the guide did not answer"
        time.sleep(0.05)
    assert client.delete(f"/api/assistant/threads/{thread_id}").status_code == 200
    assert not folder.exists()


def project_binding(repo: Path, harness: str = "claude") -> None:
    with_task(repo)
    write(
        repo,
        "backlog/P01/index.md",
        f"---\nid: P01\ntitle: Project\nharness: {harness}\n"
        "model: context-model\nthinking: high\n---\n",
    )


def stored_thread(thread_id: str) -> dict[str, Any]:
    path = haifa_home() / "assistant" / "threads" / thread_id / "thread.json"
    data: dict[str, Any] = json.loads(path.read_text())
    return data


@pytest.mark.parametrize("allow_codex", [True, False])
def test_create_inherits_project_binding_and_applies_guide_limit(
    setup: tuple[TestClient, Path, str], monkeypatch: pytest.MonkeyPatch, allow_codex: bool
) -> None:
    client, repo, repo_id = setup
    machine_settings(monkeypatch)
    project_binding(repo, "codex")
    if allow_codex:
        monkeypatch.setattr("aifactory.web.assistant.GUIDE_HARNESSES", ("claude", "codex"))
    codex = fake_unlimited(monkeypatch, "codex")
    claude = fake_harness(monkeypatch)
    response = client.post(
        "/api/assistant/threads", json={"screen": {"repo": repo_id, "task": "P01-S01-T01"}}
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    thread_id = data["id"]
    expected = ("codex", "context-model", "high") if allow_codex else ("claude", "sonnet", "medium")
    stored = stored_thread(thread_id)
    assert tuple(stored[k] for k in ("harness", "model", "thinking")) == expected
    assert tuple(data[k] for k in ("harness", "model", "thinking")) == expected
    listed = client.get("/api/assistant/threads").json()["data"]["threads"]
    assert listed[0]["id"] == thread_id
    assert listed[0]["thinking"] == stored["thinking"]
    detail = client.get(f"/api/assistant/threads/{thread_id}").json()["data"]
    assert detail["thinking"] == stored["thinking"]
    manager = client.app.state.assistant  # type: ignore[attr-defined]
    assert manager.threads[thread_id].thinking == expected[2]
    ask(client, thread_id, "Ahoj")
    request = (codex if allow_codex else claude)[0]
    assert (request.model, request.thinking) == expected[1:]
    assert not (claude if allow_codex else codex)


@pytest.mark.parametrize("configured", [True, False])
def test_context_binding_survives_messages_and_restart(
    setup: tuple[TestClient, Path, str], monkeypatch: pytest.MonkeyPatch, configured: bool
) -> None:
    from aifactory.web.assistant import AssistantManager

    client, repo, repo_id = setup
    if configured:
        machine_settings(monkeypatch)
    project_binding(repo)
    seen = fake_harness(monkeypatch)
    response = client.post(
        "/api/assistant/threads", json={"screen": {"repo": repo_id, "task": "P01-S01-T01"}}
    )
    assert response.status_code == 201, response.text
    thread_id = response.json()["data"]["id"]
    ask(client, thread_id, "První")
    project = repo / "backlog/P01/index.md"
    project.write_text(project.read_text().replace("context-model", "changed-model"))
    machine_settings(monkeypatch)
    ask(client, thread_id, "Druhá", screen={"repo": repo_id, "task": "other"})
    assert [(r.model, r.thinking) for r in seen] == [("context-model", "high")] * 2
    assert seen[0].session_id == seen[1].session_id
    stored = stored_thread(thread_id)
    assert (stored["model"], stored["thinking"]) == ("context-model", "high")
    restarted = AssistantManager(haifa_home(), lambda: [(repo_id, repo)])
    try:
        assert restarted.get(thread_id)["model"] == "context-model"
        assert restarted.get(thread_id)["thinking"] == stored["thinking"]
        assert restarted.summaries()[0]["thinking"] == stored["thinking"]
        thread = restarted.threads[thread_id]
        assert (thread.harness, thread.thinking, thread.session_id) == (
            "claude",
            "high",
            seen[0].session_id,
        )
    finally:
        restarted.close()


@pytest.mark.parametrize("screen", [None, {}, {"repo": "$repo"}, {"repo": " ", "task": None}])
def test_create_without_task_uses_computer_binding(
    setup: tuple[TestClient, Path, str], monkeypatch: pytest.MonkeyPatch, screen: Any
) -> None:
    client, repo, repo_id = setup
    machine_settings(monkeypatch)
    project_binding(repo, "codex")
    if isinstance(screen, dict):
        screen = {k: repo_id if v == "$repo" else v for k, v in screen.items()}
    response = client.post("/api/assistant/threads", json={"screen": screen})
    assert response.status_code == 201, response.text
    assert response.json()["data"]["model"] == "sonnet"


def run_context(repo: Path) -> Path:
    db = repo / ".factory/trace.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE task_runs (run_id TEXT, task_id TEXT, state TEXT, started_at TEXT, "
            "ended_at TEXT, pid INTEGER, workflow TEXT, error TEXT, harness TEXT, model TEXT)"
        )
        conn.execute(
            "INSERT INTO task_runs VALUES "
            "('r1', 'P01-S01-T01', 'done', '', '', NULL, '', '', 'codex', 'historical-model')"
        )
    conn.close()
    return db


@pytest.mark.parametrize("explicit_task", [False, True])
def test_run_uses_current_task_binding_read_only(
    setup: tuple[TestClient, Path, str], monkeypatch: pytest.MonkeyPatch, explicit_task: bool
) -> None:
    client, repo, repo_id = setup
    machine_settings(monkeypatch)
    project_binding(repo)
    db = run_context(repo)
    before = db.read_bytes()
    screen = {"repo": repo_id, "run": "r1"}
    if explicit_task:
        screen["task"] = "P01-S01-T01"
    response = client.post("/api/assistant/threads", json={"screen": screen})
    assert response.status_code == 201, response.text
    stored = stored_thread(response.json()["data"]["id"])
    assert (stored["harness"], stored["model"], stored["thinking"]) == (
        "claude",
        "context-model",
        "high",
    )
    assert db.read_bytes() == before


@pytest.mark.parametrize(
    "body",
    [
        {"extra": 1},
        *({"screen": v} for v in [False, 0, "", [], True, "repo", 1, ["repo"]]),
        {"screen": {"extra": "x"}},
        {"screen": {"repo": 1}},
        {"screen": {"task": "x" * 201}},
        {"screen": {"run": "x\ny"}},
        {"screen": {"repo": "unknown"}},
        {"screen": {"task": "P01-S01-T01"}},
        {"screen": {"run": "r1"}},
        {"screen": {"repo": "$repo", "task": "unknown"}},
        {"screen": {"repo": "$repo", "run": "unknown"}},
        {"screen": {"repo": "$repo", "task": "other", "run": "r1"}},
        {"screen": {"repo": "$repo", "task": "P01-S01-T01", "run": "unknown"}},
    ],
)
def test_create_rejects_invalid_context_without_creating_thread(
    setup: tuple[TestClient, Path, str], body: dict[str, Any]
) -> None:
    client, repo, repo_id = setup
    with_task(repo)
    run_context(repo)
    body = json.loads(json.dumps(body).replace("$repo", repo_id))
    response = client.post("/api/assistant/threads", json=body)
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "usage_error"
    assert client.get("/api/assistant/threads").json()["data"]["threads"] == []
    root = haifa_home() / "assistant/threads"
    assert not root.exists() or not list(root.iterdir())


def test_run_without_trace_db_does_not_create_it(setup: tuple[TestClient, Path, str]) -> None:
    client, repo, repo_id = setup
    db = repo / ".factory/trace.db"
    assert not db.exists()
    response = client.post(
        "/api/assistant/threads", json={"screen": {"repo": repo_id, "run": "missing"}}
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "usage_error"
    assert not db.exists()


@pytest.mark.parametrize("invalid", ["missing", "duplicate", "config", "trace"])
def test_invalid_repository_context_is_usage_error(
    setup: tuple[TestClient, Path, str], invalid: str
) -> None:
    client, repo, repo_id = setup
    screen = {"repo": repo_id, "task": "P01-S01-T01"}
    if invalid == "duplicate":
        with_task(repo)
        write(repo, TASK_FILE.replace("first", "duplicate"), (repo / TASK_FILE).read_text())
    elif invalid == "config":
        write(repo, ".factory/config.yaml", "invalid: [")
    elif invalid == "trace":
        (repo / ".factory/trace.db").write_bytes(b"invalid database")
        screen = {"repo": repo_id, "run": "r1"}
    response = client.post("/api/assistant/threads", json={"screen": screen})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "usage_error"
    if invalid == "trace":
        assert "not readable" in response.json()["error"]["message"]
    if invalid == "missing":
        assert not (repo / "backlog").exists()
    assert client.get("/api/assistant/threads").json()["data"]["threads"] == []


def test_disabled_context_harness_is_not_silently_replaced(
    setup: tuple[TestClient, Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, repo, repo_id = setup
    machine_settings(monkeypatch)
    project_binding(repo, "pi")
    response = client.post(
        "/api/assistant/threads", json={"screen": {"repo": repo_id, "task": "P01-S01-T01"}}
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "harness_unavailable"
