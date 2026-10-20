---
id: HAIFA-TODO-T18
title: Aktualizovat testy schvalování pro mazání větví po merge
status: cancelled
depends_on: []
related: [HAIFA-REFINEMENT-T51]
writes: [aifactory/tests/review/test_approve_merge_retry.py, aifactory/tests/review/test_ci_gate.py, aifactory/tests/run/test_task_pr_flow.py]
---

## Zadání
Upravit test_approve_again_after_transient_merge_failure a obě varianty test_azure_approve_final_push_before_vote_and_retry; potřebné SHA zachytit před mazáním a následně ověřit odstranění větví. V test_task_pr_flow upravit test_approve_commits_done_and_merges a test_clean_without_runs. V test_ci_gate upravit čtyři varianty test_merges_without_red_checks a dvě varianty test_red_checks_are_repaired_on_the_same_branch: obsah schvalovaného commitu ověřovat přes zachycené SHA místo odstraněného názvu větve. Zachovat kontroly CI, opravných běhů a pořadí operací. Spustit všechny tři upravené testové soubory a test_branch_cleanup.py.

### Původ

Vznikl při běhu `1a6acc89` tasku `HAIFA-REFINEMENT-T51` (Po merge PR smazat větev tasku lokálně i na remote), v kroku `build` (agent builder).
Důvod: Cílené ověření odhalilo 11 selhání zastaralých očekávání ve třech souborech mimo povolené cesty T51. Testy po úspěšném merge čtou smazanou větev nebo očekávají JSON clean bez deleted_branches.
Task `HAIFA-REFINEMENT-T51` na tomto tasku závisí a do jeho dokončení zůstává blokovaný.

<!-- factory: follow-up-of=HAIFA-REFINEMENT-T51 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
