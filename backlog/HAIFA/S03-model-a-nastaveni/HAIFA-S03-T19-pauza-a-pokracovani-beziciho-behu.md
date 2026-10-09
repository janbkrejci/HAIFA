---
id: HAIFA-S03-T19
title: Pauza a pokračování běžícího běhu
status: done
workflow: build-test-review
depends_on: []
writes: [aifactory/src/aifactory/run/, aifactory/src/aifactory/workflow/, aifactory/src/aifactory/cli.py, aifactory/src/aifactory/web/, aifactory/web/src/, aifactory/src/aifactory/skill/, aifactory/tests/]
---

## Zadání
Běžící běh jde dnes jen zastavit (`factory task stop`, `run/stop.py`), což ho ukončí jako `stopped` a pokračovat nejde. Engineer chce běh pozastavit (třeba kvůli limitům předplatného nebo kvůli ruční práci v repu) a později ho nechat doběhnout ve stejném worktree a větvi.

Pauza platí na hranici fáze: rozběhnutá fáze (agent, test) doběhne a další nezačne. Zmrazení procesu (SIGSTOP) se nepoužije, agentovi by spadlo spojení s API a test by vyčerpal timeout.

Where: `aifactory/src/aifactory/run/` (store, stop, task), smyčka workflow v `aifactory/src/aifactory/workflow/`, `cli.py`, dashboard v `aifactory/src/aifactory/web/` a `aifactory/web/src/`, `skill/`, testy v `aifactory/tests/` a vitest.

Done means:
- `factory task pause <task-id>` požádá běžící běh o pauzu. Běh dokončí aktuální fázi, přejde do stavu `paused` a čeká. Proces běhu zůstane živý, další fáze se nespustí.
- `factory task resume <task-id>` pozastavený běh pustí dál od další fáze. Pauza nad během, který neběží, a resume nad během, který není pozastavený, vrátí chybový kód a nic nezmění.
- Pauza požádaná během fáze je v dashboardu vidět jako čekající (`pausing`), dokud fáze neskončí.
- `factory task stop` funguje i na pozastavený běh.
- Pozastavený běh drží své místo v limitu souběžných běhů a auto-continue řetěz čeká, dokud běh neskončí.
- Dashboard má u běžícího běhu tlačítko Pauza, u pozastaveného Pokračovat a stav `paused` ukazuje v seznamu běhů i v detailu.
- `factory --skill` popisuje `task pause`, `task resume`, stav `paused` a jejich kódy.
- Testy: pauza na hranici fáze a pokračování s dokončením workflow, pauza v poslední fázi, stop pozastaveného běhu, chybové kódy, vitest tlačítek.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: pauza uprostřed fáze, přežití pauzy přes restart počítače, automatická pauza při vyčerpání limitů.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-06 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/68 · náklady $4.37
