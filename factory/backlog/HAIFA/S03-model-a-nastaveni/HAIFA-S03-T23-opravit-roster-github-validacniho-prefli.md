---
id: HAIFA-S03-T23
title: Opravit validační preflight a izolovat onboardingové testy
status: done
workflow: build-test-review
depends_on: []
related: [HAIFA-S90-T02]
writes: [aifactory/validation/runner.py, aifactory/tests/validation/, aifactory/tests/onboard/]
---

## Zadání
Oprav GitHub preflight validačního runneru, který nyní končí invalid_config před scénářem R10. check_config v aifactory/validation/runner.py generuje agentům pole prompt_engineering, ale skutečný factory harness check --config používá aifactory.config.loader.load_roster_file, který toto pole zakazuje.

Where: aifactory/validation/runner.py a aifactory/tests/validation/test_validation_roster.py, případně úzce související validační testy.

Done means:
- Minimalní roster generovaný check_config odpovídá současnému veřejnému loaderu a neobsahuje prompt_engineering.
- Uprav zastaralou dokumentaci této funkce.
- Regresní test načte generovaný roster stejným loaderem jako skutečný CLI (load_roster_file), ověří přesnou množinu harnessů a projde bez živých modelů či sítě. Nahradit nebo rozšířit existující test test_github_preflight_checks_the_roster_harnesses, který nyní používá příliš nízkoúrovňový loader.
- Cílené validační testy, mypy a Ruff projdou. Žádné skutečné GitHub validace ani volání modelů v testech.
- Neměň validační scénáře, roster, workflow, ani výsledky; oprava je pouze kompatibilita preflightu. Neřeš nyní další případné chyby R10.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-08 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/97 · náklady $0.00
