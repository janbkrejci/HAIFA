---
id: HAIFA-TODO-T14
title: Povolit docs/decisions.md v HAIFA-TODO-T08
status: todo
assignee: human
depends_on: []
related: [HAIFA-TODO-T08]
---

## Zadání
Přidat docs/decisions.md do povolených cest (writes) tasku HAIFA-TODO-T08 a spustit ho znovu. Druhá možnost: T08 zavřít a nechat jen nový navazující task, který docs/decisions.md v povolených cestách má. Obě kopie nenechávat.

### Původ

Vznikl při běhu `37daf127` tasku `HAIFA-TODO-T08` (Zapsat obnovu knihovny při instalaci do docs/decisions.md), v kroku `review` (agent reviewer).
Důvod: HAIFA-TODO-T08 má upravit jen docs/decisions.md, ale ten soubor nemá v povolených cestách, takže ho žádný běh nemůže dokončit. Builder založil navazující task se stejným obsahem, a ten je duplikátem T08, protože T08 už sám je follow-up HAIFA-REFINEMENT-T35.
Task `HAIFA-TODO-T08` na tomto tasku závisí a do jeho dokončení zůstává blokovaný.

<!-- factory: follow-up-of=HAIFA-TODO-T08 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
