---
id: M01-S02-T02
title: truncate
status: todo
writes: [src/sandbox/text.py, tests/test_text.py]
---

## Zadání
Add `truncate(text, n)` to `src/sandbox/text.py`: text longer than `n`
characters is cut and ends with `…`, so the result has at most `n` characters.
Shorter text is returned unchanged.

Done when `just test` passes and `tests/test_text.py::TruncateTest` runs (it is
skipped until `truncate` exists).

Constraints: standard library only, at most 40 changed lines.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
