---
id: HAIFA-TODO-T17
title: "Preflight validace má ověřit i modely rosteru, nejen harnessy"
status: done
depends_on: []
related: [HAIFA-S90-T04]
writes: [aifactory/validation/runner.py, aifactory/tests/validation/]
---

## Zadání
V `aifactory/validation/runner.py` (`check_config` a `_preflight_harnesses`) posílej do `factory harness check --config` u každého agenta i jeho `model` z rosteru, nebo dvojice harness+model ověř jinak. Neznámý model pak skončí kódem 2 ještě před založením base větve. Přidej test v `aifactory/tests/validation/`.

### Původ

Vznikl při běhu `4dbdd510` tasku `HAIFA-S90-T04` (OB4 Azure DevOps proti skutečnému repu), v kroku `build` (agent builder).
Důvod: Na macOS prošel preflight `just validate --remote azure` s výchozím rosterem šablony, ale všechny běhy pak skončily `invalid_agent`: pi nezná model `nous-portal/stealth/space-bunny-alpha` a codex s účtem ChatGPT nepustí `gpt-5.5`. `runner.check_config` posílá `factory harness check` jen jméno harnessu, bez modelu.

<!-- factory: follow-up-of=HAIFA-S90-T04 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-18 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/112 · náklady $1.72
