"""Taking a new seed into the library after a HAIFA upgrade (HAIFA-S05-T10).

The packaged seed is replaced by a seed in a temporary folder; no model and no network.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from library_tree import WORKFLOW, library_agent, put

from aifactory.library import store
from cli_json import run_json

Capsys = pytest.CaptureFixture[str]


def _git(cwd: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True, encoding="utf-8"
    )
    return out.stdout.strip()


class Env:
    def __init__(self, tmp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.tmp = tmp
        self.mp = monkeypatch
        home = tmp / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("HAIFA_HOME", str(home / ".config" / "haifa"))
        monkeypatch.delenv("HAIFA_LIBRARY", raising=False)
        for kind in ("AUTHOR", "COMMITTER"):
            monkeypatch.setenv(f"GIT_{kind}_NAME", "Ada Tester")
            monkeypatch.setenv(f"GIT_{kind}_EMAIL", "ada@example.com")
        self.lib = home / ".config" / "haifa" / "library"
        self.n = 0

    def seed(self, agents: dict[str, bytes], workflows: dict[str, bytes]) -> None:
        """Install a substitute seed: agents by their system prompt, workflows by content."""
        self.n += 1
        root = self.tmp / f"seed{self.n}"
        for name, system in agents.items():
            library_agent(root, name, system=system)
        for name, data in workflows.items():
            put(root, f"workflows/{name}.yaml", data)
        self.mp.setattr(store, "packaged_seed", lambda: store.read_seed(root, root))

    def file(self, rel: str) -> bytes:
        return (self.lib / rel).read_bytes()

    def meta_seed(self) -> dict[str, str]:
        seed: dict[str, str] = yaml.safe_load(self.file("library.yaml"))["seed"]
        return seed


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    return Env(tmp_path, monkeypatch)


def _ok(capsys: Capsys, argv: list[str]) -> dict[str, Any]:
    rc, obj = run_json(capsys, argv)
    assert rc == 0, obj
    data: dict[str, Any] = obj["data"]
    data["_warnings"] = obj["warnings"]
    return data


def _actions(data: dict[str, Any]) -> dict[str, str]:
    return {f"{i['type']}/{i['name']}": i["action"] for i in data["items"]}


SEED = ["library", "seed", "--json"]
PLAN2 = WORKFLOW.replace(b"Plan the task.", b"Plan the task well.")


def _setup(env: Env, capsys: Capsys) -> None:
    """Library from seed 1, the team changes builder, seed 2 is installed."""
    env.seed({"planner": b"plan v1\n", "builder": b"build v1\n"}, {"plan": WORKFLOW})
    _ok(capsys, ["library", "init", "--json"])
    put(env.lib, "agents/builder/system.md", b"build by the team\n")
    _git(env.lib, "commit", "--quiet", "-am", "team: builder")
    env.seed(
        {"planner": b"plan v2\n", "builder": b"build v2\n"},
        {"plan": WORKFLOW, "build": PLAN2.replace(b"name: plan", b"name: build")},
    )


def test_status_reports_seed_update(env: Env, capsys: Capsys) -> None:
    env.seed({"planner": b"plan v1\n"}, {"plan": WORKFLOW})
    _ok(capsys, ["library", "init", "--json"])
    status = _ok(capsys, ["library", "status", "--json"])
    assert status["seed_update_available"] is False and status["seed_updates"] == []
    env.seed({"planner": b"plan v2\n"}, {"plan": WORKFLOW})
    status = _ok(capsys, ["library", "status", "--json"])
    assert status["seed_update_available"] is True
    assert status["seed_updates"] == ["agent/planner"]
    assert any("seed_update_available" in w for w in status["_warnings"])


def test_seed_adds_replaces_and_keeps_team_change(env: Env, capsys: Capsys) -> None:
    _setup(env, capsys)
    head = _git(env.lib, "rev-parse", "HEAD")

    plan = _ok(capsys, [*SEED, "--dry-run"])
    assert plan["dry_run"] is True and plan["committed"] is False
    assert _git(env.lib, "rev-parse", "HEAD") == head
    assert _actions(plan) == {
        "agent/builder": "kept",
        "agent/planner": "update",
        "workflow/build": "create",
        "workflow/plan": "unchanged",
    }
    kept = next(i for i in plan["items"] if i["action"] == "kept")
    diff = "".join(f["diff"] for f in kept["diff"])
    assert "-build by the team" in diff and "+build v2" in diff

    done = _ok(capsys, SEED)
    assert done["committed"] is True and done["digest"] == plan["digest"]
    assert _git(env.lib, "rev-parse", "HEAD") == done["commit"]
    assert _git(env.lib, "status", "--porcelain") == ""
    assert env.file("agents/planner/system.md") == b"plan v2\n"
    assert env.file("agents/builder/system.md") == b"build by the team\n"
    assert (env.lib / "workflows/build.yaml").is_file()
    assert env.meta_seed() == store.seed_versions(store.packaged_seed())
    status = _ok(capsys, ["library", "status", "--json"])
    assert status["seed_update_available"] is False

    again = _ok(capsys, SEED)
    assert again["committed"] is False and again["files"] == []
    assert _actions(again)["agent/builder"] == "kept"
    assert _git(env.lib, "rev-parse", "HEAD") == done["commit"]


def test_take_replaces_team_change(env: Env, capsys: Capsys) -> None:
    _setup(env, capsys)
    done = _ok(capsys, [*SEED, "--take", "agent/builder"])
    assert done["committed"] is True
    assert _actions(done)["agent/builder"] == "take"
    assert env.file("agents/builder/system.md") == b"build v2\n"
    assert env.file("agents/planner/system.md") == b"plan v2\n"

    again = _ok(capsys, SEED)
    assert again["committed"] is False
    assert set(_actions(again).values()) == {"unchanged"}


def test_take_unknown_item(env: Env, capsys: Capsys) -> None:
    _setup(env, capsys)
    for take, code in (("agent/nope", "not_in_seed"), ("builder", "invalid_value")):
        rc, obj = run_json(capsys, [*SEED, "--take", take])
        assert rc == 2 and obj["error"]["code"] == code
