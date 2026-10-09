# Plan Task

## Variables

### prompt

{{prompt}}

### previous_envelope

{{previous_envelope}}

### context_handoff_dir

{{context_handoff_dir}}

`<context_handoff_dir>` is an absolute path outside the repo. Write handoff files at exactly that path; never create a directory of the same name inside the repo or the worktree.

## Task

Plan the work described in `prompt`.

1. Write the full plan to `<context_handoff_dir>/plan.md` — this is the copy the builder reads.
2. Copy that file into the repo as `{{spec_path}}`. The task run named it and allows only this path for the plan; do not pick another name and do not add a suffix. If the file already exists (an earlier run of this task), replace its content.
   **Copy it, do not retype it.** One bash call does the whole step:
   `mkdir -p "$(dirname "{{spec_path}}")" && cp "<context_handoff_dir>/plan.md" "{{spec_path}}"`
   Writing the plan a second time through `write` re-emits every line you already wrote, which costs the whole document again in output tokens and lets the two copies drift.
3. Emit your `Report` JSON, declaring BOTH paths in `artifacts`.

## Report

Respond with ONLY valid JSON matching `PlanOutput` — no prose before or after:

```json
{
  "status": "success",
  "summary": "<one sentence describing the plan>",
  "artifacts": ["<context_handoff_dir>/plan.md", "{{spec_path}}"],
  "commit_message": "<imperative one-line git subject for committing THIS PLAN DOCUMENT, not the work it describes — e.g. 'Add spec for the /health endpoint'; the workflow makes this commit, do not run git commit yourself>",
  "notes_for_next_agent": "<what the builder must know>"
}
```

The `artifacts` entry in the repo is exactly `{{spec_path}}`. Gates open these files — any other name fails them.
