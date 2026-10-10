# HAIFA-S03-T14: Souběžné běhy: fáze test čeká na volný slot

## Co se změnilo a proč

Při 4–5 souběžných bězích na 4 jádrech se testy přetěžovaly: fáze `test` trvala
17–25 minut, překračovala `test_timeout` a časově citlivé testy kolísaly. Nový klíč
`test_slots` v `.factory/config.yaml` (celé číslo ≥ 1, výchozí 1) omezuje, kolik příkazů
fáze `test` běží na stroji naráz. Ostatní běhy čekají ve frontě v pořadí, v jakém o slot
požádaly.

```yaml
# .factory/config.yaml
test_slots: 2
```

## Jak to funguje

- Stav je v `<HAIFA home>/test_slots` (`$HAIFA_HOME`, jinak `~/.config/haifa`), takže je
  společný pro všechny běhy na stroji (`aifactory/engine/slots.py`).
- Čekající běh má ve frontě tiket `queue/<čas>-<pid>-<token>`. Slot drží zámek `flock`
  na `slot-<k>.lock`. Zámek uvolní kernel, když proces skončí, spadne nebo je zabit
  (i `kill -9`). Tiket mrtvého procesu se z fronty sám odstraní.
- Čekání proběhne uvnitř fáze `test` ještě před spuštěním příkazu. `test_timeout` platí
  jen pro samotný příkaz.
- Krok `quality` (lint, typecheck, build a test) čeká na slot jen kvůli bloku `test`.

## Kde je čekání vidět

- **Trace**: události `log` s názvem `test_slot`. `state: waiting` přijde při začátku
  čekání a pak při každé změně počtu běhů před fází. Nese `ahead`, tedy kolik běhů je
  před ní (držitelé slotů a dřívější čekající), a dále `holding`, `queued_before` a
  `slots`. Po získání slotu přijde `state: acquired` se `slot`, `slots` a
  `waited_seconds`.
- **Konzole běhu**: `test: waiting for a test slot (N run(s) ahead, S slot(s))`.
- **Dashboard**: fáze, která běží a čeká, má v API pole `slot_wait` (`ahead`, `slots`).
  V seznamu běhů má tečka přesýpací hodiny a tooltip „čeká na volný slot testů, před ní
  N běhů“. Detail fáze ukazuje stejný text.

## Ověření

```bash
cd aifactory && uv run pytest tests/workflow/test_workflow_test_slots.py \
  tests/run/test_task_test_timeout.py tests/web/test_web_runs.py
cd aifactory/web && bunx vitest run src/components/runs/PhaseDots.test.ts src/lib/runs.test.ts
```
