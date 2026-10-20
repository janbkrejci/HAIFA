---
id: HAIFA-TODO-T22
title: Aktualizovat migrační test task_prs pro approved_at
status: cancelled
depends_on: []
related: [HAIFA-REFINEMENT-T59]
writes: [aifactory/tests/run/test_auto_merge.py]
---

## Zadání
Upravit test_store_adds_the_new_columns tak, aby ověřoval přítomnost merged_by, auto_merge_error a approved_at bez závislosti na jejich pozici. Ověřit výchozí NULL, zápis approved_at a zachování hodnot po opakovaném otevření. Znovu spustit neúspěšnou kontrolu approval-flow-and-callers.

### Původ

Vznikl při běhu `8f263ff2` tasku `HAIFA-REFINEMENT-T59` (Backend: stav „Schváleno, čeká na CI“ po ručním schválení PR), v kroku `fix` (agent builder), v kroku `test_plan` (agent tester).
Důvod: aifactory/tests/run/test_auto_merge.py:807 očekává přesně dva poslední sloupce merged_by a auto_merge_error. Po požadovaném přidání approved_at toto očekávání neplatí. Soubor není v povolených cestách T59.
Task `HAIFA-REFINEMENT-T59` na tomto tasku závisí a do jeho dokončení zůstává blokovaný.

<!-- factory: follow-up-of=HAIFA-REFINEMENT-T59 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
