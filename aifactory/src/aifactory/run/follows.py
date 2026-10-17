"""What the agents of a task with ``follows`` learn about the done task it continues.

``followed_task`` gathers the direct predecessor: its task text, its spec and
documentation from base, its pull request (URL and merge commit), the files its
change touched and its runs. ``followed_section`` renders that as a section of the
task prompt every phase gets. A text longer than ``TEXT_LIMIT`` is cut and the
section names the file in the worktree that holds all of it; the changed files and
the runs are capped the same way. Older generations of a ``follows`` chain are
listed only as references (id, title, task file, spec, documentation).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from aifactory.backlog import Backlog, Task
from aifactory.config import ProjectSettings
from aifactory.providers import git as provider_git
from aifactory.run.scope import OutputPaths, output_paths
from aifactory.run.store import SUCCEEDED, TaskPrRow, TaskRunRow, TaskRunStore

# characters of one text (task text, spec, documentation) put into the prompt
TEXT_LIMIT = 6000
# changed files listed in the prompt
FILES_LIMIT = 100
# runs listed in the prompt, newest first
RUNS_LIMIT = 10
# characters of a run's error in the run summary
ERROR_LIMIT = 200


@dataclass(frozen=True)
class FollowedTask:
    """The done task a task continues, with what its agents should know about it."""

    task: Task
    outputs: OutputPaths
    # spec and documentation text in base; None: the file is not there (or not read)
    spec_text: str | None = None
    doc_text: str | None = None
    pr: TaskPrRow | None = None
    # files the original change touched; None: unknown
    changed: tuple[str, ...] | None = None
    # the command that lists them, for when the list is cut
    changed_command: str | None = None
    runs: tuple[TaskRunRow, ...] = ()
    # older generations of the chain, the predecessor's own predecessor first
    older: tuple[tuple[Task, OutputPaths], ...] = field(default_factory=tuple)


def _file_at(main: Path, commit: str, path: str) -> str | None:
    try:
        proc = provider_git.run_bytes(main, ["show", f"{commit}:{path}"])
    except OSError:
        return None
    return proc.stdout.decode("utf-8", "replace") if proc.returncode == 0 else None


def _changed_files(
    main: Path, pr: TaskPrRow | None, runs: tuple[TaskRunRow, ...]
) -> tuple[tuple[str, ...] | None, str | None]:
    """The files of the merged change (merge commit vs. its first parent), else of the
    newest succeeded run's branch; with the git command that lists them."""
    candidates: list[tuple[str, ...]] = []
    if pr is not None and pr.merge_sha:
        candidates.append(("diff", "--name-only", f"{pr.merge_sha}^1", pr.merge_sha))
    run = next((r for r in runs if r.state == SUCCEEDED and r.head_sha), None)
    if run is not None:
        candidates.append(("diff", "--name-only", f"{run.base_sha}...{run.head_sha}"))
    for argv in candidates:
        try:
            out = provider_git.git(main, *argv)
        except (OSError, RuntimeError):
            continue
        return tuple(line for line in out.splitlines() if line), f"git {' '.join(argv)}"
    return None, None


def _older(
    backlog: Backlog, origin: Task, settings: ProjectSettings
) -> list[tuple[Task, OutputPaths]]:
    chain: list[tuple[Task, OutputPaths]] = []
    seen = {origin.id}
    current = origin
    while current.follows is not None and current.follows not in seen:
        node = backlog.by_id.get(current.follows)
        if not isinstance(node, Task):
            break
        seen.add(node.id)
        chain.append((node, output_paths(node, settings)))
        current = node
    return chain


