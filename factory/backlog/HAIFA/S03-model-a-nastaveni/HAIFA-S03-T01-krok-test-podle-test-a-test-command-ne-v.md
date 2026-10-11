---
id: HAIFA-S03-T01
title: "Krok test podle `test` a `test_command`, ne vždy `just test`"
status: done
depends_on: []
---

## Zadání
Oprav krok `test` při běhu tasku: musí spustit testovací příkaz z nastavení, ne vždy `just test`. Příkaz se vezme z pole `test` tasku, jinak z nejbližšího `index.md` nad ním (step, modul), jinak z `test_command` v `.factory/config.yaml`, a teprve bez nastavení platí `just test`. Dnes se `test` ani `test_command` nečtou, takže běhy HAIFA s `test_command: [just, check]` vynechávají typecheck a lint.

Where: `aifactory/src/aifactory/run/task.py`, `aifactory/src/aifactory/workflow/interpreter.py`, `aifactory/src/aifactory/engine/quality.py`, `aifactory/src/aifactory/backlog/loader.py`, `aifactory/src/aifactory/skill/skill.md`, testy v `aifactory/tests/run/`, `aifactory/tests/workflow/` a `aifactory/tests/backlog/`.

Done means:
- Každý krok s akcí `test` (i `retest` a test ve workflow `resolve`) spustí příkaz podle pořadí výše.
- `test` přijímá řetězec (dělí se jako v shellu) nebo seznam řetězců, stejně jako `test_command`. Neplatnou hodnotu hlásí `factory backlog check` a běh takového tasku skončí chybou před startem.
- Událost `quality:test` v trace nese příkaz, který opravdu běžel.
- Testy s opravdovým podprocesem, ne s falešným `CodeRunner`: `test` tasku přebije `index.md`, `index.md` přebije `test_command`, `test_command` přebije výchozí příkaz a nenulový návratový kód krok shodí. Výchozí příkaz zůstává `just test`.
- `factory --skill` popisuje, odkud krok test bere příkaz.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: úprava nastavení z dashboardu, `workdir`, lint a typecheck jako samostatné kroky workflow.

Pevná omezení:
- Každá změna logiky v `aifactory/src/aifactory/engine/` má značku `# aifactory` jako dnešní úpravy (`# aifactory 2.9:`).
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-02 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/1 · náklady $3.67
