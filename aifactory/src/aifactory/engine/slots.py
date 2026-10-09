"""aifactory: machine-wide slots of the ``test`` step (``test_slots``).

At most ``slots`` test commands run at once on the machine; the other runs wait in a
queue in the order they asked for a slot. The state is a directory (by default
``<HAIFA home>/test_slots``) shared by every run on the machine:

- ``queue/<ns>-<pid>-<token>`` is a ticket of a waiting run. Tickets sort by the time
  they were created; a ticket whose process no longer exists is removed by whoever
  looks at the queue next.
- ``slot-<k>.lock`` is held with ``flock`` by the run that has slot ``k``. The kernel
  drops the lock when the holder dies, so a slot of a crashed, stopped or killed
  process frees itself. ``slot-<k>.owner`` holds the holder's pid (only to count the
  runs ahead of a waiter; a dead pid there does not count).

Only the first ``free`` waiters (``free`` = slots without a live owner, at least 1) try
to lock a slot, so with one slot the queue is strictly first come, first served.
"""

from __future__ import annotations

import contextlib
import os
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from aifactory import oscompat
from aifactory.home import haifa_home

DEFAULT_TEST_SLOTS = 1
POLL_SECONDS = 0.5


def default_slots_dir() -> Path:
    """``<HAIFA home>/test_slots``: shared by every run on the machine."""
    return haifa_home() / "test_slots"


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    return oscompat.alive(pid)


def _ticket_pid(path: Path) -> int:
    parts = path.name.split("-")
    try:
        return int(parts[1])
    except (IndexError, ValueError):
        return -1


@dataclass(frozen=True)
class SlotWait:
    """What a waiting run sees: runs ahead of it (holders and earlier waiters)."""

    ahead: int
    holding: int
    queued_before: int
    slots: int


@dataclass
class SlotLease:
    """A held slot: its index and how long the run waited for it (seconds)."""

    slot: int
    waited_seconds: float


class TestSlots:
    """A queue of ``slots`` machine-wide slots in ``directory``."""

    __test__ = False  # not a pytest test class

    def __init__(self, directory: Path, slots: int, poll: float = POLL_SECONDS) -> None:
        if slots < 1:
            raise ValueError("test_slots must be at least 1")
        self.directory = Path(directory)
        self.slots = slots
        self.poll = poll

    @property
    def queue_dir(self) -> Path:
        return self.directory / "queue"

    def _lock_path(self, k: int) -> Path:
        return self.directory / f"slot-{k}.lock"

    def _owner_path(self, k: int) -> Path:
        return self.directory / f"slot-{k}.owner"

    def _owner(self, k: int) -> int | None:
        try:
            pid = int(self._owner_path(k).read_text(encoding="utf-8").strip() or "0")
        except (OSError, ValueError):
            return None
        return pid if _alive(pid) else None

    def holding(self) -> int:
        """How many slots have a live owner."""
        return sum(1 for k in range(self.slots) if self._owner(k) is not None)

    def queue(self) -> list[Path]:
        """Tickets of live waiters, oldest first; tickets of dead processes are removed."""
        try:
            tickets = sorted(p for p in self.queue_dir.iterdir() if p.is_file())
        except FileNotFoundError:
            return []
        live: list[Path] = []
        for ticket in tickets:
            if _alive(_ticket_pid(ticket)):
                live.append(ticket)
            else:
                with contextlib.suppress(OSError):
                    ticket.unlink()
        return live

    def _try_lock(self) -> tuple[int, int] | None:
        for k in range(self.slots):
            fd = os.open(self._lock_path(k), os.O_RDWR | os.O_CREAT, 0o600)
            try:
                oscompat.lock(fd, blocking=False)
            except OSError:
                os.close(fd)
                continue
            self._owner_path(k).write_text(str(os.getpid()), encoding="utf-8", newline="\n")
            return k, fd
        return None

    def _release(self, k: int, fd: int) -> None:
        with contextlib.suppress(OSError):
            if self._owner(k) == os.getpid():
                self._owner_path(k).unlink()
        with contextlib.suppress(OSError):
            oscompat.unlock(fd)
        os.close(fd)

    @contextlib.contextmanager
    def hold(self, on_wait: Callable[[SlotWait], None] | None = None) -> Iterator[SlotLease]:
        """Wait for a slot in queue order, hold it inside the block, then free it.

        ``on_wait`` is called when the run starts waiting and whenever the number of
        runs ahead of it changes; not at all when a slot is free right away.
        """
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        ticket = self.queue_dir / f"{time.time_ns():020d}-{os.getpid()}-{uuid.uuid4().hex}"
        ticket.write_text(str(os.getpid()), encoding="utf-8", newline="\n")
        clock = time.monotonic()
        last: SlotWait | None = None
        acquired: tuple[int, int] | None = None
        try:
            while acquired is None:
                tickets = self.queue()
                if ticket not in tickets:  # removed by someone else: put it back in place
                    ticket.write_text(str(os.getpid()), encoding="utf-8", newline="\n")
                    tickets = sorted([*tickets, ticket])
                before = tickets.index(ticket)
                holding = self.holding()
                # the head of the queue always tries: a stale owner file must not block it
                if before < max(self.slots - holding, 1):
                    acquired = self._try_lock()
                    if acquired is not None:
                        break
                    holding = self.holding()
                wait = SlotWait(
                    ahead=before + holding, holding=holding, queued_before=before, slots=self.slots
                )
                if on_wait is not None and (last is None or wait.ahead != last.ahead):
                    on_wait(wait)
                last = wait
                time.sleep(self.poll)
        finally:
            with contextlib.suppress(OSError):
                ticket.unlink()
        k, fd = acquired
        try:
            yield SlotLease(slot=k, waited_seconds=time.monotonic() - clock)
        finally:
            self._release(k, fd)
