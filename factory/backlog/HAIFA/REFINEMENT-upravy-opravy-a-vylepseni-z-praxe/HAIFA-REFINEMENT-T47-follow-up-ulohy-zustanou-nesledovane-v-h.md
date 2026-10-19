---
id: HAIFA-REFINEMENT-T47
title: Follow-up úlohy zůstanou nesledované v hlavním checkoutu a zablokují pull
status: done
depends_on: []
---

## Zadání
Po běhu `b4239924` (NEO_HEF, ROB-S21-T005, 2026-10-19, factory 0.1.380) zůstaly v hlavním checkoutu NEO_HEF nesledované soubory follow-up úloh (`factory/backlog/ROB-registr-obyvatel/TODO-todo/index.md`, `ROB-TODO-T01-…md`, `ROB-TODO-T02-…md`). Factory je zároveň commitla přes PR do base (commit `f4c6a22ee` „TODO tasky z běhu“), ale kopie v pracovním stromu hlavního checkoutu nechala. Následný `git pull --ff-only` v hlavním checkoutu skončil „untracked working tree files would be overwritten by merge“. Soubory byly bajtově shodné s remote.

Zadání:
1. Zápis follow-up úloh nepíše do pracovního stromu hlavního checkoutu (jako `backlog commit` / `config commit`: commit z base bez checkoutu), nebo po merge/pushi soubory z pracovního stromu uklidí, pokud se shodují s base.
2. Platí pro `base_changes: pr` i `direct`.

Hotovo znamená:
- Test: po běhu, který založí follow-up úlohy, je hlavní checkout čistý (`git status` bez nesledovaných souborů backlogu) a `git pull --ff-only` projde.
- Dotčené testy projdou podle AGENTS.md, celou sadu ověří CI.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-19 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/115 · náklady $0.00
