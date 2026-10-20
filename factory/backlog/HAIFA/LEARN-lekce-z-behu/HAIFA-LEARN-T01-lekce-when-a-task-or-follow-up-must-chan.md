---
id: HAIFA-LEARN-T01
title: "Lekce: When a task or follow-up must change docs/decisions.md, aifactory/web/src/ or any…"
status: done
workflow: build-test-review
depends_on: []
related: [HAIFA-S03-T18, HAIFA-TODO-T01, HAIFA-TODO-T05, HAIFA-TODO-T07, HAIFA-TODO-T08]
writes: [AGENTS.md]
---

## Zadání
Zapiš do `AGENTS.md` pravidlo z lekce `L984343e2`, kterou factory našla ve výtkách opakovaných v bězích:

> When a task or follow-up must change docs/decisions.md, aifactory/web/src/ or any other path outside the inherited writes, list that path in its own `writes` before the task runs.

Pravidlo formuluj stručně, zařaď ho tam, kam v souboru patří, a nenech ho odporovat tomu, co tam už je. Jiné soubory neměň.

Hotovo znamená:
- Pravidlo je v `AGENTS.md`.

### Důkazy

Výtky z 6 běhů, ze kterých lekce vznikla:

- běh `92fcfe46`, task `HAIFA-S03-T18` (review): The task asks for a dashboard that shows pr_error and a publish button for a succeeded run with no PR, but no UI was built. The Vue source is in aifactory/web/src, which is outside the allowed paths (only aifactory/src/aifactory/web/ is allowed). The operator must either widen the allowed paths to include aifactory/web/src, so the builder can add pr_error and a publish button calling POST /api/review/{task_id}/publish in the runs/review components and rebuild static/, or explicitly move the UI to a follow-up task.
- běh `dd709748`, task `HAIFA-S03-T18` (review): The dashboard UI is missing. The Runs view in aifactory/web/src must show pr_error for a succeeded run without a PR and a Publish button that calls POST /api/review/{task_id}/publish when can_publish is true, and the static bundle in aifactory/src/aifactory/web/static must be rebuilt. aifactory/web/src is outside this task's allowed paths, so the orchestrator must add aifactory/web/src/ to the allowed paths, or the engineer must explicitly move the UI to a follow-up task.
- běh `dd709748`, task `HAIFA-S03-T18` (review): Dashboard u succeeded běhu bez PR ukáže pr_error a tlačítko pro publish: Only the backend exists: web/runs.py adds pr_error and can_publish, and web/app.py adds POST /api/review/{task_id}/publish. The Vue frontend in aifactory/web/src does not render pr_error and has no publish button (grep finds nothing there). The builder says aifactory/web/src is outside the allowed paths.
- běh `00e32286`, task `HAIFA-TODO-T01` (review): docs/decisions.md is not in the task's allowed paths (aifactory/, justfile and the task's spec and doc files). The only required change cannot be made. The task must run again with docs/decisions.md in allowed paths. The builder already filed a blocking follow-up for this (blocks_task: true).
- běh `00e32286`, task `HAIFA-TODO-T01` (revise): Nothing changed again: the allowed paths are the same as in the previous run and still leave out docs/decisions.md, the task's only deliverable, so the task stays blocked.
- běh `00e32286`, task `HAIFA-TODO-T01` (review): docs/decisions.md is not in the task's allowed paths. The builder cannot make the only required change, and running again with the same allowed paths gives the same result. The task needs docs/decisions.md in its allowed paths. The builder's blocking follow-up (blocks_task: true) covers this.
- běh `b92b4e20`, task `HAIFA-TODO-T05` (review): docs/decisions.md is unchanged. The new Czech bullet '**Approve a auto-merge čekají na CI:**' (or a replacement of the older decision) is missing. The builder cannot fix this inside the run: first, outside the run, add `writes` with docs/decisions.md (plus aifactory/ and justfile if `writes` does not add to the inherited value) to the front matter of HAIFA-TODO-T05 in factory/backlog/, then run the task again.
- běh `b92b4e20`, task `HAIFA-TODO-T05` (review): Task musí mít v allowed paths docs/decisions.md: The prompt's allowed paths are only aifactory/, justfile and the task's spec and doc files. docs/decisions.md is missing from them, so the task front matter still has no `writes` for it.
- běh `b92b4e20`, task `HAIFA-TODO-T05` (revise): docs/decisions.md is still unchanged because the task still cannot write to docs/. This run confirmed the last unchecked fact (the dashboard approves in the background on GitHub) and drafted the bullet text in the blocking follow-up.
- běh `b92b4e20`, task `HAIFA-TODO-T05` (review): docs/decisions.md is unchanged and the decision bullet '**Approve a auto-merge čekají na CI:**' is missing. The builder cannot fix this inside the run, and more build rounds will not help. First, outside the run, add `writes` with docs/decisions.md (plus aifactory/ and justfile if `writes` does not add to the inherited value) to the front matter of HAIFA-TODO-T05, then run the task again.
- běh `b92b4e20`, task `HAIFA-TODO-T05` (review): Task musí mít v allowed paths docs/decisions.md: The prompt's allowed paths are still only aifactory/, justfile and the task's spec and doc files. The task front matter has no `writes` for docs/decisions.md.
- běh `a1564902`, task `HAIFA-TODO-T07` (review): docs/decisions.md has no new bullet after 'Dědičnost z knihovny' (line 22) covering: `factory library seed --all` on install and upgrade, items outside the seed staying, repo copies in .factory/ never being touched, the generated `factory` skill, and manual `seed` without `--all` keeping team edits. The builder could not write it because docs/decisions.md is not in the task's allowed paths. The builder already filed a for-human, task-blocking follow-up to add it to the task's `writes`.
- běh `a1564902`, task `HAIFA-TODO-T07` (revise): Nothing changed again: the allowed paths still leave out docs/decisions.md, the only file this task must edit, so the task stays blocked on the for-human follow-up that adds it to the task's writes.
- běh `a1564902`, task `HAIFA-TODO-T07` (review): docs/decisions.md still has no bullet after 'Dědičnost z knihovny' (line 22) covering the five points of the spec. The builder cannot fix this because docs/decisions.md is not in the task's allowed paths. A person has to add `writes: [docs/decisions.md]` to the task's front matter, as the builder's for-human follow-up (blocks_task: true) asks. Another build round will not help.
- běh `37daf127`, task `HAIFA-TODO-T08` (review): The decision is not in docs/decisions.md. The task only asks for an edit to docs/decisions.md, and that file is outside its allowed paths (aifactory/, justfile, the task's spec and doc). Before the task can be done, a person must add docs/decisions.md to the task's allowed paths, then the builder adds the new point after 'Dědičnost z knihovny' (line 22). The other way is to close T08 in favour of the follow-up the builder filed.
- běh `37daf127`, task `HAIFA-TODO-T08` (revise): No file was changed again: the task only edits docs/decisions.md, which is outside its allowed paths, so I replaced my duplicate follow-up with the reviewer's request for a person to fix the allowed paths.
- běh `37daf127`, task `HAIFA-TODO-T08` (review): The decision is still not in docs/decisions.md, and no run can write it while the file is outside the task's allowed paths. A person must add docs/decisions.md to the task's writes. The builder then adds the new point after 'Dědičnost z knihovny' (docs/decisions.md:22). The builder's for_human follow-up already asks for this.

<!-- factory: lesson=L984343e2 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-20 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/128 · náklady $0.00
