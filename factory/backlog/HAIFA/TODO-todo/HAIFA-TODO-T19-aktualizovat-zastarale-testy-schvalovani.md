---
id: HAIFA-TODO-T19
title: Aktualizovat zastaralé testy schvalování po zavedení mazání větví
status: cancelled
depends_on: []
related: [HAIFA-REFINEMENT-T51]
writes: [aifactory/tests/review/test_approve_merge_retry.py, aifactory/tests/review/test_ci_gate.py, aifactory/tests/run/test_task_pr_flow.py]
---

## Zadání
Aktualizovat test_approve_again_after_transient_merge_failure a obě varianty test_azure_approve_final_push_before_vote_and_retry; čtyři varianty test_merges_without_red_checks a dvě varianty test_red_checks_are_repaired_on_the_same_branch; test_approve_commits_done_and_merges a test_clean_without_runs. Obsah původních commitů ověřovat přes zachycená SHA, ověřit odstranění větví a doplnit deleted_branches do očekávaného JSON. Zachovat kontroly CI, opravných běhů a pořadí operací. Spustit všechny tři upravené soubory a test_branch_cleanup.py.

### Původ

Vznikl při běhu `1a6acc89` tasku `HAIFA-REFINEMENT-T51` (Po merge PR smazat větev tasku lokálně i na remote), v kroku `test_fix` (agent builder).
Důvod: Opakované cílené ověření potvrdilo 11 selhání ve třech souborech mimo povolené cesty T51. Testy čtou smazané větve nebo očekávají původní JSON clean.
Task `HAIFA-REFINEMENT-T51` na tomto tasku závisí a do jeho dokončení zůstává blokovaný.

<!-- factory: follow-up-of=HAIFA-REFINEMENT-T51 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
