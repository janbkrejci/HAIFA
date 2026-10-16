"""What an ``accept_not_met`` failure says: the facts in its detail and its one-line error.

``accept_failure`` reads a finished ``WorkflowRun`` whose ``accept`` was false (or whose
engine exit code was not 0) and returns:

- the error for ``task_runs.error``: one sentence naming what did not pass, e.g.
  ``Review neschválilo ani po 2 kolech: <první výtka>``;
- the detail for ``task_runs.failure_detail``: the ``accept`` expression, the value of
  every ``<step>.<field>`` it reads, the rounds of every ``repeat`` that ran, and the
  latest review objections and failed test checks from the envelopes, shortened.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from aifactory.engine import data_types as dt
from aifactory.workflow import WorkflowRun
from aifactory.workflow.conditions import evaluate, refs
from aifactory.workflow.model import Repeat, Step, Workflow

__all__ = ["accept_failure"]

MAX_ITEMS = 5  # objections or failed checks kept in the detail
MAX_ITEM = 300  # characters of one objection
MAX_CHECK = 800  # characters of one failed check (its first line and the output's end)
MAX_VALUE = 200  # characters of a string value of an `accept` reference
MAX_REASON = 200  # characters of the objection quoted in the error
MAX_ERROR = 400


def _short(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _check_text(text: str) -> str:
    """A failed check: its first line (name, command, exit code) and the output's end."""
    text = text.strip()
    if len(text) <= MAX_CHECK:
        return text
    head = _short(text.splitlines()[0], MAX_CHECK // 4)
    return f"{head}\n…\n{text[-(MAX_CHECK - len(head) - 3) :]}"


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _value(value: Any) -> Any:
    """A JSON-ready value of a reference; long strings and containers are shortened."""
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return _short(value, MAX_VALUE)
    return _short(str(value), MAX_VALUE)


def _render(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return repr(value)
    return str(value)


def _loops(steps: Sequence[Step], inside: str | None, into: dict[str, str]) -> list[Repeat]:
    """Every ``repeat`` in source order; ``into`` maps a step key to its innermost loop."""
    found: list[Repeat] = []
    for step in steps:
        if isinstance(step, Repeat):
            found.append(step)
            found += _loops(step.steps, step.path, into)
        elif inside is not None:
            into.setdefault(step.key, inside)
    return found


def _rounds_phrase(rounds: int | None) -> str:
    if not rounds:
        return ""
    return f" ani po {rounds} {'kole' if rounds == 1 else 'kolech'}"


def _review_objections(envelope: dt.ReviewOutput) -> list[str]:
    objections = [b for b in envelope.blocking if b.strip()]
    for finding in envelope.findings:
        if not finding.met:
            evidence = f": {finding.evidence}" if finding.evidence.strip() else ""
            objections.append(f"{finding.requirement}{evidence}")
    return [_short(o, MAX_ITEM) for o in objections[:MAX_ITEMS]]


def _failed(envelope: Any) -> bool:
    if isinstance(envelope, dt.ReviewOutput):
        return not envelope.approved
    if isinstance(envelope, dt.VerifyOutput):
        return not envelope.passed
    return False


def _culprit(workflow: Workflow, wf: WorkflowRun) -> str | None:
    """The step whose review or test failed: the first such reference of ``accept``.

    Without one, the latest failed review or test of the run.
    """
    if workflow.accept is not None:
        for ref in refs(workflow.accept.node):
            if _failed(wf.envelopes.get(ref.step)):
                return ref.step
    for key, envelope in reversed(wf.history):
        if wf.envelopes.get(key) is envelope and _failed(envelope):
            return key
    return None


def accept_failure(workflow: Workflow, wf: WorkflowRun) -> tuple[str, dict[str, Any]]:
    """The one-sentence error and the JSON-ready detail of a run that failed ``accept``."""
    source = workflow.accept.source if workflow.accept is not None else None
    values: dict[str, Any] = {}
    if workflow.accept is not None:
        for ref in refs(workflow.accept.node):
            values[f"{ref.step}.{ref.field}"] = _value(evaluate(ref, wf.results))
    loop_of: dict[str, str] = {}
    loops = _loops(workflow.steps, None, loop_of)
    rounds = [
        {
            "loop": loop.path,
            "until": loop.until.source if loop.until is not None else None,
            "rounds": wf.rounds[loop.path],
            "max": loop.max,
        }
        for loop in loops
        if loop.path in wf.rounds
    ]
    detail: dict[str, Any] = {
        "accept": source,
        "accepted": wf.accepted,
        "exit_code": wf.exit_code,
        "values": values,
        "rounds": rounds,
    }
    reviews = [
        (k, e) for k, e in wf.envelopes.items() if isinstance(e, dt.ReviewOutput) and _failed(e)
    ]
    tests = [
        (k, e) for k, e in wf.envelopes.items() if isinstance(e, dt.VerifyOutput) and _failed(e)
    ]
    if reviews:
        key, review = reviews[-1]
        detail["review"] = {
            "step": key,
            "summary": _short(review.summary, MAX_ITEM),
            "objections": _review_objections(review),
        }
    if tests:
        key, test = tests[-1]
        detail["test"] = {
            "step": key,
            "summary": _short(test.summary, MAX_ITEM),
            "failed_checks": [_check_text(f) for f in test.failures[:MAX_ITEMS]],
        }
    return _sentence(workflow, wf, values, loop_of), detail


def _sentence(
    workflow: Workflow, wf: WorkflowRun, values: dict[str, Any], loop_of: dict[str, str]
) -> str:
    culprit = _culprit(workflow, wf)
    envelope = wf.envelopes.get(culprit) if culprit is not None else None
    loop = loop_of.get(culprit) if culprit is not None else None
    after = _rounds_phrase(wf.rounds.get(loop) if loop is not None else None)
    if isinstance(envelope, dt.ReviewOutput):
        objections = _review_objections(envelope) or [envelope.summary]
        reason = _short(_one_line(objections[0]), MAX_REASON)
        text = f"Review neschválilo{after}" + (f": {reason}" if reason else "")
    elif isinstance(envelope, dt.VerifyOutput):
        first = envelope.failures[0].strip().splitlines()[0] if envelope.failures else ""
        reason = _short(_one_line(first or envelope.summary), MAX_REASON)
        text = f"Testy neprošly{after}" + (f": {reason}" if reason else "")
    elif not wf.accepted:
        shown = ", ".join(f"{name}={_render(value)}" for name, value in values.items())
        text = f"Podmínka accept `{workflow.accept.source if workflow.accept else ''}` nesplněna"
        text += f": {shown}" if shown else ""
    else:
        text = f"Workflow skončilo s kódem {wf.exit_code}"
    return _short(_one_line(text), MAX_ERROR)
