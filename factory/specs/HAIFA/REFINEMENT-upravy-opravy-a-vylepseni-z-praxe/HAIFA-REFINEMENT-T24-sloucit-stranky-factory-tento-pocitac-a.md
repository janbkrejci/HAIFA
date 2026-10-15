# HAIFA-REFINEMENT-T24: Sloučit stránky Factory, Tento počítač a Knihovna a posoudit stránku Nastavení

## Rozhodnutí o uspořádání (zdůvodnění)

Dnešní stav (4 stránky):

| Stránka | Route | Obsah |
|---|---|---|
| Factory (repo) | `#/r/<id>/factory` | `factory check` repa, verdikt, nálezy ve dvou skupinách „Repozitář“ a „Tento počítač: opravit lokálně“ (tam jsou i nálezy knihovny), instalace / commit / pull konfigurace, roster, položky repa |
| Nastavení (repo) | `#/r/<id>/settings` | formulář `.factory/config.yaml` (sdílené) a `.factory/local.yaml` (lokální); uložené sdílené hodnoty se musí commitnout tlačítkem na stránce Factory |
| Tento počítač (global) | `#/setup` | kontrola počítače ve skupinách (včetně skupiny Knihovna), **Začínáme** (je i na Přehledu), stav a sync knihovny (Stáhnout / Odeslat jako PR, PR seznam, napřed/pozadu), založení/naklonování knihovny, nastavení dashboardu (port) |
| Knihovna (global) | `#/library` | sync knihovny (znovu stav, PR, Stáhnout / Odeslat jako PR, remote), reseed, import, prohlížeč položek, kopie rep a přesun do knihovny |

Duplicity: sync knihovny (Tento počítač × Knihovna), nálezy knihovny (Factory × Tento počítač), repo-nezávislé nálezy počítače (Factory × Tento počítač), Začínáme (Přehled × Tento počítač). Nastavení je jen polovina workflow „změnit konfiguraci → commitnout“; druhá polovina je na Factory.

Nové uspořádání: **dvě stránky podle rozsahu**, obě postavené na vzoru stránky Factory (hlavička + „Znovu zkontrolovat“, verdikt, jen akční nálezy, pod tím sekce s akcemi):

1. **Factory** (`#/r/<id>/factory`) = vše o factory jednoho repa. Přibude sekce **Nastavení repozitáře** (dnešní stránka Nastavení). Záložka Nastavení zaniká: po uložení je tlačítko „Commitnout konfiguraci“ a nález `config_uncommitted` hned na stejné stránce. Nálezy knihovny a repo-nezávislé nálezy počítače na Factory nejsou (jsou na Tento počítač); zůstávají jen nálezy počítače, které plynou z tohoto repa (harness z jeho rosteru, node pro pi, login k jeho hostingu, izolace…).
2. **Tento počítač** (`#/setup`) = vše o tomto počítači: kontrola počítače, **Knihovna** (dnešní stránka Knihovna + založení/klon knihovny, jediné místo synchronizace), nastavení dashboardu. Knihovna leží v `$HAIFA_HOME` tohoto počítače, proto patří sem. Stránka Knihovna zaniká jako samostatná route, `#/library` přesměruje na `#/setup/library` (sekce knihovny).

Výslovně zrušené (zbytečné):
- **Začínáme** na Tento počítač: totéž je na Přehledu (a chybějící kroky ukazuje readiness chip). Zůstává jen na Přehledu.
- Text „HAIFA je spuštěná na tomto počítači.“ a prázdné skupiny „Bez nálezů“: informace bez akce.
- Seznam „Harnessy · claude · 2 repa / codex · nepoužívá žádné repo“ (`harness-counts`): informace bez akce; počty se dál používají na serveru k rozhodnutí, zda je chybějící harness potřeba (viz níže). Nastavení harnessů je v dialogu z horní lišty (beze změny).
- Patička „Další krok: Přidat repozitář · Přehled“ na Tento počítač: navigace, kterou nabízí přepínač rep a Začínáme na Přehledu.
- Nálezy bez opravy (`repo_installed` a jiné s `fix` i `action` = null), `hosting_skipped` a info `harness_missing` pro harness, který žádné registrované repo nepoužívá.

