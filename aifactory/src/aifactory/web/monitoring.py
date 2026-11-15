"""Server-owned checks, independent of the number of browser tabs and reloads."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from starlette.concurrency import run_in_threadpool

from aifactory.home import haifa_home
from aifactory.migration_guard import check_home
from aifactory.upgrade import UpgradeError

log = logging.getLogger(__name__)


async def _migration_ready() -> None:
    # A prepared GIRO dashboard may answer health, but must not launch work or
    # refresh mutable state before the coordinator commits the transaction.
    while True:
        try:
            check_home(haifa_home(), writing=True)
            return
        except UpgradeError:
            await asyncio.sleep(0.2)


async def once(check: Callable[[], object]) -> None:
    # Run once on every server start; later runs are explicit (fresh=1).
    try:
        await _migration_ready()
        await run_in_threadpool(check)
    except Exception:
        log.exception("Dashboard startup check failed")


async def periodic(check: Callable[[], object], interval: float) -> None:
    # Run immediately on every server start, including the restart after an upgrade.
    while True:
        try:
            await _migration_ready()
            await run_in_threadpool(check)
        except Exception:
            log.exception("Dashboard background check failed")
        await asyncio.sleep(interval)
