"""``factory backlog propose`` with a fake harness: preview, one correction, --apply."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from advice_fixture import git, make_repo
from aifactory.backlog import TaskEditError, check_backlog, load_backlog
from aifactory.cli import main
from aifactory.engine import agents
from aifactory.engine.data_types import AgentResult
from aifactory.harness.check import HarnessStatus
from aifactory.workflow.propose import (
    BacklogProposalOutput,
    Target,
    plan,
    review,
    workflow_catalog,
)

DONE = "\n\nHotovo znamená:\n- testy projdou"


def _task(key: str, title: str, **extra: Any) -> dict[str, Any]:
    return {
        "code": key,
        "title": title,
        "body": f"Udělej {title}.{DONE}",
        "depends_on": [],
        "writes": ["src/"],
        "workflow": "plan",
        **extra,
    }


def new_step(**task_extra: Any) -> dict[str, Any]:
    return {
        "status": "success",
        "summary": "Two tasks for the export.",
        "step": {"code": "S02", "title": "Export", "body": "Export dat do CSV."},
        "tasks": [
            _task("T01", "Model exportu", **{"depends_on": ["P01-S01-T01"], **task_extra}),
            _task("T02", "CLI exportu", depends_on=["T01"]),
        ],
    }


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path / "repo")


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> tuple[list[Any], list[dict[str, Any]]]:
    """The requests the fake harness saw, and the answers it gives in order."""
    seen: list[Any] = []
    answers: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "aifactory.workflow.propose.check_harness",
        lambda name: HarnessStatus(name, "fake", "fake", "1"),
    )

    def run(request: Any, **kwargs: Any) -> AgentResult:
        seen.append(request)
        answer = answers[min(len(seen), len(answers)) - 1]
        return AgentResult(text=json.dumps(answer), returncode=0)

    monkeypatch.setattr(agents.INTERFACES["claude"], "run", run)
    return seen, answers


def _status(repo: Path) -> str:
    return git(repo, "status", "--porcelain", "--untracked-files=all")


def _head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD").strip()


def test_valid_proposal_preview_and_json(
    repo: Path, fake: tuple[list[Any], list[dict[str, Any]]], capsys: pytest.CaptureFixture[str]
) -> None:
    seen, answers = fake
    answers.append(new_step())
    head = _head(repo)
    args = ["backlog", "propose", "Export do CSV", "--project", "P01", "--repo", str(repo)]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "P01-S02 (new) Export" in out
    assert "P01-S02-T01 Model exportu" in out
    assert "P01-S02-T02 CLI exportu" in out
    assert "depends_on: P01-S02-T01" in out
    assert "Hotovo znamená" in out
    assert "--apply" in out
    request = seen[0]
    assert Path(request.cwd) != repo and not Path(request.cwd).exists()
    context, _ = json.JSONDecoder().raw_decode(request.prompt[request.prompt.index("{") :])
    assert context["intent"] == "Export do CSV"
    assert context["target"] == {"kind": "new_step", "project": "P01"}
    assert "plan" in context["workflows"]
    assert context["output_schema"]["title"] == "BacklogProposalOutput"
    assert "Proposer Agent" in request.system_prompt  # the seed prompt

    assert main([*args, "--json"]) == 0
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["ok"] is True
    data = envelope["data"]
    assert data["applied"] is False
    assert data["step"]["id"] == "P01-S02" and data["step"]["new"] is True
    assert [t["id"] for t in data["tasks"]] == ["P01-S02-T01", "P01-S02-T02"]
    assert data["tasks"][0]["depends_on"] == ["P01-S01-T01"]
    assert data["tasks"][1]["depends_on"] == ["P01-S02-T01"]
    assert data["tasks"][0]["workflow"] == "plan"
    # nothing written, nothing committed
    assert _status(repo) == ""
    assert _head(repo) == head


def test_invalid_proposal_is_corrected_once(
    repo: Path, fake: tuple[list[Any], list[dict[str, Any]]], capsys: pytest.CaptureFixture[str]
) -> None:
    seen, answers = fake
    answers += [new_step(depends_on=["P01-S09-T01"]), new_step()]
    args = ["backlog", "propose", "Export", "--project", "P01", "--json", "--repo", str(repo)]
    assert main(args) == 0
    data = json.loads(capsys.readouterr().out)["data"]
    assert [t["id"] for t in data["tasks"]] == ["P01-S02-T01", "P01-S02-T02"]
    assert len(seen) == 2
    assert "failed validation" in seen[1].prompt
    assert "P01-S09-T01" in seen[1].prompt


def test_proposal_invalid_twice_fails_without_writing(
    repo: Path, fake: tuple[list[Any], list[dict[str, Any]]], capsys: pytest.CaptureFixture[str]
) -> None:
    seen, answers = fake
    answers += [new_step(workflow="missing"), new_step(depends_on=["P01-S02-T02"])]
    head = _head(repo)
    args = ["backlog", "propose", "Export", "--project", "P01", "--apply", "--json"]
    assert main([*args, "--repo", str(repo)]) == 1
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "proposal_invalid"
    assert {i["code"] for i in envelope["error"]["issues"]} == {"cycle"}
    assert len(seen) == 2
    assert "unknown_workflow" in seen[1].prompt
    assert _status(repo) == ""
    assert _head(repo) == head


def test_apply_writes_step_and_tasks_without_commit(
    repo: Path, fake: tuple[list[Any], list[dict[str, Any]]], capsys: pytest.CaptureFixture[str]
) -> None:
    _, answers = fake
    answers.append(new_step())
    head = _head(repo)
    args = ["backlog", "propose", "Export", "--project", "P01", "--apply", "--repo", str(repo)]
    assert main(args) == 0
    assert "written 3 file(s)" in capsys.readouterr().out
    assert _head(repo) == head
    assert sorted(_status(repo).splitlines()) == [
        "?? backlog/P01/S02-export/P01-S02-T01-model-exportu.md",
        "?? backlog/P01/S02-export/P01-S02-T02-cli-exportu.md",
        "?? backlog/P01/S02-export/index.md",
    ]
    backlog = load_backlog(repo)
    assert check_backlog(backlog) == []
    task = backlog.by_id["P01-S02-T02"]
    assert task.depends_on == ["P01-S02-T01"]  # type: ignore[union-attr]
    assert task.own["workflow"] == "plan"  # type: ignore[union-attr]
    assert "Hotovo znamená" in task.body
    assert backlog.by_id["P01-S02"].title == "Export"


def test_apply_tasks_to_an_existing_step(
    repo: Path, fake: tuple[list[Any], list[dict[str, Any]]], capsys: pytest.CaptureFixture[str]
) -> None:
    _, answers = fake
    answers.append(
        {
            "status": "success",
            "summary": "One task.",
            "step": None,
            "tasks": [_task("T02", "Druhý", depends_on=["P01-S01-T01"])],
        }
    )
    args = ["backlog", "propose", "Druhý", "--step", "P01-S01", "--apply", "--json"]
    assert main([*args, "--repo", str(repo)]) == 0
    data = json.loads(capsys.readouterr().out)["data"]
    assert data["applied"] is True and data["step"]["new"] is False
    assert data["files"] == ["backlog/P01/S01/P01-S01-T02-druhy.md"]
    assert check_backlog(load_backlog(repo)) == []


def test_prompt_override_in_factory_is_used(
    repo: Path, fake: tuple[list[Any], list[dict[str, Any]]], capsys: pytest.CaptureFixture[str]
) -> None:
    seen, answers = fake
    answers.append(new_step())
    folder = repo / ".factory/prompts/proposer"
    folder.mkdir(parents=True)
    (folder / "system.md").write_text("Repo proposer system prompt\n", encoding="utf-8")
    (folder / "user.md").write_text("Repo proposer task\n{{prompt}}\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "override proposer")
    args = ["backlog", "propose", "Export", "--project", "P01", "--repo", str(repo)]
    assert main(args) == 0
    capsys.readouterr()
    assert seen[0].system_prompt.startswith("Repo proposer system prompt")
    assert seen[0].prompt.startswith("Repo proposer task")


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"workflow": "missing"}, "unknown_workflow"),
        ({"body": "Bez kritérií."}, "missing_done"),
        ({"depends_on": ["T01"]}, "self_ref"),
        ({"depends_on": ["T02"]}, "cycle"),
        ({"depends_on": ["P01-S09"]}, "unknown_ref"),
        ({"code": "T-01"}, "invalid_id"),
    ],
)
def test_plan_rejects(repo: Path, change: dict[str, Any], code: str) -> None:
    value = new_step(**change)
    proposal = BacklogProposalOutput.model_validate(value)
    with pytest.raises(TaskEditError) as caught:
        plan(repo, proposal, Target(project="P01"), workflow_catalog(repo))
    assert code in {i.code for i in caught.value.issues}


def test_plan_rejects_wrong_target(repo: Path) -> None:
    proposal = BacklogProposalOutput.model_validate(new_step())
    with pytest.raises(TaskEditError) as caught:
        plan(repo, proposal, Target(step="P01-S01"), workflow_catalog(repo))
    assert "invalid_value" in {i.code for i in caught.value.issues}
    existing = BacklogProposalOutput.model_validate(
        {**new_step(), "step": {"code": "S01", "title": "Again"}}
    )
    with pytest.raises(TaskEditError) as caught:
        plan(repo, existing, Target(project="P01"), workflow_catalog(repo))
    assert "duplicate_id" in {i.code for i in caught.value.issues}


def test_quality_findings_go_to_the_agent_once(
    repo: Path, fake: tuple[list[Any], list[dict[str, Any]]], capsys: pytest.CaptureFixture[str]
) -> None:
    seen, answers = fake
    parallel = new_step()
    parallel["tasks"][1]["depends_on"] = []
    answers += [parallel, new_step()]
    args = ["backlog", "propose", "Export", "--project", "P01", "--json", "--repo", str(repo)]
    assert main(args) == 0
    data = json.loads(capsys.readouterr().out)["data"]
    assert len(seen) == 2
    assert "writes_overlap" in seen[1].prompt
    assert data["findings"] == []


def test_findings_left_after_the_correction_are_shown(
    repo: Path, fake: tuple[list[Any], list[dict[str, Any]]], capsys: pytest.CaptureFixture[str]
) -> None:
    seen, answers = fake
    closed = new_step(writes=["src/", ".factory/workflows/"])
    answers += [closed, closed]
    args = ["backlog", "propose", "Export", "--project", "P01", "--repo", str(repo)]
    assert main([*args, "--json"]) == 0
    data = json.loads(capsys.readouterr().out)["data"]
    assert len(seen) == 2
    assert "writes_closed" in seen[1].prompt
    assert data["findings"] == [
        {
            "rule": "writes_closed",
            "task": "P01-S02-T01",
            "message": data["findings"][0]["message"],
            "blocking": False,
        }
    ]
    assert ".factory/workflows/" in data["findings"][0]["message"]
    assert [t["id"] for t in data["tasks"]] == ["P01-S02-T01", "P01-S02-T02"]
    assert _status(repo) == ""

    answers[:] = [closed]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "findings of the quality check (1):" in out
    assert "[writes_closed] P01-S02-T01" in out


def test_review_maps_dependencies_by_full_id(repo: Path) -> None:
    value = new_step()
    value["tasks"][1]["depends_on"] = ["P01-S02-T01"]
    proposal = BacklogProposalOutput.model_validate(value)
    assert review(repo, proposal, Target(project="P01")) == []
    value["tasks"][1]["depends_on"] = []
    proposal = BacklogProposalOutput.model_validate(value)
    assert [f.rule for f in review(repo, proposal, Target(project="P01"))] == ["writes_overlap"]
