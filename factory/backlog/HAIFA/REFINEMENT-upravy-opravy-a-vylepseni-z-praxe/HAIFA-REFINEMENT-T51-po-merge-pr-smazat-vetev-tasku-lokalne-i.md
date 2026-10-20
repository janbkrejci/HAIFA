---
id: HAIFA-REFINEMENT-T51
title: Po merge PR smazat větev tasku lokálně i na remote
status: todo
workflow: build-test-review
depends_on: [HAIFA-TODO-T18, HAIFA-TODO-T19]
writes: [aifactory/src/aifactory/review/flow.py aifactory/src/aifactory/providers/base.py aifactory/src/aifactory/providers/git.py aifactory/src/aifactory/providers/github.py aifactory/src/aifactory/providers/local.py aifactory/src/aifactory/providers/azure.py aifactory/src/aifactory/cli.py aifactory/tests/review/test_branch_cleanup.py aifactory/tests/providers/test_providers_github.py aifactory/tests/providers/test_providers_local.py aifactory/tests/providers/gh_fake.py, aifactory/tests/review/test_approve_merge_retry.py, aifactory/tests/review/test_ci_gate.py, aifactory/tests/run/test_task_pr_flow.py]
---

## Zadání
Po úspěšném sloučení PR tasku factory smaže jeho větev, lokálně i na remote. Dnes po sloučení zůstávají všechny větve `factory/<task>-<n>`. Squash merge je navíc nechává pro `git branch -d` nesloučené, takže se v repu hromadí (v TSWebUI-a2ui 48 větví po M00–M02) a uklidit se dají jen ručně přes `git branch -D`.

## Současný stav
- `review/flow.py` `_finish_approve`: po merge zapíše `task_prs`, dorovná base (`_catch_up_base`) a smaže worktree běhů větve (`_remove_run_worktrees`). Větev nemaže.
- `providers/github.py` `merge`: `gh pr merge` bez `--delete-branch`, remote větev zůstane.
- `providers/local.py` `merge`: posune base, větev nemaže.
- `providers/azure.py` už posílá `--delete-source-branch`, remote větev se smaže. Lokální větev zůstává.
- `approve_task` po `_approve_gated` volá `restack_dependents(..., result.pr.branch, ...)`. Stacked PR se přebázují vůči sloučené větvi, takže ta musí existovat až do konce restacku.
- `factory task clean` maže jen worktree, ne větve.

## Co udělat
1. Po úspěšném merge (operator i auto-merge, všichni provideři) smazat lokální větev PR (`git branch -D`, protože squash) a remote větev na `origin`, pokud existuje. Na Azure remote větev už smazal merge, chybějící remote větev není chyba.
2. Mazat až po `restack_dependents`. Větev, na které stojí ještě otevřený stacked PR, nemazat.
3. Nemazat větev, která je checkoutnutá v hlavním checkoutu nebo ve worktree běžícího běhu.
4. Chyba mazání (síť, chráněná větev, odmítnutý push) merge neshodí. Skončí jako položka ve `warnings` výsledku.
5. `ApproveResult` (a JSON výstup `factory task approve`) uvede smazané větve, např. `deleted_branches: [...]`.
6. `factory task clean` smaže i lokální a remote větve PR ve stavu `merged`, které ještě existují (úklid repozitářů sloučených před touto změnou). Stejná pravidla jako v bodech 2–4. Výstup je uvede.
7. Upravit popisy příkazů `task approve` a `task clean` v `cli.py`, ať `factory --skill` popisuje nové chování.

## Mimo rozsah
- Větve zavřených (neslučovaných) PR a opuštěných běhů. Ty zůstávají kvůli dohledání práce.
- Nastavení, které mazání vypíná.
- Změna merge strategie.

## Hotovo znamená:
- Po `factory task approve` i auto-merge na local i GitHub providerovi větev PR neexistuje lokálně ani na `origin`. Test na fake gh a git remote to ověří.
- Stacked PR na sloučené větvi se dál přebázuje a sloučí. Test pokrývá pořadí restack → mazání.
- Selhání smazání remote větve nechá merge úspěšný a vrátí warning. Test to ověří.
- `factory task clean` smaže větve dříve sloučených PR, ale ne větve otevřených, zavřených ani opuštěných běhů. Test to ověří.
- `just test` je zelené.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
