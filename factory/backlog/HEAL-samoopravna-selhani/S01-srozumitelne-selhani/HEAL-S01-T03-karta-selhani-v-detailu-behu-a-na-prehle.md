---
id: HEAL-S01-T03
title: Karta selhání v detailu běhu a na Přehledu
status: done
archived: true
depends_on: [HEAL-S01-T01, HEAL-S01-T02]
---

## Zadání
Zadání:
1. Detail běhu ukáže nahoře kartu selhání: druh lidsky česky, jednu větu vysvětlení, detail (u accept výtky review, u writes cesty, u kvóty harness a model) a tlačítka akcí, které pro druh existují (zatím Pokračovat a Zrušit task, další doplní step HEAL-S02).
2. Přehled a Běhy ukazují u selhaného běhu druh místo prvních znaků chyby.
3. Text karty je vždy z dat běhu, ne obecná nápověda.

Hotovo znamená:
- Vitest pro kartu každého druhu, browser test detailu selhaného běhu.
- `just web-test`, `just web-build`, dotčené testy podle AGENTS.md.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-16 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/70 · náklady $5.57
