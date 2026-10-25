---
id: HAIFA-TODO-T03
title: Pauza továrny má zastavit i navazující běhy řetězu
status: done
archived: true
depends_on: []
related: [HAIFA-REFINEMENT-T30]
---

## Zadání
After the Overview's Pauza, a chain must not start new runs, or a newly started run must be paused right away. For example: make the chain check the repo pause from FactoryControl or the DB before starting the next task, or have FactoryControl pause runs that start late while its pause record is active. Add a test.

### Původ

Vznikl při běhu `80623830` tasku `HAIFA-REFINEMENT-T30` (Tlačítka pro ovládání továrny na Přehledu), v kroku `review` (agent reviewer).
Důvod: Found while reviewing T30 (web/control.py pause, run/pause.py). A pause asked for during a run's last phase does not hold that run. When it ends, its auto-continue chain starts the next task, and the new run is not paused. Stop has a sweep for runs that start late; pause has none.

<!-- factory: follow-up-of=HAIFA-REFINEMENT-T30 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-15 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/46 · náklady $1.37
