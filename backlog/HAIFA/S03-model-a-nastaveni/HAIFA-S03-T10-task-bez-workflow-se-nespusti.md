---
id: HAIFA-S03-T10
title: Task bez workflow se nespustí
status: done
depends_on: []
related: [HAIFA-S01-T24]
---

## Zadání
Task bez workflow se nesmí spustit. Bez workflow je task, jehož efektivní workflow chybí nebo je `null` (třeba celý step HAIFA-S90 má `workflow: null`, aby se otevřené body samy nespustily). Dnes ho auto-continue vybere jako další připravený task, protože `select_next` v `run/queue.py` workflow nekontroluje, a běh pak selže a zastaví řetěz.

Where: `aifactory/src/aifactory/run/queue.py`, start běhu v `aifactory/src/aifactory/run/task.py`, `aifactory/src/aifactory/backlog/derived.py`, CLI `task run`, API spuštění a dashboard (`aifactory/web/src/components/backlog/`), testy v `aifactory/tests/` a vitest.

Done means:
- `factory task run` pro task bez workflow skončí chybou s vlastním kódem a nic nezaloží: žádný worktree, větev ani záznam běhu. Platí i s `--force` a `--auto`.
- Auto-continue task bez workflow přeskočí, v přeskočených ho uvede s důvodem „bez workflow“ a řetěz pokračuje dalším taskem.
- API spuštění vrátí stejnou chybu jako CLI. V dashboardu je u tasku bez workflow tlačítko Spustit zakázané a tooltip říká proč.
- `workflow: null` na projektu, stepu nebo tasku znamená „bez workflow“ i tehdy, když vyšší úroveň workflow má. Pokrývá to test.
- Testy pro CLI, API, výběr v auto-continue a dashboard.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: přejmenování stavu „K přípravě“ na „Bez workflow“ (HAIFA-S01-T24).

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-03 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/21 · náklady $2.67
