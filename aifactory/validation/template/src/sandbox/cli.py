"""Command line of the sandbox package: `python3 -m sandbox.cli ...`."""

from __future__ import annotations

import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command and return its exit code."""
    args = list(sys.argv[1:] if argv is None else argv)
    # commands: each command is one `if` below this line
    if not args:
        return 0
    print(f"unknown command: {args[0]}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