Agregace v horní liště (readiness chip, `#/problems`, chip knihovny) nejsou duplicitní obsah: jen počítají problémy a odkazují na jediné místo, kde se řeší. Zůstávají, jen s novými odkazy.

## Změny – backend (`aifactory/src/aifactory/`)

### 1. Jen akční nálezy v dashboardu
- `web/factory.py`: přidej veřejnou funkci (např. `actionable_findings(data: JsonDict) -> JsonDict` nebo dvojici `is_actionable(finding: Mapping) -> bool` + `drop_unactionable(data)`), která:
  - vyhodí z `data["findings"]` nález, který nemá `fix` ani `action` (tím zmizí `repo_installed`; builder ověří grepem `Finding(` v `check/*_rules.py` a `web/`, které další nálezy nemají fix, a zapíše je do dokumentace),
  - vyhodí kódy z konstanty `DASHBOARD_HIDDEN = frozenset({"hosting_skipped"})` (v dashboardu nejde přepnout offline, rada „run without --offline“ je pro CLI),
  - přepočítá `data["counts"]` podle zbylých nálezů (klíče `error`, `warning`, `info` vždy přítomné). `ok` se nemění (vyhozené nálezy nejsou `error`; přidej `assert`/komentář).
- `web/factory.py::check_view`: aplikuj filtr na výsledný `data` (po přidání `trace_db_shared`, po `to_json`). Cache dál drží celý report; CLI `factory check` se nemění (tam `repo_installed` zůstává jako stavový řádek).
- `web/machine.py::check_view`: na `view` (po deep copy, po výpočtu `counts` harnessů) aplikuj stejný filtr a navíc vyhoď `harness_missing` se severity `info`, jehož harness (`HARNESSES`, zpráva začíná `f"harness {name} "`) má `counts[name] == 0`. Zachovej pořadí: filtr před připojením `harness_test_failed` (ten má fix) nebo po – výsledek musí mít konzistentní `counts`.
- `app.py`: docstring u `GET /api/factory/check` a `GET /api/machine/check` doplň o „only actionable findings“. Neměň CLI ani `skill/codes.py`.

### 2. Průvodce (`src/aifactory/guide/*.md`, česky)
Aktualizuj zmínky na nové uspořádání:
- `04-dashboard.md`: menu přepínače (už jen **Přehled**, **Tento počítač**, repa), sekce „Tento počítač“ (kontrola počítače jen s akčními nálezy, sekce Knihovna, Dashboard), sloučit sekci „Knihovna“ do ní; záložky repa bez Nastavení, Factory obsahuje Nastavení repozitáře.
- `03-prvni-spusteni.md` ř. 15–20: Začínáme je na **Přehledu**; ř. 51: skupina „Tento počítač: opravit lokálně“ obsahuje jen nálezy počítače, které plynou z repa, ostatní jsou na Tento počítač.
- `10-knihovna.md` ř. 23, 62, 84, 90: „stránka Knihovna“ → „sekce Knihovna na stránce Tento počítač“; chip vede na `#/setup/library`.
- `08-konfigurace-repa.md`, `02-instalace.md`, `11-pocitac.md`, `12-tym.md`, `15-reseni-problemu.md`: projdi grepem `Nastavení|Tento počítač|Knihovna|repo_installed` a oprav odkazy na zrušenou záložku Nastavení a stránku Knihovna. V `15-reseni-problemu.md` řádek `repo_installed` ponech (CLI), dopiš „v dashboardu se nezobrazuje“.
- Pokud `tests/web/test_web_guide.py` ověřuje odkazy/kotvy, musí dál procházet.

## Změny – frontend (`aifactory/web/src/`)

### 3. Router (`lib/router.ts`)
- `Screen` = `'backlog' | 'runs' | 'review' | 'factory'`; ze `SCREENS` odeber `settings`.
- `parseRoute`: `#/r/<id>/settings[/...]` → `{ page:'repo', screen:'factory', params:['settings'], redirect: repoHref(id,'factory','settings') }`.
- `Page` bez `'library'`. `#/setup` a `#/setup/library` jsou platné (`page:'setup'`, `params:[]` resp. `['library']`, redirect null). `#/library` → `page:'setup'`, `params:['library']`, `redirect:'#/setup/library'`.
- Exportuj `SETUP_HREF = '#/setup'`, `LIBRARY_HREF = '#/setup/library'` a `repoSettingsHref(id)` = `repoHref(id,'factory','settings')`; použij je místo literálů všude níže.
- Aktualizuj hlavičkový komentář.

