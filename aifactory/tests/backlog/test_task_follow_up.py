"""`factory task follow-up` and the `follows` key of a task."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from backlog_repo import M01_S01, T01, rewrite, sample_repo, task_md, write

import aifactory.backlog
import aifactory.cli
import aifactory.run
from aifactory.backlog import check_backlog, load_backlog
from aifactory.cli import main
from cli_json import read_envelope

Capsys = pytest.CaptureFixture[str]


def _repo(root: Path) -> list[str]:
    return ["--repo", str(root)]


def test_follow_up_creates_task_in_same_step(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / T01, "depends_on: []\n", "depends_on: []\nworkflow: custom\nwrites: [src/x/]\n")
    args = ["task", "follow-up", "M01-S01-T01", "--body", "Rozšířit schéma.", "--json"]
    assert main([*args, *_repo(root)]) == 0
    data = read_envelope(capsys)["data"]
    assert data["action"] == "add"
    task = data["task"]
    assert task["id"] == "M01-S01-T03"
    assert task["title"] == "Navazuje na M01-S01-T01: Schema"
    assert task["follows"] == "M01-S01-T01"
    assert task["own_writes"] == ["src/x/"]
    assert task["workflow"] == "custom"
    assert task["status"] == "todo"
    assert data["path"].startswith(f"{M01_S01}/M01-S01-T03-")
    text = (root / data["path"]).read_text(encoding="utf-8")
    assert "follows: M01-S01-T01\n" in text
    assert "## Zadání\nRozšířit schéma.\n" in text
    backlog = load_backlog(root)
    assert check_backlog(backlog) == []

    assert main(["task", "show", "M01-S01-T01", "--json", *_repo(root)]) == 0
    shown = read_envelope(capsys)["data"]
    assert shown["followed_by"] == ["M01-S01-T03"]
    assert shown["task"]["follows"] is None


def test_follow_up_keeps_inherited_writes_and_workflow(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    args = ["task", "follow-up", "M01-S01-T01", "--body", "Dál.", "--title", "Vlastní", "--json"]
    assert main([*args, *_repo(root)]) == 0
    data = read_envelope(capsys)["data"]
    assert data["task"]["title"] == "Vlastní"
    text = (root / data["path"]).read_text(encoding="utf-8")
    assert "writes:" not in text
    assert "workflow:" not in text
    assert data["task"]["workflow"] == "plan-build"
    assert data["task"]["writes"] == ["src/"]


def test_follow_up_refuses_task_not_done(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    args = ["task", "follow-up", "M01-S01-T02", "--body", "x", "--json", *_repo(root)]
    assert main(args) == 2
    env = read_envelope(capsys)
    assert env["ok"] is False
    assert env["error"]["code"] == "not_done"
    assert "only a done task" in env["error"]["message"]
    assert not list((root / M01_S01).glob("M01-S01-T03*"))


def test_follow_up_run_commits_and_runs(
    tmp_path: Path, capsys: Capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = sample_repo(tmp_path)
    calls: list[Any] = []

    def commit(repo: Path, message: str | None = None) -> Any:
        calls.append(("commit", message))
        return SimpleNamespace(
            commit="abcdef0123", base="main", to_json=lambda: {"commit": "abcdef0123"}
        )

    def run_chain(repo: Path, task_id: str, **kwargs: Any) -> str:
        calls.append(("run", task_id))
        return "chain"

    def chain_output(args: Any, start: Any, extra: Any = None) -> int:
        assert start() == "chain"
        calls.append(("extra", extra["task"]["id"], extra["commit"]))
        return 0

    monkeypatch.setattr(aifactory.backlog, "commit_backlog", commit)
    monkeypatch.setattr(aifactory.run, "run_chain", run_chain)
    monkeypatch.setattr(aifactory.cli, "_chain_output", chain_output)
    args = ["task", "follow-up", "M01-S01-T01", "--body", "Dál.", "--run", *_repo(root)]
    assert main(args) == 0
    assert calls == [
        ("commit", "backlog: M01-S01-T03 follows M01-S01-T01"),
        ("run", "M01-S01-T03"),
        ("extra", "M01-S01-T03", {"commit": "abcdef0123"}),
    ]


def test_follows_must_reference_a_task(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    write(root, f"{M01_S01}/M01-S01-T05-x.md", task_md("M01-S01-T05", extra="follows: NOPE\n"))
    write(root, f"{M01_S01}/M01-S01-T06-y.md", task_md("M01-S01-T06", extra="follows: M01\n"))
    write(root, f"{M01_S01}/M01-S01-T07-z.md", task_md("M01-S01-T07", extra="follows: [a]\n"))
    issues = {(i.id, i.code) for i in check_backlog(load_backlog(root))}
    assert ("M01-S01-T05", "unknown_ref") in issues
    assert ("M01-S01-T06", "unknown_ref") in issues
    assert ("M01-S01-T07", "invalid_field") in issues


def test_prompt_names_the_followed_task(tmp_path: Path, capsys: Capsys) -> None:
    from aifactory.backlog import Task
    from aifactory.run.scope import output_paths, task_scope
    from aifactory.run.task import followed_task, task_prompt

    root = sample_repo(tmp_path)
    args = ["task", "follow-up", "M01-S01-T01", "--body", "Dál.", "--json", *_repo(root)]
    assert main(args) == 0
    new_id = read_envelope(capsys)["data"]["task"]["id"]
    backlog = load_backlog(root)
    task = backlog.by_id[new_id]
    assert isinstance(task, Task)
    outputs = output_paths(task, backlog.settings)
    origin = followed_task(backlog, task, backlog.settings)
    assert origin is not None
    prompt = task_prompt(task, task_scope(task, outputs), outputs, root, None, origin)
    spec = output_paths(origin[0], backlog.settings).spec
    assert "- follows: M01-S01-T01 — Schema (done;" in prompt
    assert T01 in prompt and spec in prompt
    original = backlog.by_id["M01-S01-T01"]
    assert isinstance(original, Task)
    assert followed_task(backlog, original, backlog.settings) is None
