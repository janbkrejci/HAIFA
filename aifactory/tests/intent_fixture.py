"""A fake proposer harness for the Nový záměr dialog (API and browser tests); no model."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from aifactory.engine import agents
from aifactory.engine.data_types import AgentResult
from aifactory.harness.check import HarnessStatus

DONE = "\n\nHotovo znamená:\n- testy projdou"

Answer = dict[str, Any] | Callable[[Any], dict[str, Any]]


def task(code: str, title: str, **extra: Any) -> dict[str, Any]:
    return {
        "code": code,
        "title": title,
        "body": f"Udělej {title}.{DONE}",
        "depends_on": [],
        "writes": [f"src/{code.lower()}/"],
        "workflow": "plan",
        **extra,
    }


def export_step(*extra: dict[str, Any]) -> dict[str, Any]:
    """A new step S02 of P01 with two tasks (T02 after T01), plus ``extra`` tasks."""
    return {
        "status": "success",
        "summary": "Two tasks for the export.",
        "step": {"code": "S02", "title": "Export", "body": "Export dat do CSV."},
        "tasks": [
            task("T01", "Model exportu"),
            task("T02", "CLI exportu", depends_on=["T01"]),
            *extra,
        ],
    }


def placed(answer: dict[str, Any], reason: str, **placement: Any) -> dict[str, Any]:
    """``answer`` as an automatic placement: ``placement`` (``existing_project``,
    ``existing_step`` or ``project``) and the one-sentence ``reason``."""
    return {**answer, "placement_reason": reason, **placement}


def install_fake(
    monkeypatch: pytest.MonkeyPatch, answers: list[Answer], harness: str = "claude"
) -> list[Any]:
    """Make the selected harness answer ``answers`` in order (the last one repeats); return
    the requests it saw."""
    seen: list[Any] = []
    monkeypatch.setattr(
        "aifactory.workflow.propose.check_harness",
        lambda name: HarnessStatus(name, "fake", "fake", "1"),
    )

    def run(request: Any, **kwargs: Any) -> AgentResult:
        seen.append(request)
        answer = answers[min(len(seen), len(answers)) - 1]
        value = answer(request) if callable(answer) else answer
        return AgentResult(text=json.dumps(value), returncode=0)

    monkeypatch.setattr(agents.INTERFACES[harness], "run", run)
    return seen


def container_binding(repo: Path, path: str, values: str) -> None:
    file = repo / path
    text = file.read_text(encoding="utf-8")
    file.write_text(text.replace("---\n", f"---\n{values}", 1), encoding="utf-8")


def computer_binding(default: str | None = "codex", *, enabled: bool = True) -> None:
    from aifactory.harness.settings import HarnessChoice, HarnessSettings, path

    settings = HarnessSettings(
        default_harness=default,
        harnesses={
            "claude": HarnessChoice(model="sonnet", thinking="medium"),
            "codex": HarnessChoice(enabled=enabled, model="gpt-6.1-sol", thinking="high"),
            "pi": HarnessChoice(),
        },
    )
    file = path()
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(settings.model_dump_json(), encoding="utf-8")
