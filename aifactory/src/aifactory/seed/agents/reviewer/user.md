# Review Task

## Variables

### prompt

{{prompt}}

### previous_envelope

{{previous_envelope}}

### test_result

The test step already ran the tester's checks on this same code. Its result (`passed`, `command`, `log`, and `test_plan` with the coverage, reason and commands) is below; do not run the checks again, read the log if you need their output:

{{test_result}}

### context_handoff_dir

{{context_handoff_dir}}

`<context_handoff_dir>` is an absolute path outside the repo. Write handoff files at exactly that path; never create a directory of the same name inside the repo or the worktree.

## Task

Confirm that the work reported in `previous_envelope` is what was asked for.

1. Establish the spec: read `<context_handoff_dir>/plan.md` if it exists, else use `prompt`.
2. Read the code that was actually written, starting from `previous_envelope.changed_files`.
3. Rule on every requirement in the spec — one `findings` entry each, with evidence.
   Add one entry "test plan fits the change": sufficient for the change, not needlessly broad.
4. Write the review to `<context_handoff_dir>/review.md`, then emit your `Report` JSON.

## Report

Respond with ONLY valid JSON matching `ReviewOutput` — no prose before or after:

```json
{
  "status": "success",
  "approved": false,
  "summary": "<one sentence: N of M requirements met>",
  "findings": [
    { "requirement": "<the ask, in the requester's words>", "met": true, "evidence": "src/server.ts:42 — handler registered" }
  ],
  "blocking": ["<what must change before this can be approved>"],
  "artifacts": ["<context_handoff_dir>/review.md"],
  "follow_ups": [],
  "blocked_by": [],
  "pr_summary": {
    "goal": "<why the task exists, 1-2 sentences>",
    "done": ["<an outcome, not a file>"],
    "not_done": ["<what was left out or deviates from the task, and why>"],
    "notes": ["<risk, behaviour change, or what to check by hand>"]
  },
  "notes_for_next_agent": "<what the builder must fix, or how to verify if approved>"
}
```

`follow_ups` and `blocked_by` are empty unless you found work this task does not finish (see "Unfinished work"). A follow-up is `{"title": "...", "reason": "...", "details": "...", "blocks_task": false, "writes": null, "for_human": false, "workflow": null}`; `blocked_by` holds ids of existing backlog tasks.

`pr_summary` is the summary of the whole change on the branch, not just your step, for the person who approves the pull request. Write it in the language of the task. Do not copy the task text and do not list files: `goal` says why the task exists, `done` the outcomes, `not_done` what was left out or deviates from the task and why (empty when nothing), `notes` risks, behaviour changes and what to check by hand. The latest agent's summary is the one in the pull request, so correct an earlier one when it is wrong or incomplete. Put every deviation from the task you still approve around into `not_done`.

`status` is `success` when the review itself completed — it is not the verdict. The verdict is `approved`, and it is true only when `findings` has no unmet entry and `blocking` is empty.
