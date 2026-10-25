---
id: HAIFA-REFINEMENT-T26
title: Lepší popisy pull requestů a tvrdé zacházení s nedodělky
status: done
archived: true
workflow: simple-sdlc
depends_on: []
related: [HAIFA-S10-T01, HAIFA-S03-T09, HAIFA-S03-T04, HAIFA-S03-T11]
---

## Zadání
## Cíl

1. Popis pull requestu nemá citovat zadání tasku. Má srozumitelně shrnout, co byl cíl, co se udělalo, co se neudělalo a další důležité informace. Nemá to být přepis zadání ani výčet technikálií.
2. Zpracování tasku nesmí nechávat nedodělky schované v repu. Práce navíc má skončit v backlogu a task, který na ní závisí, nesmí skončit jako hotový.

Tato pravidla mají vést k tomu, aby práce nenarůstala do nekonečna, ale aby se zmenšovala a dokončovala.

Nejdřív rozhodni, co patří do kódu factory, co do workflows a co do promptů agentů. Pak udělej všechno, co je potřeba. Rozhodnutí stručně zdůvodni (např. v `docs/decisions.md`).

## 1. Popis pull requestu

Popis PR dnes skládá `aifactory/src/aifactory/review/prbody.py` (`pr_body`). Začíná sekcí „## Zadání“ s doslovnou kopií těla tasku.

- Vypusť citaci zadání. Místo ní dej krátké, srozumitelné shrnutí:
  - **Cíl**: proč task vznikl, jednou dvěma větami.
  - **Co bylo uděláno**: z pohledu výsledku, ne seznam souborů.
  - **Co uděláno nebylo**: vědomě vynechané věci, odchylky od zadání a nové TODO tasky v backlogu (s ID) – nebo výslovně „nic“.
  - Další důležité informace pro toho, kdo PR schvaluje (rizika, změny chování, co ověřit ručně).
- Text shrnutí musí pocházet od agentů běhu (např. z výstupu build/review), ne z kopie zadání. Technické sekce (agenti, gates a testy, review, náklady) zůstanou až za shrnutím a stručné; jejich podobu posuď.
- Skrytá značka `<!-- factory: task=... branch=... -->` musí zůstat, protože na ní závisí další logika.

## 2. Nedodělky a nová práce

Pravidla musí respektovat všichni agenti, kterých se týkají (builder, fix, revise, reviewer, planner, documenter…):

- Když se během tasku ukáže, že práce přesahuje rozsah, že je potřeba udělat něco navíc, nebo že se změnil záměr, a nedá se to dotáhnout přímo v tasku, **nesmí v repu vzniknout žádný todolist, soupis nedodělků ani poznámka s otevřenými body** (TODO soubory, sekce v docs, komentáře typu „dodělat později“ apod.).
- Taková práce se musí objevit jako nový task v backlogu projektu, ve stepu **TODO**. Pokud step TODO neexistuje, factory ho založí. Každý nový task musí vysvětlovat, kde a proč vznikl (z jakého tasku/běhu a z jakého zjištění).
- Když se zjistí, že task něco blokuje (třeba právě nový TODO task), task se **nesmí označit za hotový**. Musí se vrátit jako blokovaný, s vazbou na to, co ho blokuje. Backlog dnes počítá „blocked“ z nesplněných `depends_on`. Výsledkem tedy má být, že task zůstane nedokončený a má `depends_on` na blokující task. Běh se nesmí vydávat za úspěch, takže nesmí dojít k auto-merge ani k označení done.

## Akceptační kritéria

- Popis nového PR neobsahuje doslovnou citaci zadání. Obsahuje sekce cíl / uděláno / neuděláno (případně další důležité informace) a technické sekce jsou až za nimi.
- Prompty dotčených agentů obsahují pravidlo o zákazu skrytých nedodělků a popisují, jak novou práci a blokaci ohlásit.
- Novou práci ohlášenou agentem založí factory jako task ve stepu TODO daného projektu (step založí, pokud chybí) a uvede u něj původ a důvod.
- Task, jehož běh ohlásil blokaci, nekončí jako done ani se nemerguje. Zůstane blokovaný s `depends_on` na blokující task.
- Na novou logiku (sestavení popisu PR, založení TODO tasku/stepu, blokace) jsou testy.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-15 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/35 · náklady $7.03
