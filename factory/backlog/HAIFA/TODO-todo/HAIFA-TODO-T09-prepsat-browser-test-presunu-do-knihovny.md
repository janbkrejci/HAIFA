---
id: HAIFA-TODO-T09
title: Přepsat browser test přesunu do knihovny na stránku Knihovna
status: done
depends_on: []
related: [HAIFA-REFINEMENT-T36]
---

## Zadání
Test přepsat tak, aby přesun vlastní kopie workflow do knihovny prošel přes stránku Knihovna (`LibrarySection.vue`: `override-move` a `override-move-apply`, pak `confirm-ok`). Ponechat stejná ověření commitu v repu a v knihovně. Druhá možnost je test smazat, pokud už stejný tok pokrývá jiný browser test. Je potřeba to udělat na větvi T36 nebo hned po ní, jinak CI tohoto PR neprojde.

### Původ

Vznikl při běhu `9e7603e6` tasku `HAIFA-REFINEMENT-T36` (Factory: z „Vybavení továrny“ udělat „Nastavení agentů“, sjednotit a sbalovat sekce stránky), v kroku `build` (agent builder).
Důvod: Browser test aifactory/tests/e2e/test_factory_move_browser.py klikne na stránce Factory na karty workflow (`item-workflow-*`) a na `item-move-workflow-mine`, `item-move-plan` a `item-move-apply`. Úkol T36 tyto karty a přesun ze stránky Factory odstranil. Soubor test_factory_move_browser.py leží mimo povolené cesty tohoto úkolu, takže ho tady nešlo upravit. Test teď selže a s ním CI tohoto PR.
Task `HAIFA-REFINEMENT-T36` na tomto tasku závisí a do jeho dokončení zůstává blokovaný.

<!-- factory: follow-up-of=HAIFA-REFINEMENT-T36 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-16 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/57 · náklady $0.88
