---
id: HAIFA-REFINEMENT-T59
title: "Backend: stav „Schváleno, čeká na CI“ po ručním schválení PR"
status: todo
workflow: build-test-review
depends_on: [HAIFA-TODO-T22]
writes: [aifactory/src/aifactory/run/store.py, aifactory/src/aifactory/review/flow.py, aifactory/src/aifactory/web/backlog.py, aifactory/src/aifactory/web/overview.py, aifactory/src/aifactory/web/review.py, aifactory/src/aifactory/workflow/adaptive.py, aifactory/tests/review/test_ci_gate.py, aifactory/tests/web/test_web_backlog.py, aifactory/tests/web/test_web_overview.py, aifactory/tests/web/test_web_review.py]
---

## Zadání
Navazuje na HAIFA-REFINEMENT-T41 (stavy `in review` / `awaiting merge`) a HAIFA-REFINEMENT-T28 (approve čeká na CI).

## Problém
Když task nemá auto-merge, otevřené PR je ve stavu `in review` („Čeká na review“). Po kliknutí na Schválit běží `factory task approve` na pozadí (`web/launcher.py` `start_approve`). Ten pushne commit `status: done`, čeká na CI checky (`review/flow.py` `_approve_gated`, `review/ci.py`), případně pustí `ci-fix` běhy, a teprve potom mergne. Celou tu dobu task na Backlogu, na Přehledu i v Review dál ukazuje „Čeká na review“, i když už člověk schválil a nic dalšího dělat nemusí.

## Co udělat
1. `aifactory/src/aifactory/run/store.py`: do `task_prs` přidej sloupec `approved_at TEXT`, do `_PR_COLUMNS` a do `_PR_ADDED_COLUMNS` (starší DB ho dostanou při otevření). Přidej pole do `TaskPrRow` a umožni ho nastavit přes `update_pr`.
2. `aifactory/src/aifactory/review/flow.py` `approve_task` / `_approve_gated`: na začátku schválení, před čekáním na CI, zapiš do řádku PR `approved_at=_now()` a vynuluj `auto_merge_error`. Pokud schválení skončí důvodem (`stop()`: `checks_failing`, `checks_pending`, `ci_fix_failed`, `checks_unavailable`) nebo jinou `ReviewError` před merge (konflikt, `task_blocked`, chyba approve/merge od providera), vynuluj `approved_at`, aby se PR vrátilo do „Čeká na review“. Důvod zůstane v `auto_merge_error` jako dnes. Po úspěšném merge stav určuje `MERGED`, `approved_at` může zůstat jako záznam. Zapisuj to jen pro ruční schválení (`merged_by == MERGED_BY_OPERATOR`). Auto-merge má vlastní stav `awaiting merge` a jeho chování se nemění.
3. `aifactory/src/aifactory/web/backlog.py`: nový board state `approved` v `BOARD_STATES` hned za `in review` (před `awaiting merge`). `_Runtime` dostane množinu `approved` (nejnovější otevřené PR tasku s vyplněným `approved_at` a bez `auto_merge_error`). `board_state` vrací pro task s otevřeným PR: `approved`, pokud je PR schválené a čeká, jinak `awaiting merge` / `in review` jako dnes. Aktualizuj docstring modulu.
4. `aifactory/src/aifactory/web/overview.py`: PR schválená člověkem, která čekají na CI, nepatří do seznamu `review` (čeká na uživatele). Přidej k repu nový seznam `approved` (stejný tvar položek jako `review`) a do souhrnu počet `approved`. Prázdná repa a `fetchOverview` mají mít klíč `approved: []`. Sloty `factory.in_review` počítají dál všechna otevřená PR. Čtení `task_prs` musí snést starší trace DB bez sloupce `approved_at` (stejně jako u `auto_merge_error`).
5. `aifactory/src/aifactory/web/review.py`: položka seznamu a detail PR dostanou pole `approved` (bool) a `approved_at`. `awaiting_review` je `false` pro schválená PR, která čekají. Řazení: review, approved, automerge, ostatní.
6. `aifactory/src/aifactory/workflow/adaptive.py`: přidej `approved` do `ADVICE_CLOSED_STATES`.
7. Testy: `tests/review/test_ci_gate.py` (`approved_at` se zapíše při ručním schválení a vynuluje se při `checks_failing`/`checks_pending`; auto-merge ho nezapisuje), `tests/web/test_web_backlog.py`, `tests/web/test_web_overview.py`, `tests/web/test_web_review.py` (board state `approved`, seznam `approved` v přehledu, starší DB bez sloupce).

## Mimo rozsah
Frontend, statický build a příručka patří do navazujícího tasku. Když proces approve spadne nebo ho někdo zabije, může `approved_at` zůstat viset. Řeší se to novým Schválit, které musí ve stavu `approved` zůstat povolené. Žádný watchdog nepřidávej.

Hotovo znamená:
- `uv run pytest tests/review/test_ci_gate.py tests/web/test_web_backlog.py tests/web/test_web_overview.py tests/web/test_web_review.py tests/workflow -n0` v `aifactory/` projde.
- Ručně schválený task s otevřeným PR, jehož approve čeká na CI, má v `GET /api/backlog` stav `approved`, v přehledu je v seznamu `approved` a ne v `review`, v review API má `approved: true` a `awaiting_review: false`.
- Když CI zůstane červené nebo běží dál, PR má `auto_merge_error`, nemá `approved_at` a task je znovu `in review`.
- Task s auto-merge dál ukazuje `awaiting merge`.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
