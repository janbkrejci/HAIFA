---
id: M02-S01-T02
title: --version
status: todo
writes: [src/sandbox/cli.py, src/sandbox/__init__.py, tests/test_cli.py]
---

## Zadání
Set `__version__ = "0.1.0"` in `src/sandbox/__init__.py` and add a `--version`
option to `src/sandbox/cli.py` that prints `sandbox.__version__` and exits 0.

Done when `just test` passes and `tests/test_cli.py::VersionTest` runs.

Constraints: standard library only, at most 40 changed lines.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
