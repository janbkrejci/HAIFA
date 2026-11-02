---
id: HEAL-S01-T04
title: "Backend: stav kanbanu „Selhalo“ pro task, jehož poslední běh selhal"
status: done
workflow: build-test-review
depends_on: []
writes: [aifactory/src/aifactory/web/backlog.py, aifactory/src/aifactory/web/overview.py, aifactory/tests/web/test_web_backlog.py, aifactory/tests/web/test_web_overview.py, aifactory/tests/workflow/test_workflow_advice.py]
---

## Zadání
## Problém
Když běh tasku skončí jako `failed` nebo `aborted`, `board_state` v `aifactory/src/aifactory/web/backlog.py` pro task nic zvláštního neudělá. Stav se vezme z `core.derived_state`, takže se task v kanbanu vrátí do Připraveno a nepozná se na něm, že selhal. Přehled (`aifactory/src/aifactory/web/overview.py`, seznam `failed`) přitom stejný task jako selhaný ukazuje.

## Co udělat
1. `aifactory/src/aifactory/web/backlog.py`:
   - Do `BOARD_STATES` přidej nový stav `failed` hned za `blocked`, před `running`.
   - `_Runtime` dostane množinu `failed`. V `_display_runtime` do ní patří task, jehož nejnovější běh (podle stejného pořadí, jaké plní `rt.last_run`) má stav ve `FAILED_STATES` (`failed`, `aborted`). Výjimka je běh, jehož `failure.shown_kind(row["failure_kind"], row["error"])` je `failure.BLOCKED`, protože blokovaný běh není selhání (HEAL-S02-T06). Pravidlo musí být stejné jako u seznamu `failed` v overview.py. Sdílenou část (množinu stavů, test druhu) vytáhni tak, aby ji používaly oba moduly a nebyla zkopírovaná.
   - `board_state`: `cancelled`, chyba dokončení, `done`, `running`, sloučené PR a otevřené PR mají přednost jako dnes. Potom, ještě před `core.derived_state`, vrať `failed` pro task z `rt.failed`. Nový úspěšný nebo běžící běh task ze stavu `failed` vrátí, protože rozhoduje nejnovější běh.
   - Aktualizuj docstring modulu, kde je seznam stavů v pořadí.
2. `aifactory/src/aifactory/web/overview.py`: počty po stavech (`dict.fromkeys(BOARD_STATES, 0)`) budou mít `failed` automaticky. Seznam `failed` musí zůstat konzistentní s počtem `tasks["failed"]`.
3. Testy:
   - `aifactory/tests/web/test_web_overview.py`: `test_handoff_counts_match_kanban` očekává pro `failed` a `aborted` stav `failed` místo `ready`. Doplň případ s během `failed` druhu `blocked`, ten zůstane mimo `failed`. Uprav výčty počtů stavů.
   - `aifactory/tests/web/test_web_backlog.py`: výčty `state_counts` doplň o `failed`. Přidej test, že po selhaném běhu je `board_state` `failed`, že filtr `?status=failed` task najde a že po novějším úspěšném nebo běžícím běhu task ve `failed` není.
   - Před změnou zkontroluj grepem testy, které vyjmenovávají `BOARD_STATES` nebo očekávají `ready` po selhaném běhu, a uprav je.

## Mimo rozsah
- Výběr dalšího tasku pro auto-continue (fronta běhů) se nemění. Selhaný task dál smí pokračovat jako dnes, jde jen o zobrazení.
- Frontend a příručka (task HEAL-S01-T05).
- `ADVICE_CLOSED_STATES` pro návrh workflow se nemění, selhaný task není uzavřený.

Hotovo znamená:
- `GET /api/backlog` vrací ve `states` i `failed` a u tasku s posledním selhaným nebo přerušeným během `board_state: "failed"`. `state_counts` a počty tasků na Přehledu ho počítají.
- Task s posledním během druhu `blocked` je dál `blocked`, ne `failed`.
- Po novém běžícím nebo úspěšném běhu task ve `failed` není.
- `uv run pytest tests/web/test_web_backlog.py tests/web/test_web_overview.py -n0` v `aifactory/` projde.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-02 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/200 · náklady $2.14
