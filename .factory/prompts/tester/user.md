# Test Plan Task

## Variables

### prompt

{{prompt}}

### baseline

{{baseline}}

### previous_envelope

The step before you: the build, a fix or a revision (with the files it changed), or a review whose findings concern the test plan:

{{previous_envelope}}

### required_coverage

`full`, `scoped` or `any` (your choice):

{{required_coverage}}

### previous_test_plan

The plan the last test ran, `(none)` for the first plan of the run. Keep each of its checks or name it in `dropped`:

{{previous_test_plan}}

### failed_test

`(none)` when you plan. Otherwise you triage: the test that just failed (its checks, exit codes and logs). Decide whether the plan or the code is at fault:

{{failed_test}}

### test_result

The latest test result, `(none)` before any test ran:

{{test_result}}

### context_handoff_dir

{{context_handoff_dir}}

`<context_handoff_dir>` is an absolute path outside the repo. Write handoff files at exactly that path; never create a directory of the same name inside the repo or the worktree.

## Task

1. Read the whole change: `git diff {{baseline}}` and untracked files.
2. Find how this repo runs its tests and static checks.
3. Choose the checks: enough to trust the change, nothing beyond it.
4. Write the reasoning to `<context_handoff_dir>/test-plan.md`, then emit your `Report` JSON.

## Report

Respond with ONLY valid JSON matching `TestPlanOutput` — no prose before or after:

```json
{
  "status": "success",
  "summary": "<one sentence: what the checks cover>",
  "coverage": "scoped",
  "reason": "<why these checks are enough, and why nothing wider is needed>",
  "failure_cause": "",
  "checks": [
    { "name": "api-tests", "argv": ["uv", "run", "pytest", "tests/api", "-q"] },
    { "name": "types", "argv": ["npm", "run", "typecheck"], "timeout": 300 }
  ],
  "dropped": [
    { "name": "old-check", "reason": "<why it no longer applies: reverted code, or the reviewer's finding>" }
  ],
  "artifacts": ["<context_handoff_dir>/test-plan.md"],
  "notes_for_next_agent": ""
}
```

`coverage` is `full`, `scoped` or `none`; `none` has an empty `checks` list, the others at least one. Check names are unique and contain no `/`. `timeout` (seconds) is optional. `dropped` is empty for a first plan. `failure_cause` is `""` when you plan, `"plan"` or `"code"` when you triage.
