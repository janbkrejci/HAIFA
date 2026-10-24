# Choose checks for this change

## Task and project

{{prompt}}

## Baseline

{{baseline}}

## Build, fix or revision

{{previous_envelope}}

## Reusable testing profile

{{testing_profile}}

Use the profile to avoid rediscovering runners and test locations. Check it against the
current project and diff; refresh it when missing, stale or incomplete. Return concise
reusable knowledge in `testing_profile`, distinct from this run's selected checks.

## Required coverage and shared test time limit

Coverage: {{required_coverage}} (`full`, `scoped` or `any`).
Time limit for all checks together: {{test_timeout}} seconds.

## Previous plan and latest test evidence

{{previous_test_plan}}

{{test_result}}

Keep earlier checks or name them in `dropped` with a reason. Correct a broken command
when necessary; never weaken a check because it caught a real defect.

## Handoff directory

{{context_handoff_dir}}

`<context_handoff_dir>` is an absolute path outside the repo. Write handoff files at exactly that path; never create a directory of the same name inside the repo or the worktree.

Write a short `test-plan.md` there. Change nothing in the repository and do not run
the checks yourself.

## Report

Return only JSON matching `TestPlanOutput`:

```json
{
  "status": "success",
  "summary": "Checks covering this change",
  "coverage": "scoped",
  "reason": "Why these checks cover the diff and its direct callers",
  "testing_profile": "Reusable runner commands, test locations and selection rules for this project",
  "checks": [
    {"name": "targeted-tests", "argv": ["uv", "run", "pytest", "tests/test_example.py"]}
  ],
  "dropped": [],
  "artifacts": ["<context_handoff_dir>/test-plan.md"],
  "notes_for_next_agent": ""
}
```

Every argv runs from the repository root without a shell. Order checks from fastest to
slowest. Optional `timeout` is seconds; explicit timeouts must fit the shared limit.
Use `stop_on_fail: true` only for prerequisites such as a build or install.
`coverage: none` has no checks and needs a reason; full/scoped require checks.
Use `follow_ups`, `blocked_by` and `needs_writes` as described in your system instructions.
