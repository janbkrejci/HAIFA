---
id: HEAL-S02-T04
title: Řetěz provede bezpečnou akci sám
status: todo
depends_on: [HEAL-S02-T01, HEAL-S02-T02, HEAL-S02-T03]
---

## Zadání
Zadání:
1. Auto-continue řetěz po selhání podle druhu: `quota` se zálohou a `process_gone` jednou zopakuje, `nothing_to_do` s důkazem uzavře, ostatní druhy nechá na člověku a pokračuje jako dnes.
2. Každá automatická akce je zapsaná v událostech řetězu a viditelná na Přehledu („Factory pokračovala na Claude Code po vyčerpání kvóty Codexu“).
3. Nastavení `auto_heal` (zděděné, výchozí zapnuto) automatické akce vypne.

Hotovo znamená:
- Testy řetězu pro každý automatický druh a pro vypnuté `auto_heal`.
- Dotčené testy projdou podle AGENTS.md, celou sadu ověří CI.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
