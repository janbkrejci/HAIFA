# Plan: HAIFA-REFINEMENT-T26 — lepší popisy PR a tvrdé zacházení s nedodělky

All paths below are relative to the worktree root. Allowed paths: `aifactory/`, `justfile`,
this spec file and the task doc file
`factory/docs/HAIFA/REFINEMENT-upravy-opravy-a-vylepseni-z-praxe/HAIFA-REFINEMENT-T26-lepsi-popisy-pull-requestu-a-tvrde-zacha.md`.
**`docs/decisions.md` is outside the allowed paths — do not touch it.** The decision
record goes into the task doc file (section 6).

## 0. Decision: what goes where

| Concern | Where | Why |
|---|---|---|
| Agents report a PR summary, new work and blockers | **Envelope fields** on `EnvelopeBase` (`engine/data_types.py`) | Typed handoff is the only channel from agents to the factory; on the base class every role (builder, fix, revise, reviewer, planner, documenter, tester…) can report it without per-role plumbing. |
| Rules "no hidden TODOs, report new work / blocking, write the PR summary" | **Agent prompts** (`seed/agents/*/system.md`, `user.md`) | Only the agent knows when work overflows; the prompt is where its behaviour is defined. Seed versions are content hashes, so `library reseed` delivers the change to installed libraries. |
| Creating the TODO step/task, adding `depends_on`, failing the run, refusing done/merge | **Factory code** (`run/followups.py`, `run/task.py`, `review/flow.py`) | Must hold for every workflow, including user-written ones, and must not depend on an agent doing backlog writes (agents may not touch the backlog of base; `.factory/` and backlog are outside run scope). |
| PR body layout | **Factory code** (`review/prbody.py`) | Deterministic assembly; the summary text comes from agent envelopes. |
| Workflows | **No change** | Workflows are data and per-repo; putting the rule in a workflow would let a custom workflow skip it. Envelope fields work in all existing workflows unchanged. |

## 1. Envelope fields (`aifactory/src/aifactory/engine/data_types.py`)

Engine file: mark every change with `# aifactory 3.2:` comments. Add before `EnvelopeBase`:

```python
# aifactory 3.2: work a run found but does not finish; the factory files it as a task
# in the project's TODO step (run/followups.py). `blocks_task`: this task cannot be
# done before the new one, so the run fails as blocked and the task gets `depends_on`.
class FollowUp(BaseModel):
    title: str = Field(min_length=1)
    reason: str = Field(min_length=1)   # what was found, where, and why it is not done here
    details: str = ""                   # what the new task must do (becomes its Zadání)
    blocks_task: bool = False


# aifactory 3.2: the reviewer-facing summary of the whole PR, written by the agents.
class PrSummary(BaseModel):
    goal: str = ""                                        # why the task exists, 1–2 sentences
    done: list[str] = Field(default_factory=list)         # outcomes, not file lists
    not_done: list[str] = Field(default_factory=list)     # omissions, deviations from the ask
    notes: list[str] = Field(default_factory=list)        # risks, behaviour changes, manual checks

    @property
    def empty(self) -> bool:
        return not (self.goal.strip() or self.done)
```

Add to `EnvelopeBase` (all with defaults, so old journals and every existing envelope still validate):

```python
    # aifactory 3.2: see FollowUp / PrSummary.
    follow_ups: list[FollowUp] = Field(default_factory=list)
    blocked_by: list[str] = Field(default_factory=list)   # existing backlog ids blocking this task
    pr_summary: Optional[PrSummary] = None
```

Check `engine/agents.py` around line 405–415 (validation error message lists `model_fields`) still reads fine; no change expected.

## 2. PR body (`aifactory/src/aifactory/review/prbody.py`, `review/publish.py`)

### 2.1 New layout (Czech, like today)

