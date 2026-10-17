"""Deterministic quality check of a backlog proposal (``factory backlog propose``).

Every rule works on the proposed tasks alone (plus the repo tree for paths named in a
body), so it runs before anything is written:

- ``missing_done``: the body has no section ``Hotovo znamená`` (blocking).
- ``cycle``: the dependencies among the proposed tasks form a cycle (blocking).
- ``writes_uncovered``: the body names a repo path that no entry of ``writes`` covers.
- ``writes_closed``: an entry of ``writes`` points into ``protected_files`` or the backlog,
  which no run may change.
- ``writes_overlap``: two tasks that may run at the same time (neither depends on the other,
  even transitively) have overlapping ``writes``.

Blocking findings reject the proposal like a validation error. The other findings go back
to the agent once for a correction; what is left is shown to the person in the preview.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from aifactory.run.scope import literal_prefix, matches, normalize, paths_overlap

DONE_HEADING = "Hotovo znamená"

MISSING_DONE = "missing_done"
CYCLE = "cycle"
WRITES_UNCOVERED = "writes_uncovered"
WRITES_CLOSED = "writes_closed"
WRITES_OVERLAP = "writes_overlap"
BLOCKING = frozenset({MISSING_DONE, CYCLE})

_SPAN_RE = re.compile(r"`([^`\n]+)`")
_EXTENSION_RE = re.compile(r"\.[A-Za-z0-9]{1,8}$")
_TRAILING = ".,:;)]}"


@dataclass(frozen=True)
class Candidate:
    """One proposed task; ``depends_on`` names other candidates by ``key`` or outside ids."""

    key: str
    body: str
    writes: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class Finding:
    rule: str
    task: str
    message: str

    @property
    def blocking(self) -> bool:
        return self.rule in BLOCKING

    def to_json(self) -> dict[str, object]:
        return {
            "rule": self.rule,
            "task": self.task,
            "message": self.message,
            "blocking": self.blocking,
        }


def has_done(body: str) -> bool:
    return DONE_HEADING.lower() in body.lower()


def check_done(tasks: Iterable[Candidate]) -> list[Finding]:
    return [
        Finding(MISSING_DONE, t.key, f"task '{t.key}': the body needs a section '{DONE_HEADING}:'")
        for t in tasks
        if not has_done(t.body)
    ]


def _edges(tasks: list[Candidate]) -> dict[str, list[str]]:
    keys = {t.key for t in tasks}
    return {t.key: [d for d in dict.fromkeys(t.depends_on) if d in keys] for t in tasks}


def check_cycles(tasks: list[Candidate]) -> list[Finding]:
    """One finding per cycle among the candidates (a self reference counts as a cycle)."""
    edges = _edges(tasks)
    state: dict[str, int] = {}  # 1 on the stack, 2 finished
    stack: list[str] = []
    found: list[Finding] = []
    seen: set[frozenset[str]] = set()

    def visit(node: str) -> None:
        state[node] = 1
        stack.append(node)
        for dep in edges[node]:
            if state.get(dep) == 1:
                cycle = stack[stack.index(dep) :]
                if frozenset(cycle) not in seen:
                    seen.add(frozenset(cycle))
                    path = " -> ".join([*cycle, dep])
                    found.append(Finding(CYCLE, dep, f"dependency cycle: {path}"))
            elif dep not in state:
                visit(dep)
        stack.pop()
        state[node] = 2

    for task in tasks:
        if task.key not in state:
            visit(task.key)
    return found


def _inside(prefix: str, closed: str) -> bool:
    return prefix == closed or prefix.startswith(closed + "/")


def _closed_prefixes(closed: Iterable[str]) -> list[str]:
    return [p for p in (literal_prefix(c) for c in closed) if p]


def is_closed(path: str, closed: Iterable[str]) -> bool:
    """Whether ``path`` lies inside one of the ``closed`` patterns."""
    prefix = literal_prefix(path)
    return bool(prefix) and any(_inside(prefix, c) for c in _closed_prefixes(closed))


def check_closed(tasks: Iterable[Candidate], closed: Iterable[str]) -> list[Finding]:
    """``writes`` entries inside, or containing, a protected or backlog path."""
    prefixes = _closed_prefixes(closed)
    found: list[Finding] = []
    for task in tasks:
        for write in task.writes:
            prefix = literal_prefix(write)
            if not prefix:
                continue  # the whole repo: the run's guard still keeps the closed paths
            hit = [c for c in prefixes if _inside(prefix, c) or _inside(c, prefix)]
            if hit:
                found.append(
                    Finding(
                        WRITES_CLOSED,
                        task.key,
                        f"task '{task.key}': writes '{write}' reaches '{hit[0]}', which no "
                        "run may change (protected_files or the backlog)",
                    )
                )
    return found


def named_paths(body: str, root: Path) -> list[str]:
    """Repo paths the body names in backticks: existing ones, or new files in an existing
    directory. Commands, flags, URLs, globs and placeholders are skipped."""
    found: list[str] = []
    for match in _SPAN_RE.finditer(body):
        token = normalize(match.group(1)).rstrip(_TRAILING)
        if (
            not token
            or any(c.isspace() for c in token)
            or token.startswith(("-", "/", "$", "~"))
            or any(s in token for s in ("://", "<", ">", "{", "}", "*", "?", "[", "\\"))
            or ".." in token.split("/")
        ):
            continue
        path = root / token
        if path.exists() or (
            "/" in token.rstrip("/") and _EXTENSION_RE.search(token) and path.parent.is_dir()
        ):
            found.append(token)
    return list(dict.fromkeys(found))


def _covered(path: str, writes: Iterable[str]) -> bool:
    if path.endswith("/"):  # a directory: a write inside it is enough
        return any(paths_overlap(w, path) for w in writes)
    return any(matches(path, w) for w in writes)


def check_coverage(
    tasks: Iterable[Candidate], root: Path, closed: Iterable[str] = ()
) -> list[Finding]:
    """Paths named in the body that ``writes`` does not cover (closed paths are skipped:
    the task can only mean them as a reference)."""
    closed = list(closed)
    found: list[Finding] = []
    for task in tasks:
        missing = [
            p
            for p in named_paths(task.body, root)
            if not is_closed(p, closed) and not _covered(p, task.writes)
        ]
        if missing:
            found.append(
                Finding(
                    WRITES_UNCOVERED,
                    task.key,
                    f"task '{task.key}': the body names {', '.join(missing)}, which writes "
                    "does not cover; add it to writes or drop it from the body",
                )
            )
    return found


def _reachable(edges: Mapping[str, list[str]]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for start in edges:
        seen: set[str] = set()
        todo = list(edges[start])
        while todo:
            node = todo.pop()
            if node not in seen:
                seen.add(node)
                todo.extend(edges.get(node, []))
        result[start] = seen
    return result


def check_overlap(tasks: list[Candidate]) -> list[Finding]:
    """Pairs of tasks without a dependency path between them whose ``writes`` overlap."""
    reach = _reachable(_edges(tasks))
    found: list[Finding] = []
    for i, a in enumerate(tasks):
        for b in tasks[i + 1 :]:
            if a.key == b.key or b.key in reach[a.key] or a.key in reach[b.key]:
                continue
            shared = [f"{wa} ~ {wb}" for wa in a.writes for wb in b.writes if paths_overlap(wa, wb)]
            if shared:
                found.append(
                    Finding(
                        WRITES_OVERLAP,
                        b.key,
                        f"tasks '{a.key}' and '{b.key}' can run at the same time and their "
                        f"writes overlap ({', '.join(shared)}); add a dependency or split "
                        "the writes",
                    )
                )
    return found


def check(tasks: list[Candidate], root: Path, closed: Iterable[str] = ()) -> list[Finding]:
    """Every rule, blocking findings first."""
    closed = list(closed)
    findings = [
        *check_done(tasks),
        *check_cycles(tasks),
        *check_coverage(tasks, root, closed),
        *check_closed(tasks, closed),
        *check_overlap(tasks),
    ]
    return sorted(findings, key=lambda f: not f.blocking)
