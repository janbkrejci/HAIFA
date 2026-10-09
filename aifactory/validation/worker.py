"""``python -m validation.worker <factory argv>``: the CLI, optionally over the fake harness.

With ``HAIFA_VALIDATE_FAKE=<script.json>`` in the environment the fake harness
(``validation.fake``) is installed first; without it the real harnesses run.
With ``HAIFA_VALIDATE_HIDDEN=<dir>`` the variable is popped from ``os.environ``
(so no agent inherits it) and the hidden test gate of ``validation.hidden`` is
installed around the engine's test step. Then ``aifactory.cli.main`` gets the arguments unchanged.

Over the fake harness the worker also makes itself the command prefix of the dashboard's
run processes (``aifactory.web.launcher.set_command_prefix``) and puts the ``aifactory``
directory on ``PYTHONPATH``, so runs started by a ``factory obs`` under the worker inherit
the environment and run over the fake harness too.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from pathlib import Path

FAKE_ENV = "HAIFA_VALIDATE_FAKE"
AIFACTORY_DIR = Path(__file__).resolve().parents[1]


def _ensure_pythonpath() -> None:
    """Put the ``aifactory`` directory (home of ``validation``) first on ``PYTHONPATH``."""
    current = os.environ.get("PYTHONPATH", "")
    parts = [p for p in current.split(os.pathsep) if p]
    if str(AIFACTORY_DIR) not in parts:
        os.environ["PYTHONPATH"] = os.pathsep.join([str(AIFACTORY_DIR), *parts])


def main(argv: Sequence[str] | None = None) -> int:
    from validation.hidden import HIDDEN_ENV

    hidden_dir = os.environ.pop(HIDDEN_ENV, None)
    if hidden_dir:
        from validation import hidden

        hidden.install(Path(hidden_dir))
    script = os.environ.get(FAKE_ENV)
    if script:
        from validation import fake

        fake.install(Path(script))
        from aifactory.web import launcher

        launcher.set_command_prefix([sys.executable, "-m", "validation.worker"])
        _ensure_pythonpath()
    from aifactory import cli

    return cli.main(list(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    raise SystemExit(main())
