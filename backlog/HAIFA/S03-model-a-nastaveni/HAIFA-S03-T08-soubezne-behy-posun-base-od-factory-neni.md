---
id: HAIFA-S03-T08
title: "Souběžné běhy: posun base od factory není porušení hlídače"
status: done
depends_on: []
---

## Zadání
Oprav hlídač běhu pro souběžné běhy. Když během fáze agenta jednoho běhu posune base v hlavním checkoutu příkaz factory, hlídač to připíše agentovi a běh selže. Stalo se 2026-10-03: HAIFA-S01-T04 (run b71b5aaf) běžel souběžně s HAIFA-S01-T11. `factory task approve HAIFA-S01-T11` ve 12:06:03 fast-forwardem posunul `main` z 0b1a036 na 558bfee během fáze plan běhu S01-T04 a hlídač hlásil „planner changed paths outside its task run: main checkout: HEAD — moved to refs/heads/main, not rolled back“. Planner hlavní checkout nezměnil.

Where: `aifactory/src/aifactory/run/guard.py`, příkazy factory, které posouvají base v hlavním checkoutu (`task approve`, `backlog commit`, `config commit`, `config pull`), testy v `aifactory/tests/`.

Done means:
- Posun HEAD hlavního checkoutu, který během fáze agenta jiného běhu udělal příkaz factory (`task approve`, `backlog commit`, `config commit`, `config pull`), není porušení. Běh pokračuje a hlídač nic nevrací ani nehlásí.
- Commit, reset, checkout nebo přepnutí větve v hlavním checkoutu, které udělal agent, zůstává porušením jako dnes, i když ve stejné fázi proběhl i posun od factory.
- Posun base, který udělá příkaz factory spuštěný agentem běhu, se počítá jako posun od agenta a zůstává porušením.
- Změny souborů hlavního checkoutu během fáze agenta hlídač dál vrací a hlásí jako dnes.
- Testy hlídače: posun od factory projde, posun od agenta je porušení, oba ve stejné fázi jsou porušení.
- Test se dvěma běhy přes falešný harness: během fáze agenta běhu A se schválí běh B a běh A doběhne úspěšně.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: zápisy souborů do hlavního checkoutu od factory během fáze agenta (`task add`, `edit` a `link` z dashboardu), ruční změny operátora, limit paralelity.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-03 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/15 · náklady $2.87
