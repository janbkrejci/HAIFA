---
id: HAIFA-TODO-T28
title: "T54: Lokalizovat Přehled, problémy a demo"
status: todo
depends_on: []
related: [HAIFA-S01-T54]
writes: [aifactory/web/, aifactory/src/aifactory/web/, aifactory/tests/]
test_timeout: 2700
---

## Zadání
Převést filtry, karty repozitářů, automatizace, nálezy, akce, demo a všechny související stavy do EN/CS. Backendové hlášky lokalizovat pomocí stabilních kódů a parametrů nebo explicitního locale požadavku. Zachovat uživatelská data, stav filtrů a souběžnou práci klientů. Doplnit testy obou jazyků a úzkého okna.

### Původ

Vznikl při běhu `dc9c566b` tasku `HAIFA-S01-T54` (Dokončit anglické a české UI dashboardu a zapnout výchozí EN), v kroku `build` (agent builder).
Důvod: OverviewView, ProblemsView, jejich komponenty a demo dosud používají pevné české texty.
Závažnost: defect
Task `HAIFA-S01-T54` na tomto tasku závisí a do jeho dokončení zůstává blokovaný.

<!-- factory: follow-up-of=HAIFA-S01-T54 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
