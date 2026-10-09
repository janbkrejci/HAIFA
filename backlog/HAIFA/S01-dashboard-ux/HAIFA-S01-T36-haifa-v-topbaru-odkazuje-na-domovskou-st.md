---
id: HAIFA-S01-T36
title: HAIFA v topbaru odkazuje na domovskou stránku
status: done
workflow: build-test-review
depends_on: []
writes: [aifactory/web/src/App.vue]
test: [just, web-test]
auto_merge: false
---

## Zadání
Z textu HAIFA v topbaru v aifactory/web/src/App.vue udelej standardni odkaz href="/" (nikoli hash route). Zachovej gradient, rozlozeni a vzhled, odstran pouze pripadne vychozi podtrzeni odkazu. Minimalni zmena: span.brand nahrad a.brand href="/" a potrebne CSS. Logo muze zustat beze zmeny. Vygenerovane frontend assets obnovi workflow. Nezakladej dalsi factory tasky ani worktrees; implementuj primo v pridelenem worktree. Over frontend existujicimi testy a buildem, nepridavej redundantni test pro trivialni markup.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-07 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/79 · náklady $0.00
