---
id: HAIFA-REFINEMENT-T71
title: Triáž follow-upů s harnessem běhu tasku a lekce s výchozím nastavením počítače
status: done
workflow: plan-build-test
depends_on: [HAIFA-REFINEMENT-T69]
writes: [aifactory/src/aifactory/run/triage.py, aifactory/src/aifactory/run/task.py, aifactory/src/aifactory/learn/scan.py, aifactory/tests/run/test_triage.py, aifactory/tests/run/test_followups_triage.py, aifactory/tests/learn/test_learn_scan.py, aifactory/tests/run/test_followups_queue.py]
---

## Zadání
Cíl: pomocní agenti, kteří se spouštějí v kontextu jednoho tasku nebo repa, berou harness, model a thinking z tohoto objektu, ne jen z rosteru.

1. Triager follow-upů (`aifactory/src/aifactory/run/triage.py`, `ask_triager` a `_invoke`, volaný z `aifactory/src/aifactory/run/task.py` kolem řádku 1096) běží po běhu konkrétního tasku. Má dostat binding, se kterým ten běh tasku skutečně běžel (včetně přepnutí harnessu kvůli kvótě). Když binding chybí, spočítá se funkcí z HAIFA-REFINEMENT-T69 pro task. Binding se aplikuje přes `apply_agents_override` před `agents.resolve(cfg, "triager")`.
2. Agent lekcí (`aifactory/src/aifactory/learn/scan.py`, `_ask_learner`) pracuje nad celým repem. Má běžet s výchozím harnessem, modelem a thinking počítače (`effective_override({}, None)`), jako každý objekt na úrovni repa. Bez nastavení počítače zůstává roster agent.

Pokud v `run/task.py` stačí jen předat binding do `ask_triager`, nic dalšího v souboru neměnit.

Mimo rozsah: Nový záměr, návrh workflow, AI průvodce, frontend.

Hotovo znamená:
- `aifactory/tests/run/test_triage.py` (případně `test_followups_triage.py`) ověřuje, že triager běží s harnessem, modelem a thinking běhu tasku. Po přepnutí harnessu kvůli kvótě běží s novým harnessem.
- `aifactory/tests/learn/test_learn_scan.py` ověřuje, že learner běží s výchozím harnessem počítače, když je nastavený.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-24 · workflow plan-build-test · PR https://github.com/janbkrejci/HAIFA/pull/150 · náklady $0.00
