"""The scenarios: R1, R10, R2, R3, R4, R5 of docs/product-brief.md (Rizika), RESOLVE, B1, F2.

Each function takes the shared ``Context`` and returns a ``ScenarioResult``.
The runner calls them in the order of ``ORDER``; later ones build on earlier
ones (RESOLVE resolves the conflicting PR of R2, R3 approves the PR of R10 and
merges the PR of R1 outside factory, R4 needs the slugify of R10 in base). F2
(``validation.f2``, the acceptance of phase F2) depends on none of them. A
missing precondition makes the part that needs it ``inconclusive`` instead of
failing. The expected harnesses of R1 and R10 come from the roster (``--roster
DIR`` or the template); a roster without the harnesses they verify (R1:
claude, codex and pi in one workflow; R10: build and fix on codex) makes them
``inconclusive`` only when the harness is all that is missing and every other
check passed; a failed run or check keeps them ``failed``.

Forced repair rounds: every task run has a review -> revise round (the
validation rule of the sandbox's reviewer), and R10 a test -> fix round (the
hidden test of ``validation.hidden``). ``_review_round_checks`` verifies the
first.
"""

from __future__ import annotations

import json
import os
import re
import statistics
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from validation.context import Cmd, Context, parse_time, run_seconds
from validation.f2 import f2
from validation.fake_scripts import BREACH_FILE, REVIEW_RULE_MARKER
from validation.hidden import HIDDEN_CLASS, HIDDEN_EXPECTED, HIDDEN_TARGET
from validation.results import INCONCLUSIVE, ScenarioResult
from validation.roster import canonical, harness_of_phase
from validation.safety import check_inside
from validation.sandbox import SENTINEL, git

# simple-sdlc when the suite passes at once and the review takes one forced round:
# the reviewer rejects (review_1), the builder revises (revise_1), the tester plans
# again from the review (replan_1), the new checks run (retest_1) and the reviewer
# approves (review_2).
# `request` is the engineer phase.
FORCED_REVIEW_HAPPY: tuple[str, ...] = (
    "request",
    "plan",
    "commit_plan",
    "build",
    "test_plan",
    "test_1",
    "review_1",
    "revise_1",
    "replan_1",
    "retest_1",
    "review_2",
    "commit_build",
    "changes",
    "document",
    "commit_docs",
)
# the phases every successful run has, whatever a real model does in between
CORE_PHASES: tuple[str, ...] = (
    "request",
    "plan",
    "commit_plan",
    "build",
    "test_plan",
    "test_1",
    "review_1",
    "commit_build",
    "changes",
    "document",
    "commit_docs",
)
# phases a real model may add: repair rounds with their new plans, review rounds
# with the new plan and retest after a revision
EXTRA_PHASE = re.compile(r"^(?:fix|test|test_plan|review|revise|replan|retest)_\d+$")
R1_HARNESSES = frozenset({"claude", "codex", "pi"})

R1_TASK = "M02-S01-T02"  # --version; later merged outside factory (R3)
R10_TASK = "M01-S02-T01"  # slugify with a hidden requirement: repair round
R2_TASKS = ("M01-S01-T01", "M01-S01-T02")  # clamp, lerp: the same line of mathx.py
R3_RETURN_TASK = "M01-S02-T02"  # truncate: returned, then closed
R4_TASK = "M02-S01-T01"  # greet: depends on M01-S02-T01 of another module
B1_TASK = "M01-S01-T03"  # sign: the fake builder also writes into the main checkout
MATHX = "src/sandbox/mathx.py"


def _is_subsequence(wanted: tuple[str, ...], seen: list[str]) -> bool:
    it = iter(seen)
    return all(any(name == s for s in it) for name in wanted)


def _harness(value: Any) -> str:
    return canonical(str(value or ""))


def _inconclusive_unless_failed(res: ScenarioResult, why: str) -> ScenarioResult:
    """Inconclusive for `why` only when every kept check passed; else keep `failed`, observe why."""
    if all(c.ok for c in res.checks):
        return res.inconclusive(why)
    res.observe(why)
    return res


def _roster_gap(res: ScenarioResult, why: str) -> ScenarioResult:
    """The roster cannot show what R1/R10 verify: inconclusive unless a kept check failed."""
    return _inconclusive_unless_failed(res, why)


def _run_checks(ctx: Context, res: ScenarioResult, cmd: Cmd) -> str | None:
    run_id = ctx.reference(res, cmd)
    res.check(
        "run_ok",
        cmd.ok and cmd.run.get("state") == "succeeded",
        cmd.brief(),
    )
    return run_id


def _review_round_checks(ctx: Context, res: ScenarioResult, run_id: str) -> str | None:
    """The forced review -> revise round of `run_id`; a reason when it could not be verified.

    Locally the fake reviewer always rejects first. On GitHub a real model
    decides: a first-round approval makes the round unverifiable (the reason is
    returned and observed), not failed.
    """
    rendered = ctx.session_dir(run_id) / "reviewer" / "prompts" / "user.md"
    body = rendered.read_text(encoding="utf-8") if rendered.is_file() else ""
    res.check(
        "review_rule_in_prompt",
        REVIEW_RULE_MARKER in body,
        f"{rendered.name}: rule {'present' if REVIEW_RULE_MARKER in body else 'absent'}",
    )
    first = ctx.envelope(run_id, "review_1")
    phases = ctx.phase_rows(run_id)
    res.measurements["review_rounds"] = len([n for n in phases if re.fullmatch(r"review_\d+", n)])
    if not ctx.local and first.get("approved") is True:
        why = (
            "reviewer (skutečný model) schválil hned v prvním kole a pravidlo validace "
            "nedodržel: kolo review -> revise neproběhlo a nejde ověřit"
        )
        res.observe(why)
        return why
    res.check(
        "review_1_rejected",
        first.get("approved") is False,
        f"review_1 approved={first.get('approved')}, blocking={first.get('blocking')}",
    )
    revise = phases.get("revise_1", {})
    res.check(
        "revise_ran",
        revise.get("status") == "success",
        f"revise_1 status={revise.get('status')}",
    )
    second = ctx.envelope(run_id, "review_2")
    res.check(
        "review_2_approved",
        second.get("approved") is True,
        f"review_2 approved={second.get('approved')}",
    )
    res.trace_files.append(f"trace/sessions/{run_id}/reviewer/prompts/user.md")
    return None


