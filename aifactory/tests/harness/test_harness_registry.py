"""The harness registry: claude, codex and pi, loaded from the package itself."""

from __future__ import annotations

import inspect
from pathlib import Path
from types import ModuleType

import pytest

import aifactory.engine
import aifactory.harness
from aifactory import harness
from aifactory.engine import agents
from aifactory.harness import codex


def test_harness_install_registers_every_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agents, "INTERFACES", dict(agents.INTERFACES))
    assert harness.install() is agents
    assert harness.install() is agents
    for name in ("claude", "codex", "pi", "claude_code"):
        assert name in agents.INTERFACES
    assert agents.INTERFACES["claude_code"] is agents.INTERFACES["claude"]
    assert agents.INTERFACES["codex"] is codex


def test_harness_install_keeps_existing_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = ModuleType("fake_codex")
    monkeypatch.setitem(agents.INTERFACES, "codex", fake)
    harness.install()
    assert agents.INTERFACES["codex"] is fake


def test_harness_canonical() -> None:
    assert harness.canonical("claude_code") == "claude"
    for name in ("claude", "codex", "pi"):
        assert harness.canonical(name) == name
    with pytest.raises(ValueError, match="unknown harness 'gpt'"):
        harness.canonical("gpt")


@pytest.mark.parametrize("name", ["claude", "pi"])
def test_harness_engine_adapters_come_from_the_package(name: str) -> None:
    module = harness.load(name)
    assert module.__file__ is not None
    assert Path(module.__file__).parent == Path(aifactory.engine.__file__).parent
    assert "vendor" not in Path(module.__file__).parts


@pytest.mark.parametrize("name", ["claude", "codex", "pi"])
def test_harness_interface(name: str) -> None:
    module = harness.load(name)
    assert harness.check_interface(module) == []
    params = inspect.signature(module.run).parameters
    for param in ("request", "on_event", "on_spawn", "on_exit", "on_wait"):
        assert param in params


def test_harness_check_interface_reports_missing() -> None:
    assert harness.check_interface(ModuleType("empty")) == list(harness.REQUIRED_API)


def test_harness_never_imports_model_inference() -> None:
    """engine.models/chain/cli derive the harness from the model name (D13 forbids it)."""
    package = Path(aifactory.harness.__file__).parent
    for source in package.glob("*.py"):
        text = source.read_text()
        for forbidden in (
            "engine.models",
            "engine.chain",
            "engine.cli",
            "from aifactory.engine import models",
            "from aifactory.engine import chain",
            "from aifactory.engine import cli",
        ):
            assert forbidden not in text, f"{source.name} mentions {forbidden}"
