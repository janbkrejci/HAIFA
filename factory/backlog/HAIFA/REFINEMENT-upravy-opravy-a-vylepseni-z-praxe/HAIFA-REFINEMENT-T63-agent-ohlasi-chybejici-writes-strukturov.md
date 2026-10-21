---
id: HAIFA-REFINEMENT-T63
title: Agent ohlásí chybějící writes strukturovaně a retry --allow-writes je doplní
status: done
workflow: build-test-review
depends_on: []
writes: [aifactory/src/aifactory/failure.py, aifactory/src/aifactory/engine/data_types.py, aifactory/src/aifactory/run/task.py, aifactory/src/aifactory/run/allow_writes.py, aifactory/src/aifactory/run/retry.py, aifactory/src/aifactory/review/flow.py, aifactory/src/aifactory/review/ci.py, aifactory/src/aifactory/review/automerge.py, aifactory/src/aifactory/cli.py, aifactory/src/aifactory/web/runs.py, aifactory/src/aifactory/web/app.py, aifactory/src/aifactory/seed/agents/builder/, aifactory/src/aifactory/seed/agents/tester/, aifactory/src/aifactory/seed/agents/test-reviewer/, aifactory/src/aifactory/skill/skill.md, aifactory/src/aifactory/skill/codes.py, aifactory/src/aifactory/web/static/, aifactory/web/src/components/runs/, aifactory/web/src/lib/failure.ts, aifactory/web/src/lib/runs.ts, docs/decisions.md, aifactory/tests/run/test_allow_writes.py, aifactory/tests/run/test_writes_needed.py, aifactory/tests/review/test_ci_gate.py, aifactory/tests/web/test_web_runs.py, aifactory/tests/test_skill.py, aifactory/tests/engine/test_gate_correction.py, aifactory/tests/run/test_failure_kind.py, aifactory/tests/test_failure.py, aifactory/tests/e2e/test_failure_card_browser.py, aifactory/src/aifactory/engine/agents.py, aifactory/src/aifactory/engine/role_registry.py, aifactory/tests/engine/test_role_registry.py]
---

## Zadání
Když agent zjistí, že úkol nejde dokončit bez změny souboru mimo `writes` tasku, běh skončí jako `failure_kind: other`. Agent místo toho založí blokující follow-up s textovým popisem cest. Operátor pak musí ručně přečíst envelope, rozšířit `writes`, zrušit duplicitní follow-upy, odebrat je z `depends_on` a spustit retry. Pro zápis mimo `writes`, který zachytí guard (`writes_violation`), už HAIFA jednokrokové řešení má: `factory task retry --allow-writes`. Pro případ, kdy agent včas pozná, že potřebuje další cestu, chybí.

## Výskyty
- HAIFA-REFINEMENT-T50, běh 91a29ca3: test-reviewer vyžadoval browser test v `aifactory/tests/e2e/test_f3_browser.py`. Builder (`test_fix`) ho nesměl napsat a tester skončil `status='fail'`, `failure_kind: other`.
- HAIFA-REFINEMENT-T51, běh 1a6acc89: nové chování rozbilo 11 existujících testů ve třech souborech mimo `writes`. Builder skončil `fail` a založil dva duplicitní blokující follow-upy (HAIFA-TODO-T18, T19). Ty T51 zablokovaly a samostatně udělat nešly, protože testují kód, který existoval jen na větvi T51.
- HAIFA-REFINEMENT-T61, ci-fix běh a88bbbaf: CI selhala na chybějícím kódu `task_running` v `skill/codes.py`. Builder ci-fix běhu soubor nesměl změnit a PR zůstal s `ci_fix_failed`.

## Současný stav
- `failure.py`: `FAILURE_KINDS` nemá druh pro „agent potřebuje cestu mimo writes“. Spadá to do `other`.
- `engine/data_types.py`: envelope má `fail_kind` (dnes jen `nothing_to_do`) a `follow_ups[].writes`, ale ne pole pro cesty, které potřebuje tento task.
- `run/allow_writes.py` `plan_allow_writes` / `allow_writes`: bere jen `writes_violation` a cesty z `failure_detail.paths`. Jinak vrací `not_writes_violation`.
- `run/retry.py`: ci-fix běh nejde opakovat (`run_not_retryable`, „approve the PR again“).
- `seed/agents/builder/system.md` (a prompty testera a test-reviewera): práce mimo povolené cesty jde do `follow_ups`. Agent proto tentýž task rozdělí na blokující follow-upy.

