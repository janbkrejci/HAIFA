---
id: HAIFA-REFINEMENT-T06
title: Opravit vybrané nálezy Factory
status: done
depends_on: []
---

## Zadání
Vyřeš následující vybrané nálezy kontroly Factory. Po opravě spusť factory check a popiš výsledek každého vybraného nálezu.
Respektuj povolené cesty a chráněné soubory. Nálezy tohoto počítače a knihovny řeš jen v rámci oprávnění běhu; pokud opravu nelze provést, uveď konkrétní překážku a postup pro operátora.

1. repo_onboarded (repo, info)
   onboarded from pre_library at 2026-10-08T16:21:38Z by Jan B. Krejčí (factory 0.1.0), library library (edd1ceda-ef2e-4f4d-b7a8-68b029433780)
   Doporučená oprava: never onboard it again; on another machine run factory adopt to fill the library from the committed configuration
   Akce: adopt
2. item_local (repo, info)
   workflow manual-test-duration is local (repo 60c19b4d, manifest -, library -)
   Doporučená oprava: export workflow manual-test-duration to the library (factory config export)
   Akce: export

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-08 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/104 · náklady $0.00
