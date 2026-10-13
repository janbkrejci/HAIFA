---
id: HAIFA-REFINEMENT-T17
title: Revize testů žádající chybějící testy vrací běh builderovi místo selhání
status: todo
depends_on: []
---

## Zadání
Běh `90c66b9a` (HAIFA-S02-T05) skončil `failed` po hotovém buildu: `test_review` označil jako blocking, že build nemá testy launcheru, browserového retry a integrace s posunutou base. `plan_revision` (tester) nesmí měnit repo, tak vrátil `status: fail` a workflow tím ukončilo celý běh.

Zadání: když revize plánu testů požaduje testy, které v repu nejsou, workflow je předá builderovi (jako `fix` s nálezy revize), pak tester plánuje znovu. Tester místo `fail` takovou situaci rozliší (např. `failure_cause`/pole s chybějícími testy) a interpreter ji obslouží; počet kol zůstává omezený jako u ostatních oprav.

Hotovo znamená:
- Test workflow, kde revize testů blokuje kvůli chybějícímu testu: builder dostane nálezy, napíše test, tester ho zařadí, běh pokračuje k review.
- Tester bez chybějících testů a s nesplnitelným plánem dál vrací chybu jako dnes.
- Prompty testera a test-reviewera v seedu popisují nové chování.

Mimo rozsah: změna ostatních fází workflow.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
