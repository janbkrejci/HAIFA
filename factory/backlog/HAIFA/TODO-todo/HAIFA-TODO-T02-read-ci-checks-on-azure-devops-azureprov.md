---
id: HAIFA-TODO-T02
title: Read CI checks on Azure DevOps (AzureProvider.checks / check_logs)
status: done
depends_on: []
related: [HAIFA-REFINEMENT-T28]
---

## Zadání
Implement AzureProvider.checks (PR policy evaluations / build status via az repos pr policy list or az pipelines runs), set reports_checks=True, and implement check_logs (az pipelines runs logs) so the ci-fix run gets the failure output. Add tests with a fake az.

### Původ

Vznikl při běhu `1fb74e3c` tasku `HAIFA-REFINEMENT-T28` (Automerge se musí postarat i o zelenou CI pipeline), v kroku `plan` (agent planner).
Důvod: AzureProvider does not implement checks, so with git_provider azure the new CI gate always sees 'none' and merges without waiting for Azure Pipelines. Found in aifactory/src/aifactory/providers/ (only github.py overrides checks). This is outside T28's GitHub-focused scope.

<!-- factory: follow-up-of=HAIFA-REFINEMENT-T28 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-18 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/109 · náklady $1.68
