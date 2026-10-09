"""The sample backlog of scenario F2 and what its fake builders write.

Two new modules (M03 units, M04 stats) with five tasks and dependencies, one
of them on a task of the other module. The containers (``index.md``) are
written directly (the CLI cannot create modules or steps), the tasks through
``factory task add`` (``add_argv``). The code fragments really pass ``just
test`` of the sandbox, in any merge order the scenario uses.

No imports from ``validation.context``, ``validation.scenarios`` or
``validation.fake_scripts``: they import this module.
"""

from __future__ import annotations

from dataclasses import dataclass

STEP_DIRS: dict[str, str] = {
    "M03-S01": "backlog/M03-units/S01-temperature",
    "M04-S01": "backlog/M04-stats/S01-summary",
}
BACKLOG_DIRS: tuple[str, ...] = ("backlog/M03-units", "backlog/M04-stats")

CONTAINERS: dict[str, str] = {
    "backlog/M03-units/index.md": """\
---
id: M03
title: Unit conversions
workflow: simple-sdlc
source: src/sandbox/
target: src/sandbox/
---

Unit conversions of the sandbox package (validation scenario F2).
""",
    "backlog/M03-units/S01-temperature/index.md": """\
---
id: M03-S01
title: Temperature
---

Temperature conversions in `src/sandbox/units.py`.
""",
    "backlog/M04-stats/index.md": """\
---
id: M04
title: Statistics
workflow: simple-sdlc
source: src/sandbox/
target: src/sandbox/
---

Small statistics of the sandbox package (validation scenario F2).
""",
    "backlog/M04-stats/S01-summary/index.md": """\
---
id: M04-S01
title: Summary
---

Summary statistics in `src/sandbox/stats.py` and a report built on them.
""",
}

_TAIL = (
    " Done when `just test` passes. Constraints: standard library only, at most 40 changed lines."
)


@dataclass(frozen=True)
class F2Task:
    id: str
    step: str
    slug: str
    title: str
    writes: tuple[str, ...]
    depends_on: tuple[str, ...]
    body: str

    @property
    def stem(self) -> str:
        return f"{self.id}-{self.slug}"

    @property
    def path(self) -> str:
        return f"{STEP_DIRS[self.step]}/{self.stem}.md"


UNITS_PY = "src/sandbox/units.py"
UNITS_TEST_PY = "tests/test_units.py"
STATS_PY = "src/sandbox/stats.py"
STATS_TEST_PY = "tests/test_stats.py"
REPORT_PY = "src/sandbox/report.py"
REPORT_TEST_PY = "tests/test_report.py"

TASKS: tuple[F2Task, ...] = (
    F2Task(
        "M03-S01-T01",
        "M03-S01",
        "c-to-f",
        "Celsius to Fahrenheit",
        (UNITS_PY, UNITS_TEST_PY),
        (),
        "Create `src/sandbox/units.py` with `c_to_f(celsius: float) -> float` "
        "(`celsius * 9 / 5 + 32`) and `tests/test_units.py` with a `CToFTest` "
        "(`c_to_f(0) == 32`, `c_to_f(100) == 212`)." + _TAIL,
    ),
    F2Task(
        "M03-S01-T02",
        "M03-S01",
        "f-to-c",
        "Fahrenheit to Celsius",
        (UNITS_PY, UNITS_TEST_PY),
        ("M03-S01-T01",),
        "Add `f_to_c(fahrenheit: float) -> float` (`(fahrenheit - 32) * 5 / 9`) to "
        "`src/sandbox/units.py` and a `FToCTest` to `tests/test_units.py` "
        "(`f_to_c(32) == 0`, `f_to_c(212) == 100`)." + _TAIL,
    ),
    F2Task(
        "M04-S01-T01",
        "M04-S01",
        "mean",
        "mean",
        (STATS_PY, STATS_TEST_PY),
        (),
        "Create `src/sandbox/stats.py` with `mean(values: list[float]) -> float` "
        "(`ValueError` for an empty list) and `tests/test_stats.py` with a `MeanTest`." + _TAIL,
    ),
    F2Task(
        "M04-S01-T02",
        "M04-S01",
        "median",
        "median",
        (STATS_PY, STATS_TEST_PY),
        ("M04-S01-T01",),
        "Add `median(values: list[float]) -> float` to `src/sandbox/stats.py`: the middle "
        "item of the sorted list, the mean of the two middle items for an even length, "
        "`ValueError` for an empty list. Add a `MedianTest` to `tests/test_stats.py`." + _TAIL,
    ),
    F2Task(
        "M04-S01-T03",
        "M04-S01",
        "report",
        "mean in Fahrenheit",
        (REPORT_PY, REPORT_TEST_PY),
        ("M03-S01-T01", "M04-S01-T01"),
        "Create `src/sandbox/report.py` with `mean_fahrenheit(celsius: list[float]) -> float` "
        "(`c_to_f(mean(celsius))`, using `sandbox.units` and `sandbox.stats`) and "
        "`tests/test_report.py` with a `ReportTest` "
        "(`mean_fahrenheit([0, 100]) == 122`)." + _TAIL,
    ),
)

