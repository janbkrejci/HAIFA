---
id: HAIFA-S01-T16
title: "API přehledu: co se právě děje v každém repu"
status: done
workflow: plan-build-test
depends_on: [HAIFA-S01-T13]
---

## Zadání
Přidej endpoint přehledu, který pro každé registrované repo jen čte, co v něm běží, co čeká na review, co selhalo a v jakém stavu je konfigurace. Je to podklad obrazovky, kde je vidět, co se v kterém repu právě děje.

Where: `aifactory/src/aifactory/web/` (`app.py`, `runs.py`, `review.py`, `live.py`, `settings.py`), registr z M3, `aifactory/src/aifactory/config/` (`status.py`, `source.py`), `aifactory/src/aifactory/backlog/`, testy v `aifactory/tests/web/` (`trace_fixture.py` jako vzor). Nový modul v `aifactory/src/aifactory/web/`.

Done means:
- `GET /api/overview` vrátí `{repos, totals}`. Repo má `id`, `name`, `state`, `running[]` (task, název, workflow, běžící fáze s pokusem, začátek, dosavadní náklady), `review[]` (otevřené PR z `task_prs` bez běžícího běhu s odkazem a stářím, označené jako podle trace), `failed[]` (task, jehož nejnovější běh skončil `failed` nebo `aborted` a který není `done` ani `cancelled`, s chybou), `config` (stav instalace, neplatná konfigurace v base, necommitovaná konfigurace D4), `last_activity` a `warnings`.
- Trace DB se čte jen spojením `mode=ro`, nikdy přes `TaskRunStore`. Endpoint nezapisuje do repa, trace DB ani registru: běžící řádek s mrtvým procesem ukáže jako „proces skončil“ bez změny, nevolá provider ani `git fetch` a chybějící trace DB nevytvoří.
- Čtecí git volání konfigurace běží s `GIT_OPTIONAL_LOCKS=0`. Stav konfigurace se drží 15 s a názvy tasků 60 s pro každé repo. Repa se počítají souběžně s limitem 2 s na repo. Pomalé nebo rozbité repo dostane varování a ostatní se vrátí normálně.
- Testy (pytest): dvě repa s trace (běžící, čekající na review, selhaný, hotový a zrušený task), repo bez trace DB, chybějící složka, mrtvý proces bez zápisu do DB (řádek i soubory DB beze změny) a odpověď do 1 s, i když jiné spojení drží `BEGIN IMMEDIATE`.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: frontend, SSE pro přehled, stav PR v hostingu.

Pevná omezení:
- Přehled nic nezapisuje.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-05 · workflow plan-build-test · PR https://github.com/janbkrejci/HAIFA/pull/62 · náklady $2.69
