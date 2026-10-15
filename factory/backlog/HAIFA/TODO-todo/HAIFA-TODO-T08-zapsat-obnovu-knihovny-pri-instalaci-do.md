---
id: HAIFA-TODO-T08
title: Zapsat obnovu knihovny při instalaci do docs/decisions.md
status: todo
depends_on: []
related: [HAIFA-REFINEMENT-T35]
---

## Zadání
Doplnit rozhodnutí vedle bodu 'Dědičnost z knihovny': instalace a upgrade obnoví všechny položky semínka v knihovně na nainstalovanou verzi (`factory library seed --all`), položky mimo semínko zůstanou a kopie v `.factory/` rep se nikdy nemění. Knihovna obsahuje skill `factory` vygenerovaný z `factory --skill`. Ruční `factory library seed` bez `--all` dál ponechává položky změněné týmem.

### Původ

Vznikl při běhu `794b94cb` tasku `HAIFA-REFINEMENT-T35` (Knihovna místo „Tento počítač“, tabbar bez scrollbaru, dialogy knihovny a obnova knihovny při instalaci nové verze), v kroku `build` (agent builder).
Důvod: HAIFA-REFINEMENT-T35 mění sémantiku semínka: instalace a upgrade spouští `factory library seed --all`, který nahradí týmové úpravy položek semínka v knihovně, a knihovna nově obsahuje generovaný skill `factory`. docs/decisions.md je mimo povolené cesty tasku.

<!-- factory: follow-up-of=HAIFA-REFINEMENT-T35 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
