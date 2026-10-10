# Test Plan Review Task

## Variables

### prompt

{{prompt}}

### baseline

{{baseline}}

### required_coverage

{{required_coverage}}

### previous_envelope

The test plan to judge:

{{previous_envelope}}

### test_result

The latest test result, `(none)` before any test ran:

{{test_result}}

### context_handoff_dir

{{context_handoff_dir}}

`<context_handoff_dir>` is an absolute path outside the repo. Write handoff files at exactly that path; never create a directory of the same name inside the repo or the worktree.

## Task

1. Read the change: `git diff {{baseline}}` and untracked files.
2. Rule on the plan: is it sufficient, is it needlessly broad, is every `dropped` entry justified?
3. Write the review to `<context_handoff_dir>/test-review.md`, then emit your `Report` JSON.

## Report

Respond with ONLY valid JSON matching `ReviewOutput` — no prose before or after:

```json
{
  "status": "success",
  "approved": false,
  "summary": "<one sentence: the verdict on the plan>",
  "findings": [
    { "requirement": "checks cover the changed code", "met": true, "evidence": "tests/api cover src/api/health.py" },
    { "requirement": "nothing needless runs", "met": false, "evidence": "the e2e suite cannot be affected by a CLI-only change" }
  ],
  "blocking": ["<the missing or needless check, named>"],
  "artifacts": ["<context_handoff_dir>/test-review.md"],
  "notes_for_next_agent": "<what the tester must change>"
}
```

`status` is `success` when the review itself completed. `approved` is true only when `findings` has no unmet entry and `blocking` is empty.
