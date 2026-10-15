---
id: HAIFA-REFINEMENT-T24
title: "Sloučit stránky Factory, Tento počítač a Knihovna a posoudit stránku Nastavení"
status: done
workflow: simple-sdlc
depends_on: []
related: [HAIFA-REFINEMENT-T01, HAIFA-REFINEMENT-T03, HAIFA-REFINEMENT-T20, HAIFA-REFINEMENT-T10, HAIFA-S05-T13, HAIFA-S05-T14, HAIFA-S05-T16, HAIFA-S10-T05]
writes: [aifactory/web/, aifactory/src/aifactory/, aifactory/tests/]
---

## Zadání
## Problém
Stránky **Factory**, **Tento počítač** a **Knihovna** se v dashboardu obsahem dost překrývají. Stránka Factory se celkem líbí. Ukazuje ale i informace, se kterými uživatel nic neudělá. Příklad je info „factory is installed in main; agents and workflows the repo lacks come from library 8a22887“, tedy nález `repo_installed` v `aifactory/src/aifactory/check/repo_rules.py`. Na téhle stránce ani jinde v dashboardu by neměly být položky, které se nedají vyřešit. Mají tam být jen věci, které je opravdu potřeba řešit.

## Zadání
1. Pořádně rozmyslet, jestli jsou tři různé stránky opravdu potřeba. Z pohledu UX a efektivity navrhnout lepší uspořádání, například sloučení nebo jasné rozdělení odpovědností bez duplicit. Za základ vzít stránku Factory.
2. Posoudit, jestli je potřeba samostatná stránka **Nastavení**. Pokud ne, přesunout její obsah tam, kam logicky patří, nebo ji zrušit.
3. Odstranit z UI informační hlášky, se kterými uživatel nemůže nic udělat, a to na těchto stránkách i jinde v dashboardu. Začít hláškou „factory is installed in … come from library …“. Zobrazovat jen nálezy, které vyžadují akci nebo které se dají opravit.

## Akceptační kritéria
- Rozhodnutí o uspořádání stránek, tedy co se slučuje, co zůstává a proč, je stručně zdůvodněné v plánu nebo výsledku.
- Každá funkce dnešních stránek Factory, Tento počítač, Knihovna a Nastavení zůstane dostupná. Výjimkou je jen to, co je výslovně zdůvodněné jako zbytečné.
- Stejná informace ani stejná akce se nezobrazuje na více stránkách.
- Dashboard nezobrazuje info `repo_installed` ani jiné hlášky, které nevyžadují akci.
- Navigace a odkazy na zrušené stránky vedou na nové místo a nikam nevedou naprázdno.
- Stávající testy webu a backendu jsou upravené tak, aby odpovídaly novému uspořádání, a procházejí.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
