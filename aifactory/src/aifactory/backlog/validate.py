"""Structural checks of a loaded backlog."""

from __future__ import annotations

from aifactory.backlog.derived import active_tasks, ancestors
from aifactory.backlog.loader import iter_nodes, iter_tasks
from aifactory.backlog.model import Backlog, Issue, Node, Task, node_file


def _check_duplicates(backlog: Backlog) -> list[Issue]:
    issues: list[Issue] = []
    first: dict[str, Node] = {}
    for node in iter_nodes(backlog):
        assert node.id is not None
        if node.id in first:
            other = first[node.id]
            issues.append(
                Issue(
                    "duplicate_id",
                    f"duplicate id '{node.id}' in {node_file(node)} "
                    f"(first defined in {node_file(other)})",
                    node_file(node),
                    node.id,
                )
            )
        else:
            first[node.id] = node
    return issues


def _check_refs(backlog: Backlog) -> list[Issue]:
    issues: list[Issue] = []
    for task in iter_tasks(backlog):
        for key, refs in (("depends_on", task.depends_on), ("related", task.related)):
            for ref in refs:
                if ref not in backlog.by_id:
                    issues.append(
                        Issue(
                            "unknown_ref",
                            f"task '{task.id}' {key} refers to unknown id '{ref}'",
                            task.path,
                            task.id,
                        )
                    )
    return issues


def _check_prefixes(backlog: Backlog) -> list[Issue]:
    issues: list[Issue] = []
    for node in iter_nodes(backlog):
        assert node.id is not None
        for ancestor in ancestors(node):
            if ancestor.id is None:
                continue
            prefix = f"{ancestor.id}-"
            if not node.id.startswith(prefix):
                issues.append(
                    Issue(
                        "id_prefix",
                        f"id '{node.id}' must start with '{prefix}' "
                        f"({ancestor.level} {ancestor.path})",
                        node_file(node),
                        node.id,
                    )
                )
    return issues


def dependency_graph(backlog: Backlog) -> dict[str, list[str]]:
    """Edges: task -> its existing dependencies, container -> its non-cancelled tasks."""
    graph: dict[str, set[str]] = {node_id: set() for node_id in backlog.by_id}
    for node_id, node in backlog.by_id.items():
        if isinstance(node, Task):
            graph[node_id].update(d for d in node.depends_on if d in backlog.by_id)
        else:
            graph[node_id].update(t.id for t in active_tasks(node))
    return {k: sorted(v) for k, v in sorted(graph.items())}


def _strongly_connected(graph: dict[str, list[str]]) -> list[list[str]]:
    """Tarjan's algorithm, iterative."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    result: list[list[str]] = []
    counter = 0

    for start in graph:
        if start in index:
            continue
        work: list[tuple[str, int]] = [(start, 0)]
        index[start] = low[start] = counter
        counter += 1
        stack.append(start)
        on_stack.add(start)
        while work:
            node, i = work[-1]
            neighbours = graph.get(node, [])
            if i < len(neighbours):
                work[-1] = (node, i + 1)
                nxt = neighbours[i]
                if nxt not in index:
                    index[nxt] = low[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, 0))
                elif nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                component: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                result.append(sorted(component))
    return result


def _cycle_path(graph: dict[str, list[str]], members: set[str], start: str) -> list[str]:
    path = [start]
    visited = {start}
    iters = [iter(graph.get(start, []))]
    while iters:
        for nxt in iters[-1]:
            if nxt == start:
                return [*path, start]
            if nxt in members and nxt not in visited:
                visited.add(nxt)
                path.append(nxt)
                iters.append(iter(graph.get(nxt, [])))
                break
        else:
            iters.pop()
            path.pop()
    return [start, start]


def _check_cycles(backlog: Backlog) -> list[Issue]:
    graph = dependency_graph(backlog)
    issues: list[Issue] = []
    for component in _strongly_connected(graph):
        start = component[0]
        if len(component) == 1 and start not in graph.get(start, []):
            continue
        cycle = _cycle_path(graph, set(component), start)
        issues.append(
            Issue(
                "cycle",
                f"dependency cycle: {' -> '.join(cycle)}",
                node_file(backlog.by_id[start]),
                start,
            )
        )
    return issues


def check_backlog(backlog: Backlog) -> list[Issue]:
    """All problems: those found while loading plus structural checks."""
    issues = [
        *backlog.issues,
        *_check_duplicates(backlog),
        *_check_refs(backlog),
        *_check_prefixes(backlog),
        *_check_cycles(backlog),
    ]
    return sorted(issues, key=lambda i: (i.path, i.code, i.message))
