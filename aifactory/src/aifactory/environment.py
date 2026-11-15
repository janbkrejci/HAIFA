"""GIRO settings and their supported HAIFA aliases, before env-file flattening."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from typing import TextIO

SUFFIXES = (
    "HOME",
    "LIBRARY",
    "LIBRARY_URL",
    "UPDATE_REPO",
    "DATABASE_URL",
    "DASH_HOST",
    "FACTORY_REPO",
    "RUN_ID",
    "GUIDE_REPO",
    "OBS_RESTART",
    "SANDBOX_REPO",
    "AZURE_SANDBOX_REPO",
    "VALIDATE_FAKE",
    "VALIDATE_HIDDEN",
    "E2E_CHANNEL",
    "LAUNCH_STUB",
)


def value(name: str, environ: Mapping[str, str] | None = None) -> str | None:
    """Read a pair from one layer; empty means unset, invalid values stay invalid."""
    env = os.environ if environ is None else environ
    suffix = name.removeprefix("HAIFA_").removeprefix("GIRO_")
    new, old = f"GIRO_{suffix}", f"HAIFA_{suffix}"
    if env.get(new) and env.get(old) and env[new] != env[old]:
        print(f"giro: warning: {new} conflicts with {old}; {new} wins", file=sys.stderr)
    return env.get(new) or env.get(old) or None


def resolve(
    process: Mapping[str, str],
    file: Mapping[str, str | None] | None = None,
    *,
    stderr: TextIO | None = None,
) -> dict[str, str]:
    """Normalize aliases, keeping shell precedence over either env-file spelling."""
    out = sys.stderr if stderr is None else stderr
    result = dict(process)
    settings = file or {}
    for key, item in settings.items():
        if key not in {"HOME", "XDG_CONFIG_HOME", "GIRO_HOME", "HAIFA_HOME"}:
            if item is not None and key not in result:
                result[key] = item
    for suffix in SUFFIXES:
        new, old = f"GIRO_{suffix}", f"HAIFA_{suffix}"
        layers = (process,) if suffix == "HOME" else (process, settings)
        selected = None
        for layer in layers:
            if layer.get(new) and layer.get(old) and layer[new] != layer[old]:
                print(
                    f"giro: warning: {new} conflicts with {old}; {new} wins in this layer", file=out
                )
            candidate = layer.get(new) or layer.get(old)
            if selected is None and candidate:
                # A migrated HAIFA default must never send GIRO back to HAIFA releases.
                if (
                    suffix == "UPDATE_REPO"
                    and not layer.get(new)
                    and candidate == "janbkrejci/HAIFA"
                ):
                    print(
                        "giro: warning: ignoring HAIFA_UPDATE_REPO pointing "
                        "to the retired HAIFA release source",
                        file=out,
                    )
                    selected = "janbkrejci/GIRO"
                else:
                    selected = candidate
        if selected is not None:
            result[new] = result[old] = selected
    return result


def child_environment(base: Mapping[str, str] | None = None, **overrides: str) -> dict[str, str]:
    """A child sees identical aliases; explicit per-call values replace both names."""
    env = resolve(os.environ if base is None else base)
    for key, item in overrides.items():
        suffix = key.removeprefix("HAIFA_").removeprefix("GIRO_")
        if suffix in SUFFIXES:
            env[f"GIRO_{suffix}"] = env[f"HAIFA_{suffix}"] = item
        else:
            env[key] = item
    return env
