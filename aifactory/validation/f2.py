"""Scenario F2: the acceptance of phase F2 on the sample repo, from the CLI only.

A sample backlog (``validation.f2_backlog``: modules M03 and M04, five tasks
with dependencies, one across modules) is created with ``factory task add``
and pushed to base. Then two tasks run at the same time, one ``task run
--auto`` runs a chain of two tasks, one more task runs alone, and all five are
approved with ``factory task approve``. Checks: five merged PRs, ``status:
done`` of all five in base, no write outside the worktrees, no leftover
worktree of the five runs and a passing ``backlog check``.

F2 depends on no other scenario (it uses its own modules), so ``--only F2``
works alone.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from validation import f2_backlog as fb
from validation.context import Cmd, Context, parse_time, run_seconds
from validation.results import ScenarioResult
from validation.sandbox import git


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _start_backlog(ctx: Context, st: F2Run) -> bool:
    """No F2 task in base yet: write the containers and add the first tasks."""
    ctx.fetch_base()
    existing = [t.id for t in fb.TASKS if _exists_in_base(ctx, t.path)]
    if existing:
        st.res.inconclusive(f"F2: tasky už v base existují: {existing}")
        return False
    for rel, text in fb.CONTAINERS.items():
        path = ctx.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return True


def _add_tasks(ctx: Context, st: F2Run, tasks: tuple[fb.F2Task, ...]) -> None:
    st.adds.extend((t.id, ctx.haifa(*fb.add_argv(t))) for t in tasks)


def _push_backlog(ctx: Context, res: ScenarioResult, adds: list[tuple[str, Cmd]]) -> str | None:
    """``backlog check``, commit and push of the five added tasks; the base sha."""
    check = ctx.haifa("backlog", "check")
    git(ctx.repo, "add", "--", *fb.BACKLOG_DIRS)
    git(ctx.repo, "commit", "-q", "-m", "F2: sample backlog (2 modules, 5 tasks)")
    git(ctx.repo, "push", "-q", "origin", f"HEAD:{ctx.base}")
    sha = ctx.fetch_base()
    if sha:
        res.commits.append(sha)
    statuses = {t: ctx.status_in_base(t) for t in fb.ALL}
    failed = [f"{t}: {c.brief()}" for t, c in adds if not c.ok]
    if not check.ok:
        failed.append(f"backlog check: {check.brief()}")
    ok = res.check(
        "backlog_created",
        not failed and all(s == "todo" for s in statuses.values()),
        f"failed {failed}; status in base {statuses}",
    )
    return sha if ok else None


def _exists_in_base(ctx: Context, rel: str) -> bool:
    return bool(
        git(ctx.repo, "ls-tree", "--name-only", f"origin/{ctx.base}", "--", rel, check=False)
    )


def _record(
    ctx: Context,
    res: ScenarioResult,
    runs: dict[str, dict[str, Any]],
    task_id: str,
    run: dict[str, Any],
    pr: dict[str, Any],
) -> None:
    runs[task_id] = {"run": run, "pr": pr}
    ctx.reference(res, str(run.get("run_id") or "") or None)
    ctx.add_pr(res, task_id, pr)


def _run_ok(run: dict[str, Any], pr: dict[str, Any], ok: bool = True) -> bool:
    return ok and run.get("state") == "succeeded" and bool(pr.get("url"))


def _approve(ctx: Context, res: ScenarioResult, task_id: str) -> Cmd:
    cmd = ctx.haifa("task", "approve", task_id)
    for _ in range(0 if ctx.local else 6):
        if cmd.error_code != "merge_failed":
            break
        time.sleep(10)
        cmd = ctx.haifa("task", "approve", task_id)
    if cmd.payload.get("merge_sha"):
        res.commits.append(str(cmd.payload["merge_sha"]))
    ctx.catch_up_base()
    return cmd


def _approve_all(ctx: Context, res: ScenarioResult, name: str, tasks: tuple[str, ...]) -> bool:
    return _approved(res, name, [(t, _approve(ctx, res, t)) for t in tasks])


def _approved(res: ScenarioResult, name: str, cmds: list[tuple[str, Cmd]]) -> bool:
    return res.check(
        name,
        all(c.ok for _, c in cmds),
        " | ".join(f"{t}: {c.brief()}" for t, c in cmds),
    )


def _parallel(ctx: Context, res: ScenarioResult, runs: dict[str, dict[str, Any]]) -> bool:
    pending = [ctx.haifa_async("task", "run", t, task=t) for t in fb.PARALLEL]
    cmds = [p.wait() for p in pending]
    for task_id, cmd in zip(fb.PARALLEL, cmds, strict=True):
        _record(ctx, res, runs, task_id, cmd.run, cmd.pr)
    ok = res.check(
        "parallel_runs_ok",
        all(_run_ok(c.run, c.pr, c.ok) for c in cmds),
        " | ".join(c.brief() for c in cmds),
    )
    rows = [ctx.task_run(str(c.run.get("run_id") or "")) for c in cmds]
    starts = [parse_time(r.get("started_at")) for r in rows]
    ends = [parse_time(r.get("ended_at")) for r in rows]
    overlap = 0.0
    if all(starts) and all(ends):
        overlap = (min(e for e in ends if e) - max(s for s in starts if s)).total_seconds()
    res.check("runs_overlapped", overlap > 0, f"overlap {overlap:.3f} s")
    res.measurements["overlap_s"] = round(overlap, 3)
    worktrees = [c.run.get("worktree") for c in cmds]
    res.check("distinct_worktrees", len(set(worktrees)) == 2 and all(worktrees), str(worktrees))
    return ok


def _auto_chain(ctx: Context, res: ScenarioResult, runs: dict[str, dict[str, Any]]) -> bool:
    cmd = ctx.run_task(fb.AUTO_START, "--auto", variant="auto")
    chain = _dict(cmd.payload.get("chain"))
    items = chain.get("runs")
    items = items if isinstance(items, list) else []
    tasks: list[str] = []
    all_ok = True
    for item in items:
        entry = _dict(item)
        run, pr = _dict(entry.get("run")), _dict(entry.get("pr"))
        task_id = str(
            run.get("task_id") or ctx.task_run(str(run.get("run_id") or "")).get("task_id", "")
        )
        tasks.append(task_id)
        _record(ctx, res, runs, task_id, run, pr)
        all_ok = all_ok and _run_ok(run, pr, entry.get("ok") is True)
    waiting = [
        str(_dict(w).get("task_id")) for w in chain.get("waiting") or [] if isinstance(w, dict)
    ]
    stop = chain.get("stop")
    res.measurements["auto_chain"] = {"tasks": tasks, "stop": stop, "waiting": waiting}
    return res.check(
        "auto_chain",
        cmd.ok and tasks == list(fb.AUTO_CHAIN) and all_ok and stop == "exhausted",
        f"{cmd.brief()}; tasks {tasks}; stop {stop}; waiting {waiting}",
    )


def _branch(entry: Any) -> str:
    run, pr = _dict(_dict(entry).get("run")), _dict(_dict(entry).get("pr"))
    return str(pr.get("branch") or run.get("branch") or "")


def _worktree_list(ctx: Context) -> set[str]:
    out = git(ctx.repo, "worktree", "list", "--porcelain", check=False)
    listed: set[str] = set()
    for line in out.splitlines():
        if line.startswith("worktree "):
            path = line.removeprefix("worktree ")
            listed.add(path)
            listed.add(str(Path(path).resolve()))
    return listed


def _final_checks(
    ctx: Context,
    res: ScenarioResult,
    runs: dict[str, dict[str, Any]],
    before_status: str,
    base_sha: str,
) -> None:
    ctx.catch_up_base()
    branches = {t: _branch(runs.get(t)) for t in fb.ALL}
    pr_states = {t: ctx.task_pr(b).get("state") if b else None for t, b in branches.items()}
    for pr in res.prs:  # evidence: the state after approve, not the one at run time
        pr["state"] = ctx.task_pr(str(pr.get("branch") or "")).get("state", pr.get("state"))
    res.check(
        "five_prs_merged",
        len({b for b in branches.values() if b}) == 5
        and all(s == "merged" for s in pr_states.values()),
        f"PR states {pr_states}",
    )

    done: dict[str, str] = {}
    for t in fb.ALL:
        header, text = ctx.task_in_base(t)
        url = str(_dict(_dict(runs.get(t)).get("pr")).get("url") or "")
        runs_part = text.split("## Běhy", 1)[1] if "## Běhy" in text else ""
        linked = bool(url) and url in runs_part
        done[t] = f"{header.get('status')}, PR in ## Běhy: {linked}"
        if header.get("status") != "done" or not linked:
            done[t] = "!" + done[t]
    res.check(
        "all_done_in_base",
        not any(v.startswith("!") for v in done.values()),
        str(done),
    )

    after_status = git(ctx.repo, "status", "--porcelain", "--untracked-files=all")
    run_ids = [str(_dict(r.get("run")).get("run_id") or "") for r in runs.values()]
    breaches = {r: len(ctx.events(r, "error", "permission_breach")) for r in run_ids if r}
    allowed = set(fb.TASK_PATHS.values())
    for task in fb.TASKS:
        allowed.update(task.writes)
        allowed.update({f"specs/{task.stem}.md", f"app_docs/{task.stem}.md"})
    changed = git(
        ctx.repo, "diff", "--name-only", f"{base_sha}..origin/{ctx.base}", check=False
    ).splitlines()
    unexpected = sorted(set(changed) - allowed)
    res.check(
        "no_write_outside_worktree",
        after_status == before_status and not any(breaches.values()) and not unexpected,
        f"status {after_status!r} (before {before_status!r}); permission_breach {breaches}; "
        f"unexpected files in base {unexpected}",
    )

    listed = _worktree_list(ctx)
    leftover = []
    for t in fb.ALL:
        wt = str(_dict(_dict(runs.get(t)).get("run")).get("worktree") or "")
        if not wt or Path(wt).exists() or wt in listed or str(Path(wt).resolve()) in listed:
            leftover.append(wt or f"{t}: no worktree")
    res.measurements["leftover_worktrees"] = leftover
    res.check("no_leftover_worktrees", not leftover, str(leftover))

    check = ctx.haifa("backlog", "check")
    res.check("backlog_check_ok", check.ok and check.code == 0, check.brief())

    if ctx.local:
        suite_ok, suite = ctx.base_suite("f2-check")
        res.check("base_suite_green", suite_ok, f"just test in base: {suite}")
    else:
        res.observe("just test v čistém checkoutu base se na githubu nespouští")
    res.measurements["run_seconds"] = {
        t: run_seconds(ctx.task_run(str(_dict(_dict(runs.get(t)).get("run")).get("run_id") or "")))
        for t in fb.ALL
    }


@dataclass
class F2Run:
    """The state F2 carries from one stage to the next."""

    res: ScenarioResult
    runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    base_sha: str | None = None
    before_status: str = ""
    adds: list[tuple[str, Cmd]] = field(default_factory=list)  # task id, `task add`
    approvals: list[tuple[str, Cmd]] = field(default_factory=list)  # all_approved


# the sample backlog: containers and five ``task add`` (in two stages), then
# ``backlog check``, commit and push
_FIRST_ADDS = 2


def _stage_backlog_start(ctx: Context, st: F2Run) -> bool:
    ctx.catch_up_base()
    if not _start_backlog(ctx, st):
        return False
    _add_tasks(ctx, st, fb.TASKS[:_FIRST_ADDS])
    return True


def _stage_backlog_add(ctx: Context, st: F2Run) -> bool:
    _add_tasks(ctx, st, fb.TASKS[_FIRST_ADDS:])
    return True


def _stage_backlog(ctx: Context, st: F2Run) -> bool:
    st.base_sha = _push_backlog(ctx, st.res, st.adds)
    if st.base_sha is None:
        return False
    st.res.observe(
        "F2: 2 moduly, 5 tasků; paralelně M03-S01-T01 a M04-S01-T01; --auto od M04-S01-T02 "
        "spustil M04-S01-T03; approve bez approve review (D11)"
    )
    if ctx.local:
        st.res.observe("local: agenty nahrazuje falešný harness, kódové kroky běží doopravdy")
    st.before_status = git(ctx.repo, "status", "--porcelain", "--untracked-files=all")
    return True


def _stage_parallel(ctx: Context, st: F2Run) -> bool:
    return _parallel(ctx, st.res, st.runs)


def _stage_approve_parallel(ctx: Context, st: F2Run) -> bool:
    return _approve_all(ctx, st.res, "parallel_approved", fb.PARALLEL)


def _stage_auto_chain(ctx: Context, st: F2Run) -> bool:
    return _auto_chain(ctx, st.res, st.runs)


def _stage_last_run(ctx: Context, st: F2Run) -> bool:
    last = ctx.run_task(fb.LAST)
    _record(ctx, st.res, st.runs, fb.LAST, last.run, last.pr)
    return st.res.check("last_run_ok", _run_ok(last.run, last.pr, last.ok), last.brief())


def _stage_approve_chain(ctx: Context, st: F2Run) -> bool:
    st.approvals.extend((t, _approve(ctx, st.res, t)) for t in fb.AUTO_CHAIN)
    return True


def _stage_approve_rest(ctx: Context, st: F2Run) -> bool:
    st.approvals.append((fb.LAST, _approve(ctx, st.res, fb.LAST)))
    return _approved(st.res, "all_approved", st.approvals)


def _stage_final(ctx: Context, st: F2Run) -> bool:
    assert st.base_sha is not None
    _final_checks(ctx, st.res, st.runs, st.before_status, st.base_sha)
    return True


# F2 in order; it stops at the first stage that returns False
F2_STAGES: tuple[tuple[str, Callable[[Context, F2Run], bool]], ...] = (
    ("backlog_start", _stage_backlog_start),
    ("backlog_add", _stage_backlog_add),
    ("backlog", _stage_backlog),
    ("parallel", _stage_parallel),
    ("approve_parallel", _stage_approve_parallel),
    ("auto_chain", _stage_auto_chain),
    ("last_run", _stage_last_run),
    ("approve_chain", _stage_approve_chain),
    ("approve_rest", _stage_approve_rest),
    ("final", _stage_final),
)


def f2(ctx: Context) -> ScenarioResult:
    st = F2Run(ScenarioResult("F2", ctx.remote))
    for _, stage in F2_STAGES:
        if not stage(ctx, st):
            break
    return st.res
