"""What the fake agents do per task in ``--remote local``: envelopes and file edits.

The code the fake builder writes really passes (or, for the first build of
slugify, really fails the hidden test of ``validation.hidden``) ``just test``
of the sandbox: the code steps (test, commit, changes, rebase) run for real
through the engine. Edits are anchored on lines of the template, so a task
still applies on a base that already has another task merged.

Forced repair rounds: every run's reviewer first rejects (the validation rule
of the sandbox's reviewer prompt, ``REVIEW_RULE_MARKER`` missing), the builder
revises by appending the marker to the first file of the task's ``writes``, and
the reviewer approves. Slugify's first build misses the hidden requirement
(``slugify("!!!") == "x-empty"``), so ``test_1`` fails and ``fix`` runs.

F2 (``validation.f2_backlog``): one script per task, and for ``task run
M04-S01-T02 --auto`` (one process, two runs) the queues of both tasks of the
chain one after the other (``chain_script``).

The fake tester plans one check, the sandbox's ``just test`` (full coverage),
for ``test_plan``, again after every fix and for ``replan_1`` after the forced
revision. Every plan has the same check, so ``plan_keeps_checks`` passes.

Envelope fields follow ``aifactory.engine.data_types`` (PlanOutput,
BuildOutput, TestPlanOutput, ReviewOutput, DocumentOutput).
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

from validation import f2_backlog
from validation.fake import OUTPUT
from validation.sandbox import TEMPLATE_DIR

REVIEW_RULE_MARKER = "# haifa-validate: revised"
CLI_ANCHOR = "    # commands: each command is one `if` below this line\n"
ALL_EMPTY = "__all__: list[str] = []"
MATHX = "src/sandbox/mathx.py"
TEXT = "src/sandbox/text.py"
CLI = "src/sandbox/cli.py"
BREACH_FILE = "B1-breach.md"
# file stems of the task files: specs/<stem>.md and app_docs/<stem>.md are the paths
# a task run's write guard allows for the plan and the write-up. The fake planner and
# documenter do not use them: they write to `@output`, the path the rendered prompt names.
TASK_STEMS: dict[str, str] = {
    "M01-S01-T01": "M01-S01-T01-clamp",
    "M01-S01-T02": "M01-S01-T02-lerp",
    "M01-S01-T03": "M01-S01-T03-sign",
    "M01-S02-T01": "M01-S02-T01-slugify",
    "M01-S02-T02": "M01-S02-T02-truncate",
    "M02-S01-T01": "M02-S01-T01-greet",
    "M02-S01-T02": "M02-S01-T02-version",
    **f2_backlog.TASK_STEMS,
}

CLAMP = '''

def clamp(x: float, lo: float, hi: float) -> float:
    """`x` limited to the closed interval [lo, hi]."""
    return max(lo, min(hi, x))
'''
LERP = '''

def lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation between `a` (t=0) and `b` (t=1)."""
    return a + (b - a) * t
'''
SIGN = '''

def sign(x: float) -> int:
    """-1, 0 or 1 by the sign of `x`."""
    return (x > 0) - (x < 0)
'''
SLUGIFY = '''

def slugify(text: str) -> str:
    """`text` lowercased, without diacritics and punctuation, words joined by hyphens."""
    import re
    import unicodedata

    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return "-".join(re.findall(r"[a-z0-9]+", plain.lower()))
'''
SLUGIFY_RETURN = '    return "-".join(re.findall(r"[a-z0-9]+", plain.lower()))\n'
SLUGIFY_RETURN_FIXED = """\
    slug = "-".join(re.findall(r"[a-z0-9]+", plain.lower()))
    return slug or "x-empty"
"""
TRUNCATE = '''

def truncate(text: str, n: int) -> str:
    """`text` cut to at most `n` characters, ending with an ellipsis when cut."""
    if len(text) <= n:
        return text
    return text[: n - 1] + "…"
'''
TRUNCATE_TAIL = '    return text[: n - 1] + "…"\n'
TRUNCATE_TAIL_RETURNED = """\
    if n < 1:
        return ""
    return text[: n - 1].rstrip() + "…"
"""
VERSION_CLI = """\
    if args[:1] == ["--version"]:
        from sandbox import __version__

        print(__version__)
        return 0
"""
GREET_CLI = """\
    if args[:1] == ["greet"] and len(args) == 2:
        print(greet(args[1]))
        return 0
"""
GREET = '''

def greet(name: str) -> str:
    """The greeting for `name`, with the name slugified."""
    from sandbox.text import slugify

    return f"Hello, {slugify(name)}!"
