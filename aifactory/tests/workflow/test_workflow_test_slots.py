"""`test_slots`: machine-wide slots of the `test` step (`engine.slots`), real processes.

Slot holders and waiters are separate Python processes, as concurrent runs are.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from workflow_fakes import (
    EngineEnv,
    workflow,
    workflow_env_fixture,  # noqa: F401  (pytest fixture)
)

from aifactory.config.settings import ProjectSettings
from aifactory.engine import quality
from aifactory.engine.quality import TEST_SLOT_EVENT
from aifactory.engine.slots import SlotWait, TestSlots
from aifactory.workflow import run_workflow

POLL = 0.05

# A process that takes a slot of `dir` (one slot), logs `start`/`end` lines to `log`
# and holds the slot for `hold` seconds.
HOLDER = """\
import sys, time
from pathlib import Path
from aifactory.engine.slots import TestSlots
directory, label, hold, log = sys.argv[1], sys.argv[2], float(sys.argv[3]), Path(sys.argv[4])
def note(text):
    with log.open("a") as f:
        f.write(f"{text} {label} {time.time():.4f}\\n")
note("ask")
with TestSlots(Path(directory), 1, poll=0.02).hold():
    note("start")
    if len(sys.argv) > 5:
        ready = Path(sys.argv[5])
        while not ready.exists():
            time.sleep(0.02)
    time.sleep(hold)
    note("end")
"""

TEXT = """\
name: t
description: A workflow written only to exercise the test step
steps:
  - test
