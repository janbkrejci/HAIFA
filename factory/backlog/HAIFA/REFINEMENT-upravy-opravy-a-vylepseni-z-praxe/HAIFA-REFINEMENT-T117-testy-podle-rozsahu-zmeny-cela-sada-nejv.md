---
id: HAIFA-REFINEMENT-T117
title: "Testy podle rozsahu změny: celá sada nejvýš jednou na běh, mezikola a resolve scoped"
status: done
workflow: build-test-review
depends_on: []
writes: [aifactory/src/aifactory/engine/gates.py, aifactory/src/aifactory/workflow/interpreter.py, aifactory/src/aifactory/engine/defaults/roles.yaml, aifactory/src/aifactory/defaults/workflows/, aifactory/src/aifactory/seed/agents/tester/, aifactory/validation/template/.factory/prompts/tester/, aifactory/src/aifactory/skill/skill.md, aifactory/src/aifactory/run/, aifactory/tests/]
---

## Zadání
Hlášení z provozu (repo NEO_HEF, workflow `haifa-implement-task` a vestavěný `resolve-reviewed`, factory 0.1.58x): i malá změna spouští v jednom běhu opakovaně celou testovací sadu. Celá sada ROB trvá 35–46 min (5 069 testů na skryté ploše). Rozsah testů má odpovídat tomu, co běh změnil, a celá sada má v běhu proběhnout nejvýš jednou, na konečném kódu.

## Naměřeno (NEO_HEF `.factory/trace.db`, ukončené běhy od 2026-11-01)

- 103 běhů, ve fázích `test*` celkem 44,5 h. Testery zvolily `coverage: full` v 91 ze 186 plánů.
- Celou sadu (kontrola `*full*suite*` v platném plánu) spustilo 40 běhů, dohromady 174×, tedy 4,4× na běh, za 36 h. Podle velikosti změny produkčního kódu (`src/**/*.cs|resx|csproj` mimo testy): 1–3 soubory 10 běhů, 45 spuštění, 425 min; 4–10 souborů 25 běhů, 103 spuštění, 1 393 min; 11+ souborů 5 běhů, 26 spuštění, 360 min.
- Příklady: `ROB-TODO-T110` (běh `946d31ec`) změnil 1 produkční soubor a spustil celou sadu 15×, 170 min. `ROB-S13-T005` (`8b44504f`) 2 soubory, 4×, 56 min.
- Resolve `ROB-S12-T005` (běh `e66e61a8`, 2026-11-11): konflikt byl jen v QA registru a matici (dokumentace), běh trval 56 min s build a cílenými testy a třemi kolečky fix/test_plan kvůli koncům řádků. Ruční vyřešení stačilo s jedním buildem, protože git automaticky sloučil jediný soubor kódu.

## Příčiny v kódu (ověřit před změnou)

1. Ratchet: `seed/agents/tester/system.md:24` říká u replánu „Keep every previous check“ a gate `plan_keeps_checks` (`engine/gates.py:163`) pustí jen plán, který předchozí kontrolu nechá, nebo ji uvede v `dropped`. Jakmile se celá sada jednou dostane do plánu, běží v každém dalším `test`/`retest`: po každé opravě (repeat max 4) i po každé revizi review (max 3).
2. Volba rozsahu nemá oporu v diffu: `system.md:18` dává `full`, „when you cannot tell what depends on it“. V NEO_HEF tester volí `full` u poloviny plánů, i když se změnil 1 soubor.
3. Krok `test` spouští všechny kontroly plánu i po opravě, která se týkala jedné z nich (`system.md:21`).
4. Vestavěné `resolve.yaml` a `resolve-reviewed.yaml` po rebase plánují testy stejně jako implementační běh. Neberou v úvahu, které soubory rebase nebo resolve skutečně změnil (jen dokumentace, nebo i kód sloučený automaticky).

Vzor už v HAIFA existuje: workflow `heal` opravuje se `scoped` kontrolami a celou sadou potvrdí jen na konci.

## Co udělat

1. Celá sada nejvýš jednou na běh, na konečném kódu: mezikola (`test` po `fix`, `retest` po `revise`) běží `scoped`, tedy nesplněné kontroly a kontroly souborů, které oprava nebo revize změnila, a jejich přímé volající. Celá sada (je-li v plánu) proběhne jednou před `commit_build`, respektive před akceptací. Když tam selže, vrátí se do opravy jako dnes.
2. Rozsah prvního plánu odvodit z diffu proti `baseline` podle druhu souborů:
   - jen dokumentace a backlog → kontroly, které tyto soubory čtou (např. `factory backlog check`, gate plánu repa), žádný build ani testy;
   - kód → build a testy dotčených projektů nebo jmenných prostorů;
   - `full` jen při změně sdílené infrastruktury (build soubory, testovací setup, závislosti, CI, konfigurace čtená všude) nebo cest, které repo v testovacím profilu označí jako sdílené (např. `RobTextMode` v NEO_HEF).
   Dnešní „nevím, co na tom závisí → full“ nahradit pravidlem: najdi volající. `full` se volí až tehdy, když volající nejdou dohledat.
3. `plan_keeps_checks`: v mezikole povolit náhradu celé sady jejím odložením na konec („the whole suite confirms later“, jako `required_coverage: scoped` dnes) bez důvodu psaného pokaždé znovu. Nesplněná kontrola se dál nesmí zahodit.
4. Resolve: rozsah testů odvodit ze souborů, které rebase a resolve změnily proti hlavě PR před rebase. Jen dokumentace → kontroly dokumentace. Automaticky sloučený kód → build a testy dotčených projektů. Celou sadu jen podle bodu 2.
5. Do výsledku běhu (PR, dashboard) zapsat, kolikrát a proč proběhla celá sada.

## Hotovo znamená

- Test workflow: běh s červeným testem po `fix` spustí v mezikole jen nesplněnou a dotčené kontroly, celou sadu jednou na konci. Test na `plan_keeps_checks`: odložení celé sady v mezikole projde, zahození nesplněné kontroly ne.
- Test resolve: rebase s konfliktem jen v `.md` naplánuje kontroly dokumentace bez buildu. Rebase, který automaticky sloučil `.cs`, naplánuje build a testy dotčeného projektu.
- Test volby rozsahu: diff jen v dokumentaci → `none` nebo kontroly dokumentace, diff ve sdílené cestě z testovacího profilu → `full`.
- Upravený `seed/agents/tester/system.md` (a `validation/template/.factory/prompts/tester/system.md`) a `skill/skill.md` popisují nová pravidla.
- Projdou `just lint`, `just typecheck` a cílené `just pytest` pro změněné chování.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-11 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/219 · náklady $0.00
