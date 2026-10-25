---
id: HAIFA-LEARN-T05
title: "Lekce: Run every test file the change itself edits, including browser tests under `tests/…"
status: done
archived: true
workflow: build-review
depends_on: []
related: [HAIFA-REFINEMENT-T10, HAIFA-S10-T03, HAIFA-S10-T04]
writes: [AGENTS.md]
---

## Zadání
Zapiš do `AGENTS.md` pravidlo z lekce `Lca9fa166`, kterou factory našla ve výtkách opakovaných v bězích:

> Run every test file the change itself edits, including browser tests under `tests/e2e/`, in some check of the test plan.

Pravidlo formuluj stručně, zařaď ho tam, kam v souboru patří, a nenech ho odporovat tomu, co tam už je. Jiné soubory neměň.

Hotovo znamená:
- Pravidlo je v `AGENTS.md`.

### Důkazy

Výtky z 3 běhů, ze kterých lekce vznikla:

- běh `4edbeb85`, task `HAIFA-REFINEMENT-T10` (test_review): Missing check: aifactory/tests/e2e/test_f3_browser.py::test_add_and_remove_repo_in_browser. The change edited it, and it is the only coverage of the new 'unsupported' repo state in the dashboard.
- běh `4edbeb85`, task `HAIFA-REFINEMENT-T10` (test_review): checks cover the changed code: pytest-collect catches leftover imports of the deleted package. pytest-scoped covers check/, config/ (including repo_state), library/, web/, skill, smoke and validation. But the change edits aifactory/tests/e2e/test_f3_browser.py: _check_report() now returns state 'unsupported' without sssf_leftover/alternate_rosters, and test_add_and_remove_repo_in_browser renders it in the dashboard. No check runs that test.
- běh `53703a25`, task `HAIFA-S10-T03` (review): just check a just e2e projdou: The test step ran scoped pytest, lint, typecheck and web-test only. It ran neither the full `just check` (which includes slow tiers) nor `just e2e`. tests/e2e/f3_repo.py changed and was never run.
- běh `53b4adeb`, task `HAIFA-S10-T04` (test_review): Add tests/e2e/test_factory_install_browser.py to the e2e-move argv.
- běh `53b4adeb`, task `HAIFA-S10-T04` (test_review): edited browser tests run: The diff edits tests/e2e/test_factory_install_browser.py, which is not in any check.

<!-- factory: lesson=Lca9fa166 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-25 · workflow build-review · PR https://github.com/janbkrejci/HAIFA/pull/161 · náklady $0.00
