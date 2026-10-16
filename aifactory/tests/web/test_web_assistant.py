"""The dashboard guide (``web/assistant.py``, ``web/assistant_gate.py``) with a fake harness."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
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
            "claude": settings.HarnessChoice(model="sonnet"),
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


def test_a_write_to_a_repo_fails_and_is_undone(
    setup: tuple[TestClient, Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, repo, _repo_id = setup
    status_before = git(repo, "status", "--porcelain")
    head_before = git(repo, "rev-parse", "HEAD")

    def act(request: Any) -> str:
        (repo / "README.md").write_text("changed by the guide\n", encoding="utf-8")
        (repo / "new.txt").write_text("new\n", encoding="utf-8")
        return "hotovo"

    fake_harness(monkeypatch, act)
    thread_id = new_thread(client)
    data = ask(client, thread_id, "Uprav README")
    answer = data["messages"][-1]
    assert "error" in answer
    assert "README.md" in answer["error"]
    assert (repo / "README.md").read_text(encoding="utf-8") == "readme\n"
    assert not (repo / "new.txt").exists()
    assert git(repo, "status", "--porcelain") == status_before
    assert git(repo, "rev-parse", "HEAD") == head_before


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
        "```haifa-action\nnot json\n```",
    ):
        text, actions = parse_actions(bad, {"r"})
        assert actions == [] and text.startswith("> Návrh akce nejde nabídnout")