def followed_task(
    backlog: Backlog,
    task: Task,
    settings: ProjectSettings,
    *,
    main: Path | None = None,
    commit: str | None = None,
    store: TaskRunStore | None = None,
) -> FollowedTask | None:
    """The task `task` follows (``follows``), if it exists.

    With `main` and `commit` the spec and documentation are read from that commit;
    with `store` (and `main`) the PR, the changed files and the runs come from the
    trace DB and git.
    """
    if task.follows is None:
        return None
    node = backlog.by_id.get(task.follows)
    if not isinstance(node, Task):
        return None
    outputs = output_paths(node, settings)
    spec_text = doc_text = None
    if main is not None and commit is not None:
        spec_text = _file_at(main, commit, outputs.spec)
        doc_text = _file_at(main, commit, outputs.doc)
    pr: TaskPrRow | None = None
    runs: tuple[TaskRunRow, ...] = ()
    changed: tuple[str, ...] | None = None
    command: str | None = None
    if store is not None:
        prs = store.prs_for_task(node.id)
        pr = next((p for p in prs if p.state == "merged"), prs[0] if prs else None)
        runs = tuple(store.for_task(node.id))
        if main is not None:
            changed, command = _changed_files(main, pr, runs)
    return FollowedTask(
        task=node,
        outputs=outputs,
        spec_text=spec_text,
        doc_text=doc_text,
        pr=pr,
        changed=changed,
        changed_command=command,
        runs=runs,
        older=tuple(_older(backlog, node, settings)),
    )


def _text_block(title: str, path: str, text: str | None) -> list[str]:
    if text is None:
        return [f"### {title} ({path})", "", "(not in base)", ""]
    text = text.strip()
    lines = [f"### {title} ({path})", ""]
    if len(text) > TEXT_LIMIT:
        lines += [
            text[:TEXT_LIMIT].rstrip(),
            "",
            f"[cut after {TEXT_LIMIT} of {len(text)} characters; read the whole text in "
            f"{path} in the working directory]",
        ]
    else:
        lines.append(text or "(empty)")
    return [*lines, ""]


def _run_line(run: TaskRunRow) -> str:
    when = run.started_at[:16].replace("T", " ")
    parts = [f"- {when} · run {run.run_id} · workflow {run.workflow or '-'} · {run.state}"]
    if run.branch:
        parts.append(f"branch {run.branch}")
    line = " · ".join(parts)
    if run.error:
        error = " ".join(run.error.split())
        if len(error) > ERROR_LIMIT:
            error = error[:ERROR_LIMIT].rstrip() + "…"
        line += f" · error: {error}"
    return line


def followed_section(followed: FollowedTask) -> str:
    """The prompt section about the done task `followed` describes."""
    origin, outputs = followed.task, followed.outputs
    lines = [
        f"## Original task {origin.id}: {origin.title}",
        "",
        f"This task continues {origin.id}, which is done. What it asked for, how it was "
        "specified and documented and what its change did:",
        "",
        f"- task file: {origin.path}",
        f"- spec file: {outputs.spec}",
        f"- documentation file: {outputs.doc}",
    ]
    pr = followed.pr
    if pr is not None:
        lines.append(f"- pull request: {pr.url} ({pr.state})")
        if pr.merge_sha:
            lines.append(f"- merge commit: {pr.merge_sha}")
    else:
        lines.append("- pull request: none recorded")
    lines.append("")
    lines += _text_block("Task text", origin.path, origin.body)
    if followed.spec_text is not None or followed.doc_text is not None:
        lines += _text_block("Spec", outputs.spec, followed.spec_text)
        lines += _text_block("Documentation", outputs.doc, followed.doc_text)
    if followed.changed is not None:
        changed = followed.changed
        lines += [f"### Changed files ({len(changed)})", ""]
        lines += [f"- {path}" for path in changed[:FILES_LIMIT]] or ["(none)"]
        if len(changed) > FILES_LIMIT:
            lines.append(
                f"[{len(changed) - FILES_LIMIT} more; list them all with "
                f"`{followed.changed_command}` in the working directory]"
            )
        lines.append("")
    if followed.runs:
        runs = followed.runs
        lines += [f"### Runs ({len(runs)}, newest first)", ""]
        lines += [_run_line(run) for run in runs[:RUNS_LIMIT]]
        if len(runs) > RUNS_LIMIT:
            lines.append(f"[{len(runs) - RUNS_LIMIT} older runs not listed]")
        lines.append("")
    if followed.older:
        lines += [f"### Earlier tasks of the chain ({origin.id} continues them)", ""]
        for task, paths in followed.older:
            lines.append(
                f"- {task.id} — {task.title}: task file {task.path}, spec {paths.spec}, "
                f"documentation {paths.doc}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
