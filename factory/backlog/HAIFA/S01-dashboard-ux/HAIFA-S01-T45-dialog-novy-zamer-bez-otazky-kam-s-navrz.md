---
id: HAIFA-S01-T45
title: "Dialog Nový záměr bez otázky Kam, s navrženým umístěním"
status: done
workflow: build-test-review
depends_on: [HAIFA-S01-T44]
writes: [aifactory/web/src/components/backlog/IntentDialog.vue, aifactory/web/src/components/backlog/IntentDialog.test.ts, aifactory/web/src/lib/intent.ts, aifactory/web/src/views/BacklogView.vue, aifactory/web/src/views/BacklogView.test.ts, aifactory/tests/e2e/test_intent_browser.py, aifactory/tests/intent_fixture.py, aifactory/src/aifactory/web/static/]
---

## Zadání
## Zadání

Dialog Nový záměr v Backlogu se už neptá, kam práce patří. Umístění navrhne agent (API z HAIFA-S01-T44) a dialog ho ukáže v návrhu.

1. `aifactory/web/src/components/backlog/IntentDialog.vue`:
   - Odstraň pole „Kam“ (`SelectMenu`, `targetOptions`, props `projects`, `steps`, `allowProjects`, `initial`).
   - Navrhnout jde, jakmile je vyplněný záměr. `startIntent` pošle jen `{intent}`.
   - Nahoře ve výsledku se ukáže umístění:
     - řádek projektu (úroveň podle `useLevels`, id, titulek, štítek nový/existující; u nového projektu i jeho popis přes `MarkdownView preview-only`),
     - pod ním step jako dnes,
     - `placement_reason`.
   - Zpráva po zápisu uvede i nový projekt.
   - Placeholder záměru napoví, že umístění jde změnit v poli Upřesni (např. „dej to do HAIFA-S03“).
2. `aifactory/web/src/lib/intent.ts`: cíl `startIntent` je nepovinný. Typ `Proposal` dostane `project`, `placement_reason` a `target`. Pokud `parseTarget` už nikdo nepoužívá, smaž ho.
3. `aifactory/web/src/views/BacklogView.vue`: přestaň předávat odstraněné props. Cesta `/backlog/intent[/<id>]` dialog dál otevře, parametr se ignoruje. `onIntentApplied` po zápisu ukáže step návrhu i v novém projektu.
4. Přegeneruj statický build (`just web-build`).

Mimo rozsah: backend.

Hotovo znamená:
- `IntentDialog.test.ts` a `BacklogView.test.ts` ověřují:
  - že dialog nemá výběr Kam a Navrhnout pošle jen záměr,
  - zobrazení existujícího i nového projektu a stepu a důvodu umístění,
  - zprávu po zápisu.
- `aifactory/tests/e2e/test_intent_browser.py` projde s fake harnessem celý tok bez výběru cíle až po zápis a commit, i pro návrh nového projektu.
- `just web-test`, `just web-build`, `just lint`, `just typecheck` a `just pytest tests/e2e/test_intent_browser.py -n0` projdou.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-17 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/104 · náklady $1.80
