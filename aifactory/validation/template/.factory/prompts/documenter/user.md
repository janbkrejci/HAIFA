# Document Task

## Variables

### prompt

{{prompt}}

### previous_envelope

{{previous_envelope}}

### context_handoff_dir

{{context_handoff_dir}}

`<context_handoff_dir>` is an absolute path outside the repo. Write handoff files at exactly that path; never create a directory of the same name inside the repo or the worktree.

## Task

Document the completed work described by `previous_envelope`, using `prompt` for what was originally asked.

1. Read the full diff at `previous_envelope.diff_path`, plus any changed file that needs context.
2. Write the write-up to `<context_handoff_dir>/document.md`. Cover: what changed and why it matters, the files that carry it, and how to use or verify it.
3. Copy that file into the repo as `{{doc_path}}`. The task run named it and allows only this path for the write-up; do not pick another name and do not add a suffix. If the file already exists (an earlier run of this task), replace its content.
   **Copy it, do not retype it.** One bash call does the whole step:
   `mkdir -p "$(dirname "{{doc_path}}")" && cp "<context_handoff_dir>/document.md" "{{doc_path}}"`
   Writing the document a second time through `write` re-emits every line you already wrote, which costs the whole write-up again in output tokens and lets the two copies drift.
4. Emit your `Report` JSON, declaring BOTH paths in `artifacts`.

## Report

Respond with ONLY valid JSON matching `DocumentOutput` — no prose before or after:

```json
{
  "status": "success",
  "summary": "<one sentence describing what you documented>",
  "document_path": "{{doc_path}}",
  "documented_files": ["src/server.ts"],
  "artifacts": ["<context_handoff_dir>/document.md", "{{doc_path}}"],
  "commit_message": "<imperative one-line git subject for committing THIS WRITE-UP, not the change it describes — e.g. 'Document the /health endpoint'; the workflow makes this commit, do not run git commit yourself>",
  "notes_for_next_agent": "<anything the diff left unexplained>"
}
```

`document_path` and the repo entry in `artifacts` are exactly `{{doc_path}}`. Gates open these files — any other name fails them.
