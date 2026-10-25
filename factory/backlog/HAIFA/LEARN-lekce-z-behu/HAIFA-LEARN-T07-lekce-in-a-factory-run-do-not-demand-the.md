---
id: HAIFA-LEARN-T07
title: "Lekce: In a factory run, do not demand the full `just check` or `just e2e` even when the…"
status: done
workflow: build-review
depends_on: []
related: [HAIFA-S10-T03, HAIFA-S10-T04]
writes: [.factory/prompts/reviewer/]
---

## Zadání
Zapiš do promptu role reviewer (`.factory/prompts/reviewer/`) pravidlo z lekce `L328f600c`, kterou factory našla ve výtkách opakovaných v bězích:

> In a factory run, do not demand the full `just check` or `just e2e` even when the task names them as done criteria; CI runs the full gate, so judge the scoped test plan instead.

Pravidlo formuluj stručně, zařaď ho tam, kam v souboru patří, a nenech ho odporovat tomu, co tam už je. Jiné soubory neměň.

Hotovo znamená:
- Pravidlo je v promptu role reviewer (`.factory/prompts/reviewer/`).

### Důkazy

Výtky z 2 běhů, ze kterých lekce vznikla:

- běh `53703a25`, task `HAIFA-S10-T03` (review): B2: Show that `just check` and `just e2e` pass. Both are explicit done criteria, and neither was run.
- běh `53b4adeb`, task `HAIFA-S10-T04` (review): B1: Run the full pytest suite (just check, using the isolated HAIFA_HOME env-file if the live HAIFA process trips the conftest home guard) and the full just e2e (run just e2e-install first if Chromium is missing). Fix any failures in tests/run, tests/review, tests/workflow and the other e2e files that the loader and named_workflow changes affect.
- běh `53b4adeb`, task `HAIFA-S10-T04` (review): just check and just e2e pass: Neither ran in full. The test step ran scoped pytest (733 passed) and 2 e2e files. The builder reports test_limits_layout failing because Chromium is missing and test_multi_repo_browser failing once.
- běh `53b4adeb`, task `HAIFA-S10-T04` (review): test plan fits the change: Insufficient. load_config now injects library or seed agents and workflows into every roster and config.workflows. named_workflow lost its packaged fallback. FactoryConfig.manifest is gone. The plan runs only 4 files of tests/run, 1 of tests/workflow and none of tests/review, and the task names just check and just e2e as done criteria. The pytest-scoped drop is justified by the isolated env-file replacement.

<!-- factory: lesson=L328f600c -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-25 · workflow build-review · PR https://github.com/janbkrejci/HAIFA/pull/164 · náklady $0.00
