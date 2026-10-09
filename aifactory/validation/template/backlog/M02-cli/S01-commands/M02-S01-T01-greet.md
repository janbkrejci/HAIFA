---
id: M02-S01-T01
title: greet command
status: todo
depends_on: [M01-S02-T01]
writes: [src/sandbox/cli.py, tests/test_cli.py]
---

## Zadání
Add a function `greet(name) -> str` and a command `greet NAME` to
`src/sandbox/cli.py`. `greet("Jan Novák")` returns `Hello, jan-novak!`: the name
goes through `sandbox.text.slugify`. The command prints that line and exits 0.

Done when `just test` passes and `tests/test_cli.py::GreetTest` runs.

Constraints: standard library only, at most 40 changed lines. Needs `slugify`
from M01-S02-T01 in base.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
