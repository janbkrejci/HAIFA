"""The engine is a regular package: no ``sys.path`` tricks, no ``vendor/``."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import aifactory.engine
import aifactory.engine.runner
from aifactory.engine import loader

MODULES = (
    "runner agents session tracer permissions gates data_types chain changes quality cli "
    "models console prompts utils git_helper roles agent_cc agent_pi loader role_registry"
).split()

PROBE = f"""
import importlib, sys
from pathlib import Path
import aifactory, aifactory.engine
for name in {MODULES!r}:
    importlib.import_module("aifactory.engine." + name)
bad = [p for p in sys.path if "vendor" in p or "adw_modules" in p]
assert not bad, bad
assert "adw_modules" not in sys.modules
runner = sys.modules["aifactory.engine.runner"]
engine_dir = Path(aifactory.__file__).parent / "engine"
assert Path(runner.__file__).parent == engine_dir, runner.__file__
"""


def test_engine_imports_without_sys_path(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr


def test_loader_returns_package_modules() -> None:
    assert loader.load_engine_module("runner") is aifactory.engine.runner
    assert loader.load_engine_module("") is aifactory.engine
    assert loader.ENGINE_DIR == Path(aifactory.engine.__file__).resolve().parent