## Jak se to má chovat
Princip: chybějící cesta ve `writes` tasku je problém rozsahu tohoto tasku, ne nová práce. Agent ji ohlásí strukturovaně, factory ji pozná a operátor ji vyřeší jedním příkazem nebo tlačítkem stejně jako `writes_violation`.

## Co udělat
1. **Envelope.** Přidat (v `engine/` označit změnu `# aifactory 2.9:`) do výstupu agentů pole `needs_writes: [{path, reason}]` (cesty, které tento task potřebuje změnit a jeho `writes` je nepokrývají) a hodnotu `fail_kind: needs_writes`. Agent, který kvůli tomu nemůže pokračovat, vrátí `status: fail`, `fail_kind: needs_writes` a vyplněné `needs_writes`. Kvůli tomu nezakládá follow-up.
2. **Druh selhání.** Nový `failure_kind` `writes_needed` v `failure.py` (`AgentFailed` dnes rozlišuje jen `nothing_to_do`). `failure_detail` obsahuje `agent`, `summary` a `paths` (normalizované cesty z `needs_writes` s důvody). `factory task runs` ho ukazuje jako ostatní druhy. Na dashboardu karta selhání (`web/src/components/runs/FailureCard.vue`, `web/src/lib/failure.ts`) nabídne u `writes_needed` stejné tlačítko „povolit zápis“ jako u `writes_violation`. Statický build se přegeneruje (`just web-build`).
3. **Allow-writes.** `plan_allow_writes` a `allow_writes` přijmou i `writes_needed` se stejným tříděním `allow` / `refused` (protected, backlog, main_checkout, already_allowed). `factory task retry --allow-writes` a `POST /api/runs/{id}/allow-writes` tedy fungují pro oba druhy. Retry pokračuje od fáze, která selhala, a agent dostane do `## Retry note` povolené cesty.
4. **Ci-fix.** Ci-fix běh, který skončí `writes_needed`, zapíše do `auto_merge_error` kód `writes_needed` s cestami. `factory task approve --allow-writes` (nebo stejné tlačítko na dashboardu) cesty povolí, commitne backlog a schválení spustí znovu, takže nové ci-fix běhy už s rozšířenými `writes` poběží.
5. **Prompty.** Builder, tester a test-reviewer (`seed/agents/<role>/`) dostanou pravidlo: cesta, kterou potřebuje tento task (test rozbitý novým chováním, registr, browser test, který review vyžaduje), jde do `needs_writes`, ne do `follow_ups`. `follow_ups` zůstávají pro práci, která do tasku nepatří. Test-reviewer, který vyžaduje test mimo `writes`, to řekne v `blocking` s cestou, aby ji tester a builder předali v `needs_writes`.
6. **Dokumentace.** Popisy `task retry --allow-writes` a `task approve` v `cli.py`, sekci Retry v `skill/skill.md`, nový kód v `skill/codes.py` a rozhodnutí v `docs/decisions.md`.

## Mimo rozsah
- Automatické povolení cest bez operátora.
- Lepší odhad `writes` při zakládání tasku (řeší se zvlášť lekcí pro autory tasků).
- Úklid follow-upů, které starší běhy založily místo `needs_writes`.

## Hotovo znamená:
- Builder, který vrátí `fail_kind: needs_writes` s cestou, ukončí běh jako `writes_needed` s `failure_detail.paths`. Žádný follow-up ani `depends_on` nevznikne. Test v `tests/run/`.
- `factory task retry --allow-writes` po `writes_needed` přidá cesty do `writes`, commitne backlog a běh dokončí (fake agent cestu na retry zapíše). Cesta v `protected_files` nebo v backlogu je `refused`. Testy v `tests/run/test_allow_writes.py`.
- Ci-fix běh se `writes_needed` nechá PR otevřený s `auto_merge_error` `writes_needed`. `factory task approve --allow-writes` cesty povolí a nový ci-fix PR opraví a sloučí. Test v `tests/review/`.
- Prompty builderu, testera a test-reviewera obsahují pravidlo z bodu 5. Test generovaného skillu (`tests/test_skill.py`) je zelený s novým kódem.
- `FailureCard` ukazuje u `writes_needed` cesty a tlačítko povolení. Test ve `FailureCard.test.ts`.
- `just lint`, `just typecheck`, `just web-test` a pytest dotčených balíčků (`tests/run`, `tests/review`, `tests/web`, `tests/test_skill.py`) jsou zelené.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-21 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/136 · náklady $8.65
