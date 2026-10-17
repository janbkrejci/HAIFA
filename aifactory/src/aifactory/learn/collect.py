"""The objections of the task runs of a repo, read from its trace DB.

An objection is one thing an agent of a run found wrong:

- ``review`` / ``test_review``: an envelope with a bool ``approved`` (``ReviewOutput`` of
  the reviewer or the test reviewer): every ``blocking`` item and every finding with
  ``met: false``.
- ``test_triage``: a ``TestPlanOutput`` with ``failure_cause`` (the tester judged failed
  checks): its ``reason`` and its ``missing_tests``.
- ``revise``: a phase ``revise`` (the builder closing the reviewer's findings): its
  ``summary``.

Only valid envelopes of rows in ``task_runs`` count. Every objection has a stable ``key``
(``<envelope_id>#<n>``), so a lesson remembers which objections it was made of.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aifactory import database
from aifactory.engine.tracer import BUSY_TIMEOUT

REVIEW, TEST_REVIEW, TEST_TRIAGE, REVISE = "review", "test_review", "test_triage", "revise"
SOURCES = (REVIEW, TEST_REVIEW, TEST_TRIAGE, REVISE)
_REVISE_PHASE = re.compile(r"^revise(_\d+)*$")
_TEXT_LIMIT = 1000


@dataclass(frozen=True)
class Objection:
    key: str
    run_id: str
    task_id: str
    source: str
    agent: str
    phase: str
    text: str
    created_at: str

    def to_json(self) -> dict[str, str]:
        return {
            "key": self.key,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "source": self.source,
            "agent": self.agent,
            "phase": self.phase,
            "text": self.text,
            "created_at": self.created_at,
        }


def _clip(text: str, limit: int = _TEXT_LIMIT) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _texts(
    payload: dict[str, Any], output_type: str, agent: str, phase: str
) -> tuple[str, list[str]]:
    """The source and the objection texts of one envelope (none: it objects to nothing)."""
    if isinstance(payload.get("approved"), bool):
        source = (
            TEST_REVIEW if agent == "test-reviewer" or phase.startswith("test_review") else REVIEW
        )
        texts = [str(b) for b in payload.get("blocking") or [] if str(b).strip()]
        for finding in payload.get("findings") or []:
            if isinstance(finding, dict) and finding.get("met") is False:
                requirement = str(finding.get("requirement") or "").strip()
                evidence = str(finding.get("evidence") or "").strip()
                texts.append(f"{requirement}: {evidence}" if evidence else requirement)
        return source, texts
    cause = payload.get("failure_cause")
    if output_type == "TestPlanOutput" and cause in ("code", "plan"):
        texts = [f"[{cause}] {payload.get('reason') or ''}".strip()]
        texts += [
            f"missing test: {t}" for t in payload.get("missing_tests") or [] if str(t).strip()
        ]
        return TEST_TRIAGE, texts
    if _REVISE_PHASE.match(phase) and str(payload.get("summary") or "").strip():
        return REVISE, [str(payload["summary"])]
    return "", []


def _rows(conn: sqlite3.Connection, since: str | None) -> list[tuple[Any, ...]]:
    where = "e.valid = 1" + (" AND e.created_at >= ?" if since else "")
    return conn.execute(
        "SELECT e.envelope_id, e.adw_id, r.task_id, e.agent, e.output_type, "
        "COALESCE(p.name, ''), e.payload_json, e.created_at FROM envelopes e "
        "JOIN task_runs r ON r.run_id = e.adw_id "
        "LEFT JOIN phases p ON p.phase_id = e.phase_id "
        f"WHERE {where} ORDER BY e.created_at, e.rowid",
        (since,) if since else (),
    ).fetchall()


def collect(trace_db: Path, since: str | None = None) -> list[Objection]:
    """Every objection of the task runs in ``trace_db`` (from ``since``, an ISO timestamp)."""
    if not database.available(trace_db):
        return []
    conn = database.connect(f"file:{trace_db}?mode=ro", uri=True, timeout=BUSY_TIMEOUT)
    try:
        try:
            rows = _rows(conn, since)
        except sqlite3.OperationalError:  # no runs recorded yet (tables missing)
            return []
    finally:
        conn.close()
    found: list[Objection] = []
    for envelope_id, run_id, task_id, agent, output_type, phase, payload_json, created in rows:
        try:
            payload = json.loads(payload_json) if payload_json else None
        except ValueError:
            continue
        if not isinstance(payload, dict) or payload.get("status") == "fail":
            continue
        source, texts = _texts(payload, str(output_type or ""), str(agent or ""), str(phase))
        seen: set[str] = set()
        for n, text in enumerate(texts):
            clipped = _clip(text)
            if not clipped or clipped in seen:
                continue
            seen.add(clipped)
            found.append(
                Objection(
                    key=f"{envelope_id}#{n}",
                    run_id=str(run_id),
                    task_id=str(task_id),
                    source=source,
                    agent=str(agent or ""),
                    phase=str(phase),
                    text=clipped,
                    created_at=str(created or ""),
                )
            )
    return found