accept: test.passed
"""


@pytest.fixture(name="procs")
def procs_fixture() -> Iterator[list[subprocess.Popen[bytes]]]:
    started: list[subprocess.Popen[bytes]] = []
    yield started
    for proc in started:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)


def _spawn(
    procs: list[subprocess.Popen[bytes]],
    slots: Path,
    label: str,
    hold: float,
    log: Path,
    ready: Path | None = None,
) -> subprocess.Popen[bytes]:
    command = [sys.executable, "-c", HOLDER, str(slots), label, str(hold), str(log)]
    if ready is not None:
        command.append(str(ready))
    proc = subprocess.Popen(command)
    procs.append(proc)
    return proc


def _lines(log: Path) -> list[tuple[str, str, float]]:
    if not log.exists():
        return []
    out = []
    for line in log.read_text().splitlines():
        what, label, at = line.split()
        out.append((what, label, float(at)))
    return out


def _wait_for(predicate, timeout: float = 20.0) -> None:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.02)


def _started(log: Path, label: str) -> bool:
    return any(w == "start" and lab == label for w, lab, _ in _lines(log))


def test_test_slots_config_defaults_to_one() -> None:
    assert ProjectSettings().test_slots == 1
    assert ProjectSettings.model_validate({"test_slots": 3}).test_slots == 3
    for bad in (0, -1, "2", True):
        with pytest.raises(ValueError, match="test_slots"):
            ProjectSettings.model_validate({"test_slots": bad})


def test_two_runs_with_one_slot_test_one_after_another(
    tmp_path: Path, procs: list[subprocess.Popen[bytes]]
) -> None:
    slots, log = tmp_path / "slots", tmp_path / "log"
    a = _spawn(procs, slots, "a", 0.6, log)
    b = _spawn(procs, slots, "b", 0.6, log)
    assert a.wait(timeout=30) == 0
    assert b.wait(timeout=30) == 0
    events = [(w, lab) for w, lab, _ in _lines(log) if w in ("start", "end")]
    first = events[0][1]
    second = "b" if first == "a" else "a"
    assert events == [("start", first), ("end", first), ("start", second), ("end", second)]


def test_waiters_get_the_slot_in_the_order_they_asked(
    tmp_path: Path, procs: list[subprocess.Popen[bytes]]
) -> None:
    slots, log = tmp_path / "slots", tmp_path / "log"
    _spawn(procs, slots, "holder", 1.0, log)
    _wait_for(lambda: _started(log, "holder"))
    labels = ["w1", "w2", "w3"]
    for label in labels:
        _spawn(procs, slots, label, 0.1, log)
        _wait_for(lambda label=label: any(lab == label for _, lab, _ in _lines(log)))
        time.sleep(0.05)  # distinct ticket times
    for proc in procs:
        assert proc.wait(timeout=30) == 0
    order = [lab for w, lab, _ in _lines(log) if w == "start"]
    assert order == ["holder", *labels]


def test_slot_of_a_killed_process_frees_itself(
    tmp_path: Path, procs: list[subprocess.Popen[bytes]]
) -> None:
    slots, log = tmp_path / "slots", tmp_path / "log"
    holder = _spawn(procs, slots, "holder", 60, log)
    _wait_for(lambda: _started(log, "holder"))
    # a waiter that is killed too must not block the queue
    waiter = _spawn(procs, slots, "waiter", 60, log)
    _wait_for(lambda: any(lab == "waiter" for _, lab, _ in _lines(log)))
    seen: list[SlotWait] = []
    test_slots = TestSlots(slots, 1, poll=POLL)
    assert test_slots.holding() == 1
    holder.kill()
    holder.wait(timeout=10)
    _wait_for(lambda: _started(log, "waiter"))
    waiter.kill()
    waiter.wait(timeout=10)
    started = time.monotonic()
    with test_slots.hold(seen.append) as lease:
        assert lease.slot == 0
        assert time.monotonic() - started < 10
    assert list((slots / "queue").iterdir()) == []


def test_dead_waiter_ticket_is_dropped(tmp_path: Path) -> None:
    slots = tmp_path / "slots"
    (slots / "queue").mkdir(parents=True)
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait(timeout=10)
    (slots / "queue" / f"{0:020d}-{dead.pid}-x").write_text(
        str(dead.pid), encoding="utf-8", newline="\n"
    )
    seen: list[SlotWait] = []
    with TestSlots(slots, 1, poll=POLL).hold(seen.append):
        pass
    assert seen == []
    assert list((slots / "queue").iterdir()) == []


def _slot_events(env: EngineEnv) -> list[dict[str, object]]:
    conn = sqlite3.connect(str(env.cfg.observability.db))
    try:
        rows = conn.execute(
            "SELECT payload_json FROM events WHERE name = ? ORDER BY rowid", (TEST_SLOT_EVENT,)
        ).fetchall()
    finally:
        conn.close()
    return [json.loads(r[0]) for r in rows]


def test_wait_for_a_slot_is_traced_and_not_part_of_the_timeout(
    workflow_env: EngineEnv,
    tmp_path: Path,
    procs: list[subprocess.Popen[bytes]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slots, log = tmp_path / "slots", tmp_path / "log"
    ready = tmp_path / "waiting"
    slot_event = quality._slot_event

    def signal_waiting(run: Any, payload: dict[str, Any]) -> None:
        slot_event(run, payload)
        if payload["state"] == "waiting":
            ready.touch()

    monkeypatch.setattr(quality, "_slot_event", signal_waiting)
    # Start the hold duration only after the workflow reaches the slot queue.
    # Workflow preparation can take longer than the original fixed hold under load.
    holder = _spawn(procs, slots, "holder", 1.5, log, ready)
    _wait_for(lambda: _started(log, "holder"))
    clock = time.monotonic()
    result = run_workflow(
        workflow(TEXT),
        "do it",
        workflow_env.cfg,
        test_command=[sys.executable, "-c", "import time; time.sleep(0.3)"],
        test_timeout=1,
        test_slots=TestSlots(slots, 1, poll=POLL),
    )
    waited = time.monotonic() - clock
    assert holder.wait(timeout=30) == 0
    assert waited > 1.5  # longer than test_timeout, yet the step passed
    assert result.results["test"]["passed"] is True
    assert result.accepted is True
    events = _slot_events(workflow_env)
    assert events[0]["state"] == "waiting"
    assert events[0]["ahead"] == 1
    assert events[0]["slots"] == 1
    assert events[-1]["state"] == "acquired"
    assert float(events[-1]["waited_seconds"]) > 1.0  # type: ignore[arg-type]


def test_timeout_still_limits_the_command_inside_a_slot(
    workflow_env: EngineEnv, tmp_path: Path
) -> None:
    slots = tmp_path / "slots"
    result = run_workflow(
        workflow(TEXT),
        "do it",
        workflow_env.cfg,
        test_command=[sys.executable, "-c", "import time; time.sleep(30)"],
        test_timeout=1,
        test_slots=TestSlots(slots, 1, poll=POLL),
    )
    assert result.results["test"]["passed"] is False
    assert "exceeded the time limit of 1s" in result.results["test"]["failures"][0]
    # the slot was freed after the failed step
    with TestSlots(slots, 1, poll=POLL).hold() as lease:
        assert lease.waited_seconds < 1
    assert [e["state"] for e in _slot_events(workflow_env)] == ["acquired"]


def test_slot_is_freed_when_the_step_raises(tmp_path: Path) -> None:
    slots = TestSlots(tmp_path / "slots", 1, poll=POLL)
    with pytest.raises(RuntimeError), slots.hold():
        raise RuntimeError("boom")
    assert slots.holding() == 0
    with slots.hold() as lease:
        assert lease.waited_seconds < 1
