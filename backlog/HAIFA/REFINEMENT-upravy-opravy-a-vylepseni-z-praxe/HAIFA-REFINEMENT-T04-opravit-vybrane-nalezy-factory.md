---
id: HAIFA-REFINEMENT-T04
title: Opravit vybrané nálezy Factory
status: done
depends_on: []
---

## Zadání
Vyřeš následující vybrané nálezy kontroly Factory. Po opravě spusť factory check a popiš výsledek každého vybraného nálezu.
Respektuj povolené cesty a chráněné soubory. Nálezy tohoto počítače a knihovny řeš jen v rámci oprávnění běhu; pokud opravu nelze provést, uveď konkrétní překážku a postup pro operátora.

1. workflow_not_in_repo (repo, error)
   backlog in main names workflow 'manual-test-duration' (tasks HAIFA-S90-T06), which this repo with a manifest does not have in .factory/workflows/
   Doporučená oprava: factory config add workflow manual-test-duration, or change the tasks
2. config_uncommitted (repo, warning)
   .factory/workflows/manual-test-duration.yaml is untracked in the working tree but not committed to main (592eabb); runs use the committed version
   Doporučená oprava: commit the change to main, or discard it
   Akce: config_commit

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-08 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/102 · náklady $0.00
