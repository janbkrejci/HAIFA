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


class _WindowsOs:
    name = "nt"

    def __getattr__(self, attribute: str) -> Any:
        import os

        return getattr(os, attribute)


def test_catalog_on_windows_without_pi_path_uses_npm_shim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shim = r"C:\Users\me\AppData\Roaming\npm\pi.cmd"
    monkeypatch.setattr(agent_pi, "os", _WindowsOs())
    monkeypatch.setattr(agent_pi, "PI_PATH", "pi")  # PI_PATH not set
    monkeypatch.setattr(
        "aifactory.engine.agent_pi.shutil.which", lambda name: shim if name == "pi" else None
    )

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[0] != shim:  # CreateProcess does not resolve a bare `pi` to pi.cmd
            raise FileNotFoundError(command[0])
        listing = HEADER + "openrouter  nvidia/nemotron-3-super:free  262.1K  32K  yes  no\n"
        return subprocess.CompletedProcess(command, 0, stdout=listing, stderr="")

    monkeypatch.setattr("aifactory.engine.agent_pi.subprocess.run", run)
    agent_pi._pi_catalog.cache_clear()
    try:
        assert agent_pi._pi_catalog() == [("openrouter", "nvidia/nemotron-3-super:free", 262_100)]
    finally:
        agent_pi._pi_catalog.cache_clear()
