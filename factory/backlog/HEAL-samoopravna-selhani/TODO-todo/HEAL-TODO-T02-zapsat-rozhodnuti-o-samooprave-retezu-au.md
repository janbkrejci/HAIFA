---
id: HEAL-TODO-T02
title: Zapsat rozhodnutí o samoopravě řetězu (auto_heal) do docs/decisions.md
status: todo
workflow: build-review
depends_on: []
related: [HEAL-S02-T04]
writes: [docs/decisions.md]
---

## Zadání
Do docs/decisions.md přidej za odrážku **Auto-continue** odrážku **Samooprava řetězu (`auto_heal`)**. Řetěz, který by po tasku pokračoval, jedná po selhání podle druhu: `quota` jednou pokračuje na záložním harnessu, `process_gone` jednou zopakuje, `nothing_to_do` s důvodem agenta uzavře task jako hotový bez změn a pokračuje. Ostatní druhy (i `nothing_to_do` bez důvodu) nechá na člověku a zastaví se. Každý běh se opravuje nejvýš jednou. Akce jsou v `task_chains.events` a na Přehledu. `auto_heal` se dědí jako `auto_continue`, výchozí je true, a `false` vypne i automatický fallback u jednotlivého běhu. Odrážku o záložním harnessu doplň o větu, že s `auto_heal: false` se nepřepíná.

### Původ

Vznikl při běhu `ef54fa58` tasku `HEAL-S02-T04` (Řetěz provede bezpečnou akci sám), v kroku `build` (agent builder).
Důvod: CLAUDE.md žádá aktualizovat docs/decisions.md, když změna mění platné rozhodnutí. HEAL-S02-T04 přidává nové rozhodnutí: samooprava řetězu a nastavení auto_heal, které vypíná i automatické přepnutí harnessu u jednotlivého běhu. docs/decisions.md ale není v povolených cestách tohoto tasku a změna by se vrátila.

<!-- factory: follow-up-of=HEAL-S02-T04 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
