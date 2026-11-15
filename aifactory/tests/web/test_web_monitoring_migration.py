"""Prepared migrations must not start background writes while health is validated."""

import asyncio
import json
from pathlib import Path

import pytest

from aifactory import migration_guard
from aifactory.web import monitoring


def test_startup_check_waits_until_migration_commits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HAIFA_HOME", str(tmp_path))
    marker = tmp_path / migration_guard.MARKER
    marker.write_text(json.dumps({"state": "prepared"}))
    calls: list[str] = []

    async def scenario() -> None:
        task = asyncio.create_task(monitoring.once(lambda: calls.append("checked")))
        await asyncio.sleep(0.05)
        assert calls == []
        marker.unlink()
        await asyncio.wait_for(task, timeout=2)

    asyncio.run(scenario())
    assert calls == ["checked"]