### 4. Factory: sekce Nastavení repozitáře
- Nový `components/factory/RepoSettings.vue` z logiky `views/SettingsView.vue` (fetch/save, `fieldErrors`, `configStatus.refresh()`, `formKey`, „Uloženo“), bez page paddingu, s `<h2>Nastavení repozitáře</h2>`, intro textem o commitu do base a řádkem „Repozitář: …“ vynech (repo je v hlavičce). Emituje `saved` po úspěšném uložení. `data-test` hodnoty z SettingsView zachovej (`saved`, `error`, `repository` může odpadnout), kořen `data-test="repo-settings"`.
- `views/FactoryView.vue`: vlož `<section ref="settingsSection" data-test="factory-settings">` s `RepoSettings` za `RosterEditor` (před `RepoItems`), jen když `report && report.state !== 'none'` (bez instalace není config.yaml). Na `saved` zavolej `load(true)` (objeví se `config_uncommitted` a uživatel commitne tlačítkem nahoře).
- `watch(params)` rozšiř: `params[0] === 'settings'` → po vykreslení `settingsSection.scrollIntoView(...)` (nextTick; když ještě není report, scrolluj po prvním načtení).
- Smaž `views/SettingsView.vue`, `SettingsView.test.ts`, `SettingsView.spinner.test.ts`; jejich testované chování přenes do `components/factory/RepoSettings.test.ts` (a spinner případ, pokud testuje stav načítání).
- `components/RepoScreen.vue`: odeber `settings: SettingsView` a ikonu `Settings` z map.
- `lib/overview.ts::problems`: `href` přestane mířit na `settings`; problémy `not_installed`/`invalid`/`uncommitted` se řeší na Factory: `repoHref(repo.id, 'factory')`, pro `uncommitted` `repoHref(repo.id,'factory','config_commit')` (stejně jako `lib/readiness.ts`). Uprav `overview.test.ts`.
- Grep `'settings'`, `here('settings'`, `repoHref(..., 'settings'` ve `web/src` (např. `components/backlog/TaskDetail.vue`, `lib/configStatus.ts`, `UncommittedBanner`, `RepoCard`) a přesměruj na `repoSettingsHref` / Factory. Backlog „Nastavení“ projektu/stepu (`ContainerSettings`) se nemění.

### 5. Factory: bez duplicit s Tento počítač
- `FactoryView.vue`: paralelně s `fetchFactoryCheck` načti `fetchMachineCheck()` (chyba se ignoruje → pak se nic nefiltruje). Skupina `local` (přejmenuj na „Tento počítač: potřebné pro toto repo“) obsahuje jen nálezy se `scope === 'machine'` (plus `trace_db_shared`), které **nejsou** v machine checku se stejným `code` a `message`. Nálezy `scope === 'library'` na Factory nejsou; tag „knihovna“ odeber.
- Pokud byly nějaké nálezy odfiltrovány (počet > 0), pod skupinou ukaž jediný řádek s odkazem: „Další nálezy tohoto počítače a knihovny: N · Otevřít Tento počítač“ (`data-test="factory-machine-link"`, href `SETUP_HREF`). Jinak nic.
- Verdikt a počty (`report.counts`) přepočítej z viditelných nálezů, aby odpovídaly seznamu (`ok` = žádný viditelný `error`; když jsou chyby jen mezi odfiltrovanými, verdikt „Factory je v pořádku“ + odkazový řádek). Indexy pro výběr (`selected`) počítej nad viditelným seznamem.
- Skupina bez nálezů se nevykresluje (žádné „Bez nálezů“); když nejsou žádné nálezy, stačí verdikt.
- `SEVERITY_TEXT`/`sev-info` ponech (akční info nálezy jako `remote_base_missing`, `roles_full_copy` dál existují).

