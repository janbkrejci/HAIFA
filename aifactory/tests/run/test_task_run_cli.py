"""``factory task run`` and the runs in ``factory task show``."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from run_repo import SPEC, T01, Script, fake_env, make_run_repo, ok, write

from aifactory.cli import main
from cli_json import read_envelope

Capsys = pytest.CaptureFixture[str]


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


def test_run_json_success_and_show(repo: Path, script: Script, capsys: Capsys) -> None:
    script.on("planner", lambda wt: write(wt, SPEC, "# spec\n"))
    script.add("planner", ok(artifacts=[SPEC]))
    capsys.readouterr()

    assert main(["task", "run", T01, "--json", "--repo", str(repo)]) == 0

    env = read_envelope(capsys)
    assert env["ok"] is True
    data = env["data"]
    assert data["run"]["state"] == "succeeded"
    assert data["run"]["branch"] == f"factory/{T01}-1"
    run_id = data["run"]["run_id"]

    assert main(["task", "show", T01, "--json", "--repo", str(repo)]) == 0
    shown = read_envelope(capsys)["data"]
    assert [r["run_id"] for r in shown["runs"]] == [run_id]

    assert main(["task", "show", T01, "--repo", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "runs:" in out and run_id in out and "succeeded" in out


def test_run_failure_exits_1(repo: Path, script: Script, capsys: Capsys) -> None:
    script.on("planner", lambda wt: write(wt, "src/other.py", "x\n"))
    script.add("planner", ok())
    capsys.readouterr()

    assert main(["task", "run", T01, "--json", "--repo", str(repo)]) == 1

    env = read_envelope(capsys)
    assert env["ok"] is False
    assert env["error"]["code"] == "run_failed"
    data = env["data"]
    assert data["run"]["state"] == "failed"
    assert "src/other.py" in data["run"]["error"]


def test_run_text_output(repo: Path, script: Script, capsys: Capsys) -> None:
    script.add("planner", ok())
    capsys.readouterr()

    assert main(["task", "run", T01, "--note", "be brief", "--repo", str(repo)]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert any(line.startswith("run ") and " succeeded: branch " in line for line in lines)
    assert "be brief" in script.calls[0].prompt


def test_show_without_runs(repo: Path, capsys: Capsys) -> None:
    assert main(["task", "show", T01, "--repo", str(repo)]) == 0
    assert "no runs" in capsys.readouterr().out
    assert not (repo / ".factory" / "trace.db").exists()


def test_run_error_text(repo: Path, script: Script, capsys: Capsys) -> None:
    assert main(["task", "run", "NOPE", "--repo", str(repo)]) == 2
    assert "unknown_task" in capsys.readouterr().err


def test_run_passes_the_roster_override(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: Capsys
) -> None:
    import aifactory.run as run_pkg

    seen: dict[str, object] = {}

    def fake_chain(root: Path, task_id: str, **kwargs: object) -> object:
        seen.update(kwargs, task_id=task_id)
        raise SystemExit(0)

    monkeypatch.setattr(run_pkg, "run_chain", fake_chain)
    argv = ["task", "run", T01, "--repo", str(repo), "--auto"]
    with pytest.raises(SystemExit):
        main([*argv, "--harness", "codex", "--model", "gpt-5.5", "--thinking", "high"])
    assert seen["agents_override"] == {"harness": "codex", "model": "gpt-5.5", "thinking": "high"}
    assert seen["auto"] is True
    seen.clear()
    with pytest.raises(SystemExit):
        main(argv)
    assert seen["agents_override"] is None
    with pytest.raises(SystemExit):
        main([*argv, "--thinking", "loud"])
