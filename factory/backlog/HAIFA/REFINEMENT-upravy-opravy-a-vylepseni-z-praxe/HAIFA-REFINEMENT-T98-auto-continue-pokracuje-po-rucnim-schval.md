---
id: HAIFA-REFINEMENT-T98
title: "Auto-continue pokračuje po ručním schválení PR, které auto-merge nesloučil"
status: done
archived: true
workflow: build-test-review
depends_on: []
writes: [aifactory/src/aifactory/run/queue.py, aifactory/src/aifactory/run/__init__.py, aifactory/src/aifactory/run/store.py, aifactory/src/aifactory/review/flow.py, aifactory/src/aifactory/cli.py, aifactory/tests/review/test_approve_continue.py, aifactory/tests/run/test_auto_continue.py]
---

## Zadání
Situace: task s `auto_merge` a `auto_continue` doběhne, ale `try_auto_merge` (aifactory/src/aifactory/review/automerge.py) PR nesloučí. Důvodem je například `no_review_phase` nebo `no_review` (workflow bez review), zamítnuté review nebo červené CI. Řetěz pak skončí se `stop == "not_merged"` (aifactory/src/aifactory/run/queue.py: `_sequential` i `_run_parallel`) a záznam v `task_chains` to uloží. Když člověk PR potom schválí přes `factory task approve` nebo tlačítkem Schválit v dashboardu (web spouští `factory task approve` v procesu, web/launcher.py `start_approve`), PR se sloučí, ale nic dalšího se nespustí. `approve_task` v aifactory/src/aifactory/review/flow.py řetěz neobnoví.

Co udělat:
- V run/queue.py přidej funkci, například `continue_after_merge(repo, task_id, ...)`. Ta zjistí, zda poslední řetěz, jehož posledním během byl běh tohoto tasku, skončil se `stop == "not_merged"`, a zda task v base (po merge) má zděděné `auto_continue` zapnuté. Řetěz spuštěný s `--auto` platí také. Pokud ano, pokračuje stejně, jako by auto-merge PR sloučil: vybere další task přes `select_next` s `after=` sloučeným taskem, tedy se stejnými pravidly projektu, ruční fronty, závislostí i výjimky T56, s `require_auto_continue` podle původního řetězu, a spustí ho jako nový řetěz (`run_chain`). Paralelní limit a obsazené sloty (`Slots`, `Occupancy`) platí jako jinde. Bez splněných podmínek se nestane nic.
- Pokračování z jednoho zastaveného řetězu proběhne jen jednou. Původní řetěz v `task_chains` označ, že už pokračoval (například novým stop/stavem nebo sloupcem přidaným přes `_CHAIN_ADDED_COLUMNS` v run/store.py), aby opakované approve nebo souběh nespustily dva řetězy.
- `approve_task` po úspěšném merge (merged_by operator) pokračování zavolá. `ApproveResult` dostane pole `chain` (vzor `PublishResult.chain`) a `to_json` ho vrátí. `_task_approve` v cli.py vypíše řetěz stejně jako `_chain_output` (běhy, `auto-continue: stopped (...)`, waiting).
- Volání `approve_task` z auto-merge (merged_by auto-merge) pokračování spouštět nesmí, protože tam řetěz pokračuje sám.

Mimo rozsah: sloučení PR mimo factory, tedy na GitHubu nebo v Azure (samostatný task), změny UI a dokumentace.

Hotovo znamená:
- Nový test aifactory/tests/review/test_approve_continue.py (s mockem provideru a run_task jako stávající testy auto-merge). Po řetězu zastaveném na `not_merged` (workflow bez review) a následném `approve_task` se spustí další připravený task stejného projektu s `auto_continue` a `ApproveResult.chain` ho obsahuje.
- Test: task bez `auto_continue`, nebo řetěz zastavený z jiného důvodu (failed, exhausted), po approve nic nespustí.
- Test: druhé approve nebo opakované volání pokračování nespustí druhý řetěz.
- Test: auto-merge (merged_by auto-merge) nespouští pokračování podruhé.
- Dotčené stávající testy v aifactory/tests/run/test_auto_continue.py, test_auto_merge.py, tests/review/test_approve_merge_retry.py a test_task_run_cli.py procházejí.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-01 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/190 · náklady $0.00
