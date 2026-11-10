"""Read-request snapshots: bounded policy reads and freshly keyed roster counts."""

import shutil
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from backlog_fixture import _task, git, make_backlog_repo
from starlette.testclient import TestClient

from aifactory import repo_settings
from aifactory.check.context import CheckContext
from aifactory.harness.config import SSSFConfig
from aifactory.library.install import init_repo
from aifactory.repo_settings import RepositorySettings
from aifactory.run.errors import TaskRunError
from aifactory.web import backlog, create_app, machine


def _tree_tasks(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        task
        for node in nodes
        for task in (_tree_tasks(node["children"]) if node["kind"] == "container" else [node])
    ]


def test_board_policy_reads_are_constant_with_many_open_prs(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    ids = set()
    for index in range(120):
        task_id = f"M03-S{index // 10:02}-T{index:03}"
        ids.add(task_id)
        directory = root / "backlog" / "M03-many" / f"S{index // 10:02}"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{task_id}-task.md").write_text(_task(task_id, "Task"), encoding="utf-8")
    settings = RepositorySettings(root)
    settings.update({"auto_merge": True})
    blocked, approved = sorted(ids)[:2]
    awaiting = ids - {blocked, approved}
    rt = backlog._Runtime(in_review=ids, merge_blocked={blocked}, approved={approved})
    with (
        patch.object(backlog, "_runtime", return_value=(rt, [])),
        patch.object(backlog, "_merge_policy", wraps=backlog._merge_policy) as policy,
        patch.object(
            repo_settings, "repository_identity", wraps=repo_settings.repository_identity
        ) as identity,
    ):
        data, _ = backlog.backlog_view(root)
        assert policy.call_count == identity.call_count == 1
        assert len(data["tasks"]) == 127
        tree = {task["id"]: task for task in _tree_tasks(data["items"])}
        assert tree == {task["id"]: task for task in data["tasks"]}
        assert data["state_counts"]["awaiting merge"] == 118
        assert tree[blocked]["board_state"] == "in review"
        assert tree[approved]["board_state"] == "approved"
        assert all(tree[task_id]["board_state"] == "awaiting merge" for task_id in awaiting)
        assert all(task["auto_merge_policy"]["value"] for task in data["tasks"])
        filtered, _ = backlog.backlog_view(root, status="awaiting merge")
        assert policy.call_count == identity.call_count == 2
        assert {task["id"] for task in filtered["tasks"]} == awaiting
        assert filtered["state_counts"] == data["state_counts"]
        assert {task["id"] for task in _tree_tasks(filtered["items"])} == awaiting
        assert all(c["effective_auto_merge"] for c in data["items"])
        assert [t["id"] for t in filtered["tasks"]] == [
            t["id"] for t in data["tasks"] if t["board_state"] == "awaiting merge"
        ]
        for container in data["items"]:
            descendants = _tree_tasks(container["children"])
            assert container["state_counts"] == {
                state: sum(t["board_state"] == state for t in descendants)
                for state in backlog.BOARD_STATES
            }


def test_board_snapshot_is_consistent_then_revalidates_next_request(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo", with_trace=True)
    settings = RepositorySettings(root)
    settings.update({"auto_merge": True})
    original = backlog._merge_policy

    def read_then_disable(repo: Path) -> dict[str, Any]:
        result = original(repo)
        settings.update({"auto_merge": False})
        return result

    with patch.object(backlog, "_merge_policy", side_effect=read_then_disable):
        first, _ = backlog.backlog_view(root)
    assert first["state_counts"]["awaiting merge"] == 1
    assert all(t["effective_auto_merge"] for t in first["tasks"])
    second, _ = backlog.backlog_view(root)
    assert second["state_counts"]["awaiting merge"] == 0
    assert all(not t["effective_auto_merge"] for t in second["tasks"])
    settings.path.unlink()
    default, _ = backlog.backlog_view(root)
    assert all(t["auto_merge_policy"]["source"] == "default" for t in default["tasks"])
    assert all(not t["effective_auto_merge"] for t in default["tasks"])


@pytest.mark.parametrize("invalid", ["{", '{"version": 99, "auto_merge": true}'])
def test_bad_settings_after_success_never_reuses_policy(tmp_path: Path, invalid: str) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    settings = RepositorySettings(root)
    settings.update({"auto_merge": True})
    backlog.backlog_view(root)
    settings.path.write_text(invalid, encoding="utf-8")
    with pytest.raises(TaskRunError):
        backlog.backlog_view(root)


def test_summary_counts_archived_projects_without_runtime_or_policy(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    index = root / "backlog/M01-core/index.md"
    index.write_text(
        index.read_text(encoding="utf-8").replace("title: Core", "archived: true\ntitle: Core"),
        encoding="utf-8",
    )
    with (
        patch.object(backlog, "_runtime", side_effect=AssertionError("runtime read")),
        patch.object(backlog, "_merge_policy", side_effect=AssertionError("policy read")),
        TestClient(
            create_app(root, static_dir=tmp_path / "nostatic"), base_url="http://127.0.0.1:4700"
        ) as client,
    ):
        response = client.get("/api/backlog/summary")
        assert response.status_code == 200
        assert response.json()["data"] == {"projects": 2}
    for path in (root / "backlog").iterdir():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    assert backlog.summary(root)[0] == {"projects": 0}
    (root / ".factory/config.yaml").write_text("levels: [invalid", encoding="utf-8")
    with TestClient(
        create_app(root, static_dir=tmp_path / "nostatic"), base_url="http://127.0.0.1:4700"
    ) as client:
        assert client.get("/api/backlog/summary").status_code == 500


def test_roster_cache_follows_config_base_library_and_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "commit", "--allow-empty", "-m", "initial")
    init_repo(root)
    registered = [SimpleNamespace(path=str(root))]
    monkeypatch.setattr(machine, "_registered", lambda home: registered)
    global_state = machine.GlobalState()
    original: Callable[[CheckContext], SSSFConfig | None] = vars(CheckContext)["roster"].func
    reads = []

    def roster(context: CheckContext) -> SSSFConfig | None:
        reads.append(context.main)
        return original(context)

    with patch.object(CheckContext, "roster", new=property(roster)):

        def counts() -> dict[str, int]:
            return machine._harness_repos(tmp_path, None, global_state)

        first = counts()
        assert first["claude"] == 1
        assert len(reads) == 1
        assert counts() == first
        assert len(reads) == 1
        agents = root / ".factory/agents.yaml"
        agents.write_text("defaults:\n  harness: codex\n", encoding="utf-8")
        assert counts()["codex"] == 1
        assert len(reads) == 2
        # A base commit makes the committed roster authoritative.
        git(root, "add", ".factory")
        git(root, "commit", "-m", "install")
        assert counts()["codex"] == 1
        assert len(reads) == 3
        # Change the configured base to the pre-install commit: worktree fallback.
        config = root / ".factory/config.yaml"
        config.write_text(
            config.read_text(encoding="utf-8").replace("base: main", "base: HEAD~1"),
            encoding="utf-8",
        )
        assert counts()["codex"] == 1
        assert len(reads) == 4
        # Library identity/HEAD participates even when probes remain cached.
        library = tmp_path / "library"
        library.mkdir()
        git(library, "init", "-b", "main")
        git(library, "commit", "--allow-empty", "-m", "library")
        monkeypatch.setenv("HAIFA_LIBRARY", str(library))
        assert counts()["codex"] == 0
        assert len(reads) == 5
        git(library, "commit", "--allow-empty", "-m", "advance")
        counts()
        assert len(reads) == 6
        agents.write_text("agents: [invalid", encoding="utf-8")
        assert counts() == {"claude": 0, "codex": 0, "pi": 0}
        registered.clear()
        assert counts() == {"claude": 0, "codex": 0, "pi": 0}
        assert not global_state.roster_counts
