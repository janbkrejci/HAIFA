# Spec: Panel AI průvodce na každé obrazovce

## Cíl

Konverzace s průvodcem (backend GUIDE-S02-T01) je dostupná z každé obrazovky dashboardu
a sama ví, na co se uživatel dívá.

## Návrh

- `web/src/lib/assistant.ts`: API `/api/assistant/threads…`, stav konverzace na úrovni
  modulu (přežije přechod mezi obrazovkami), id otevřeného vlákna a otevření panelu
  v `sessionStorage` (přežije reload karty).
- Tlačítko v horní liště (`App.vue`, ikona Sparkles) otevře `components/assistant/AssistantPanel.vue`,
  pevný panel vpravo nad obsahem.
- Odeslání: vlákno se založí až s první zprávou (`POST /threads`), pak
  `POST /threads/{id}/messages` a `EventSource` na `/stream?after=SEQ`. Události `text`
  se skládají do průběžné odpovědi, `tool` ukáže spuštěný příkaz, `done`/`error` přidá
  hotovou zprávu a stream zavře. Přerušené spojení vlákno znovu načte a pokračuje.
  Otevřené vlákno, které ještě odpovídá, přehraje stream od začátku odpovědi (`after=0`).
- Kontext obrazovky (`describeScreen`): na stránce repa `{repo}`, detail běhu `{repo, run}`,
  detail tasku v Backlogu a PR v Review `{repo, task}`. Ukáže se jako chip, křížek ho
  odebere do změny obrazovky.
- Navržené otázky prázdného vlákna (`suggestions`) podle druhu obrazovky. U běhu se
  načte jeho stav: selhaný nabídne „Proč tenhle běh selhal?“.
- Odkazy: `linkify` před vykreslením markdownu převede zmínky tasků (`…-T01`),
  běhů (`běh 740183f7`) a PR (`PR #12`) na odkazy `#/r/REPO/…`. Repo je z kontextu otázky,
  jinak jediné registrované, jinak repo v URL. Fenced kód a hotové odkazy se nemění.
  Prompt agenta `guide` navíc žádá odkazy s repem psát rovnou.
- Hlavička ukáže harness a model vlákna, seznam starších vláken je pod ikonou hodin.

## Testy

- Vitest: `lib/assistant.test.ts` (kontext, otázky, odkazy),
  `components/assistant/AssistantPanel.test.ts` (stream, odkazy, chip, vlákna, chyby),
  `App.test.ts` (tlačítko v liště, panel zůstane otevřený).
- Browser: `tests/e2e/test_assistant_browser.py` s fake harnessem claude.