def _unverified(res: ScenarioResult, why: str | None) -> ScenarioResult:
    """Inconclusive for `why` (a round a real model skipped), unless a check failed."""
    if why is not None and all(c.ok for c in res.checks):
        res.forced = INCONCLUSIVE
    return res


# ── R1 ───────────────────────────────────────────────────────────────────────


def r1(ctx: Context) -> ScenarioResult:
    res = ScenarioResult("R1", ctx.remote)
    missing = sorted(R1_HARNESSES - set(ctx.harnesses.values()))
    ctx.catch_up_base()
    cmd = ctx.run_task(R1_TASK)
    run_id = _run_checks(ctx, res, cmd)
    res.check(
        "pr_opened",
        bool(cmd.pr.get("url")),
        str(cmd.pr.get("url") or cmd.payload.get("pr_error")),
    )
    ctx.add_pr(res, R1_TASK, cmd.pr)
    if cmd.ok:
        ctx.state["R1"] = {"task": R1_TASK, "run": cmd.run, "pr": cmd.pr}
    if not run_id:
        return res
    phases = ctx.phases(run_id)
    names = [p["name"] for p in phases]
    if ctx.local:
        order_ok = tuple(names) == FORCED_REVIEW_HAPPY
    else:
        extras = [n for n in names if n not in CORE_PHASES]
        order_ok = _is_subsequence(CORE_PHASES, names) and all(EXTRA_PHASE.match(n) for n in extras)
    res.check("phase_order", order_ok, " -> ".join(names))
    starts = ctx.agent_starts(run_id)
    wrong = []
    for start in starts:
        want = harness_of_phase(ctx.harnesses, start["phase"])
        if want is not None and _harness(start["coding_agent"]) != want:
            wrong.append(f"{start['phase']}: {start['coding_agent']} (want {want})")
    used = {s["phase"]: _harness(s["coding_agent"]) for s in starts}
    if not missing:
        res.check(
            "harness_per_phase",
            not wrong and R1_HARNESSES <= set(used.values()),
            "; ".join(wrong) or ", ".join(f"{k}={v}" for k, v in used.items()),
        )
    failed = [p["name"] for p in phases if p["status"] != "success"]
    res.check("all_phases_ok", not failed, ", ".join(failed) or "every phase success")
    why = _review_round_checks(ctx, res, run_id)
    usage = ctx.session_usage(run_id)
    row = ctx.task_run(run_id)
    res.measurements.update(
        {
            "phase_count": len(phases),
            "phases": names,
            "harness_per_phase": used,
            "run_seconds": run_seconds(row),
            "total_tokens": usage.get("total_tokens"),
            "total_cost": usage.get("total_cost"),
        }
    )
    per_phase = ctx.phase_tokens(run_id)
    if per_phase:
        res.measurements["tokens_per_phase"] = per_phase
    else:
        res.observe("tokeny po fázích trace neobsahuje (events.tokens prázdné), jen součet session")
    res.observe(f"fáze běhu: {' -> '.join(names)}")
    res.observe(
        "smyčky aifactory (2.7) kontrolují `until` po každém kroku: po posledním zamítnutí "
        "revise_2 ani po posledním červeném testu fix_3 neběží (Python adw_simple_sdlc.py "
        "fix_3 ještě spustí, výsledek je stejný)"
    )
    if ctx.local:
        res.observe("local: falešný harness, harnessy ověřeny z agent_start v trace, ne z CLI")
    res.trace_files.append(f"trace/sessions/{run_id}/planner/prompts/user.md")
    if missing:
        return _roster_gap(
            res,
            f"roster nemá ve workflow harness {', '.join(missing)}: R1 (claude, codex i pi "
            f"v jednom workflow) nejde ověřit; harness po krocích: {ctx.harnesses}",
        )
    return _unverified(res, why)


# ── R10 ──────────────────────────────────────────────────────────────────────


def _codex_threads(raw: Path) -> list[str]:
    ids: list[str] = []
    if not raw.is_file():
        return ids
    for line in raw.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "thread.started":
            ids.append(str(event.get("thread_id")))
    return ids