```
<!-- factory: task=<id> branch=<branch> -->

## Cíl

<goal>

## Co bylo uděláno

- <done item>

## Co uděláno nebylo

- <not_done item>               # or "- nic" when there is nothing at all
- nový task `<ID>`: <title> (<reason>)      # follow-ups created by this run (non-blocking)

## Důležité pro schválení        # only when notes non-empty

- <note>

<!-- factory: summary-end -->

## Technické podrobnosti

### Agenti
### Gates a testy
### Review
### Náklady
```

- No `## Zadání`, never `task.body`. Delete the body-copy code.
- The hidden marker `<!-- factory: task=... branch=... -->` stays the **first line**, unchanged.
- Operator notes of runs (`Poznámka k běhu …`) move into the technical part, as a `### Poznámky k běhům` subsection (only when there are notes) — they include roster overrides, which are technical.
- Technical sections become `###` under `## Technické podrobnosti` and get terser:
  - Agenti: `- \`step\` (owner, harness/model)` + the envelope `summary` truncated to ~160 chars (add a small `_short(text, n)` helper; ends with `…`).
  - Gates a testy: unchanged lines (they are already compact).
  - Review: verdict + blocking; summary truncated the same way.
  - Náklady: unchanged.

### 2.2 Where the summary comes from

New pure helpers in `prbody.py`:

```python
SUMMARY_END = "<!-- factory: summary-end -->"

def latest_summary(wf: WorkflowRun | None) -> PrSummary | None:
    """The newest non-empty `pr_summary` in `wf.history` (oldest first), else None."""

def previous_summary(body: str | None) -> str | None:
    """The summary block of an earlier PR body: text between the first line (marker)
    and SUMMARY_END, stripped; None when the body has no SUMMARY_END."""

def summary_block(summary: PrSummary | None, task: Task, wf: WorkflowRun | None,
                  follow_ups: Sequence[CreatedFollowUp]) -> str:
```

Fallback when no agent wrote a summary (`summary is None or summary.empty`):
`## Cíl` = `task.title` + line `_Agenti běhu shrnutí nedodali._`; `## Co bylo uděláno` = the
`summary` of the last agent record whose envelope is a `BuildOutput` (or `- (bez shrnutí)`);
`## Co uděláno nebylo` = follow-ups or `- nic`. Never the task body.

`pr_body` signature becomes:

```python
def pr_body(task, runs, wf, trace_db, branch, *,
            follow_ups: Sequence[CreatedFollowUp] = (),
            previous_body: str | None = None,
            reuse_summary: bool = False) -> str
```

Rule: if `reuse_summary` (resolve runs) or the run has no agent summary, and
`previous_summary(previous_body)` exists → reuse that block verbatim (it already contains the
earlier follow-ups). Otherwise build it from `latest_summary(wf)`; the follow-ups are appended to
"Co uděláno nebylo".

`review/publish.py::run_pr_body(store, row, task, wf, follow_ups=())`:
- `previous_body = existing.body if (existing := store.pr_for_branch(row.branch)) else None`
- `reuse_summary = row.workflow in (RESOLVE_WORKFLOW, RESOLVE_REVIEWED_WORKFLOW)` (constants in
  `run/resolve.py`; check the exact name of the reviewed one, `review/flow.py` imports both).
- `CreatedFollowUp` is imported from `aifactory.run.followups` (TYPE_CHECKING-only import in
  prbody if a cycle appears; publish already imports `aifactory.run.store`).

## 3. Follow-ups and blocking (new `aifactory/src/aifactory/run/followups.py`)