BY_ID: dict[str, F2Task] = {t.id: t for t in TASKS}
TASK_PATHS: dict[str, str] = {t.id: t.path for t in TASKS}
TASK_STEMS: dict[str, str] = {t.id: t.stem for t in TASKS}

PARALLEL: tuple[str, str] = ("M03-S01-T01", "M04-S01-T01")
AUTO_START = "M04-S01-T02"
AUTO_CHAIN: tuple[str, str] = ("M04-S01-T02", "M04-S01-T03")
LAST = "M03-S01-T02"
ALL: tuple[str, ...] = tuple(t.id for t in TASKS)


def add_argv(task: F2Task) -> list[str]:
    """``factory task add`` arguments of `task` (without ``--repo`` and ``--json``)."""
    argv = ["task", "add", task.step, task.title, "--id", task.id, "--slug", task.slug]
    argv += ["--writes", *task.writes]
    if task.depends_on:
        argv += ["--depends-on", *task.depends_on]
    return [*argv, "--body", task.body]


# ── what the fake builders write ─────────────────────────────────────────────

UNITS = '''"""Unit conversions."""


def c_to_f(celsius: float) -> float:
    """Degrees Celsius in degrees Fahrenheit."""
    return celsius * 9 / 5 + 32
'''
UNITS_TEST = """import unittest

from sandbox import units


class CToFTest(unittest.TestCase):
    def test_c_to_f(self) -> None:
        self.assertEqual(units.c_to_f(0), 32)
        self.assertEqual(units.c_to_f(100), 212)
"""
F_TO_C = '''

def f_to_c(fahrenheit: float) -> float:
    """Degrees Fahrenheit in degrees Celsius."""
    return (fahrenheit - 32) * 5 / 9
'''
F_TO_C_TEST = """

class FToCTest(unittest.TestCase):
    def test_f_to_c(self) -> None:
        self.assertEqual(units.f_to_c(32), 0)
        self.assertEqual(units.f_to_c(212), 100)
"""
STATS = '''"""Summary statistics."""


def mean(values: list[float]) -> float:
    """The arithmetic mean of `values`; ValueError when empty."""
    if not values:
        raise ValueError("mean of an empty list")
    return sum(values) / len(values)
'''
STATS_TEST = """import unittest

from sandbox import stats


class MeanTest(unittest.TestCase):
    def test_mean(self) -> None:
        self.assertEqual(stats.mean([1, 2, 3, 4]), 2.5)
        with self.assertRaises(ValueError):
            stats.mean([])
"""
MEDIAN = '''

def median(values: list[float]) -> float:
    """The middle value of `values` (mean of the two middle ones); ValueError when empty."""
    if not values:
        raise ValueError("median of an empty list")
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2
'''
MEDIAN_TEST = """

class MedianTest(unittest.TestCase):
    def test_median(self) -> None:
        self.assertEqual(stats.median([3, 1, 2]), 2)
        self.assertEqual(stats.median([4, 1, 3, 2]), 2.5)
        with self.assertRaises(ValueError):
            stats.median([])
"""
REPORT = '''"""Reports built on the units and stats helpers."""

from sandbox.stats import mean
from sandbox.units import c_to_f


def mean_fahrenheit(celsius: list[float]) -> float:
    """The mean of `celsius` in degrees Fahrenheit."""
    return c_to_f(mean(celsius))
'''
REPORT_TEST = """import unittest

from sandbox import report


class ReportTest(unittest.TestCase):
    def test_mean_fahrenheit(self) -> None:
        self.assertEqual(report.mean_fahrenheit([0, 100]), 122)
"""

_EDITS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "M03-S01-T01": ((UNITS_PY, "write", UNITS), (UNITS_TEST_PY, "write", UNITS_TEST)),
    "M03-S01-T02": ((UNITS_PY, "append", F_TO_C), (UNITS_TEST_PY, "append", F_TO_C_TEST)),
    "M04-S01-T01": ((STATS_PY, "write", STATS), (STATS_TEST_PY, "write", STATS_TEST)),
    "M04-S01-T02": ((STATS_PY, "append", MEDIAN), (STATS_TEST_PY, "append", MEDIAN_TEST)),
    "M04-S01-T03": ((REPORT_PY, "write", REPORT), (REPORT_TEST_PY, "write", REPORT_TEST)),
}


def edits_for(task_id: str) -> list[dict[str, str]]:
    """The build edits of `task_id` (``fake.apply_edits`` format)."""
    return [{"path": path, kind: text} for path, kind, text in _EDITS[task_id]]
