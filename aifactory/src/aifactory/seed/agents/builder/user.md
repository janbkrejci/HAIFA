# Build Task

## Variables

### prompt

{{prompt}}

### previous_envelope

{{previous_envelope}}

### context_handoff_dir

{{context_handoff_dir}}

`<context_handoff_dir>` is an absolute path outside the repo. Write handoff files at exactly that path; never create a directory of the same name inside the repo or the worktree.

## Task

Implement the work described in `prompt`, guided by `previous_envelope` if present, then emit your `Report` JSON.

## Report

Respond with ONLY valid JSON matching `BuildOutput` — no prose before or after:

```json
{
  "status": "success",
  "summary": "<one sentence describing what you built>",
  "changed_files": ["src/server.ts"],
  "artifacts": [],
  "commit_message": "<imperative one-line git subject for the code you changed — the workflow makes this commit; do not run git commit yourself>",
  "follow_ups": [],
  "blocked_by": [],
  "pr_summary": {
    "goal": "<why the task exists, 1-2 sentences>",
    "done": ["<an outcome, not a file>"],
    "not_done": ["<what was left out or deviates from the task, and why>"],
    "notes": ["<risk, behaviour change, or what to check by hand>"]
  },
  "notes_for_next_agent": "<how to verify this work>"
}
```

When the work is already done (another task or commit made the change), change nothing and report `"status": "success"` with `"already_done": {"evidence": ["<commit sha or subject, or repo file where the change is>"], "reason": "<one sentence>"}`, `"changed_files": []` and the evidence in `summary`. The run then ends as done without changes. Name only evidence you checked in the repo.

When the request asks only for a change of the backlog (a task's front matter, status or text), or for no change at all, report `"status": "fail"` with `"fail_kind": "nothing_to_do"` and say in `summary` what must change and where. The backlog is the factory's, never edit it. Leave `fail_kind` and `already_done` out in every other case, except `needs_writes` below.

`needs_writes` lists the paths this task must change that its allowed paths do not cover, each `{"path": "...", "reason": "..."}` (see "Unfinished work"). When you cannot finish without them, report `"status": "fail"` with `"fail_kind": "needs_writes"` and the paths in `needs_writes`, and no follow-up for them. Otherwise leave `needs_writes` out.

`follow_ups` and `blocked_by` are empty unless you found work this task does not finish (see "Unfinished work"). A follow-up is `{"title": "...", "reason": "...", "details": "...", "blocks_task": false, "writes": null, "for_human": false, "workflow": null}`; `blocked_by` holds ids of existing backlog tasks.

`pr_summary` is the summary of the whole change on the branch, not just your step, for the person who approves the pull request. Write it in the language of the task. Do not copy the task text and do not list files: `goal` says why the task exists, `done` the outcomes, `not_done` what was left out or deviates from the task and why (empty when nothing), `notes` risks, behaviour changes and what to check by hand. The latest agent's summary is the one in the pull request, so correct an earlier one when it is wrong or incomplete.
