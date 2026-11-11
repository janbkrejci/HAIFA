---
id: HAIFA-REFINEMENT-T116
title: "Zrychlit kontrolu na Přehledu: lehký krok roster, poslední známý výsledek a žádné git timeouty z vyčerpaného rozpočtu"
status: done
workflow: build-test-review
depends_on: [HAIFA-REFINEMENT-T113]
writes: [aifactory/src/aifactory/web/machine.py, aifactory/src/aifactory/web/factory.py, aifactory/src/aifactory/web/app.py, aifactory/src/aifactory/web/repos.py, aifactory/tests/web/test_web_machine.py, aifactory/tests/web/test_web_factory_roster.py, aifactory/tests/web/test_web_repos.py, aifactory/web/src/lib/readiness.ts, aifactory/web/src/lib/machineProgress.ts, aifactory/web/src/lib/api.ts, aifactory/web/src/components/OverviewReadiness.test.ts, aifactory/src/aifactory/web/static/, aifactory/web/src/App.test.ts, aifactory/tests/e2e/test_machine_check_browser.py, aifactory/src/aifactory/procrun.py, aifactory/tests/test_procrun.py]
---

## Zadání
## Zadání
Hlášení z provozu (Windows 11, repo NEO_HEF, factory 0.1.586, dashboard `factory obs`, souběžně 2 taskruny): Přehled ukazuje „Kontrola nedoběhla do 75 s. Nedokončený krok: roster. Dřívější výsledek není k dispozici.“ Ruční `factory check --json` trvá 76 s, téměř celý čas je čekání, ne CPU. Dashboard navíc opakovaně loguje `subprocess.TimeoutExpired: git rev-parse --verify --quiet HEAD^{commit} timed out after 0.27 s`.

Zjištěné příčiny v kódu (ověřit před změnou):
- Limit 75 s je klientský `CHECK_DEADLINE_MS` v `aifactory/web/src/lib/readiness.ts`. Krok `roster` je následný požadavek `fetchFactoryRoster(repo.id)` (`GET /api/repos/{id}/factory/roster`, `roster()` v `aifactory/src/aifactory/web/factory.py`). Readiness z něj používá jen `roster.agents.length`, ale endpoint kvůli počtům použití workflow čte celý backlog z base (`_base_tasks` v `library/config_edit.py`: git tree, bloby, parsování). Ve velkém repu pod zátěží je to nejpomalejší krok.
- `lastCheckedAt` v `readiness.ts` se nastaví až po doběhnutí rosteru a backlogu, takže timeout následného kroku zahodí i hotový výsledek kontroly počítače („Dřívější výsledek není k dispozici“).
- 0,27 s není pevný limit, je to zbytek vyčerpaného rozpočtu `procrun.budget` (`CHECK_BUDGET`, `REGISTRY_BUDGET` v `web/machine.py`). Čtení `read_git(root, "rev-parse", "--verify", "--quiet", "HEAD^{commit}")` je ve `web/repos.py`. Dohledat, kde se pod rozpočtem volá a kde se výjimka loguje se stack trace.

Upravit:
1. Readiness na Přehledu nebude kvůli počtu agentů volat plný roster. Přidat lehký údaj o počtu agentů bez čtení backlogu z base, např. do `GET /api/repos/{id}/backlog/summary` nebo jako lehký režim rosteru, a `readiness.ts` přepnout na něj. Plný `GET …/factory/roster` pro editor rosteru (`RosterEditor.vue`, `FactoryView.vue`) zůstává beze změny výstupu.
2. Timeout nebo chyba následného kroku (roster, backlog, knihovna, repa) nesmí zahodit hotový výsledek kontroly počítače. Zobrazí se poslední známý výsledek s časem (`lastKnown`) a u nedokončeného kroku upozornění, že jeho údaj není k dispozici. Kontrola počítače, která sama doběhla, se nehlásí jako „Kontrola nedoběhla“.
3. Čtení gitu se nespouští s téměř vyčerpaným rozpočtem a vyčerpaný rozpočet (`procrun.BudgetExceeded`) se při čtení registru a rep neloguje opakovaně jako stack trace. Stačí jednořádkové varování nebo tichá degradace na poslední známý stav, podle toho, co volající už umí. Ověřit, že `REGISTRY_BUDGET` a `LIBRARY_BUDGET` stačí na Windows pod zátěží; když ne, upravit hodnoty se zdůvodněním v komentáři. `CHECK_BUDGET` a `CHECK_DEADLINE_MS` drží konzistentní vztah popsaný v `lib/machineProgress.ts`.

Před změnou dohledat přímé volající `roster`, `_base_tasks`, `fetchFactoryRoster`, `useReadiness`, `read_git` ve `web/repos.py` a `REGISTRY_BUDGET` v celém `aifactory/tests/` a webových testech. Testy bez živých modelů, služeb a reálných zpoždění: pomalost simulovat falešnými funkcemi nebo bariérami, ne `sleep` v řádu sekund.

Mimo rozsah: obsah kontrol (`workflow_unknown`, `skill_mirror_*` v repu uživatele nejsou chyby Factory), CLI `factory check`, pravidlo spouštění kontroly z HAIFA-REFINEMENT-T113.

Hotovo znamená:
- Webový nebo backendový test ukáže, že readiness Přehledu nevolá plný roster a lehký údaj o počtu agentů nečte backlog z base (falešné `_base_tasks` se nezavolá).
- Test v `OverviewReadiness.test.ts`: kontrola počítače doběhne, následný krok vyprší, a stránka ukáže výsledek kontroly počítače s časem a upozornění na nedokončený krok, ne „Dřívější výsledek není k dispozici“.
- Backendový test: čtení registru či repa s vyčerpaným rozpočtem nespustí git a nezaloguje stack trace `TimeoutExpired`.
- Testy plného rosteru (`tests/web/test_web_factory_roster.py`) projdou beze změny výstupu endpointu.
- Projdou `just lint`, `just typecheck`, `just web-test`, cílené `just pytest` pro změněné chování a všechny editované testovací soubory.
- Proběhne `just web-build` a aktualizuje se distribuovaný statický frontend.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-11 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/218 · náklady $0.00
