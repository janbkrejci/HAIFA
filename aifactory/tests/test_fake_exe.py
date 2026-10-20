"""Portable fake programs keep their scripts isolated and their Windows launchers reusable."""

import subprocess
import sys
from pathlib import Path

import pytest

from fake_exe import _windows_launcher, make_executable


@pytest.mark.parametrize("python", [True, False])
def test_launchers_share_bytes_but_run_their_own_script(tmp_path: Path, python: bool) -> None:
    executables = []
    for name in ("first", "second"):
        folder = tmp_path / f"{name} with spaces"
        folder.mkdir()
        script = folder / "fake.tool"
        if python:
            body = f"#!/usr/bin/env python3\nimport sys\nprint({name!r}, sys.argv[1])\n"
        else:
            body = f'#!/bin/sh\nprintf "%s %s\\n" "{name}" "$1"\n'
        script.write_text(body, encoding="utf-8", newline="\n")
        _windows_launcher.cache_clear()
        executable = make_executable(script)
        result = subprocess.run(
            [str(executable), "argument with spaces"], capture_output=True, text=True, check=True
        )
        assert result.stdout.strip() == f"{name} argument with spaces"
        executables.append(executable)
    if sys.platform == "win32":
        assert executables[0].read_bytes() == executables[1].read_bytes()