```python
@dataclass(frozen=True)
class Reported:
    step: str; owner: str; follow_up: FollowUp          # from wf.history + wf.records

@dataclass(frozen=True)
class CreatedFollowUp:
    id: str; title: str; reason: str; blocks: bool; existed: bool
    def to_json(self) -> dict[str, object]: ...

@dataclass
class FollowUpOutcome:
    created: list[CreatedFollowUp]
    blocked_by: list[str]        # ids that block the task and are not done
    step_id: str | None          # the TODO step
    committed: bool
    warnings: list[str]
    def to_json(self) -> dict[str, object]: ...

def collect(wf: WorkflowRun) -> tuple[list[Reported], list[str]]:
    """Follow-ups (deduplicated by casefolded, whitespace-normalised title, first wins,
    but blocks_task is OR-ed) and `blocked_by` ids (deduplicated) of every envelope in
    `wf.history`. Owner/step: match the history key to the last StepRecord with that step."""

def reported_blockers(wf: WorkflowRun) -> bool  # any blocks_task or any blocked_by

def record(main: Path, task_id: str, run_id: str, wf: WorkflowRun) -> FollowUpOutcome:
```

`record` algorithm (all writes via `aifactory.backlog.edit`, never by hand):

1. `reported, blocked_ids = collect(wf)`; nothing → return empty outcome.
2. `backlog = load_for_edit(main)`; `task = find_task(backlog, task_id)`.
3. Project = `task.parent.parent` (the container above the task's step; `None` means the
   step is top level → TODO step is created top level with `parent=None`).
4. TODO step: a child of the project with `id == compose_id(project.id, "TODO")` or
   `title.strip().casefold() == "todo"`. Missing → `add_container(main, project.id, "TODO",
   "TODO", body="Práce, která vznikla při zpracování jiných tasků a nevešla se do nich. "
   "Tasky sem zakládá factory z hlášení agentů (follow_ups).")`.
5. For each follow-up: look for an existing task in the TODO step whose body contains
   `<!-- factory: follow-up-of=<task_id> -->` and whose title equals (normalised) → reuse
   (`existed=True`; makes retries and journal replays idempotent). Else
   `add_task(main, todo_step.id, title, related=[task_id], body=...)` with body:

   ```
   <details, or the reason when details are empty>

   ### Původ

   Vznikl při běhu `<run_id>` tasku `<task_id>` (<task title>), v kroku `<step>` (agent <owner>).
   Důvod: <reason>
   [Task `<task_id>` na tomto tasku závisí a do jeho dokončení zůstává blokovaný.]

   <!-- factory: follow-up-of=<task_id> -->
   ```
6. Blockers: ids of follow-ups with `blocks_task` + `blocked_ids` that exist in the backlog
   (Task or Container), `!= task_id`. Unknown ids → warning, ignored. Keep only ids whose
   node is not done (`derived.is_done`; for a Task status `done`). Ids not already in
   `task.depends_on` → `link_task(main, task_id, depends_on=new_ids)`. A `TaskEditError` (e.g.
   cycle) → warning; the id still counts as a blocker.
7. If anything was written: `commit_backlog(main, f"{task_id}: TODO tasky z běhu {run_id}")`;
   `TaskEditError` (not on base, push failed…) → warning "backlog changes are written but not
   committed: …", `committed=False`.
8. Each `TaskEditError` from steps 4–5 → warning, continue with the next follow-up.

### 3.1 Wiring in `run/task.py::_execute`

After `run_workflow` and the `accept not met` check, before `state` is decided, only when
`wf is not None and resolve is None`:

```python
follow = None
if wf is not None and resolve is None and followups.collect(wf) != ([], []):
    try:
        with store.serialized():
            follow = followups.record(main, row.task_id, row.run_id, wf)
    except Exception as exc:          # recording must never hide a blocker
        follow = None; warnings.append(f"follow-ups not recorded: {exc}")
    blockers = follow.blocked_by if follow is not None else (
        ["(neuložené hlášení agenta)"] if followups.reported_blockers(wf) else [])
    if blockers:
        reason = f"blocked: task {row.task_id} waits for {', '.join(blockers)}"
        error = reason if error is None else f"{reason}; {error}"
```

- A blocked run therefore ends `FAILED` with an error starting `blocked:` → no publish, no
  auto-merge (`try_auto_merge` / `member_auto_merge` already require `SUCCEEDED`), no done.
  The task now has `depends_on` on the blocker in base, so `derived_state` is `blocked` and the
  chain / `_unmet_error` will not start it again until the blocker is done. Work stays on the
  run's branch/worktree; a retry after the blocker is done replays the envelopes, finds the
  existing (done) TODO task and no longer blocks.
