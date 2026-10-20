---
id: HAIFA-REFINEMENT-T53
title: "API přehledu: běhy, PR, selhání a stavy tasků po projektech"
status: done
workflow: build-test-review
depends_on: []
writes: [aifactory/src/aifactory/web/overview.py, aifactory/tests/web/test_web_overview.py, aifactory/tests/web/overview_fixture.py]
---

## Zadání
## Zadání
V repu s více projekty (nejvyšší úroveň backlogu při `levels` `project -> step -> task`) má `GET /api/overview` vracet data repa i rozdělená po projektech. Podle nich pak dashboard ukáže dlaždici repa po projektech (navazující task).

## Současný stav
- `aifactory/src/aifactory/web/overview.py`: `Overview.repo()` skládá položku repa. `_lists()` vrací `running`, `review`, `automerge`, `failed`, `merged_outside` a `auto_actions`, položky mají `task_id`. `_task_summary()` počítá tasky podle `BOARD_STATES` (`board_state`) za celé repo do `tasks`.
- Projekt tasku je nejvyšší předek (`aifactory.backlog.derived.ancestors`, viz také `_container_json`/`steps` ve `web/backlog.py`: `top = c; while top.parent ...`). Backlog bez úrovně project (méně než tři `levels`) projekty nemá.

## Požadavek
- Každá položka `running`, `review`, `automerge`, `failed`, `merged_outside` a `auto_actions` dostane pole `project`: id projektu svého tasku, nebo `null`, když task v backlogu není nebo backlog projekty nemá.
- Položka repa dostane `projects`: seznam `{id, title, tasks}` v pořadí projektů backlogu. `tasks` má stejný tvar jako `tasks` repa (každý stav z `BOARD_STATES`, i nuly) a počítá jen tasky projektu. Backlog bez úrovně project a repo bez backlogu (stub: missing, not_git, timeout, error) mají `projects` prázdný seznam. `_stub` má `projects: []`.
- Součty `tasks` repa a `totals` se nemění. Stav tasku se počítá jedním průchodem `board_state` (nepočítat dvakrát).
- Docstring modulu popíše `project` a `projects`.
- Jen čtení, žádné nové volání gitu ani providera.

## Mimo rozsah
Frontend (navazující task), změny `web/backlog.py` a backlogu.

Hotovo znamená:
- Test v `aifactory/tests/web/test_web_overview.py`: repo se dvěma projekty, kde v každém je běžící běh, otevřené PR a selhání, vrací u položek správné `project` a v `projects` správné počty stavů po projektech; jejich součet se rovná `tasks` repa.
- Test: backlog se dvěma úrovněmi (bez project) vrací `projects: []` a `project: null`; stub repa má `projects: []`.
- Stávající testy přehledu projdou.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-20 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/120 · náklady $0.00
