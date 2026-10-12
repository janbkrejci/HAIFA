---
id: HAIFA-S90-T03
title: OB3 Approve review jménem uživatele
status: done
workflow: build-test-review
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
- 2026-10-12 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/21 · náklady $2.87 (běh aff335c7, ověření a dokončení ručně)