def _hidden_unseen_check(ctx: Context, res: ScenarioResult, cmd: Cmd) -> None:
    """No agent saw the hidden test (fake calls locally, the pushed head on GitHub)."""
    calls_path = (
        cmd.script.with_name(cmd.script.name + ".calls.jsonl") if cmd.script is not None else None
    )
    if calls_path is not None and calls_path.is_file():
        calls = [
            json.loads(line)
            for line in calls_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        seen = [str(c.get("agent")) for c in calls if c.get("hidden_file") or c.get("hidden_env")]
        res.check(
            "hidden_unseen_by_agents",
            bool(calls) and not seen,
            f"{len(calls)} agent calls, saw the hidden test: {seen}",
        )
        return
    head = str(cmd.run.get("head_sha") or "")
    if not head:
        res.observe("hidden_unseen_by_agents: no head_sha and no fake calls, not verified")
        return
    git(ctx.repo, "fetch", "-q", "origin", head, check=False)
    listed = git(ctx.repo, "ls-tree", "-r", head, "--", HIDDEN_TARGET, check=False)
    res.check(
        "hidden_unseen_by_agents",
        not listed,
        f"{HIDDEN_TARGET} in {head[:12]}: {bool(listed)}",
    )


def r10(ctx: Context) -> ScenarioResult:
    res = ScenarioResult("R10", ctx.remote)
    on_codex = ctx.harnesses.get("build") == "codex" and ctx.harnesses.get("fix") == "codex"
    gap = (
        f"build běží na {ctx.harnesses.get('build')}, fix na {ctx.harnesses.get('fix')}, "
        "ne oba na codexu: R10 (opravné kolo v Codex threadu) nejde ověřit"
    )
    ctx.catch_up_base()
    cmd = ctx.run_task(R10_TASK, variant="slugify_with_repair")
    run_id = _run_checks(ctx, res, cmd)
    ctx.add_pr(res, R10_TASK, cmd.pr)
    if cmd.ok:
        ctx.state["R10"] = {"task": R10_TASK, "run": cmd.run, "pr": cmd.pr}
    if not run_id:
        return res
    names = [p["name"] for p in ctx.phases(run_id)]
    fixes = [n for n in names if re.fullmatch(r"fix_\d+", n)]
    starts = {s["phase"]: s for s in ctx.agent_starts(run_id)}
    usage = ctx.session_usage(run_id)
    tokens = ctx.phase_tokens(run_id)
    res.measurements.update(
        {
            "repair_rounds": len(fixes),
            "phases": names,
            "run_seconds": run_seconds(ctx.task_run(run_id)),
            "total_tokens": usage.get("total_tokens"),
            "total_cost": usage.get("total_cost"),
            "builder_tokens": sum(
                v for k, v in tokens.items() if k == "build" or re.fullmatch(r"(fix|revise)_\d+", k)
            ),
        }
    )
    first_output = ctx.test_output(run_id, "test_1")
    res.check(
        "test_failed_first",
        ctx.test_passed(run_id, "test_1") is False,
        f"test_1 passed={ctx.test_passed(run_id, 'test_1')}",
    )
    res.check(
        "hidden_test_failed_first",
        HIDDEN_CLASS in first_output,
        f"{HIDDEN_CLASS} in the output of test_1: {HIDDEN_CLASS in first_output}"
        f" ({HIDDEN_EXPECTED} in it: {HIDDEN_EXPECTED in first_output})",
    )
    _hidden_unseen_check(ctx, res, cmd)
    res.trace_files.append(f"trace/sessions/{run_id}/builder/raw_output.jsonl")
    why = _review_round_checks(ctx, res, run_id)
    if not fixes:
        if not ctx.local:
            return _inconclusive_unless_failed(
                res, "opravné kolo neproběhlo, přestože skrytý test měl selhat; R10 nejde ověřit"
            )
        if not on_codex:
            return _roster_gap(res, gap)
        res.check("fix_ran_on_codex", False, f"no fix phase in {names}")
        return res
    fix = starts.get("fix_1", {})
    if on_codex:
        res.check(
            "fix_ran_on_codex",
            _harness(fix.get("coding_agent")) == "codex",
            f"fix_1 coding_agent={fix.get('coding_agent')}",
        )
    tests = [n for n in names if re.fullmatch(r"test_\d+", n)]
    last_test = tests[-1] if tests else "test_1"
    res.check(
        "test_passed_after_fix",
        ctx.test_passed(run_id, last_test) is True,
        f"{last_test} passed={ctx.test_passed(run_id, last_test)}",
    )
    if not on_codex:
        return _roster_gap(res, gap)
    build = starts.get("build", {})
    res.check(
        "same_session",
        bool(build.get("session_id")) and build.get("session_id") == fix.get("session_id"),
        f"build={build.get('session_id')} fix_1={fix.get('session_id')}",
    )
    builder_dir = ctx.session_dir(run_id) / "builder"
    if ctx.local:
        res.observe(
            "resume codex threadu v local režimu neověřeno (falešný harness), pokrývá contract "
            "test harnessu codex (tests/harness/test_harness_contract.py)"
        )
    else:
        session_id = str(build.get("session_id") or "")
        state_files = list((builder_dir / "codex_sessions").glob("*.codex.json"))
        threads = _codex_threads(builder_dir / "raw_output.jsonl")
        res.check(
            "thread_resumed",
            bool(state_files) and len(set(threads)) <= 1,
            f"codex.json: {[p.name for p in state_files]}, thread ids: {sorted(set(threads))}",
        )
        res.observe(f"session_id builderu {session_id}, thread.started událostí: {len(threads)}")
    return _unverified(res, why)


# ── R2 ───────────────────────────────────────────────────────────────────────


@dataclass
class R2Run:
    """The state R2 carries from its runs to the approvals (see ``R2_STAGES``)."""

    res: ScenarioResult
    cmds: list[Cmd] = field(default_factory=list)


def _r2_runs(ctx: Context, st: R2Run) -> bool:
    res = st.res
    ctx.catch_up_base()
    first, second = R2_TASKS
    pending = [
        ctx.haifa_async("task", "run", first, task=first),
        ctx.haifa_async("task", "run", second, task=second),
    ]
    st.cmds = cmds = [p.wait() for p in pending]
    for task_id, cmd in zip(R2_TASKS, cmds, strict=True):
        ctx.reference(res, cmd)
        ctx.add_pr(res, task_id, cmd.pr)
    res.check("both_runs_ok", all(c.ok for c in cmds), " | ".join(c.brief() for c in cmds))
    rows = [ctx.task_run(str(c.run.get("run_id"))) for c in cmds]
    starts = [parse_time(r.get("started_at")) for r in rows]
    ends = [parse_time(r.get("ended_at")) for r in rows]
    overlap = 0.0
    if all(starts) and all(ends):
        overlap = (min(e for e in ends if e) - max(s for s in starts if s)).total_seconds()
    res.check("runs_overlapped", overlap > 0, f"overlap {overlap:.3f} s")
    res.measurements["overlap_s"] = round(overlap, 3)
    res.measurements["run_seconds"] = {
        t: run_seconds(r) for t, r in zip(R2_TASKS, rows, strict=True)
    }
    res.check("both_prs_opened", all(c.pr.get("url") for c in cmds), "")
    worktrees = [c.run.get("worktree") for c in cmds]
    res.check("distinct_worktrees", len(set(worktrees)) == 2 and all(worktrees), str(worktrees))
    touched = []
    for cmd in cmds:
        run = cmd.run
        if run.get("base_sha") and run.get("head_sha"):
            files = git(
                ctx.repo,
                "diff",
                "--name-only",
                f"{run['base_sha']}..{run['head_sha']}",
                check=False,
            ).splitlines()
            touched.append(MATHX in files)
        else:
            touched.append(False)
    res.check("shared_file_touched", all(touched), f"mathx.py changed per branch: {touched}")
    return all(c.ok for c in cmds)


def _r2_approve(ctx: Context, st: R2Run) -> bool:
    res, cmds = st.res, st.cmds
    first, second = R2_TASKS
    approve1 = ctx.haifa("task", "approve", first)
    ctx.catch_up_base()
    res.check(
        "first_merged",
        approve1.ok and ctx.status_in_base(first) == "done",
        f"{approve1.brief()}; status in base: {ctx.status_in_base(first)}",
    )
    if approve1.payload.get("merge_sha"):
        res.commits.append(str(approve1.payload["merge_sha"]))
    before = ctx.fetch_base()
    conflict_codes = ("conflict",) if ctx.local else ("conflict", "merge_failed")
    approve2 = ctx.haifa("task", "approve", second)
    after = ctx.fetch_base()
    conflict = approve2.code == 2 and approve2.error_code in conflict_codes and before == after
    res.check(
        "second_reports_conflict",
        conflict,
        f"{approve2.brief()}; base {str(before)[:7]} -> {str(after)[:7]}",
    )
    if not ctx.local and approve2.error_code == "merge_failed":
        res.observe(
            "GitHub ještě nespočítal mergeability, approve skončil merge_failed místo conflict"
        )
    if conflict:
        ctx.state["R2"] = {
            "first": first,
            "second": second,
            "branches": [str(c.pr.get("branch") or c.run.get("branch") or "") for c in cmds],
            "pr": cmds[1].pr,
        }
        res.observe(f"druhý PR zůstává otevřený, řeší ho scénář RESOLVE (task resolve {second})")
    return True


# R2 in order; it stops after the runs when one of them failed
R2_STAGES: tuple[tuple[str, Callable[[Context, R2Run], bool]], ...] = (
    ("runs", _r2_runs),
    ("approve", _r2_approve),
)


def r2(ctx: Context) -> ScenarioResult:
    st = R2Run(ScenarioResult("R2", ctx.remote))
    for _, stage in R2_STAGES:
        if not stage(ctx, st):
            break
    return st.res


# ── RESOLVE ──────────────────────────────────────────────────────────────────


@dataclass
class ResolveRun:
    """The state RESOLVE carries from ``task resolve`` to the approval."""

    res: ScenarioResult
    cmd: Cmd | None = None


def _resolve_run(ctx: Context, st: ResolveRun) -> bool:
    res = st.res
    state = ctx.state.get("R2")
    if not state:
        res.inconclusive("R2 neskončil konfliktem druhého PR, task resolve nejde ověřit")
        return False
    second = str(state["second"])
    ctx.catch_up_base()
    st.cmd = cmd = ctx.haifa("task", "resolve", second, task=second, variant="resolve")
    run_id = ctx.reference(res, cmd)
    res.check("resolve_ok", cmd.ok and cmd.run.get("state") == "succeeded", cmd.brief())
    ctx.add_pr(res, second, cmd.pr or state["pr"])
    if run_id:
        phases = ctx.phase_rows(run_id)
        rebase = phases.get("rebase", {})
        agent = phases.get("resolve", {})
        test = [n for n in phases if n == "test" or re.fullmatch(r"test(_\d+)?", n)]
        test_ok = bool(test) and ctx.test_passed(run_id, test[-1]) is True
        if ctx.local or agent:
            ok = rebase.get("status") == "success" and agent.get("status") == "success" and test_ok
        else:
            ok = rebase.get("status") == "success" and test_ok
            res.observe("rebase na GitHubu konflikt nehlásil, agent resolve se nespustil")
        res.check(
            "resolve_phase_ran",
            ok,
            f"phases {' -> '.join(phases)}; rebase={rebase.get('status')}, "
            f"resolve={agent.get('status')}, test passed={test_ok}",
        )
        res.measurements["phases"] = list(phases)
        res.measurements["run_seconds"] = run_seconds(ctx.task_run(run_id))
    head = str(cmd.run.get("head_sha") or "")
    shown = git(ctx.repo, "show", f"{head}:{MATHX}", check=False) if head else ""
    res.check(
        "no_conflict_markers",
        bool(shown) and "<<<<<<<" not in shown and ">>>>>>>" not in shown,
        f"{MATHX} at {head[:7] or '?'}: {len(shown)} chars",
    )
    return cmd.ok


def _resolve_approve(ctx: Context, st: ResolveRun) -> bool:
    res = st.res
    state = ctx.state["R2"]
    first, second = str(state["first"]), str(state["second"])
    approve = ctx.haifa("task", "approve", second)
    for _ in range(0 if ctx.local else 6):
        if approve.error_code != "merge_failed":
            break
        time.sleep(10)
        approve = ctx.haifa("task", "approve", second)
    ctx.catch_up_base()
    res.check(
        "second_merged",
        approve.ok and ctx.status_in_base(second) == "done",
        f"{approve.brief()}; status in base: {ctx.status_in_base(second)}",
    )
    if approve.payload.get("merge_sha"):
        res.commits.append(str(approve.payload["merge_sha"]))
    branches = [b for b in state["branches"] if b]
    pr_states = {b: ctx.task_pr(b).get("state") for b in branches}
    statuses = {t: ctx.status_in_base(t) for t in (first, second)}
    res.check(
        "both_prs_merged",
        len(branches) == 2
        and all(s == "merged" for s in pr_states.values())
        and all(s == "done" for s in statuses.values()),
        f"PR states {pr_states}; status in base {statuses}",
    )
    ctx.fetch_base()
    merged = git(ctx.repo, "show", f"origin/{ctx.base}:{MATHX}", check=False)
    both = "def clamp" in merged and "def lerp" in merged
    detail = f"clamp {'present' if 'def clamp' in merged else 'absent'}, " + (
        f"lerp {'present' if 'def lerp' in merged else 'absent'}"
    )
    if ctx.local:
        suite_ok, suite = ctx.base_suite()
        both = both and suite_ok
        detail += f"; just test in base: {suite}"
    res.check("base_has_both", both, detail)
    return True


# RESOLVE in order; it stops when `task resolve` failed (or R2 left nothing to resolve)
RESOLVE_STAGES: tuple[tuple[str, Callable[[Context, ResolveRun], bool]], ...] = (
    ("resolve", _resolve_run),
    ("approve", _resolve_approve),
)


def resolve(ctx: Context) -> ScenarioResult:
    st = ResolveRun(ScenarioResult("RESOLVE", ctx.remote))
    for _, stage in RESOLVE_STAGES:
        if not stage(ctx, st):
            break
    return st.res


# ── R3 ───────────────────────────────────────────────────────────────────────


@dataclass
class R3Run:
    """The state R3 carries from one stage to the next (see ``R3_STAGES``)."""

    res: ScenarioResult
    missing: list[str] = field(default_factory=list)
    commits: dict[str, int] = field(default_factory=dict)
    approve: Cmd | None = None  # `task approve` of R10's task
    first: Cmd | None = None
    ret: Cmd | None = None
    close_before: int | None = None  # base commits before the PR was closed


def _r3_dependency(ctx: Context, st: R3Run) -> bool:
    ctx.catch_up_base()
    # 1. a dependency on a task of another module blocks the run
    if ctx.status_in_base(R10_TASK) != "done":
        blocked = ctx.run_task(R4_TASK)
        st.res.check(
            "dependency_blocks",
            blocked.code == 2 and blocked.error_code == "unmet_dependencies",
            blocked.brief(),
        )
    else:
        st.missing.append(f"{R10_TASK} je v base už done, vazbu nejde ověřit")
    return True


def _r3_approve(ctx: Context, st: R3Run) -> bool:
    res = st.res
    # 2. approve in factory (the PR of R10)
    if "R10" in ctx.state:
        before = ctx.base_commits()
        approve = ctx.haifa("task", "approve", R10_TASK)
        ctx.catch_up_base()
        st.commits["approve_in_factory"] = ctx.base_commits() - before
        res.check("approve_ok", approve.ok, approve.brief())
        header, text = ctx.task_in_base(R10_TASK)
        url = str(ctx.state["R10"]["pr"].get("url", ""))
        res.check(
            "done_in_base_after_approve",
            header.get("status") == "done" and bool(url) and url in text.split("## Běhy", 1)[-1],
            f"status {header.get('status')}, PR {url} under ## Běhy: {url in text}",
        )
        st.approve = approve
    else:
        st.missing.append("R10 neotevřel PR, schválení ve factory neověřeno")
    return True


def _r3_approve_show(ctx: Context, st: R3Run) -> bool:
    res, approve = st.res, st.approve
    if approve is not None:
        show = ctx.haifa("task", "show", R10_TASK)
        prs = show.payload.get("prs", [])
        states = [p.get("state") for p in prs if isinstance(p, dict)]
        res.check("pr_merged", "merged" in states, f"task_prs states: {states}")
        ctx.add_pr(res, R10_TASK, ctx.state["R10"]["pr"])
        ctx.reference(res, str(ctx.state["R10"]["run"].get("run_id")))
        if approve.payload.get("merge_sha"):
            res.commits.append(str(approve.payload["merge_sha"]))
    return True


def _r3_merge_outside(ctx: Context, st: R3Run) -> bool:
    res = st.res
    # 3. merge outside factory, then backlog sync opens a sync PR, merged outside too
    if "R1" in ctx.state:
        pr = ctx.state["R1"]["pr"]
        status_before = ctx.status_in_base(R1_TASK)
        res.check("status_before_sync", status_before == "todo", f"status {status_before}")
        before = ctx.base_commits()
        _merge_outside(ctx, res, pr)
        if ctx.local:
            # the local provider reads merged/open from the main checkout's base branch,
            # and sync refreshes the PR states before it catches base up itself
            ctx.catch_up_base()
            res.observe(
                "local: provider local zjišťuje stav PR z lokální větve base a sync obnovuje "
                "stavy PR dřív, než base dotáhne; validace proto base dotáhla před sync"
            )
        sync = ctx.haifa("backlog", "sync")
        synced = [t.get("task_id") for t in sync.payload.get("tasks", []) if isinstance(t, dict)]
        sync_pr = sync.payload.get("pr") if isinstance(sync.payload.get("pr"), dict) else {}
        res.check(
            "sync_pr_opened",
            sync.ok and R1_TASK in synced and bool(sync_pr),
            f"{sync.brief()}; tasks {synced}; PR {sync.payload.get('url')}",
        )
        status_unmerged = ctx.status_in_base(R1_TASK)
        res.check(
            "base_untouched_by_sync",
            status_unmerged == "todo",
            f"status in base before the sync PR is merged: {status_unmerged}",
        )
        if sync_pr:
            _merge_outside(ctx, res, sync_pr)
        st.commits["merge_outside_and_sync"] = ctx.base_commits() - before
        header, _ = ctx.task_in_base(R1_TASK)
        res.check(
            "done_in_base_after_sync", header.get("status") == "done", str(header.get("status"))
        )
        ctx.catch_up_base()
        ctx.add_pr(res, R1_TASK, pr)
        ctx.reference(res, str(ctx.state["R1"]["run"].get("run_id")))
        res.observe(
            "backlog sync ve factory necommituje do base: otevře sync PR (factory-sync/<n>), "
            "který validace mergne mimo factory"
        )
    else:
        st.missing.append("R1 neotevřel PR, merge mimo factory neověřen")
    return True


def _r3_first_run(ctx: Context, st: R3Run) -> bool:
    # 4. returned PR
    st.first = first = ctx.run_task(R3_RETURN_TASK)
    ctx.reference(st.res, first)
    if not first.ok:
        st.res.check("return_new_run", False, f"first run of {R3_RETURN_TASK}: {first.brief()}")
    return True


def _r3_return(ctx: Context, st: R3Run) -> bool:
    res, first = st.res, st.first
    if first is None or not first.ok:
        return True
    before = ctx.base_commits()
    number_before = _pr_number(ctx, first.pr)
    st.ret = ret = ctx.haifa(
        "task",
        "return",
        R3_RETURN_TASK,
        "--note",
        "Pro n < 1 vrať prázdný řetězec a před … odstraň koncové mezery.",
        task=R3_RETURN_TASK,
        variant="return",
    )
    ctx.reference(res, ret)
    res.check(
        "return_new_run",
        ret.ok
        and ret.run.get("run_id") != first.run.get("run_id")
        and ret.run.get("branch") == first.run.get("branch"),
        f"{first.run.get('run_id')} -> {ret.run.get('run_id')} on {ret.run.get('branch')}",
    )
    number_after = _pr_number(ctx, ret.pr or first.pr)
    res.check(
        "pr_updated",
        bool(ret.run.get("head_sha"))
        and ret.run.get("head_sha") != first.run.get("head_sha")
        and number_before == number_after,
        f"head {str(first.run.get('head_sha'))[:7]} -> {str(ret.run.get('head_sha'))[:7]}, "
        f"PR {number_before} -> {number_after}",
    )
    status = ctx.status_in_base(R3_RETURN_TASK)
    res.check("base_unchanged_after_return", status == "todo", f"status {status}")
    st.commits["return"] = ctx.base_commits() - before
    ctx.add_pr(res, R3_RETURN_TASK, ret.pr or first.pr)
    return True


def _r3_close(ctx: Context, st: R3Run) -> bool:
    res, first, ret = st.res, st.first, st.ret
    if first is None or not first.ok or ret is None:
        return True
    # 5. closed PR
    before = ctx.base_commits()
    _close_outside(ctx, res, ret.pr or first.pr, ret.run or first.run)
    refused = ctx.haifa("task", "approve", R3_RETURN_TASK)
    res.check(
        "approve_refused",
        refused.code == 2 and refused.error_code == "pr_not_open",
        refused.brief(),
    )
    st.close_before = before
    return True


def _r3_close_sync(ctx: Context, st: R3Run) -> bool:
    res, first, ret, before = st.res, st.first, st.ret, st.close_before
    if first is None or not first.ok or ret is None or before is None:
        return True
    sync = ctx.haifa("backlog", "sync")
    synced = [t.get("task_id") for t in sync.payload.get("tasks", []) if isinstance(t, dict)]
    res.check(
        "sync_ignores_closed",
        sync.ok and R3_RETURN_TASK not in synced,
        f"{sync.brief()}; tasks {synced}",
    )
    status = ctx.status_in_base(R3_RETURN_TASK)
    res.check("base_unchanged_after_close", status == "todo", f"status {status}")
    st.commits["close"] = ctx.base_commits() - before
    branch = str((ret.pr or first.pr).get("branch", ""))
    db_state = ctx.task_pr(branch).get("state")
    res.observe(f"task_prs.state zavřeného PR {branch} v trace je {db_state!r}")
    return True


def _r3_finish(ctx: Context, st: R3Run) -> bool:
    res = st.res
    res.measurements["commits_added_to_base"] = st.commits
    if ctx.local:
        res.observe(
            "local: squash merge mimo factory lokální provider nezachytí (tip větve není předkem "
            "base), proto merge mimo factory použil --no-ff; squash se ověřuje na githubu"
        )
    else:
        res.observe(
            "approve neposílá review na hosting (D11, dočasné), protože GitHub nedovolí "
            "schválit vlastní PR; approve review se proto neověřuje"
        )
    if st.missing:
        for why in st.missing:
            res.observe(why)
        if all(c.ok for c in res.checks):
            res.forced = INCONCLUSIVE
    return True


# R3 in order, one CLI step each; every stage runs (R3 does not stop early)
R3_STAGES: tuple[tuple[str, Callable[[Context, R3Run], bool]], ...] = (
    ("dependency", _r3_dependency),
    ("approve", _r3_approve),
    ("approve_show", _r3_approve_show),
    ("merge_outside", _r3_merge_outside),
    ("first_run", _r3_first_run),
    ("return", _r3_return),
    ("close", _r3_close),
    ("close_sync", _r3_close_sync),
    ("finish", _r3_finish),
)


def r3(ctx: Context) -> ScenarioResult:
    st = R3Run(ScenarioResult("R3", ctx.remote))
    for _, stage in R3_STAGES:
        if not stage(ctx, st):
            break
    return st.res


def _pr_number(ctx: Context, pr: dict[str, Any]) -> str | None:
    if ctx.local:
        return str(pr.get("pr_id") or pr.get("branch") or "") or None
    branch = str(pr.get("branch") or "")
    if not branch:
        return None
    out = ctx.gh("pr", "view", branch, "--json", "number", check=False)
    try:
        return str(json.loads(out).get("number"))
    except (ValueError, AttributeError):
        return None


def _merge_outside(ctx: Context, res: ScenarioResult, pr: dict[str, Any]) -> None:
    branch = str(pr.get("branch"))
    if ctx.local:
        assert ctx.sandbox.bare is not None
        outside = ctx.workdir / "outside"
        check_inside(outside, ctx.workdir, ctx.owned)
        if not outside.exists():
            git(ctx.workdir, "clone", "-q", str(ctx.sandbox.bare), str(outside))
            git(outside, "config", "user.name", "Outside factory")
            git(outside, "config", "user.email", "outside@example.invalid")
            git(outside, "config", "commit.gpgsign", "false")
        git(outside, "fetch", "-q", "origin")
        git(outside, "checkout", "-q", ctx.base)
        git(outside, "merge", "-q", "--ff-only", f"origin/{ctx.base}")
        git(
            outside,
            "merge",
            "-q",
            "--no-ff",
            "-m",
            f"Merge {branch} outside factory",
            f"origin/{branch}",
        )
        git(outside, "push", "-q", "origin", ctx.base)
        res.commits.append(git(outside, "rev-parse", "HEAD"))
        res.observe(f"merge mimo factory: git merge --no-ff {branch} v druhém klonu, push do base")
    else:
        number = str(pr.get("pr_id"))
        ctx.gh("pr", "merge", number, "--squash")
        res.observe(f"merge mimo factory: gh pr merge {number} --squash")


def _close_outside(
    ctx: Context, res: ScenarioResult, pr: dict[str, Any], run: dict[str, Any]
) -> None:
    branch = str(pr.get("branch"))
    if ctx.local:
        worktree = run.get("worktree")
        if worktree and Path(worktree).exists():
            check_inside(Path(worktree), ctx.workdir, ctx.owned)
            git(ctx.repo, "worktree", "remove", "--force", str(worktree))
        git(ctx.repo, "branch", "-D", branch)
        git(ctx.repo, "push", "-q", "origin", "--delete", branch)
        res.observe(
            f"zavření PR v local: worktree odstraněn, větev {branch} smazána lokálně i v remote"
        )
    else:
        number = str(pr.get("pr_id"))
        ctx.gh("pr", "close", number)
        res.observe(f"zavření PR mimo factory: gh pr close {number}")


# ── R4 ───────────────────────────────────────────────────────────────────────

PLANNER_PROMPT = ".factory/prompts/planner/user.md"
AGENTS_CONFIG = ".factory/agents.yaml"


def r4(ctx: Context) -> ScenarioResult:
    res = ScenarioResult("R4", ctx.remote)
    ctx.catch_up_base()
    marker = f"R4-UNCOMMITTED {uuid.uuid4()}"
    prompt = ctx.repo / PLANNER_PROMPT
    config = ctx.repo / AGENTS_CONFIG
    try:
        prompt.write_text(
            prompt.read_text(encoding="utf-8") + f"<!-- {marker} -->\n",
            encoding="utf-8",
            newline="\n",
        )
        text = config.read_text(encoding="utf-8")
        anchor = "  - name: planner\n"
        changed = text.replace(anchor, anchor + "    thinking: high\n", 1)
        config.write_text(changed, encoding="utf-8", newline="\n")
        dirty = git(ctx.repo, "status", "--porcelain")
        res.check(
            "tree_dirty",
            PLANNER_PROMPT in dirty and AGENTS_CONFIG in dirty and changed != text,
            dirty.replace("\n", "; "),
        )
        extra: list[str] = []
        if ctx.status_in_base(R10_TASK) != "done":
            extra.append("--force")
            res.observe(f"{R10_TASK} není v base done, běh spuštěn s --force")
        cmd = ctx.run_task(R4_TASK, *extra)
        run_id = _run_checks(ctx, res, cmd)
        ctx.add_pr(res, R4_TASK, cmd.pr)
        mentioned = [w for w in cmd.warnings if "agents.yaml" in w or "prompts" in w]
        res.check(
            "uncommitted_warning",
            bool(mentioned),
            "; ".join(cmd.warnings) or "no warnings",
        )
        if run_id:
            rendered = ctx.session_dir(run_id) / "planner" / "prompts" / "user.md"
            body = rendered.read_text(encoding="utf-8") if rendered.is_file() else ""
            res.check(
                "prompt_change_invisible",
                bool(body) and marker not in body and SENTINEL in body,
                f"{rendered.name}: marker {'present' if marker in body else 'absent'}, "
                f"sentinel {'present' if SENTINEL in body else 'absent'}",
            )
            res.trace_files.append(f"trace/sessions/{run_id}/planner/prompts/user.md")
            plan = next((s for s in ctx.agent_starts(run_id) if s["phase"] == "plan"), {})
            thinking = plan.get("thinking")
            res.measurements["planner_thinking"] = thinking
            res.check(
                "config_change_invisible",
                bool(plan) and thinking != "high",
                f"planner thinking in the run: {thinking!r}",
            )
        res.observe(
            "konfigurace (agents.yaml, prompty, workflow) se čte z commitu v base; necommitnutá "
            "změna se neprojeví a factory na ni upozorní varováním (D4 vyřešeno)"
        )
    finally:
        git(ctx.repo, "checkout", "--", PLANNER_PROMPT, AGENTS_CONFIG, check=False)
    return res


# ── R5 ───────────────────────────────────────────────────────────────────────


def tree_size(path: Path, skip_git: bool = True) -> tuple[int, int]:
    """(bytes, files) under `path`, without ``.git`` entries."""
    total = files = 0
    for top, dirs, names in os.walk(path):
        if skip_git and ".git" in dirs:
            dirs.remove(".git")
        for name in names:
            if skip_git and name == ".git":
                continue
            try:
                total += os.lstat(os.path.join(top, name)).st_size
            except OSError:
                continue
            files += 1
    return total, files


def r5(ctx: Context) -> ScenarioResult:
    res = ScenarioResult("R5", ctx.remote)
    ctx.fetch_base()
    parent = ctx.workdir / "r5"
    parent.mkdir(parents=True, exist_ok=True)
    seconds: list[float] = []
    sizes: list[int] = []
    counts: list[int] = []
    leftovers: list[str] = []
    for i in range(max(1, ctx.r5_samples)):
        path = parent / str(i)
        check_inside(path, ctx.workdir, ctx.owned)
        clock = time.perf_counter()
        git(ctx.repo, "worktree", "add", "-q", "--detach", str(path), f"origin/{ctx.base}")
        seconds.append(round(time.perf_counter() - clock, 4))
        size, n = tree_size(path)
        sizes.append(size)
        counts.append(n)
        git(ctx.repo, "worktree", "remove", "--force", str(path))
        listed = git(ctx.repo, "worktree", "list", "--porcelain")
        if path.exists() or str(path) in listed or str(path.resolve()) in listed:
            leftovers.append(str(path))
    res.check("measured", bool(seconds) and all(s > 0 for s in sizes), f"{len(seconds)} samples")
    res.check("cleanup_ok", not leftovers, ", ".join(leftovers) or "every sample removed")
    run_worktrees: dict[str, int] = {}
    wt_root = ctx.repo / ".factory" / "worktrees"
    if wt_root.is_dir():
        for child in sorted(wt_root.iterdir()):
            if child.is_dir():
                run_worktrees[child.name] = tree_size(child)[0]
    git_bytes, _ = tree_size(ctx.repo / ".git", skip_git=False)
    res.measurements.update(
        {
            "samples": len(seconds),
            "add_seconds": {
                "values": seconds,
                "median": statistics.median(seconds),
                "max": max(seconds),
            },
            "worktree_bytes": statistics.median(sizes),
            "worktree_files": statistics.median(counts),
            "git_dir_bytes": git_bytes,
            "run_worktrees": run_worktrees,
        }
    )
    res.observe(
        "sandbox je malý, čísla jsou dolní mez; náklad buildu (.NET, node_modules) tu není "
        "zastoupen. Úklid po merge dělá approve (removed_worktrees), zavřené a neschválené "
        f"běhy nechávají worktree (teď {len(run_worktrees)}), uklízí je `factory task clean`"
    )
    return res


# ── B1 ───────────────────────────────────────────────────────────────────────


def b1(ctx: Context) -> ScenarioResult:
    res = ScenarioResult("B1", ctx.remote)
    ctx.catch_up_base()
    readme = ctx.repo / "README.md"
    breach = ctx.repo / BREACH_FILE
    before_status = git(ctx.repo, "status", "--porcelain")
    before_readme = readme.read_text(encoding="utf-8")
    before_commits = ctx.base_commits()
    cmd = ctx.run_task(B1_TASK, variant="breach", fake=True)
    run_id = ctx.reference(res, cmd)
    res.check(
        "run_failed",
        cmd.code == 1 and cmd.error_code == "run_failed" and cmd.run.get("state") == "failed",
        cmd.brief(),
    )
    message = f"{cmd.run.get('error') or ''} {cmd.error.get('message') or ''}"
    res.check("breach_reported", BREACH_FILE in message, message.strip()[:500])
    after_status = git(ctx.repo, "status", "--porcelain")
    head_readme = git(ctx.repo, "show", "HEAD:README.md", check=False)
    readme_now = readme.read_text(encoding="utf-8")
    res.check(
        "write_reverted",
        not breach.exists()
        and readme_now == before_readme
        and readme_now.rstrip("\n") == head_readme.rstrip("\n")
        and after_status == before_status,
        f"{BREACH_FILE} exists: {breach.exists()}; README.md unchanged: "
        f"{readme_now == before_readme}; status {after_status!r} (before {before_status!r})",
    )
    if run_id:
        phases = ctx.phase_rows(run_id)
        build = phases.get("build", {})
        breaches = ctx.events(run_id, "error", "permission_breach")
        res.check(
            "phase_failed",
            bool(build) and build.get("status") != "success" and bool(breaches),
            f"build status={build.get('status')}, permission_breach events: {len(breaches)}",
        )
        res.measurements["phases"] = list(phases)
    else:
        res.check("phase_failed", False, "no run id")
    res.check(
        "no_pr",
        not cmd.pr and ctx.base_commits() == before_commits,
        f"pr {cmd.pr.get('url') if cmd.pr else None}; base commits {before_commits} -> "
        f"{ctx.base_commits()}",
    )
    res.observe(
        "B1 běží s falešným harnessem v obou režimech: hlídač zápisů (run/guard.py) je kód, "
        "model k ověření nepotřebuje; zápisy jdou do negitignorovaných souborů, "
        "gitignorované hlídač nevidí"
    )
    return res


ORDER: tuple[tuple[str, Callable[[Context], ScenarioResult]], ...] = (
    ("R1", r1),
    ("R10", r10),
    ("R2", r2),
    ("RESOLVE", resolve),
    ("R3", r3),
    ("R4", r4),
    ("R5", r5),
    ("B1", b1),
    ("F2", f2),
)
