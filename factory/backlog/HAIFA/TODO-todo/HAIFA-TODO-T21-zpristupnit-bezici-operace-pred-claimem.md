---
id: HAIFA-TODO-T21
title: Zpřístupnit běžící operace před claimem a během opakované publikace
status: done
depends_on: []
related: [HAIFA-REFINEMENT-T58]
writes: [aifactory/src/aifactory/run/store.py, aifactory/src/aifactory/run/members.py, aifactory/src/aifactory/review/flow.py, aifactory/src/aifactory/web/launcher.py, aifactory/src/aifactory/web/backlog.py, aifactory/src/aifactory/web/overview.py, aifactory/tests/web/test_web_launcher.py, aifactory/tests/web/test_web_backlog.py, aifactory/tests/web/test_web_overview.py, aifactory/tests/run/test_parallel_chain.py, aifactory/tests/run/test_task_operation_store.py, aifactory/web/src/lib/api.ts, aifactory/web/src/lib/overview.ts, aifactory/web/src/lib/overview.test.ts, aifactory/web/src/components/overview/RepoWork.vue, aifactory/web/src/components/overview/RepoCard.test.ts, aifactory/web/src/test/overviewFixtures.ts, aifactory/src/aifactory/web/static/, aifactory/web/src/components/factory/FactoryOperation.vue, aifactory/web/src/components/factory/FactoryOperation.live.test.ts, aifactory/web/src/components/factory/FactoryOperation.test.ts, aifactory/tests/e2e/test_multi_repo_browser.py]
---

## Zadání
Zveřejnit identitu tasku a životnost spuštěné operace pro dashboard i auto-continue před vznikem task_runs. Zahrnout retry a opakované publish s uloženým pr_error. Sdílené odvození zobrazení má používat tato data, odstraňovat ukončené operace a zachovat výpočty kapacity. Doplnit testy před claimem, při selhání procesu a během opakované publikace.

### Původ

Vznikl při běhu `debad1ee` tasku `HAIFA-REFINEMENT-T58` (Přehled: revize stavů tasku, aby se při přechodech (běží → automerge, merge a další) na chvíli neukázal jako Ready), v kroku `build` (agent builder), v kroku `test_fix` (agent builder), v kroku `fix` (agent builder), v kroku `review` (agent reviewer), v kroku `revise` (agent builder).
Důvod: RunLauncher eviduje procesy pouze v paměti a ProcessRunner zveřejní člena až po claimu. Čtenáři Přehledu a kanbanu tyto údaje nedostávají. Opakované task publish navíc ponechává starý pr_error až do dokončení. Oprava vyžaduje zápisy mimo povolené cesty T58.

<!-- factory: follow-up-of=HAIFA-REFINEMENT-T58 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-20 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/134 · náklady $0.00