- Non-blocking follow-ups on a successful run: pass `follow.created` to
  `run_pr_body(store, final, job.task, wf, follow_ups=...)` so they appear under
  "Co uděláno nebylo".
- `TaskRunResult` gets `follow_ups: FollowUpOutcome | None = None`; its warnings are appended
  to `result.warnings` (tuple). Add `"follow_ups": ...to_json() or None` to the JSON in
  `cli.py` (~line 2233), `run/queue.py` (~line 363) and the member (de)serialisation in
  `run/members.py` (~line 257) if it round-trips TaskRunResult fields (keep it optional/None
  when absent).

### 3.2 Hard guard on approve (`review/flow.py::_approve`)

Before writing `status: done`: load the backlog of the main checkout
(`load_backlog(ctx.main, settings)`) and the branch backlog already loaded; if the task has
`unmet(...)` dependencies in either → `ReviewError("task_blocked", f"task {task_id} is blocked
by {ids}; finish them first")`. This covers an older open PR of the same branch (returned
task) and auto-merge (it goes through approve). Register `task_blocked` (exit 2) in
`skill/codes.py` next to `conflict`, and in the error table/docstring of `review/errors.py` if it
lists codes. If an existing test approves a task with unmet dependencies on purpose, adapt the
fixture rather than weakening the guard.

## 4. Prompts (`aifactory/src/aifactory/seed/agents/`)

Add the same section to `system.md` of **builder, planner, reviewer, documenter, tester**
(builder covers build/fix/revise/resolve):

```
## Unfinished work

- Never leave open work in the repository: no TODO files, no lists of open points, no "later"
  sections in docs or specs, no `TODO`/`FIXME`/"finish later" comments.
- Work that turns out to be out of scope, extra, or a changed intent, and that you cannot finish
  in this task, goes into `follow_ups` in your Report: `title`, `reason` (what you found, where,
  why it is not done here), `details` (what the new task must do). The factory files each one as a
  task in the project's TODO step.
- If this task cannot be correctly finished until that work (or an existing backlog task) is
  done, set `blocks_task: true` on the follow-up, or list the existing task id in `blocked_by`.
  The factory then stops the task as blocked instead of done. Do not report blocking for work
  that is merely nice to have.
- Prefer finishing the work in this task when it fits its scope; follow-ups are for what does not.
```

`user.md` JSON examples: add `"follow_ups": []` and `"blocked_by": []` to builder, planner,
reviewer, documenter, tester; plus one sentence after the example describing the follow-up
object shape (`{"title", "reason", "details", "blocks_task"}`).

PR summary (`pr_summary`) — add to **builder, reviewer, documenter** `user.md` example and a
short instruction:

```
"pr_summary": {
  "goal": "<why the task exists, 1–2 sentences, in the language of the task>",
  "done": ["<an outcome for the PR reviewer, not a file list>"],
  "not_done": ["<what was left out or deviates from the task, and why>"],
  "notes": ["<risk, behaviour change, or what to check by hand>"]
}
```
Instruction: "Summarise the whole change on the branch, not just your step, for the person who
approves the PR. Do not copy the task text and do not list files. Write in the task's language.
The latest agent's summary is the one in the PR, so the reviewer and documenter correct earlier
ones." Reviewer: `not_done` must include every unmet finding it still approves around (e.g.
deliberate deviations). Do not add `pr_summary` to tester/planner.

Do not touch `.factory/` (protected). Seed item versions are content hashes — check
`tests/library/` for any test pinning a seed hash or prompt text and update it.

## 5. Tests (no live models; use the fakes in `tests/workflow/workflow_fakes.py`, `tests/run/run_repo.py`)

New/changed files:

