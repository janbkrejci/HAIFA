# HEAL-S02-T06: Blokovaný běh není selhání

## Co se změnilo

Běh, ve kterém agent ohlásí blokující follow-up (`blocks_task`) nebo blokující existující
task (`blocked_by`), dál končí ve stavu `failed`, ale s vlastním druhem selhání `blocked`.
Retry, řetěz (`run_blockers`) i samooprava proto fungují beze změny.

| Kde | Dřív | Teď |
| --- | --- | --- |
| `task_runs.failure_kind` | `other`, detail `{"cause": "blocked"}` | `blocked`, detail `{"blockers": [...]}` |
| Přehled (`/api/overview`) | mezi selhanými a v počtu `failed` | nezobrazuje se |
| Běhy, detail běhu, task | chip „chyba“ | chip „blokovaný“ (fialový) a odkazy na blokující tasky |
| Karta selhání | „Jiná chyba“ | „Blokovaný“ s vlastní barvou, věta s blokátory, odkazy, Pokračovat a Zrušit task |
| `factory task runs`, `task show` | druh `other` | druh `blocked` a `blocked: waits for A, B` |

## Starší běhy

Běh zapsaný bez druhu, jehož chyba začíná `blocked: `, se čte jako `blocked`
(`failure.shown_kind`), blokátory se čtou z chyby (`failure.error_blockers`). Totéž dělá
dashboard (`shownFailureKind`, `runBlockers` v `web/src/lib/failure.ts`).

## Kód

- `aifactory/failure.py`: `BLOCKED`, `BLOCKED_PREFIX`, `blocked_error`, `error_blockers`,
  `shown_kind`. `run/task.py` z nich skládá `blocked_reason` a `run_blockers`.
- `run/store.py`: `TaskRunRow.shown_failure_kind` a `failure_detail_dict` (doplní
  `blockers` u staršího běhu).
- `web/overview.py`: seznam `failed` blokované běhy vynechá.
- Frontend: `shownState` vrací `blocked`, `StatusChip` má stav `blocked`, `FailureCard` a
  `RunsList` ukazují odkazy na blokující tasky.

## Ověření

- `tests/test_failure.py`, `tests/web/test_web_overview.py::test_blocked_run_is_not_failed`,
  `tests/run/test_failure_kind.py::test_cli_lists_a_blocked_run_with_its_blockers`,
  `tests/run/test_auto_continue.py` (blokovaný běh v řetězu).
- Vitest: `FailureCard.test.ts`, `RunsList.test.ts`.
