---
id: HAIFA-TODO-T11
title: Popisek důvodu no_slot v dashboardu
status: done
archived: true
depends_on: []
related: [HAIFA-REFINEMENT-T39]
---

## Zadání
Doplnit do `SKIP_LABELS` (aifactory/web/src/lib/chains.ts) `no_slot: 'žádný volný slot (PR v review)'` nebo podobně, případně doplnit `in_review` do typů v `web/src/lib/api.ts` a `chains.ts` a zobrazit ho u slotů (ChainPanel, RepoControls). Pak spustit `just web-build`.

### Původ

Vznikl při běhu `09c25782` tasku `HAIFA-REFINEMENT-T39` (Task čekající na review neuvolňuje slot pro paralelní běhy), v kroku `build` (agent builder).
Důvod: HAIFA-REFINEMENT-T39 přidal důvod přeskočení `no_slot` (PR čekající na review drží volné sloty) a klíč `in_review` do odpovědí `/api/chains`, `factory.in_review` v přehledu a výsledku Spustit továrnu. Frontend `aifactory/web/` nebyl mezi povolenými cestami, takže `SKIP_LABELS` v `web/src/lib/chains.ts` pro `no_slot` nemá český popisek a UI ukáže holý kód.

<!-- factory: follow-up-of=HAIFA-REFINEMENT-T39 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-16 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/60 · náklady $0.98
