---
id: HAIFA-TODO-T31
title: "T54: Lokalizovat Review"
status: done
depends_on: []
related: [HAIFA-S01-T54]
writes: [aifactory/web/, aifactory/src/aifactory/web/, aifactory/tests/]
---

## Zadání
Převést seznam a detail Review, schvalování, vracení, řešení konfliktů, kontroly a prázdné/loading/chybové stavy. Zachovat obsah PR, diffy a odpovědi agentů. Přidat EN/CS regresní testy včetně rozepsané poznámky při přepnutí a lokalizované chyby API.

### Původ

Vznikl při běhu `dc9c566b` tasku `HAIFA-S01-T54` (Dokončit anglické a české UI dashboardu a zapnout výchozí EN), v kroku `build` (agent builder).
Důvod: ReviewView a související akce, verdikty a kontroly obsahují pevné české texty.
Závažnost: defect
Task `HAIFA-S01-T54` na tomto tasku závisí a do jeho dokončení zůstává blokovaný.

<!-- factory: follow-up-of=HAIFA-S01-T54 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-15 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/239 · náklady $0.00