### 6. Tento počítač = počítač + knihovna + dashboard
- Nový `components/setup/LibrarySection.vue` z `views/LibraryView.vue` (celá logika: sync, remote connect, PR, reseed, import, záložky, detail, kopie rep, přesun). Změny:
  - kořen `<section data-test="library" id="library">`, nadpis `<h2>Knihovna</h2>`, tlačítka Reseed/Import v hlavičce sekce,
  - když knihovna neexistuje: místo odkazu „Nastavit na tomto počítači“ obsahuje formulář založení ze SetupView (`library-url`, `library-clone`, `library-init`, `ConfirmDialog` s `PlanView`, `preview/apply`), tj. přesun z `SetupView`,
  - nahoře v sekci nálezy se `scope === 'library'` z machine checku (prop `findings: CheckFinding[]`), stejné vykreslení jako nálezy počítače (komponenta níže),
  - emituje `changed` po každé zápisové akci (init/clone/pull/push/import/seed/move) → SetupView znovu načte kontrolu (`load(true)`) a pošle `window.dispatchEvent(new Event('factory-applied'))`, aby se obnovil chip knihovny a readiness.
- Vytáhni vykreslení nálezu do `components/setup/MachineFinding.vue` (severity · code, zpráva, fix + tlačítko Kopírovat, `data-test="machine-finding"`, `copy-fix`); fallback text „Zkontroluj nastavení prostředí podle nálezu.“ odstraň (nálezy bez fixu server už neposílá).
- `views/SetupView.vue` přepiš podle vzoru FactoryView:
  1. hlavička `<h1>Tento počítač</h1>` + „Znovu zkontrolovat“ (`machine-refresh`),
  2. souhrn: verdikt „Počítač je v pořádku“ / „N chyb, M varování“ (`data-test="machine-verdict"`), „Zkontrolováno: … (z mezipaměti)“,
  3. nálezy se `scope !== 'library'` ve skupinách `FINDING_GROUPS` bez `'Knihovna'`, vykreslit jen neprázdné skupiny,
  4. `<LibrarySection :findings="libraryFindings" @changed="..." />`,
  5. `<DashboardSettings />` v sekci „Dashboard“.
  - odstranit: `GettingStarted`, text „HAIFA je spuštěná…“, `harness-counts`, starý blok knihovny (`library-path`, `library-sync-state`, `library-prs`, `library-pull`, `library-push`, „Otevřít knihovnu“), patičku s `add-repo-link`.
  - `route params[0] === 'library'` → po načtení scroll na `#library` sekci (`useRouteParams`, nextTick).
- `lib/library.ts`: `FINDING_GROUPS` – `'Knihovna'` může zůstat, ale SetupView ji pro skupiny počítače vynechá; nebo zaveď `MACHINE_GROUPS`. Uprav související test.
- Smaž `views/LibraryView.vue` a `LibraryView.test.ts` (testy přesuň do `components/setup/LibrarySection.test.ts`). `views/library.css` přesuň/importuj tak, aby styly `.global-page` platily (SetupView ji dál importuje; LibrarySection používá stejné třídy uvnitř `.global-page`).
- `App.vue`: odeber `LibraryView` a větev `viewPage === 'library'`; titulek jen `'setup'` → „Tento počítač · HAIFA“.
- `components/RepoSwitcher.vue`: odeber položku `switch-library` a větev labelu `library`; `switch-setup` zůstává („Tento počítač“).
- `components/LibraryChip.vue`: oba stavy odkazují na `LIBRARY_HREF` (`#/setup/library`).
- `lib/gettingStarted.ts`: krok `library` → `LIBRARY_HREF`; `machine`/`harnesses` dál `SETUP_HREF`. Komentář „GettingStarted on the overview and on #/setup“ → jen overview (i v `GettingStarted.vue`).
- `lib/readiness.ts`: `'#/setup'` → `SETUP_HREF` (beze změny chování).

### 7. Ostatní informační hlášky v dashboardu
Projdi ještě `OverviewView.vue`, `RepoCard.vue`, `OverviewReadiness.vue`, `ProblemsView.vue`: readiness bere jen `error|warning` (OK). Pokud najdeš další hlášku, se kterou uživatel nic neudělá, odstraň ji a zapiš do dokumentace; jinak nic dalšího neměň (stavové údaje jako base, verze, napřed/pozadu nejsou „nálezy“ a zůstávají).

## Testy

