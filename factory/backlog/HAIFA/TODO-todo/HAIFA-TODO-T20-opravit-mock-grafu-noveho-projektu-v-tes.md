---
id: HAIFA-TODO-T20
title: Opravit mock grafu nového projektu v testu BacklogView
status: done
archived: true
depends_on: []
related: [HAIFA-REFINEMENT-T54]
writes: [aifactory/web/src/views/BacklogView.test.ts]
---

## Zadání
Doplnit platnou odpověď grafu M03-S01 a vyčkat dokončení navigace před unmount. Ověřit BacklogView.test.ts a povinný web-test bez neošetřených výjimek; nepotlačovat hlášení Vitestu.

### Původ

Vznikl při běhu `75e24093` tasku `HAIFA-REFINEMENT-T54` (Přehled: dlaždice repa po projektech (přepínač, výchozí zapnuto)), v kroku `review` (agent reviewer).
Důvod: quality/17_web-tests/command.log hlásí TypeError na BacklogView.vue:215. Nezměněný BacklogView.test.ts:377 po aplikaci přesměruje na graf M03-S01, ale mock obsluhuje pouze graf M01-S01 a pro nový vrací backlogData bez container. Backlog je výslovně mimo rozsah T54 a změny Přehledu tento tok nemění.

<!-- factory: follow-up-of=HAIFA-REFINEMENT-T54 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-20 · workflow build-test-review · bez změn, běh 4330c36b · už hotovo: aifactory/web/src/views/BacklogView.test.ts:381–394 vytváří newGraph s container, nodes a edges a vrací jej pro /containers/M03-S01/graph., aifactory/web/src/views/BacklogView.test.ts:432–439 používá vi.waitFor pro ověření názvu Export a odkazu nového tasku, kontroluje načtení grafu a teprve poté v… · náklady $0.00
