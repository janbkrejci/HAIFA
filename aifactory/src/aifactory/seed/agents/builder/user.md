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

`follow_ups` and `blocked_by` are empty unless you found work this task does not finish (see "Unfinished work"). A follow-up is `{"title": "...", "reason": "...", "details": "...", "blocks_task": false, "writes": null, "for_human": false, "workflow": null}`; `blocked_by` holds ids of existing backlog tasks.

`pr_summary` is the summary of the whole change on the branch, not just your step, for the person who approves the pull request. Write it in the language of the task. Do not copy the task text and do not list files: `goal` says why the task exists, `done` the outcomes, `not_done` what was left out or deviates from the task and why (empty when nothing), `notes` risks, behaviour changes and what to check by hand. The latest agent's summary is the one in the pull request, so correct an earlier one when it is wrong or incomplete.