- `aifactory/tests/review/test_prbody_summary.py` (pure, build `WorkflowRun` objects by hand):
  - body starts with the marker line; has `## Cíl`, `## Co bylo uděláno`,
    `## Co uděláno nebylo` before `## Technické podrobnosti`; contains no `## Zadání` and not the
    task body text.
  - latest non-empty `pr_summary` in `history` wins.
  - empty `not_done` and no follow-ups → `- nic`; follow-ups listed with their ids.
  - `## Důležité pro schválení` only when notes exist.
  - no summary → fallback (title + "_Agenti běhu shrnutí nedodali._"), still no task body.
  - `reuse_summary=True` with a previous body → summary block reused verbatim;
    `previous_summary` returns None for a body without `SUMMARY_END`.
- `aifactory/tests/run/test_followups.py` (backlog repo from `tests/run/run_repo.py` or
  `tests/backlog/backlog_repo.py`; call `followups.record` directly with a hand-made `WorkflowRun`):
  - creates step `<project>-TODO` when missing, task in it with `related`, the `### Původ`
    section (task id, run id, step, reason) and the marker; backlog stays valid (`check_backlog`).
  - reuses an existing TODO step (by id and by title "TODO").
  - second `record` with the same envelopes creates nothing new (idempotent).
  - `blocks_task` → task gets `depends_on` on the new id and `blocked_by` contains it;
    `derived_state` of the task is `blocked`.
  - `blocked_by` with an existing not-done id → linked; with a done id → not blocking;
    unknown id → warning, ignored.
  - changes are committed to base (`git log -1` subject) when the main checkout is on base.
- Run-level (extend `tests/run/test_task_run.py` or `test_task_pr_flow.py`, scripted fake agents
  returning `ok(follow_ups=[...])`):
  - builder reports a blocking follow-up → run `failed`, `error` starts with `blocked:`, no PR in
    store, TODO task exists in base, task has `depends_on`.
  - non-blocking follow-up → run succeeds, PR body lists the new task id under
    "Co uděláno nebylo".
- `tests/review/test_approve_merge_retry.py` (or the auto-merge tests): approve of a task with
  unmet `depends_on` raises `ReviewError` `task_blocked` and does not merge.
- Update existing assertions: `tests/run/test_task_pr_flow.py:76` (drop `## Zadání` and the
  task text; assert the new headings), `tests/web/test_web_review.py:193`,
  `tests/run/test_task_publish.py:177` if headings change, and any other hit of
  `grep -rn "## Zadání\|## Agenti" aifactory/tests` that refers to PR bodies (task-file tests
  about `## Zadání` in backlog files are unrelated — leave them).

## 6. Documentation (task doc file)

Write `factory/docs/HAIFA/REFINEMENT-upravy-opravy-a-vylepseni-z-praxe/HAIFA-REFINEMENT-T26-lepsi-popisy-pull-requestu-a-tvrde-zacha.md`
in Czech: the new PR body layout; the `follow_ups` / `blocked_by` / `pr_summary` envelope
fields; how the TODO step and tasks are created; that a blocked run ends `failed` with
`blocked:`, the task gets `depends_on`, approve refuses with `task_blocked`; and a short
**Rozhodnutí** section with the table from section 0 (why code vs prompts vs no workflow change).
Note that `docs/decisions.md` should take this decision over in a follow-up outside this task's
allowed paths — report that as a `follow_ups` entry in your own envelope, not as a note in the repo.

## 7. Verification

- `just lint`, `just typecheck`.
- `just pytest tests/review tests/run/test_followups.py tests/run/test_task_pr_flow.py tests/run/test_task_publish.py tests/run/test_task_run.py tests/web/test_web_review.py tests/library tests/engine`
  (run the narrower files first while iterating: `cd aifactory && uv run pytest <file> -n0`).
- `grep -rn "Zadání" aifactory/src/aifactory/review/` → no hit.
- No frontend change expected; skip `just web-test` unless `aifactory/web/` changes.
