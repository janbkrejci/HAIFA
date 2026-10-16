---
id: GUIDE-S02-T02
title: Panel AI průvodce na každé obrazovce
status: done
depends_on: [GUIDE-S02-T01]
---

## Zadání
Zadání:
1. Tlačítko v horní liště otevře boční panel s konverzací, dostupný z každé obrazovky. Panel si drží otevřené vlákno při přechodu mezi obrazovkami.
2. Odpověď se streamuje a vykresluje jako markdown. Zmínky o tascích, bězích a PR jsou odkazy do dashboardu.
3. Panel automaticky přiloží kontext aktuální obrazovky a ukáže ho jako chip, který jde odebrat.
4. Seznam starších vláken a nové vlákno. Panel ukáže, který harness a model odpovídá.
5. Prázdné vlákno nabídne 3 otázky podle obrazovky (např. u selhaného běhu „Proč tenhle běh selhal?“).

Hotovo znamená:
- Vitest panelu, browser test konverzace s fake harnessem.
- `just web-test`, `just web-build`, dotčené testy podle AGENTS.md.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-16 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/71 · náklady $4.01
