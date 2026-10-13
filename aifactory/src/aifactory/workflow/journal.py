"""The phase journal of a workflow run: what each finished phase returned, for a retry.

``run_workflow(journal=...)`` writes one entry per finished role or code phase into
``<session>/workflow_journal.json``: the phase name, the step key, the top-level step it
belongs to and the result the interpreter stored (the envelope, a test report, a
commit). The phase in progress is ``current``; when the run fails or is stopped it is
the phase to continue from.

``factory task retry`` (``aifactory.run.retry``) loads the journal and replays its first
``limit`` entries: the interpreter walks the workflow as usual, and while the next phase
has the name and step of the next entry, it takes the stored result instead of calling
the agent or the code step. Conditions, loops and inputs see exactly what they saw in the
first attempt. At the first phase that is not replayed the run goes on live, and the
journal is cut there so it keeps describing the attempt that is running.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["JOURNAL_FILE", "Journal", "JournalEntry", "read_journal"]

JOURNAL_FILE = "workflow_journal.json"


@dataclass
class JournalEntry:
    """One finished phase and what the interpreter kept of it."""

    phase: str  # the phase name, e.g. ``test_2``
    step: str  # the step key, e.g. ``test``
    kind: str  # ``agent`` or ``code``
    top: str  # the top-level step it ran in (``top_key``)
    action: str = ""  # code steps: test, command, commit, changes, rebase, rebuild
    output: str = ""  # class name of the envelope
    envelope: dict[str, Any] | None = None
    result: dict[str, Any] | None = None  # a commit step's result
    report: dict[str, Any] | None = None  # a test or command step's report
    summary: str = ""
    kept: bool = True  # False for a triage call: its envelope is no step result

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> JournalEntry:
        names = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in names})


@dataclass
class Journal:
    """The journal file of one run, and the part of it a retry replays."""

    path: Path | None
    baseline: str = ""
    workflow: str = ""
    entries: list[JournalEntry] = field(default_factory=list)
    current: dict[str, str] | None = None  # the phase in progress (or the one that failed)
    limit: int = 0  # how many leading entries a retry replays
    pos: int = 0  # how many of them were replayed so far
    replaying: bool = False
    resumed_at: str | None = None  # the first phase that ran live after the replay

    def start_replay(self, limit: int) -> None:
        self.limit = max(0, min(limit, len(self.entries)))
        self.pos = 0
        self.replaying = self.limit > 0
        if not self.replaying:
            self._cut()

    def take(self, phase: str, step: str) -> JournalEntry | None:
        """The stored result of `phase` when it is the next one to replay, else None.

        The first phase that does not match ends the replay for good: the rest of the
        run is live and the journal is cut to the replayed entries.
        """
        if not self.replaying:
            return None
        if self.pos < self.limit:
            entry = self.entries[self.pos]
            if entry.phase == phase and entry.step == step:
                self.pos += 1
                return entry
        self.replaying = False
        self._cut()
        return None

    def _cut(self) -> None:
        del self.entries[self.pos :]
        self.save()

    def begin(self, phase: str, step: str) -> None:
        """`phase` starts live."""
        if self.resumed_at is None:
            self.resumed_at = phase
        self.current = {"phase": phase, "step": step}
        self.save()

    def done(self, entry: JournalEntry) -> None:
        self.entries.append(entry)
        self.current = None
        self.save()

    def to_json(self) -> dict[str, Any]:
        return {
            "baseline": self.baseline,
            "workflow": self.workflow,
            "entries": [asdict(e) for e in self.entries],
            "current": self.current,
        }

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self.to_json(), indent=1), encoding="utf-8", newline="\n")
        tmp.replace(self.path)


def read_journal(path: Path) -> Journal:
    """The journal at `path`; an empty one when the file is missing or unreadable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Journal(path)
    if not isinstance(data, dict):
        return Journal(path)
    entries = [JournalEntry.from_json(e) for e in data.get("entries") or [] if isinstance(e, dict)]
    current = data.get("current")
    return Journal(
        path,
        baseline=str(data.get("baseline") or ""),
        workflow=str(data.get("workflow") or ""),
        entries=entries,
        current=current if isinstance(current, dict) else None,
    )
