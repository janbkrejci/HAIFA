"""The PR body starts with the agents' summary, never with the task text."""

from __future__ import annotations

from pathlib import Path

from aifactory.backlog import Container, Task
from aifactory.engine.data_types import BuildOutput, PlanOutput, PrSummary
from aifactory.review.prbody import SUMMARY_END, pr_body, previous_summary
from aifactory.run.followups import CreatedFollowUp
from aifactory.workflow import WorkflowRun

TASK_TEXT = "## Zadání\nNavrhnout schéma pro tabulku faktur se všemi sloupci.\n"
MARKER = "<!-- factory: task=M01-S01-T01 branch=factory/M01-S01-T01-1 -->"
BRANCH = "factory/M01-S01-T01-1"


def task() -> Task:
    step = Container(id="M01-S01", title="Model", level="step", path="backlog/M01/S01")
    return Task(
        id="M01-S01-T01",
        title="Schema",
        status="todo",
        level="task",
        path="backlog/M01/S01/M01-S01-T01.md",
        parent=step,
        body=TASK_TEXT,
    )


def run_with(*envelopes: object) -> WorkflowRun:
    wf = WorkflowRun(exit_code=0, accepted=True, adw_id="r1")
    for index, envelope in enumerate(envelopes):
        wf.history.append((f"step{index}", envelope))
    return wf


def summary(**fields: object) -> PrSummary:
    return PrSummary.model_validate({"goal": "Faktury potřebují schéma.", **fields})


def body(wf: WorkflowRun | None, tmp_path: Path, **kwargs: object) -> str:
    return pr_body(task(), [], wf, tmp_path / "trace.db", BRANCH, **kwargs)  # type: ignore[arg-type]


def test_summary_sections_come_first_and_task_text_is_not_copied(tmp_path: Path) -> None:
    pr = summary(done=["Schéma faktur existuje."], not_done=["Bez indexů."], notes=["Migrace."])
    text = body(run_with(BuildOutput(status="success", pr_summary=pr)), tmp_path)

    assert text.splitlines()[0] == MARKER
    assert "## Zadání" not in text and "tabulku faktur" not in text
    heads = [
        "## Cíl",
        "## Co bylo uděláno",
        "## Co uděláno nebylo",
        "## Důležité pro schválení",
        SUMMARY_END,
        "## Technické podrobnosti",
        "### Agenti",
        "### Gates a testy",
        "### Review",
        "### Náklady",
    ]
    positions = [text.index(h) for h in heads]
    assert positions == sorted(positions)
    for part in ("Faktury potřebují schéma.", "- Schéma faktur existuje.", "- Bez indexů."):
        assert part in text
    assert "- Migrace." in text


def test_latest_summary_wins(tmp_path: Path) -> None:
    old = BuildOutput(status="success", pr_summary=summary(goal="Starý cíl.", done=["a"]))
    new = PlanOutput(status="success", pr_summary=summary(goal="Nový cíl.", done=["b"]))
    empty = BuildOutput(status="success", pr_summary=PrSummary())
    text = body(run_with(old, new, empty), tmp_path)
    assert "Nový cíl." in text and "Starý cíl." not in text


def test_nothing_left_out_says_so_and_follow_ups_are_listed(tmp_path: Path) -> None:
    wf = run_with(BuildOutput(status="success", pr_summary=summary(done=["x"])))
    text = body(wf, tmp_path)
    not_done = text.split("## Co uděláno nebylo", 1)[1].split(SUMMARY_END)[0]
    assert not_done.strip() == "- nic"
    assert "## Důležité pro schválení" not in text

    created = CreatedFollowUp("M01-TODO-T01", "Indexy", "nejsou v rozsahu", False)
    text = body(wf, tmp_path, follow_ups=[created])
    not_done = text.split("## Co uděláno nebylo", 1)[1].split(SUMMARY_END)[0]
    assert "- nic" not in not_done
    assert "`M01-TODO-T01`: Indexy (nejsou v rozsahu)" in not_done


def test_without_an_agent_summary_the_title_stands_in(tmp_path: Path) -> None:
    wf = run_with(BuildOutput(status="success", summary="Přidal schéma.", changed_files=["a"]))
    text = body(wf, tmp_path)
    goal = text.split("## Cíl", 1)[1].split("## Co bylo uděláno")[0]
    assert "Schema" in goal and "_Agenti běhu shrnutí nedodali._" in goal
    assert "- Přidal schéma." in text
    assert "tabulku faktur" not in text
    assert "tabulku faktur" not in body(None, tmp_path)


def test_resolve_run_reuses_the_previous_summary(tmp_path: Path) -> None:
    first = body(run_with(BuildOutput(status="success", pr_summary=summary(done=["x"]))), tmp_path)
    kept = previous_summary(first)
    assert kept is not None and kept.startswith("## Cíl") and SUMMARY_END not in kept

    other = run_with(BuildOutput(status="success", pr_summary=summary(goal="Jiný.", done=["y"])))
    text = body(other, tmp_path, previous_body=first, reuse_summary=True)
    assert kept in text and "Jiný." not in text
    # a run without a summary keeps the earlier one too
    assert kept in body(run_with(), tmp_path, previous_body=first)
    # a run with its own summary replaces it
    assert "Jiný." in body(other, tmp_path, previous_body=first)


def test_previous_summary_needs_the_end_marker() -> None:
    assert previous_summary(None) is None
    assert previous_summary(f"{MARKER}\n\n## Zadání\n\nText\n") is None
