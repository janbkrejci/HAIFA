# HAIFA-REFINEMENT-T28 — Schválení a auto-merge čekají na zelenou CI a červenou opravují

Ruční schválení PR (`factory task approve`, tlačítko **Schválit** v dashboardu) i auto-merge mergují jen PR, jehož CI je zelená. Když je CI červená, HAIFA ji zkusí opravit do téhož PR.

## Chování

1. Schválení přidá commit se `status: done` a odešle ho. Pak čeká na CI kontroly přesně tohoto commitu. Na GitHubu nejdřív počká (nejvýš `AUTO_MERGE_CHECKS_APPEAR`, 90 s), až hosting ukáže nový head. Kontroly předchozího commitu se tedy nepočítají.
2. PR bez kontrol (`none`, ani po 90 s na GitHubu) se merguje hned. Stejně se chovají lokální provider a Azure DevOps, protože z nich HAIFA kontroly nečte.
3. Když kontroly skončí zeleně, PR se merguje.
4. Když je některá kontrola červená, spustí se opravný běh workflow `ci-fix` na větvi téhož PR (`started_by` `auto-ci-fix`). Poznámka běhu obsahuje názvy červených kontrol, jejich log a pokyn opravit příčinu, ne vypnout kontroly. Na GitHubu jde o `gh run view --job ID --log-failed`, posledních 150 řádků na kontrolu, celkem nejvýš 16 000 znaků. Běh opraví, otestuje, nechá zkontrolovat a commitne. Na konci se větev odešle do téhož PR. Pak se znovu čeká na CI.
5. Opravných běhů je nejvýš `CI_FIX_ROUNDS` (2). Když je CI i potom červená, PR zůstane otevřený s chybou `checks_failing`. Když kontroly běží déle než 30 minut, zůstane otevřený s `checks_pending`. Když opravný běh selže, s `ci_fix_failed`. Důvod se zapíše do `task_prs.auto_merge_error`, stejně jako dnešní chyby auto-merge, takže ho ukáže dashboard i CLI. Ruční schválení navíc skončí chybou s tímto kódem.
6. Opravný běh je běžný běh tasku. Je vidět v **Bězích** se spouštěčem `auto-ci-fix` a výsledek schválení vypisuje jeho id (`ci_fix_runs`).

## Implementace

- `review/ci.py` je brána CI.
  - `head_checks` čeká na head a na doběhnutí kontrol.
  - `checks_reason` převádí stav kontrol na kód a důvod.
  - `ci_report` skládá poznámku pro opravný běh.
  - `run_ci_fix` spouští `run_task(..., branch=<větev PR>, workflow_name="ci-fix", started_by="auto-ci-fix")`.
  - `provider_reports_checks` používá web.
  - Konstanty čekání se sem přesunuly z `review/automerge.py`.
- `review/flow.py`: `approve_task` se rozdělil na `_prepare_approve` (commit `status: done` a push) a `_finish_approve` (approve, merge, úklid). Mezi nimi běží brána CI s opravnými běhy. Před opravným během se uvolní větev (`_free_branch`).
- `review/automerge.py` už kontroly nečte sám. Podmínku CI splní `approve_task` na mergovaném headu. `try_auto_merge` předává `code` (`CodeRunner`) až do opravného běhu. Člen paralelního řetězce drží zámek merge i během čekání na CI a opravných běhů.
- `providers`:
  - `GitProvider.check_logs` ve výchozím stavu nevrací nic,
  - `GitHubProvider.check_logs` čte logy selhaných jobů.
- `run/task.py`: nový interní parametr `workflow_name` (vyžaduje `branch`). `ci-fix` je v `INTERNAL_WORKFLOWS` a jeho definice je `defaults/workflows/ci-fix.yaml`. Na vlastní workflow repa je ho možné přepsat v `.factory/workflows/ci-fix.yaml`. `task retry` běh `ci-fix` neopakuje a radí schválit PR znovu.
- Web:
  - Na hostingu s kontrolami (GitHub) spouští `POST /api/review/<id>/approve` schválení jako samostatný proces (`Launcher.start_approve`) a vrací HTTP 202 s `started: true`. Dashboard pak ukáže „Schvalování běží na pozadí…“.
  - U ostatních providerů zůstává synchronní odpověď s výsledkem merge.

## Omezení

- Azure DevOps kontroly zatím nečte, takže tam brána CI vždy vidí `none` a merguje hned.
