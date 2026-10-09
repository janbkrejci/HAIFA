---
id: HAIFA-S01-T27
title: "Události fáze: u logu text zprávy místo názvu fáze"
status: done
depends_on: [HAIFA-S02-T02]
---

## Zadání
V detailu fáze (sekce „Události a tool calls“) mají události typu `log` jako popisek název fáze, protože `eventLabel` v `aifactory/web/src/lib/events.ts` vrací pro všechno kromě tool call `e.name`. Fáze test řízená kódem tak ukáže dva stejné řádky „log test_1“, i když jde o hlavičku fáze („▶ 05 test_1 code · quality …“) a o spuštěný příkaz („· quality test: just check“). Text zprávy je vidět až v rozbaleném payloadu.

Where: `aifactory/web/src/lib/events.ts`, panel fáze v `aifactory/web/src/components/runs/` (po HAIFA-S02-T02), testy (vitest), build v `aifactory/src/aifactory/web/static/`.

Done means:
- Událost `log` má jako popisek text `payload.message` na jednom řádku, bez úvodních mezer a odrážek.
- Log, který jen opakuje `phase_start` (hlavička „▶ NN název …“), se v seznamu událostí nezobrazuje.
- Vitest: popisek logu je text zprávy, hlavička fáze v seznamu není, tool call a ostatní typy se nezměnily.
- Build frontendu v `aifactory/src/aifactory/web/static/` odpovídá změnám.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: změny API, zápis logů v enginu.

Pevná omezení:
- Žádná nová závislost frontendu.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-03 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/30 · náklady $0.55
