---
id: HAIFA-REFINEMENT-T90
title: Automatický úklid worktree a větví po dokončeném nebo zrušeném tasku a před každým během
status: done
archived: true
workflow: build-test-review
depends_on: []
writes: [aifactory/src/aifactory/review/flow.py, aifactory/src/aifactory/review/__init__.py, aifactory/src/aifactory/run/task.py, aifactory/src/aifactory/cli.py, aifactory/src/aifactory/guide/05-behy-a-review.md, aifactory/src/aifactory/skill/skill.md, docs/decisions.md, aifactory/tests/review/test_branch_cleanup.py, aifactory/tests/run/test_task_auto_clean.py, aifactory/tests/run/test_task_pr_flow.py]
---

## Zadání
## Problém

Po bězích zůstávají na disku worktree v `<worktrees_dir>/<run-id>` (výchozí `.factory/worktrees/`) a lokální i remote větve `factory/<task-id>-<n>`. Dnes je ruší jen merge v `approve` (`_remove_run_worktrees` a `_delete_merged_branch` v `aifactory/src/aifactory/review/flow.py`) a ruční `factory task clean` (`clean_worktrees` a `_clean` ve stejném souboru). `factory task clean` nikdo nespouští, takže se disk plní. Na `factory task stop` worktree i větev zůstanou vždy (viz nápověda v `cli.py`).

## Co udělat

1. Rozšířit `_clean` v `review/flow.py`, aby kromě dnešních případů (PR merged/closed, starší běh bez PR) uklidil i tyto:
   - Worktree všech běhů tasku, který je v backlogu `done` nebo `cancelled`. Platí i pro poslední běh bez PR a pro selhaný nebo zastavený běh: zrušený nebo hotový task se už opakovat nebude. Jako zdroj stavu tasku použít backlog načtený z main checkoutu (loader v `aifactory/backlog`).
   - Lokální větev a větev na remote u běhů zrušeného tasku a u PR ve stavu CLOSED, pokud jde o větev factory (`factory/…`), na větvi nic neběží (`RUNNING`), není checkoutnutá jinde a nestojí na ní žádný otevřený stacked PR. Použít stejná pravidla jako `_delete_merged_branch` a sdílet kód, ne ho kopírovat.
   - Osiřelé adresáře v `<worktrees_dir>`, které nejsou v `git worktree list` a nepatří žádnému běžícímu běhu, plus `git worktree prune`. Patří sem i dočasné `sync-*`/`<prefix>-<branch>` worktree z `_branch_worktree` a `sync.py`, které zůstaly po pádu.
   - Nikdy nemazat: worktree běžícího běhu (i souběžného z jiného procesu), worktree otevřeného PR, worktree s necommitnutými změnami u tasku, který není `done` ani `cancelled` (ty jen nahlásit ve `warnings`), a poslední selhaný nebo zastavený běh tasku ve stavu `todo` (zůstává pro `task retry`).
   - Do `CleanResult` doplnit důvod (`done`, `cancelled`, `closed`, `orphan`…) k odstraněným worktree a smazaným větvím.
2. Úklid spouštět automaticky, vždy best-effort: chyba se jen zapíše do `warnings` výsledku a běh nikdy neshodí.
   - V `run_task` (`aifactory/src/aifactory/run/task.py`) před vytvořením nového worktree. Tím se uklidí i to, co po předchozím běhu nedoběhlo.
   - V `run_task` po dokončení běhu (po `store.finish`, i při selhání a stopu), aby se uvolnily worktree hotových nebo zrušených tasků a starších pokusů.
   - Úklid nesmí sáhnout na worktree ani větev běhu, který se právě spouští nebo opakuje (`retry` pokračuje ve vlastním worktree, `return_task`/`resolve` pracují na větvi PR).
3. Přidat `--dry-run`/JSON výstup `factory task clean` jen tehdy, pokud to nový výstup s důvody potřebuje. Přepínač pro vypnutí automatického úklidu nepřidávat.
4. Aktualizovat zmínky o `factory task clean` v `aifactory/src/aifactory/guide/05-behy-a-review.md`, ve `skill/skill.md` a v nápovědě `cli.py` (stop: worktree uklidí další běh nebo `task clean`). Rozhodnutí zapsat do `docs/decisions.md`.

## Mimo rozsah

Složky AI agentů (`~/.claude/projects`, sessions) a volání úklidu z dashboardu řeší jiné tasky.

Hotovo znamená:
- Nový test v `aifactory/tests/run/test_task_auto_clean.py` ukazuje, že po zrušení tasku (status `cancelled`) a spuštění jiného tasku zmizí worktree i lokální větev zrušeného tasku.
- Test ukazuje, že worktree souběžně běžícího běhu, otevřeného PR a posledního selhaného běhu tasku `todo` zůstane.
- Test ukazuje, že osiřelý adresář v `.factory/worktrees/` bez záznamu v `git worktree list` zmizí.
- Chyba při mazání (např. zamčený soubor) skončí jako warning a běh pokračuje.
- Existující testy v `aifactory/tests/review/test_branch_cleanup.py` jsou upravené nebo rozšířené a procházejí.
- `docs/decisions.md` a příručka popisují automatický úklid.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-27 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/179 · náklady $0.00