Backend (`aifactory/tests/web/`):
- `test_web_factory.py`: nový test, že `GET /api/repos/<id>/factory/check` na nainstalovaném repu nevrací `repo_installed`, `counts.info` odpovídá vráceným nálezům a `ok` je beze změny. Uprav existující asserty, které `repo_installed` nebo počty `info` čekají.
- `test_web_machine.py`: test, že info `harness_missing` pro harness bez rep zmizí a pro harness, který registrované repo používá, zůstane; `hosting_skipped` se s `offline=1` nevrací.
- `tests/check/*` se nemění (CLI dál hlásí `repo_installed`).
- `tests/web/test_web_guide.py` musí procházet po úpravě průvodce.

Frontend (vitest):
- `lib/router.test.ts`: `#/r/x/settings` → redirect `#/r/x/factory/settings`; `#/library` → redirect `#/setup/library`; `#/setup/library` platná; `SCREENS` bez settings (smyčka na ř. 71).
- `views/FactoryView.test.ts`: nálezy knihovny se nezobrazují; machine nález shodný s machine checkem se nezobrazí a místo něj je `factory-machine-link` s počtem; repo-specifický machine nález zůstane; prázdná skupina se nevykreslí; sekce `factory-settings` existuje, uložení zavolá znovu kontrolu; `#/r/x/factory/settings` scrolluje (stačí ověřit volání `scrollIntoView` mocku).
- `components/factory/RepoSettings.test.ts`: převzaté testy SettingsView.
- `views/SetupView.test.ts`: verdikt, jen neprázdné skupiny, žádný `harness-counts`, `GettingStarted`, `add-repo-link`; nálezy knihovny jsou v `[data-test="library"]`; init/clone knihovny funguje ze sekce.
- `components/setup/LibrarySection.test.ts`: převzaté testy LibraryView (data-testy ponechané).
- `LibraryChip.test.ts`, `GettingStarted.test.ts`, `gettingStarted.test.ts`, `OverviewReadiness.test.ts`, `overview.test.ts`, `App.test.ts` (ř. ~407 a ~490, menu přepínače, titulek): nové odkazy.
- `noNativeUi.test.ts` a další, které vyjmenovávají views, uprav při mazání souborů.

E2E (`aifactory/tests/e2e/`):
- `test_library_browser.py`: po kliknutí na readiness odkaz `#/setup`, `h1` „Tento počítač“, init knihovny, `library-path` → nahraď kontrolou, že sekce `[data-test="library"]` ukazuje položky; místo `switch-library` klikni na chip knihovny a čekej URL `#/setup/library`.
- `test_f3_browser.py` (ř. ~503 „Nastavení panel“) a ostatní: grep `settings`, `Nastavení`, `switch-library`, `#/library`, `library-pull` a uprav.

## Ověření

Z kořene worktree:
1. `just lint`, `just typecheck`.
2. `just pytest tests/web/test_web_factory.py tests/web/test_web_machine.py tests/web/test_web_guide.py tests/check`.
3. `just web-test` (vue-tsc + vitest).
4. `just web-build` – `aifactory/src/aifactory/web/static` je commitnutý a musí odpovídat zdroji.
5. `just pytest tests/e2e/test_library_browser.py -n0` a `just pytest tests/e2e/test_factory_install_browser.py -n0` (a `test_f3_browser.py`, pokud se měnil).
6. Grep kontrola, že nic nevede naprázdno: `grep -rn "'#/library'\|\"#/library\"\|'settings')" aifactory/web/src` vrací jen router (redirect) a testy redirectu.

## Dokumentace

Do `factory/docs/HAIFA/REFINEMENT-upravy-opravy-a-vylepseni-z-praxe/HAIFA-REFINEMENT-T24-sloucit-stranky-factory-tento-pocitac-a.md` (česky) zapiš: rozhodnutí o uspořádání a proč (tabulka výše zkráceně), mapu „stará funkce → nové místo“, seznam výslovně odstraněných prvků se zdůvodněním, pravidlo pro akční nálezy (fix/action, `hosting_skipped`, nepotřebný `harness_missing`) a redirecty (`#/r/<id>/settings`, `#/library`). `docs/decisions.md` je mimo povolené cesty – neměnit; případnou potřebu zmínit v dokumentaci tasku.
