---
id: HAIFA-REFINEMENT-T73
title: "Průvodce z topbaru vždy otevře nové vlákno s kontextem obrazovky, minulá jsou v historii"
status: todo
workflow: plan-build-test
depends_on: [HAIFA-REFINEMENT-T72]
writes: [aifactory/web/src/lib/assistant.ts, aifactory/web/src/lib/assistant.test.ts, aifactory/web/src/components/assistant/, aifactory/web/src/App.vue, aifactory/web/src/App.test.ts, aifactory/tests/e2e/test_assistant_browser.py, aifactory/src/aifactory/web/static/]
---

## Zadání
Cíl: tlačítko AI průvodce v topbaru (`data-test="assistant-toggle"` v `aifactory/web/src/App.vue`) otevře panel vždy s novým prázdným vláknem. Minulá vlákna zůstanou dostupná z historie (seznam vláken v panelu).

Co udělat:
- `aifactory/web/src/lib/assistant.ts`: otevření z topbaru (`toggleOpen` a `setOpen(true)`) zavolá `newThread()` a neobnoví poslední vlákno ze sessionStorage. Obnova po reloadu stránky (`restoreOpen`) a otevření vlákna ze seznamu fungují dál.
- `createThread` posílá `screen` aktuální obrazovky (stejný kontext, který panel ukazuje jako chip; když ho uživatel odebral, neposílá nic). Na Přehledu kontext není, takže vlákno dostane výchozí harness počítače z topbaru.
- `aifactory/web/src/components/assistant/AssistantPanel.vue`: popisek „odpovídá …“ ukazuje harness a model vlákna (už existuje `harnessLabel`), doplnit thinking, pokud ho vlákno má.
- Upravit testy `aifactory/web/src/lib/assistant.test.ts`, `components/assistant/AssistantPanel.test.ts`, `App.test.ts` a browser test `aifactory/tests/e2e/test_assistant_browser.py`. Grepnout testy na selektory a chování obnovy vlákna.
- Přegenerovat statický build: `just web-build` (`aifactory/src/aifactory/web/static/`).

Mimo rozsah: backend (HAIFA-REFINEMENT-T72).

Hotovo znamená:
- Vitest ověřuje: otevření z topbaru ukáže nové prázdné vlákno i po předchozí konverzaci. Starší vlákno jde otevřít ze seznamu vláken. První zpráva založí vlákno s `screen` obrazovky.
- `just web-test` projde a browser test průvodce projde.
- Statický build v `aifactory/src/aifactory/web/static/` odpovídá zdroji.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
