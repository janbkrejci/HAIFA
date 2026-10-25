---
id: HAIFA-TODO-T01
title: Update docs/decisions.md for CI-gated approve and auto-merge
status: done
archived: true
depends_on: [HAIFA-TODO-T05]
related: [HAIFA-REFINEMENT-T28]
---

## Zadání
Add or replace the decision in docs/decisions.md. Approve and auto-merge wait for the checks of the merge head (after the status: done push). Red checks start up to CI_FIX_ROUNDS=2 internal ci-fix runs on the PR branch. If CI stays red or pending, the PR stays open with auto_merge_error. On GitHub the dashboard approves in the background.

### Původ

Vznikl při běhu `1fb74e3c` tasku `HAIFA-REFINEMENT-T28` (Automerge se musí postarat i o zelenou CI pipeline), v kroku `plan` (agent planner).
Důvod: T28 changes the decision that auto-merge only checks the CI and leaves red PRs open: approve and auto-merge now wait for the merge head's CI and run ci-fix repairs. docs/decisions.md is outside this task's allowed paths.

<!-- factory: follow-up-of=HAIFA-REFINEMENT-T28 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-16 · bez změn: rozhodnutí je v docs/decisions.md z HAIFA-TODO-T05 (6a6cb2a)
