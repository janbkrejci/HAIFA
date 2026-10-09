---
id: HAIFA-S03-T09
title: "Souběžné běhy: úpravy backlogu přes factory během běhu"
status: done
depends_on: [HAIFA-S03-T08]
---

## Zadání
Hlídač běhu dnes vrátí a nahlásí každou změnu hlavního checkoutu během fáze agenta, i když ji udělal operátor přes factory. Založení nebo úprava tasku v dashboardu nebo v CLI během běhu se proto ztratí a běh selže. Operátor musí s úpravami backlogu čekat, až žádný běh není ve fázi agenta, a při průběžných bězích taková chvíle skoro nenastane.

Where: `aifactory/src/aifactory/run/guard.py`, `aifactory/src/aifactory/run/backup.py`, zápisy backlogu v `aifactory/src/aifactory/backlog/` (`edit.py`, `commit.py`) a jejich volání z CLI a z API dashboardu, testy v `aifactory/tests/`.

Done means:
- Zápis backlogu přes příkaz factory (`task add`, `task edit`, `task link`, `backlog auto-continue`, z CLI i z dashboardu) během fáze agenta jiného běhu hlídač nevrátí ani nenahlásí. Běh pokračuje a zápis zůstane v hlavním checkoutu.
- Následný `backlog commit` během fáze agenta jiného běhu projde, běh pokračuje a zápis je v base.
- Zápis přes příkaz factory spuštěný agentem běhu se počítá jako zápis agenta a zůstává porušením.
- Ostatní změny hlavního checkoutu během fáze agenta hlídač dál vrací a hlásí jako dnes.
- Když ve stejné fázi zapíše do stejného souboru příkaz factory i agent, zůstane obsah od factory a zápis agenta hlídač vrátí a nahlásí.
- Testy hlídače: zápis od factory projde, zápis od agenta je porušení, zápis obou do stejného souboru nechá obsah od factory.
- Test přes falešný harness: během fáze agenta běhu A se založí task a commitne backlog, běh A doběhne úspěšně a nový task je v base.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: zápisy konfigurace v `.factory/` během běhu (Nastavení, `config set`), ruční úpravy souborů mimo factory, limit paralelity.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-03 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/17 · náklady $2.67 · dokončeno ručně (běh 710f734b spadl v review)
