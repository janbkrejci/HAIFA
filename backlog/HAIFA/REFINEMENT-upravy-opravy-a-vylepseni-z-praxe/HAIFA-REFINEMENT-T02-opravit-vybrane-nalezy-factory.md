---
id: HAIFA-REFINEMENT-T02
title: Opravit vybrané nálezy Factory
status: done
workflow: build-test-review
depends_on: []
---

## Zadání
Vyřeš následující vybrané nálezy kontroly Factory. Po opravě spusť factory check a popiš výsledek každého vybraného nálezu.
Respektuj povolené cesty a chráněné soubory. Nálezy tohoto počítače a knihovny řeš jen v rámci oprávnění běhu; pokud opravu nelze provést, uveď konkrétní překážku a postup pro operátora.

1. sssf_leftover (repo, info)
   adws/ is still committed next to .factory/ in main; runs ignore it
   Doporučená oprava: delete adws/ in a separate commit once nobody runs sssf in this repo

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-08 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/100 · náklady $0.23
