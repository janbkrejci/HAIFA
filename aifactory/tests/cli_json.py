"""Read the ``--json`` envelope of a CLI call and check it against the envelope rules."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import pytest

from aifactory.cli import main
from aifactory.skill import envelope_problems


def read_envelope(capsys: pytest.CaptureFixture[str]) -> Any:
    """The envelope on stdout; fails the test when it breaks a rule."""
    obj = json.loads(capsys.readouterr().out)
    assert envelope_problems(obj) == []
    return obj


def run_json(capsys: pytest.CaptureFixture[str], argv: Sequence[str]) -> tuple[int, Any]:
    """Run ``factory argv`` and return (exit code, envelope); ``ok`` must match the code."""
    rc = main(list(argv))
    obj = read_envelope(capsys)
    assert obj["ok"] == (rc == 0)
    return rc, obj
