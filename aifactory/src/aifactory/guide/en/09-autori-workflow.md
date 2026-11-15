# Workflow author appendix

A workflow is YAML with a name, description, steps and an `accept` condition. Save custom workflows in the repository's `.factory/workflows/<name>.yaml` or the library; validate with `giro workflow check .factory/workflows/<name>.yaml`.

## Steps <!-- section:kroky -->

**Agent steps**: `plan`, `scout`, `build`, `fix`, `revise`, `ask`, `resolve`, `test_plan`, `review`, `document`. Options: `agent`, `harness`, `model`, `thinking`, `when`, `id`, `description`, `input`.

**Code steps**: `test` (executes the tester's plan), `commit`, `changes`, `command` (`id`, `argv`, `timeout`), `rebase`, `rebuild`.

The tester uses a local project profile containing commands, selection rules and measured times; it refreshes the profile when configuration changes. The builder repairs failures; the final reviewer checks missing tests. Automatic plan revision and triage do not run; `test_review` can be specified explicitly.

`test_plan.coverage`: `full` requests the whole suite, `scoped` checks the change; other values are rejected.

## Conditions and loops <!-- section:podminky-a-smycky -->

- `repeat: {max: N, until: condition}` with nested `steps` repeats steps; `until` is evaluated after each step.
- `when: condition` skips a step when false.
- `accept: condition` determines whether the run succeeded.

Conditions read step outputs (`test.passed`, `test.coverage`, `review.approved`, `rebase.conflict`) and support `and`, `or`, `not` and comparisons. They are never evaluated as code.

```yaml
name: build-test-review
description: Build, test with repairs, review with revision
steps:
  - build
  - test_plan
  - repeat: {max: 3, until: test.passed}
    steps:
      - test
      - fix
      - test_plan
  - repeat: {max: 2, until: review.approved}
    steps:
      - review:
          input: [build, fix, revise]
      - revise
      - test_plan:
          id: replan
          input: [review]
      - test:
          id: retest
  - commit:
      when: test.passed and review.approved
accept: test.passed and review.approved
```

Auto-merge merges only PRs from workflows containing a `review` step.

## roles.yaml <!-- section:roles-yaml -->

`.factory/roles.yaml` overrides which agent performs each step. Keep only changed roles; a full copy of the built-in registry (`roles_full_copy`) would prevent you from receiving future registry changes.
