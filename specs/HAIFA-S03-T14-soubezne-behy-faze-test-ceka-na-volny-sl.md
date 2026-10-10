# HAIFA-S03-T14: Souběžné běhy: fáze test čeká na volný slot

## Cíl

Omezit, kolik fází `test` běží na stroji naráz (`test_slots`, výchozí 1). Ostatní běhy
čekají ve frontě v pořadí, v jakém o slot požádaly. Čekání je vidět v trace i v dashboardu
a nepočítá se do `test_timeout`.

## Návrh

- `aifactory/engine/slots.py` (`TestSlots`): adresář `<HAIFA home>/test_slots`
  sdílený všemi běhy na stroji.
  - `queue/<ns>-<pid>-<token>`: tiket čekajícího běhu; řadí se podle času vytvoření.
    Tiket mrtvého procesu odstraní ten, kdo frontu čte příště.
  - `slot-<k>.lock`: drží ho `flock` běh se slotem `k`. Kernel zámek uvolní při pádu,
    zastavení i zabití procesu. `slot-<k>.owner` obsahuje pid držitele (jen pro počet
    běhů před čekajícím).
  - O slot se pokouší jen prvních `free` čekajících (`free` = sloty bez živého držitele,
    aspoň 1), takže při jednom slotu platí přísně FIFO.
- `engine/quality.test`: s `run.test_slots` nejdřív čeká na slot, pak teprve spustí
  příkaz (limit `test_timeout` začíná až se spuštěním příkazu). Do trace zapisuje události
  `log` / `test_slot`: `state: waiting` (`ahead`, `holding`, `queued_before`, `slots`)
  při začátku čekání a při každé změně `ahead`, pak `state: acquired`
  (`slot`, `slots`, `waited_seconds`).
- `run_workflow(test_slots=...)` → `Run.test_slots`; `run_task` předá
  `TestSlots(default_slots_dir(), settings.test_slots)`.
- `ProjectSettings.test_slots: int = Field(default=1, ge=1, strict=True)`.
- Dashboard: `web/runs.py` přidá k fázím (tečky v seznamu i detail) `slot_wait`
  (`ahead`, `slots`), pokud fáze běží a poslední událost `test_slot` je `waiting`.
  `PhaseDots` ukáže přesýpací hodiny a tooltip „čeká na volný slot testů, před ní N běhů“,
  `PhaseDetail` stejný text v pruhu.

## Testy

- `tests/workflow/test_workflow_test_slots.py`: dva procesy se slotem 1 testují jeden po
  druhém; FIFO pořadí; zabitý držitel i zabitý čekající slot uvolní; mrtvý tiket se zahodí;
  čekání se nezapočítá do `test_timeout`, limit platí pro samotný příkaz; trace má
  `waiting` a `acquired`; konfigurace `test_slots`.
- `tests/run/test_task_test_timeout.py`: běh tasku drží slot v `<HAIFA home>/test_slots`.
- `tests/web/test_web_runs.py`: `slot_wait` v seznamu i detailu.
- `web/src/components/runs/PhaseDots.test.ts`, `web/src/lib/runs.test.ts`.
