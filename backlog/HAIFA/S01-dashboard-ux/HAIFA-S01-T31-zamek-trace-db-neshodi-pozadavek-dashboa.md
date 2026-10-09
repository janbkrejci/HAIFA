---
id: HAIFA-S01-T31
title: Zámek trace.db neshodí požadavek dashboardu
status: done
depends_on: []
---

## Zadání
Při čtyřech souběžných bězích a spuštění resolve z dashboardu ukázal dashboard chybu „database is locked“. Do `trace.db` zapisují všechny běhy i dashboard. SQLite pustí jednoho zapisovatele a ostatní čekají nejvýš 5 s (`busy_timeout` v `aifactory/src/aifactory/engine/tracer.py` a `aifactory/src/aifactory/run/store.py`). Když zámek drží někdo déle, požadavek dashboardu skončí chybou. S dalšími souběžnými běhy to bude častější.

Where: `aifactory/src/aifactory/run/store.py`, `aifactory/src/aifactory/engine/tracer.py`, zápisy v `aifactory/src/aifactory/review/` a `aifactory/src/aifactory/web/`, zobrazení chyb v dashboardu (`aifactory/web/src/`), testy.

Done means:
- Žádná zápisová transakce do `trace.db` nedrží zámek přes volání hostingu (`gh`), gitu nebo jinou dlouhou práci. Místa, kde se to dnes děje, jsou nalezená a opravená.
- Zápis běhu i požadavek dashboardu při obsazené databázi počká a zkusí to znovu s omezenou dobou (desítky sekund), místo aby skončil chybou po 5 s.
- Když se ani po čekání zápis nepovede, dashboard ukáže srozumitelnou hlášku s možností zkusit znovu, ne surové „database is locked“.
- Test: jiný proces drží zápisový zámek déle než 5 s a zápis běhu i API dashboardu doběhnou úspěšně po jeho uvolnění.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: přechod z SQLite na jinou databázi.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-04 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/37 · náklady $3.01
