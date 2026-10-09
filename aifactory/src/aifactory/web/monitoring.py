"""Server-owned checks, independent of the number of browser tabs and reloads."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from starlette.concurrency import run_in_threadpool

log = logging.getLogger(__name__)


async def once(check: Callable[[], object]) -> None:
    # Run once on every server start; later runs are explicit (fresh=1).
    try:
        await run_in_threadpool(check)
    except Exception:
        log.exception("Dashboard startup check failed")


async def periodic(check: Callable[[], object], interval: float) -> None:
    # Run immediately on every server start, including the restart after an upgrade.
    while True:
        try:
            await run_in_threadpool(check)
        except Exception:
            log.exception("Dashboard background check failed")
        await asyncio.sleep(interval)
