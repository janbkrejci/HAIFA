# Test Plan Task

## Variables

### prompt

{{prompt}}

### baseline

{{baseline}}

### previous_envelope

{{previous_envelope}}

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
  "checks": [
    { "name": "api-tests", "argv": ["uv", "run", "pytest", "tests/api", "-q"] },
    { "name": "types", "argv": ["npm", "run", "typecheck"], "timeout": 300 }
  ],
  "artifacts": ["<context_handoff_dir>/test-plan.md"],
  "notes_for_next_agent": ""
}
```

`coverage` is `full`, `scoped` or `none`; `none` has an empty `checks` list, the others at least one. Check names are unique and contain no `/`. `timeout` (seconds) is optional.
