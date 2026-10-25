---
id: HAIFA-REFINEMENT-T48
title: task retry vrací run_failed i po úspěšném a mergnutém pokusu
status: done
archived: true
depends_on: []
---

## Zadání
`factory task retry ROB-S21-T005 --from plan --json` (NEO_HEF, 2026-10-19, factory 0.1.380) skončil exit 1 s obálkou `ok: false`, `error.code: run_failed`, přestože běh `b4239924` skončil `succeeded`, otevřel PR #30400 a auto-merge ho mergnul (`data.auto_merge.merged: true`). Kdo řídí factory skriptem podle `ok` / exit kódu, považuje úspěšný a mergnutý běh za selhaný.

Zadání: obálka `task retry` odpovídá výsledku pokusu stejně jako u `task run`: úspěšný pokus = exit 0 a `ok: true`, `run_failed` jen pro skutečně selhaný nebo `accept_not_met` pokus.

Hotovo znamená:
- Test: úspěšný retry (i s `--from`) vrací exit 0 a `ok: true` s `data.run.state: succeeded`.
- Test: selhaný retry vrací `run_failed` jako dosud.
- Dotčené testy projdou podle AGENTS.md, celou sadu ověří CI.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-19 · workflow build-test-review · bez změn, běh 61e65f98 · už hotovo: aifactory/src/aifactory/cli.py: _task_retry a _task_run používají společné _chain_output a _emit_runs., aifactory/src/aifactory/run/task.py: TaskRunResult.ok vyhodnocuje aktuální stav succeeded a pr_error., aifactory/tests/run/test_auto_merge.py: test_retry_merges_and_continues ověřuje exit 0 a úsp… · náklady $0.00
