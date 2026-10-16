---
id: HAIFA-TODO-T12
title: Povolit HAIFA-TODO-T07 zápis do docs/decisions.md a zrušit duplicitní HAIFA-TODO-T08
status: todo
assignee: human
workflow: build-review
depends_on: []
related: [HAIFA-TODO-T07]
writes: [docs/decisions.md]
---

## Zadání
V front matter HAIFA-TODO-T07 přidej `writes: [docs/decisions.md]` (případně se zachováním spec a docs souboru tasku). HAIFA-TODO-T08 zruš jako duplicitu, nebo naopak oprav T08 a zruš T07. Pak task spusť znovu. Obsah, který se má zapsat (v sekci 'Konfigurace a knihovna' za bodem 'Dědičnost z knihovny'): instalace a upgrade obnoví každou položku semínka v knihovně na nainstalovanou verzi (`factory library seed --all`), i když ji tým upravil. Položky mimo semínko zůstanou a kopie v `.factory/` rep se nikdy nemění, vlastní úpravy patří tam. Knihovna obsahuje skill `factory` vygenerovaný z `factory --skill`. Ruční `factory library seed` bez `--all` dál ponechá položky změněné týmem. Toto chování už je v kódu (aifactory/src/aifactory/upgrade.py, cli.py, library/seed.py) a v guide/02-instalace.md.

### Původ

Vznikl při běhu `a1564902` tasku `HAIFA-TODO-T07` (Record the install-time library refresh in docs/decisions.md), v kroku `build` (agent builder).
Důvod: HAIFA-TODO-T07 má jen změnit docs/decisions.md, ale jeho povolené cesty jsou jen aifactory/, justfile a jeho spec a docs. Rozhodnutí se tak nedá zapsat. Navíc HAIFA-TODO-T08 (z téhož běhu 794b94cb tasku HAIFA-REFINEMENT-T35, krok build) zadává totéž česky a má stejný problém s cestami.
Task `HAIFA-TODO-T07` na tomto tasku závisí a do jeho dokončení zůstává blokovaný.

<!-- factory: follow-up-of=HAIFA-TODO-T07 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
