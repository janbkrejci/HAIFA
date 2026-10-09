"""A model missing from the cached ``pi --list-models`` listing is looked up again."""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from aifactory.engine import agent_pi

HEADER = "provider  model  context  max-out  thinking  images\n"


def test_resolve_rereads_a_stale_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    listings = [
        HEADER + "openrouter  nvidia/nemotron-3-super:free  262.1K  32K  yes  no\n",
        HEADER + "openrouter  nvidia/nemotron-3-ultra:free  1M  65.5K  yes  no\n",
    ]

    def run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, stdout=listings.pop(0), stderr="")

    monkeypatch.setattr("aifactory.engine.agent_pi.subprocess.run", run)
    agent_pi._pi_catalog.cache_clear()
    try:
        agent_pi._pi_catalog()  # the dashboard cached the first, partial listing
        assert agent_pi.resolve_model("openrouter/nvidia/nemotron-3-ultra:free") == (
            "openrouter",
            "nvidia/nemotron-3-ultra:free",
        )
    finally:
        agent_pi._pi_catalog.cache_clear()