'''


def _ok(summary: str, **fields: Any) -> dict[str, Any]:
    return {"status": "success", "summary": summary, **fields}


def _plan(task_id: str, text: str) -> dict[str, Any]:
    spec = OUTPUT
    return {
        "envelope": _ok(f"planned {task_id}", artifacts=[spec], commit_message=f"Plan {task_id}"),
        "edits": [{"path": spec, "write": f"# Plan {task_id}\n\n{text}\n"}],
    }


def _build(summary: str, edits: list[dict[str, Any]], message: str) -> dict[str, Any]:
    files = sorted({str(e["path"]) for e in edits})
    return {
        "envelope": _ok(summary, changed_files=files, commit_message=message),
        "edits": edits,
    }


TEST_CHECK = {"name": "test", "argv": ["just", "test"]}


def test_plan(task_id: str) -> dict[str, Any]:
    """The fake tester's plan: the sandbox's whole suite (``just test``)."""
    envelope = _ok(
        f"the suite covers {task_id}",
        coverage="full",
        reason="the sandbox has one small suite; it covers the change",
        checks=[dict(TEST_CHECK)],
    )
    return {"envelope": envelope, "edits": []}


def revise_edit(path: str) -> dict[str, Any]:
    """The revision the validation reviewer asks for in its first round."""
    return {"path": path, "append": f"{REVIEW_RULE_MARKER}\n"}


def _revise(path: str) -> dict[str, Any]:
    return _build("added the line the review asked for", [revise_edit(path)], "Address the review")


def rejection(path: str) -> dict[str, Any]:
    """The first-round envelope of the validation reviewer (passes ``verdict_consistent``)."""
    return _ok(
        "0 of 1 requirements met: the validation rule is not satisfied",
        approved=False,
        blocking=[f"Add the line `{REVIEW_RULE_MARKER}` at the end of {path}."],
        findings=[{"requirement": "validation rule", "met": False, "evidence": "marker missing"}],
    )


def _reviews(task_id: str, path: str) -> list[dict[str, Any]]:
    approve = _ok(
        f"{task_id} matches the plan",
        approved=True,
        findings=[{"requirement": "validation rule", "met": True, "evidence": path}],
    )
    return [{"envelope": rejection(path), "edits": []}, {"envelope": approve, "edits": []}]


def _document(task_id: str, text: str) -> dict[str, Any]:
    doc = OUTPUT
    return {
        "envelope": _ok(
            f"documented {task_id}",
            artifacts=[doc],
            document_path=doc,
            commit_message=f"Document {task_id}",
        ),
        "edits": [{"path": doc, "write": f"# {task_id}\n\n{text}\n"}],
    }


def _script(
    task_id: str,
    revised: str,
    builds: list[dict[str, Any]],
    plan: str = "Implement the task as written.",
    doc: str = "What changed and why.",
) -> dict[str, Any]:
    """Planner, the builds, the forced revision of `revised`, two reviews, the test
    plans (``test_plan``, one after every fix, ``replan_1``), documenter."""
    return {
        "task": task_id,
        "agents": {
            "planner": [_plan(task_id, plan)],
            "builder": [*builds, _revise(revised)],
            # test_plan, one plan after every fix, and replan_1 after the revision
            "tester": [test_plan(task_id) for _ in range(len(builds) + 1)],
            "reviewer": _reviews(task_id, revised),
            "documenter": [_document(task_id, doc)],
        },
    }


def _clamp_edits() -> list[dict[str, Any]]:
    return [
        {"path": MATHX, "replace": [ALL_EMPTY, '__all__: list[str] = ["clamp"]']},
        {"path": MATHX, "append": CLAMP},
    ]


def _lerp_edits() -> list[dict[str, Any]]:
    return [
        {"path": MATHX, "replace": [ALL_EMPTY, '__all__: list[str] = ["lerp"]']},
        {"path": MATHX, "append": LERP},
    ]


def _clamp() -> dict[str, Any]:
    return _script("M01-S01-T01", MATHX, [_build("added clamp", _clamp_edits(), "Add clamp")])


def _lerp() -> dict[str, Any]:
    return _script("M01-S01-T02", MATHX, [_build("added lerp", _lerp_edits(), "Add lerp")])


def resolved_mathx() -> str:
    """``mathx.py`` with clamp and lerp and both revision markers, built from the edits."""
    text = (TEMPLATE_DIR / MATHX).read_text(encoding="utf-8")
    text = text.replace(ALL_EMPTY, '__all__: list[str] = ["clamp", "lerp"]', 1)
    return text + CLAMP + f"{REVIEW_RULE_MARKER}\n" + LERP + f"{REVIEW_RULE_MARKER}\n"


def _lerp_resolve() -> dict[str, Any]:
    edits: list[dict[str, Any]] = [{"path": MATHX, "write": resolved_mathx()}]
    resolve = {
        "envelope": _ok(
            "kept clamp and lerp, both in __all__",
            changed_files=[MATHX],
            commit_message="Resolve the mathx.py conflict with clamp",
        ),
        "edits": edits,
    }
    return {
        "task": "M01-S01-T02",
        "agents": {"builder": [resolve], "tester": [test_plan("M01-S01-T02")]},
    }


def _slugify_with_repair() -> dict[str, Any]:
    build: list[dict[str, Any]] = [{"path": TEXT, "append": SLUGIFY}]
    fix: list[dict[str, Any]] = [{"path": TEXT, "replace": [SLUGIFY_RETURN, SLUGIFY_RETURN_FIXED]}]
    return _script(
        "M01-S02-T01",
        TEXT,
        [
            _build("added slugify", build, "Add slugify"),
            _build("an empty slug becomes x-empty", fix, "Fix slugify of empty text"),
        ],
    )


def _truncate() -> dict[str, Any]:
    edits: list[dict[str, Any]] = [{"path": TEXT, "append": TRUNCATE}]
    return _script("M01-S02-T02", TEXT, [_build("added truncate", edits, "Add truncate")])


def _truncate_returned() -> dict[str, Any]:
    edits: list[dict[str, Any]] = [
        {"path": TEXT, "replace": [TRUNCATE_TAIL, TRUNCATE_TAIL_RETURNED]}
    ]
    return _script(
        "M01-S02-T02",
        TEXT,
        [_build("truncate handles n < 1", edits, "Handle n < 1 in truncate")],
        plan="Revision after review: handle n < 1 and trailing spaces.",
        doc="truncate after the review: n < 1 gives an empty string.",
    )


def _version() -> dict[str, Any]:
    edits: list[dict[str, Any]] = [
        {"path": "src/sandbox/__init__.py", "append": '\n__version__ = "0.1.0"\n'},
        {"path": CLI, "replace": [CLI_ANCHOR, CLI_ANCHOR + VERSION_CLI]},
    ]
    return _script("M02-S01-T02", CLI, [_build("added --version", edits, "Add --version")])


def _greet() -> dict[str, Any]:
    edits: list[dict[str, Any]] = [
        {"path": CLI, "replace": [CLI_ANCHOR, CLI_ANCHOR + GREET_CLI]},
        {"path": CLI, "replace": ["\n\ndef main(", GREET.rstrip("\n") + "\n\n\ndef main("]},
    ]
    return _script("M02-S01-T01", CLI, [_build("added greet", edits, "Add greet")])


def _sign_breach(repo: Path | None) -> dict[str, Any]:
    """B1: a legal change of mathx.py plus writes into the main checkout (absolute paths)."""
    if repo is None:
        raise ValueError("the breach script needs the main checkout (repo=...)")
    edits: list[dict[str, Any]] = [
        {"path": MATHX, "append": SIGN + '\n__all__.append("sign")\n'},
        {"path": str(repo / BREACH_FILE), "write": "written outside the worktree\n"},
        {"path": str(repo / "README.md"), "append": "\nB1: written outside the worktree\n"},
    ]
    build = {
        "envelope": _ok("added sign", changed_files=[MATHX], commit_message="Add sign"),
        "edits": edits,
    }
    return {
        "task": "M01-S01-T03",
        "agents": {"planner": [_plan("M01-S01-T03", "Add sign.")], "builder": [build]},
    }


def _f2(task_id: str) -> dict[str, Any]:
    task = f2_backlog.BY_ID[task_id]
    edits: list[dict[str, Any]] = list(f2_backlog.edits_for(task_id))
    build = _build(f"added {task.title}", edits, f"Add {task.slug}")
    return _script(task_id, task.writes[0], [build])


def chain_script(*scripts: dict[str, Any]) -> dict[str, Any]:
    """One script for a ``--auto`` chain: the agent queues of `scripts` one after another."""
    agents: dict[str, list[Any]] = {}
    for script in scripts:
        for agent, queue in script["agents"].items():
            agents.setdefault(agent, []).extend(queue)
    return {"task": scripts[0]["task"], "agents": agents}


def _f2_auto() -> dict[str, Any]:
    return chain_script(*(_f2(t) for t in f2_backlog.AUTO_CHAIN))


_SCRIPTS: dict[tuple[str, str], Callable[[], dict[str, Any]]] = {
    ("M01-S01-T01", "happy"): _clamp,
    ("M01-S01-T02", "happy"): _lerp,
    ("M01-S01-T02", "resolve"): _lerp_resolve,
    ("M01-S02-T01", "slugify_with_repair"): _slugify_with_repair,
    ("M01-S02-T02", "happy"): _truncate,
    ("M01-S02-T02", "return"): _truncate_returned,
    ("M02-S01-T01", "happy"): _greet,
    ("M02-S01-T02", "happy"): _version,
    **{(t, "happy"): partial(_f2, t) for t in f2_backlog.ALL},
    (f2_backlog.AUTO_START, "auto"): _f2_auto,
}


def script_for(task_id: str, variant: str = "happy", repo: Path | None = None) -> dict[str, Any]:
    """The fake script of one ``factory`` command running `task_id`."""
    if (task_id, variant) == ("M01-S01-T03", "breach"):
        return _sign_breach(repo)
    try:
        return _SCRIPTS[(task_id, variant)]()
    except KeyError:
        raise KeyError(f"no fake script for {task_id} ({variant})") from None
