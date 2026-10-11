---
id: HAIFA-S90-T03
title: OB3 Approve review jménem uživatele
status: todo
depends_on: []
---

## Zadání
Doplň při schválení approve review v hostingu jménem uživatele (D11). Dnes factory approve review neposílá a rovnou merguje, protože GitHub nedovolí schválit vlastní PR.

Podmínka: spustit, až bude rozhodnuté, jestli approve review pošle jiný účet, nebo bot, a ten bude k dispozici.

Done means:
- Schválení v CLI i dashboardu pošle approve review, pokud je nastavený schvalující účet, a jinak se chová jako dnes.
- Ověřeno proti GitHubu.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
