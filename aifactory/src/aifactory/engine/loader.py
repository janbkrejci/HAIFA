"""Single entry point for loading engine modules by name.

The sssf engine lives in ``aifactory.engine`` as a regular package; nothing here
touches ``sys.path``. Kept so callers ported from the prototype can look modules
up by name (``load_engine_module("data_types")``).
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

ENGINE_PACKAGE = "aifactory.engine"
ENGINE_DIR = Path(__file__).resolve().parent


def load_engine_module(name: str) -> ModuleType:
    """Import ``aifactory.engine.<name>`` (or ``aifactory.engine`` for an empty name)."""
    full = ENGINE_PACKAGE if not name else f"{ENGINE_PACKAGE}.{name}"
    return importlib.import_module(full)
