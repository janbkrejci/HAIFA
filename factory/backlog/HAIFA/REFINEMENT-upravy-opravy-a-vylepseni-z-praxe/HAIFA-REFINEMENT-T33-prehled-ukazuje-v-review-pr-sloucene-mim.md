---
id: HAIFA-REFINEMENT-T33
title: Přehled ukazuje v review PR sloučené mimo factory
status: done
archived: true
workflow: simple-sdlc
depends_on: []
related: [HAIFA-REFINEMENT-T24, HAIFA-REFINEMENT-T20]
writes: [aifactory/src/aifactory/web/, aifactory/src/aifactory/review/, aifactory/src/aifactory/run/, aifactory/web/src/, aifactory/tests/]
---

## Zadání
Když se PR tasku sloučí mimo factory (`gh pr merge`, web GitHubu nebo Azure), zůstane v `task_prs` v trace DB ve stavu `open`. Přehled (`web/overview.py`) čte review jen z `task_prs`, a tak task dál ukazuje jako „čeká na review“. Platí to i pro task, který už má v base `status: done`. Stav PR se dnes obnoví jen ručním `factory backlog sync`. Stalo se to s HAIFA-REFINEMENT-T24 (PR #37): po ručním merge byl na Přehledu v review, dokud se nespustil sync.

Stejný zastaralý stav čtou i kanban (`web/backlog.py`, `in_review` z `store.open_prs()`) a výběr dalšího tasku (`run/queue.py`).

## Úkol
1. Dashboard obnovuje stav otevřených task PR od providera sám, bez ručního `factory backlog sync`. Použít stávající `_refresh_task_prs` / `_record_state` z `review/sync.py`, neduplikovat je. Obnova běží na pozadí s rozumným intervalem. `GET /api/overview` dál jen čte a nevolá providera synchronně.
2. Review na Přehledu nezobrazuje tasky, které jsou v base `done` nebo `cancelled`, stejně jako už to dělá seznam `failed` (`CLOSED_STATUSES`).
3. Když obnova zjistí merge mimo factory a task v base není `done`, Přehled to ukáže jako akci (otevřít sync PR přes stávající `sync_backlog`). Sync PR se nezakládá automaticky.
4. `merged_at` ukládat podle času merge od providera, pokud ho provider vrací, ne podle času syncu.

## Akceptační kritéria
- PR sloučený mimo factory zmizí z review na Přehledu i z `in_review` na kanbanu nejpozději po jednom intervalu obnovy.
- Task s `status: done` v base se v review nezobrazí ani s PR, který je v trace `open`.
- Testy pokrývají obnovu i filtr stavů s fake providerem, bez sítě.
- `just lint`, `just typecheck` a testy dotčených balíčků projdou.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-15 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/45 · náklady $5.07
