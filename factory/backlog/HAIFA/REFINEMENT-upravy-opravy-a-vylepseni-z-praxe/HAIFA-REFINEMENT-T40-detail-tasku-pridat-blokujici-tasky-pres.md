---
id: HAIFA-REFINEMENT-T40
title: "Detail tasku: přidat blokující tasky přes modální výběr s hledáním a opravit přetékání ve Writes"
status: done
archived: true
workflow: build-test-review
depends_on: []
related: [HAIFA-REFINEMENT-T21, HAIFA-REFINEMENT-T11, HAIFA-REFINEMENT-T23]
writes: [aifactory/web/src/components/backlog/, aifactory/web/src/components/ui/, aifactory/src/aifactory/web/static/]
---

## Zadání
Na detailu tasku v režimu editace je potřeba umět přidat, kdo task blokuje (modal picker s hledáním), a opravit panel Writes. Soubory jsou v CODE rámečcích a přetékají přes okraj karty Writes.

## Co udělat

### 1. Přidání blokujících tasků (Závisí na) v editaci
- V režimu editace detailu tasku (TaskForm v `mode="edit"`, otevřený z `TaskDetail.vue`) jde přidat task, který tento task blokuje, tedy položku do `depends_on`.
- Výběr se otevře v **modálním dialogu s hledáním**. Hledá se podle kódu i názvu tasku. Dialog umí ovládání klávesnicí a zavření bez výběru. Vzorem je stávající `ui/ModelPickerDialog.vue` s `ConfirmDialog`.
- Už vybrané kódy a samotný task se v nabídce nezobrazují.
- Vybrané vazby zůstávají vidět jako čipy a jde je odebrat, stejně jako dnes v `IdPicker.vue`.
- Ukládání vazeb se nemění: stávající `EditTaskInput.depends_on` a stávající API.

### 2. Oprava layoutu Writes
- Cesty ve Writes (sekce Nastavení na detailu tasku) nesmí přetékat přes okraj karty. Dlouhé cesty se zalamují, nebo se zkrátí s plnou hodnotou v tooltipu. Čip nesmí být širší než karta.
- Ověřit i pole Writes ve formuláři editace, aby ani tam nic nepřetékalo.

## Akceptační kritéria
- V editaci tasku jde přes modální výběr s hledáním přidat blokující task. Po uložení se objeví v sekci „Závisí na“ na detailu.
- Hledání filtruje podle kódu i názvu. Už vybrané kódy ani vlastní task se nedají vybrat.
- Ani dlouhá cesta bez mezer ve Writes nepřeteče přes okraj karty.
- Stávající odebírání vazeb na detailu i ve formuláři dál funguje.
- Unit testy komponent jsou aktualizované nebo doplněné (TaskForm.test.ts, TaskDetail.test.ts, případně test nového dialogu).

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-15 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/53 · náklady $2.23
