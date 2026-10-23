---
id: HAIFA-REFINEMENT-T74
title: "Zapsat do docs/decisions.md a příručky, s jakým harnessem běží pomocní AI agenti"
status: todo
workflow: build-test
depends_on: [HAIFA-REFINEMENT-T70, HAIFA-REFINEMENT-T71, HAIFA-REFINEMENT-T73]
writes: [docs/decisions.md, aifactory/src/aifactory/guide/]
---

## Zadání
Cíl: zapsat platné rozhodnutí. Pomocní AI agenti (návrh workflow a parametrů tasku, Nový záměr, triáž follow-upů, lekce a AI průvodce) běží s harnessem, modelem a thinking objektu, ve kterém je uživatel vyvolá: task, step, projekt, jinak repo. Na úrovni repa a na Přehledu platí výchozí nastavení počítače z topbaru. Průvodce z topbaru vždy otevře nové vlákno a minulá vlákna jsou v historii.

Co udělat:
- Upravit nebo nahradit dotčená rozhodnutí v `docs/decisions.md` (česky, stručně).
- Upravit kapitoly příručky v `aifactory/src/aifactory/guide/`, které popisují průvodce, Nový záměr nebo „Vylepšit task“, aby odpovídaly novému chování.

Mimo rozsah: změny kódu a testů.

Hotovo znamená:
- `docs/decisions.md` popisuje nové pravidlo výběru harnessu pomocných agentů a otevírání průvodce.
- Stávající testy příručky a jejího souladu s UI a CLI projdou beze změny.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
