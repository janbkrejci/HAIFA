"""Parse YAML with libyaml when PyYAML ships it, else with the pure-Python parser.

The C parser is several times faster. It matters on Windows, where the dashboard and
every run parse every backlog header and configuration file.
"""

from __future__ import annotations

from typing import Any

import yaml

LOADER: type[yaml.SafeLoader] = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def safe_load(stream: str | bytes) -> Any:
    """``yaml.safe_load`` through the fastest available safe loader."""
    return yaml.load(stream, Loader=LOADER)  # noqa: S506 - LOADER is a safe loader
