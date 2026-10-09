---
id: HAIFA-S06-T01
title: "Časový limit kroku test (`test_timeout`)"
status: done
depends_on: []
---

## Zadání
Umožni nastavit časový limit kroku test. Dnes má krok test pevně 600 s (`engine/quality.py`), testy Omnibusu potřebují 1800 s a onboarding sssf limit převezme z `quality.py`.

Where: `aifactory/src/aifactory/config/settings.py`, `aifactory/src/aifactory/run/task.py` (`resolve_test_command`), `aifactory/src/aifactory/workflow/interpreter.py`, `aifactory/src/aifactory/engine/quality.py`, `aifactory/src/aifactory/backlog/` (`model.py`, `loader.py`, `validate.py`), `aifactory/src/aifactory/skill/skill.md`, testy v `aifactory/tests/run/`, `aifactory/tests/workflow/` a `aifactory/tests/backlog/` (`test_task_test_command.py` a `test_workflow_test_command.py` jako vzor).

Done means:
- `test_timeout` (celé sekundy větší než 0) jde nastavit v tasku, v `index.md` (dědí se jako `test`) a v `.factory/config.yaml`. Bez nastavení zůstává 600 s.
- Každý krok s akcí `test` (i `retest` a test ve workflow `resolve`) použije limit podle tohoto pořadí. Událost `quality:test` v trace nese limit.
- Neplatnou hodnotu hlásí `factory backlog check` a `load_config` a běh takového tasku skončí chybou před startem.
- Překročený limit krok shodí s hláškou o limitu. Dnešní pád `TypeError: can't concat str to bytes` v `engine/quality.py` (výstup `TimeoutExpired` je `bytes` i při `text=True`) je opravený a test ho pokrývá.
- `factory --skill` popisuje klíč.
- Testy s opravdovým podprocesem: limit z tasku přebije `index.md`, ten přebije `config.yaml`, překročený limit krok shodí, výchozí limit je 600 s.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: limity lint, typecheck a build, `command` kroky (mají `timeout`), dashboard.

Pevná omezení:
- Každá změna logiky v `aifactory/src/aifactory/engine/` má značku `# aifactory`.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-03 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/9 · náklady $2.47
