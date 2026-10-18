"""`just validate-azure-e2e`: preflight, PR evidence, backlog, cleanup; never real Azure."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from aifactory.backlog import Task, load_backlog
from aifactory.config.settings import ProjectSettings
from aifactory.run.queue import auto_continue_enabled, auto_merge_enabled
from validation import azure_e2e

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "providers"))

from az_fake import install_fake_az, reply  # noqa: E402

NAME = "HAIFA-E2E-20261018-120000-abcd"


def _results(tmp_path: Path) -> dict[str, Any]:
    found = list((tmp_path / "results").rglob("azure-e2e.json"))
    assert len(found) == 1, found
    data: dict[str, Any] = json.loads(found[0].read_text(encoding="utf-8"))
    return data


def test_no_login_stops_before_azure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_az(
        tmp_path,
        monkeypatch,
        {"account show": reply(exit=1, stderr="ERROR: Please run 'az login' to setup account.")},
    )
    code = azure_e2e.main(["--name", NAME, "--results-dir", str(tmp_path / "results")])
    assert code == azure_e2e.EXIT_SETUP
    assert not any(argv[:2] == ["repos", "create"] for argv in log.argvs())
    assert not (tmp_path / "results").exists()


def test_missing_extension_stops(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_az(tmp_path, monkeypatch, {"extension show": reply(exit=1, stderr="not found")})
    assert azure_e2e.main(["--name", NAME]) == azure_e2e.EXIT_SETUP


@pytest.mark.parametrize("name", ["NEO_HEF", "HAIFA-Azure-Sandbox", "other"])
def test_refuses_a_name_outside_the_prefix(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = install_fake_az(tmp_path, monkeypatch)
    assert azure_e2e.main(["--name", name]) == azure_e2e.EXIT_SETUP
    assert log.argvs() == []


def test_default_name_is_unique_with_the_prefix() -> None:
    import datetime

    when = datetime.datetime(2026, 10, 18, 12, 0, 0)
    name = azure_e2e.repo_name(when)
    assert name.startswith("HAIFA-E2E-20261018-120000-")
    assert len(name) == len("HAIFA-E2E-20261018-120000-") + 4


def test_cleanup_runs_after_a_failed_step(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_az(
        tmp_path,
        monkeypatch,
        {
            "repos list": reply([{"id": "other", "name": "NEO_HEF"}]),
            "repos policy show": reply(exit=1, stderr="policy 5 not found"),
        },
    )
    seen: dict[str, Path] = {}

    def failing(e2e: azure_e2e.E2E) -> None:
        seen["workdir"] = e2e.workdir
        e2e.repo_id, e2e.policy_ids = "repo-1", [5]
        e2e.report.step("create_repo", True)
        raise RuntimeError("boom")

    code = azure_e2e.main(
        ["--name", NAME, "--results-dir", str(tmp_path / "results")], steps=failing
    )

    assert code == azure_e2e.EXIT_FAILED
    data = _results(tmp_path)
    assert data["outcome"] == "failed"
    assert data["steps"][-1]["name"] == "exception" and "boom" in data["steps"][-1]["detail"]
    cleanup = {s["name"]: s["ok"] for s in data["cleanup"]["steps"]}
    assert cleanup == {
        "delete_policy_5": True,
        "delete_repo": True,
        "purge_recycle_bin": True,
        "repo_gone": True,
        "policy_5_gone": True,
        "local_workdir": True,
    }
    assert data["cleanup"]["ok"] is True
    argvs = log.argvs()
    assert any(a[:4] == ["repos", "delete", "--id", "repo-1"] for a in argvs)
    assert any(a[:5] == ["repos", "policy", "delete", "--id", "5"] for a in argvs)
    purge = next(a for a in argvs if a[:2] == ["devops", "invoke"])
    assert "repositoryId=repo-1" in purge and "DELETE" in purge
    assert not seen["workdir"].exists()


def test_cleanup_fails_when_the_repo_is_still_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fake_az(
        tmp_path,
        monkeypatch,
        {
            "repos delete": reply(exit=1, stderr="ERROR: access denied"),
            "repos list": reply([{"id": "repo-1", "name": NAME}]),
        },
    )

    def created(e2e: azure_e2e.E2E) -> None:
        e2e.repo_id = "repo-1"
        e2e.report.step("create_repo", True)

    code = azure_e2e.main(
        ["--name", NAME, "--results-dir", str(tmp_path / "results")], steps=created
    )

    assert code == azure_e2e.EXIT_FAILED
    data = _results(tmp_path)
    cleanup = {s["name"]: s for s in data["cleanup"]["steps"]}
    assert cleanup["delete_repo"]["ok"] is False
    assert "access denied" in cleanup["delete_repo"]["detail"]
    assert cleanup["repo_gone"]["ok"] is False
    assert data["outcome"] == "failed"


def _pr(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "pullRequestId": 3,
        "status": "completed",
        "sourceRefName": "refs/heads/factory-init/1",
        "targetRefName": "refs/heads/main",
        "createdBy": {"id": "me", "uniqueName": "me@example.com"},
        "reviewers": [{"id": "me", "uniqueName": "me@example.com", "vote": 10}],
        "completionOptions": {"squashMerge": True},
        "lastMergeSourceCommit": {"commitId": "a" * 40},
        "lastMergeCommit": {"commitId": "b" * 40},
    }
    data.update(overrides)
    return data


def test_pr_evidence_of_a_self_approved_merge() -> None:
    ev = azure_e2e.pr_evidence(_pr())
    assert ev["source_branch"] == "factory-init/1"
    assert ev["creator_approved"] is True and ev["bypass_policy"] is False
    assert ev["merge_sha"] == "b" * 40
    ok, detail = azure_e2e.pr_accepted(ev)
    assert ok, detail
    assert "me@example.com=10" in detail


@pytest.mark.parametrize(
    "overrides",
    [
        {"completionOptions": {"bypassPolicy": True}},
        {"reviewers": [{"id": "me", "vote": 0}]},
        {"reviewers": [{"id": "someone-else", "vote": 10}]},
        {"status": "active"},
        {"targetRefName": "refs/heads/dev"},
    ],
)
def test_pr_not_accepted(overrides: dict[str, Any]) -> None:
    ok, _detail = azure_e2e.pr_accepted(azure_e2e.pr_evidence(_pr(**overrides)))
    assert not ok


def test_backlog_has_two_dependent_auto_tasks(tmp_path: Path) -> None:
    for rel, text in azure_e2e.backlog_files("factory").items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    backlog = load_backlog(tmp_path, ProjectSettings())
    first, second = (backlog.by_id[t[0]] for t in azure_e2e.TASKS)
    assert isinstance(first, Task) and isinstance(second, Task)
    assert list(second.depends_on) == [first.id]
    for task in (first, second):
        assert auto_continue_enabled(task) and auto_merge_enabled(task)
    rel = azure_e2e.task_path("factory", second.id)
    assert rel.endswith(f"/{second.id}-second.md")


def test_fake_script_builds_and_approves_each_task() -> None:
    script = azure_e2e.fake_script()
    builds, reviews = script["agents"]["builder"], script["agents"]["reviewer"]
    assert len(builds) == len(reviews) == len(azure_e2e.TASKS)
    assert all(r["envelope"]["approved"] is True for r in reviews)
    assert [b["edits"][0]["path"] for b in builds] == [t[3] for t in azure_e2e.TASKS]


@pytest.mark.parametrize(
    ("code", "stdout", "gone"),
    [
        (1, "", True),
        (0, json.dumps({"id": 5, "isDeleted": True}), True),
        (0, json.dumps({"id": 5, "isDeleted": False}), False),
        (0, "not json", False),
    ],
)
def test_policy_gone(code: int, stdout: str, gone: bool) -> None:
    import subprocess

    proc = subprocess.CompletedProcess(["az"], code, stdout, "")
    assert azure_e2e.policy_gone(proc)[0] is gone
