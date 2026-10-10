# HAIFA-S01-T20: Přidání repozitáře, správa repozitářů a kontrola factory v UI

## Cíl

Dashboard dostane:

1. průvodce přidáním repa na `#/repos/add` (cesta s našeptáváním, prohlížeč složek, systémový dialog, karta z inspect, Přidat),
2. stránku `#/repos` s tabulkou, odebráním přes vlastní modál, portem dashboardu a cestou k registru,
3. záložku Factory `#/r/<id>/factory` s výsledkem `factory check` a stavem onboardingu,
4. `factory obs --repo` otevře Factory místo Backlogu, když repo není `ok`.

**Backend API už existuje** (HAIFA-S01-T17 a dřívější). Tento task je hlavně frontend. Na backendu jsou jen dvě malé změny: fragment v `factory obs` a pole `manifest` a `version` v odpovědi check.

## Existující API (kontrakt, nemění se)

Všechno vrací obálku `{ok, data, error, warnings}`. Globální endpointy jsou pod `/api`, endpointy repa pod `/api/repos/<id>`.

| Endpoint | Tělo / dotaz | Data |
|---|---|---|
| `GET /api/repos` | | `{repos: RepoItem[], home}`; `RepoItem = {id, name, path, added_at, status: ok\|uncommitted\|not_installed\|missing\|not_git, factory}` |
| `POST /api/repos` | `{path}` | `{repo: RepoItem, created}` (201 při přidání, 200 když už tam repo je) |
| `POST /api/repos/inspect` | `{path}` (absolutní nebo `~…`) | viz níže; relativní cesta vrací 4xx `usage_error` |
| `DELETE /api/repos/<id>` | bez těla | `{removed: entry}`; `unknown_repo` 404 |
| `GET /api/dashboard/settings` | | `{port, home, registry, restart_required}` |
| `POST /api/dashboard/settings` | `{port}` | stejná data; špatný port dá HTTP 422 `invalid_value` s issue `id: "port"` |
| `GET /api/fs/dirs?path=` | absolutní cesta, výchozí je domov | `{path, parent, entries: [{name, path, is_git, has_factory}], truncated}`; chyby `outside_home` 403, `path_not_found`, `not_a_directory`, `permission_denied`, `invalid_value` (relativní cesta, `~` server **neexpanduje**) |
| `GET /api/fs/pick` | | `{available: boolean}` |
| `POST /api/fs/pick` | bez těla | `{path}` nebo `{cancelled: true}`; chyby `picker_unavailable` 503, `picker_busy` 409, `picker_timeout` 504, `picker_failed` 502 |
| `GET /api/repos/<id>/factory/check?offline=&fresh=1` | | report (viz níže); **když jsou nálezy typu error, přijde `ok:false`, `error.code="checks_failed"` a report je přesto v `data`** |

Odpověď inspect (`aifactory/src/aifactory/web/repos.py::inspect_repo`):
```
{ path, root|null, subdir|null, registered: <repo id>|null, addable: bool,
  problem: {code, message, ...data}|null,   // data: linked_worktree → main_checkout; trace_db_shared → repo
  branch|null, remote: {name:"origin", url}|null, trace_db|null,
  factory: { repo, base, commit, state: none|working_tree|sssf|pre_library|onboarded, action,
             sssf_leftover, alternate_rosters, rosters, onboarding|null, library|null, manifest_error } | null }
```
`onboarding = {source: init|sssf|pre_library, source_commit|null, at, by|null, factory, library_commit|null}`.

Kódy `problem.code`: `path_not_found`, `not_a_directory`, `not_git`, `run_worktree`, `bare_repo`, `linked_worktree`, `no_commits`, `trace_db_shared`. Poznámka: `registered` se plní ještě před kontrolou commitu. Když je zároveň vyplněný `problem`, má přednost problém.

Report check (`check/model.py::CheckReport.to_json` + `checked_at`, `cached`):
```
{ in_repo, repo, state, action, sssf_leftover, alternate_rosters, onboarding, base, commit, remote,
  ahead, behind, offline, ok, counts:{error,warning,info}, groups, backlog,
  findings:[{code, scope: repo|machine|library, severity: error|warning|info, message, fix|null, action|null}],
  checked_at, cached }
```

## Backend (Python)

### B1. `factory obs --repo` otevře Factory, když repo není `ok`
Soubor `aifactory/src/aifactory/cli.py`, funkce `_obs`, kolem `fragment = f"#/r/{entry.id}/backlog"`:
```python
from aifactory.web.repos import register_repo, repo_status
...
screen = "backlog" if repo_status(entry)["status"] == "ok" else "factory"
fragment = f"#/r/{entry.id}/{screen}"
```
Upravit `--repo` help a docstring, pokud tam je zmínka o backlogu.

Testy v `aifactory/tests/web/test_obs_cli.py`: stávající testy používají `init_repo` (stav `none`, tedy `not_installed`), takže teď čekají `#/r/<id>/factory`. Uprav jejich asserty (řádky kolem 117, 203 a 239). Přidej test, kde repo projde `onboard(root)` z `multi_repo` a fragment je `#/r/<id>/backlog`. Pokud onboardované repo z helperu nevyjde `ok`, ověř to přes `repo_status` a test podle toho uprav. Přidej i test s `--json` a už běžícím dashboardem (`reused`), pokud takový test existuje, aby URL obsahovala `factory`.

### B2. Manifest a verze v odpovědi check
Soubor `aifactory/src/aifactory/web/factory.py::check_view`: do `data` přidej
```python
"manifest": {"format": m.format, "written_by": m.written_by} | None,
"manifest_error": str | None,
"version": aifactory.__version__,
```
Manifest se čte z base přes `aifactory.onboard.state.repo_state(root)` (pole `.manifest`, `.manifest_error`). Obal to `try/except (ConfigError, OSError)`, při chybě nastav `manifest=None` a `manifest_error=None`, stejně jako `repos.py::_factory`. Počítej to při každém volání, nedávej to do cache: jsou to levné čtení gitu a cache se pak nemusí měnit. Doplň docstring v `web/app.py` (odstavec Factory tab). Test v `aifactory/tests/web/test_web_factory.py`: onboardované repo vrací `manifest.format`, `manifest.written_by` a `version == __version__`. Repo bez manifestu (`pre_library`) vrací `manifest is None`.

Nic dalšího se na backendu nemění. Přidání ani odebrání nic nezapíše do repa (to už platí: registr je v `HAIFA_HOME/dashboard.yaml`).

## Frontend (`aifactory/web/src/`)

Žádná nová závislost. Ikony bereš z `lucide-vue-next` (`Factory`, `FolderOpen`, `Trash2`, `RefreshCw`, …). Dialogy dělej jen přes vlastní `ConfirmDialog` nebo vlastní modál. `noNativeUi.test.ts` zakazuje `window.confirm`, `alert`, `prompt`, atribut `title=` a `<select>`. Texty jsou česky. Pro testy přidej atributy `data-test`.

### F1. Router (`lib/router.ts`)
- `Screen` = `'backlog' | 'runs' | 'review' | 'factory' | 'settings'`. Do `SCREENS` přidej `{ id: 'factory', label: 'Factory' }` před `settings`.
- Komentář hlavičky doplň o `factory`.
- `App.vue` `ICONS`: přidej `factory: Factory` (lucide). `RepoScreen.vue` `VIEWS`: přidej `factory: FactoryView`.
- `router.test.ts`: `#/r/x/factory` se naparsuje na screen `factory` bez redirectu a `repoHref('x','factory')` vrátí `#/r/x/factory`.

### F2. API (`lib/api.ts`)
Přidej typy a funkce:
- `deleteGlobal<T>(path)` = `fetch('/api'+path, {method:'DELETE'})` přes `readEnvelope`. Bez těla a bez Content-Type, guard to propustí.
- `RepoFactory` (typ `factory` z inspect a `RepoItem.factory`), `Onboarding`, `RepoProblem {code, message, main_checkout?, repo?}`, `InspectResult`.
- `inspectRepo(path)` → `postGlobal('/repos/inspect', {path})`; `addRepo(path)` → `postGlobal<{repo: RepoItem; created: boolean}>('/repos', {path})`; `removeRepo(id)` → `deleteGlobal('/repos/'+encodeURIComponent(id))`.
- `FsDirs`, `FsEntry`; `fetchDirs(path?: string)` → `getGlobal('/fs/dirs' + (path ? '?path='+encodeURIComponent(path) : ''))`.
- `fetchPickStatus()` → `{available}`; `pickFolder()` → `postGlobal<{path?: string; cancelled?: boolean}>('/fs/pick')`.
- `DashboardSettings {port, home, registry, restart_required}`; `fetchDashboardSettings()`, `saveDashboardSettings(port: number)`.
- `CheckFinding`, `FactoryCheck` (report výše plus `manifest`, `manifest_error`, `version`); `fetchFactoryCheck({fresh}: {fresh?: boolean} = {})` → `apiBase() + '/factory/check' + (fresh ? '?fresh=1' : '')`. **Vrací `data` i při `ok:false` s `error.code === 'checks_failed'`.** Udělej na to malý helper `readReport<T>(response, tolerated: string[])`, nebo rozšiř `readEnvelope` o volitelný parametr. Jiné chyby vyhazuje jako `ApiError` stejně jako `readEnvelope`.
- `api.test.ts`: `fetchFactoryCheck` vrátí data při `checks_failed`, při `not_a_repository` vyhodí chybu, `removeRepo` pošle `DELETE /api/repos/<id>`.

### F3. Sdílené texty a helpery (`lib/repos.ts`, plus nový `lib/addRepo.ts`)
`lib/repos.ts`:
- `ADD_REPO_HINT` přepiš: repo se přidá v dashboardu (tlačítko Přidat repozitář), z terminálu jde dál `factory obs --repo <cesta>`. `ADD_REPO_COMMAND` ponech.
- `REPO_STATUS_TEXT` (přesuň sem `STATUS_TEXT` z `RepoList.vue`, ať se nemnoží).
- `FACTORY_STATE_TEXT: Record<state,string>`: `none` „bez factory“, `working_tree` „konfigurace jen v pracovním stromu (necommitnutá)“, `sssf` „instalace sssf“, `pre_library` „factory z doby před knihovnou“, `onboarded` „onboardováno“.
- `ONBOARDING_SOURCE_TEXT`: `init` „factory init“, `sssf` „převod ze sssf“, `pre_library` „factory z doby před knihovnou“.
- `removeConfirm(repo: {name, path})` vrátí `ConfirmOptions`: `title: \`Odebrat ${name} z dashboardu?\``, `message: \`Ve složce ${path} se nic nezmění: .factory/, backlog, trace DB, worktree a větve zůstanou. Běžící běhy doběhnou.\``, `confirmLabel: 'Odebrat'`, `tone: 'danger'`. Na tenhle text míří test, musí sedět přesně.

`lib/addRepo.ts` (čisté funkce, unit testy v `lib/addRepo.test.ts`):
- `expandHome(value, home)`: `~` nahradí za `home` a `~/x` za `home + '/x'`. Jinak vrátí hodnotu beze změny.
- `splitForSuggest(value)`: vrátí `{dir, prefix}`, rozdělené za posledním `/`. Pro `~/co` dá `{dir:'~/', prefix:'co'}`, pro `/Users/a/` dá `{dir:'/Users/a/', prefix:''}`. Hodnota bez `/` dá `null`.
- `filterEntries(entries, prefix, limit=12)`: prefix bez ohledu na velikost písmen, zachová pořadí ze serveru.
- `PROBLEM_TEXT: Record<code, (p, inspect) => string>`:
  - `path_not_found` „Složka neexistuje.“
  - `not_a_directory` „Cesta nevede ke složce.“
  - `not_git` „Složka není v git repozitáři. HAIFA nespouští git init.“
  - `linked_worktree` „Složka je propojený worktree. Přidej hlavní checkout {main_checkout}.“
  - `run_worktree` „Složka je worktree běhu úkolu (.factory/worktrees/), ne repozitář.“
  - `bare_repo` „Holé repo bez pracovního stromu nejde přidat.“
  - `no_commits` „Repo ještě nemá žádný commit. Nejdřív něco commitni.“
  - `trace_db_shared` „Trace DB {trace_db} už používá registrované repo {repo}.“
  - Pro neznámý kód se zobrazí `message` ze serveru.

  Chyba `ApiError` `usage_error` z inspect, třeba u relativní cesty, se ukáže jako „Zadej absolutní cestu nebo cestu začínající ~.“

### F4. Průvodce `#/repos/add` (`views/ReposAddView.vue` + `components/repos/`)
`App.vue`: místo `EmptyScreen` pro `repos-add` renderuj `<ReposAddView :repos="repos" @added="onAdded" />`.
`onAdded(id)` nejdřív udělá `await loadRepos()` a pak nastaví `window.location.hash = repoHref(id, 'factory')`. Bez toho by po navigaci na chvíli blikla obrazovka „Repo … v dashboardu není“.

**Krok Složka** (nadpis „Přidat repozitář“, krok „1 Složka“):
- `components/repos/PathField.vue`: `<input data-test="add-path">` předvyplněné `~/` s fokusem. Pod ním dropdown `data-test="path-suggestions"`, položky `data-test="path-suggestion"` se jménem a štítky `git` (když `is_git`) a `factory` (když `has_factory`), štítky mají `data-test="tag-git"` a `data-test="tag-factory"`.
  - Domov zjistí `fetchDirs()` bez cesty (`data.path`) při mountu. Ve view se uloží a předá do pole a prohlížeče.
  - Při psaní (debounce asi 150 ms, generační čítač proti zastaralým odpovědím, cache podle adresáře) spočítá `splitForSuggest`, zavolá `fetchDirs(expandHome(dir, home))` a vyfiltruje `filterEntries`. Každá chyba (`outside_home`, `path_not_found`, …) jen schová našeptávání, nic nehlásí.
  - Šipky ↑↓ vybírají, Enter nebo klik na položku dosadí `dir + name + '/'` (ve tvaru, jak ho uživatel napsal, tedy s `~/`) a načte podsložky. Esc a blur zavřou dropdown. Enter bez vybrané položky spustí Zkontrolovat (`emit('submit')`).
- Tlačítka: `Zkontrolovat` (`data-test="add-inspect"`), `Procházet…` (`data-test="add-browse"`) a `Vybrat ve Finderu…` (`data-test="add-pick"`). Poslední se ukáže **jen když** `fetchPickStatus()` vrátí `available: true`. Při chybě nebo `false` se neukáže.
- `Vybrat ve Finderu…` zavolá `pickFolder()`. Na `{path}` dosadí cestu a spustí inspect, na `{cancelled}` neudělá nic. Chyby ukáže jako text, např. `picker_busy` „Dialog výběru složky už je otevřený.“, jinak `message`. Během čekání je tlačítko disabled se Spinnerem.
- `components/repos/FolderBrowser.vue`: vlastní modál (teleport do body, Esc zavře, `role="dialog"`, styl podle `ConfirmDialog`), `data-test="folder-browser"`. Začíná v domově (`fetchDirs()`), ukazuje aktuální cestu, „Nahoru“ (když `parent !== null`) a seznam podsložek se štítky git a factory. Klik na složku do ní vstoupí, „Vybrat tuto složku“ (`data-test="browser-choose"`) vrátí `path`. Pokud je `truncated`, ukáže „Zobrazeno prvních 500 složek“. Chyby jako text. Po výběru se cesta dosadí do pole a spustí se inspect.
- `Zkontrolovat` zavolá `inspectRepo(value.trim())`. `~` se pošle beze změny, server ho expanduje. Během dotazu se ukáže Spinner. Nový inspect zahodí starou kartu.

**Karta repa** (`components/repos/InspectCard.vue`, `data-test="inspect-card"`, atribut `data-state` se stavem factory nebo `problem`):
- Řádky: Kořen repozitáře (`root`), u `subdir` text „Použije se kořen repozitáře {root}.“ (`data-test="inspect-subdir"`), Větev (`branch`), Remote (`remote.url` nebo „bez remote“), Factory (`FACTORY_STATE_TEXT[factory.state]`, `data-test="inspect-state"`) a Trace DB (`trace_db`).
- **Odmítnutí** (`problem !== null`): `data-test="inspect-problem"` s důvodem z `PROBLEM_TEXT`, **žádné tlačítko Přidat**. U `linked_worktree` s `main_checkout` je tlačítko „Použít hlavní checkout“ (`data-test="use-main-checkout"`), které dosadí cestu a spustí inspect znovu. Řádky, které jsou `null`, se nezobrazí.
- **Registrované** (`registered !== null` a bez problému): „Repo už je v dashboardu.“ a odkaz Otevřít (`data-test="inspect-open"`, `repoHref(registered, 'backlog')`), bez Přidat.
- **`pre_library`, `working_tree`, `onboarded`** (`addable` a nic z výše uvedeného): tlačítko Přidat (`data-test="inspect-add"`).
  - U `onboarded` blok `data-test="inspect-onboarding"`: „Onboardoval {by ?? 'neznámo'} {fmt(at)} z {ONBOARDING_SOURCE_TEXT[source]}“ (plus `source_commit` zkráceně, když je, a `factory` verze). Formátování data vezmi z `lib/format.ts`.
  - U `working_tree` poznámka, že konfigurace není commitnutá a běhy ji neuvidí. Dořešit to jde v záložce Factory nebo přes `factory config commit`.
  - Přidat zavolá `addRepo(root)` a pak `emit('added', repo.id)`. Chyba (např. `trace_db_shared` při souběhu) se ukáže na kartě textem z `PROBLEM_TEXT`.
- **`none`**: text „V repu není factory. Nainstaluj ji z terminálu a pak repo přidej:“ a dva bloky kódu `factory init --dry-run --repo {root}` a `factory init --commit --repo {root}` (`data-test="inspect-init"`), bez Přidat.
- **`sssf`**: „V repu je konfigurace sssf. Vytěží se jednou příkazem:“ a kód `factory onboard --repo {root} --dry-run` (`data-test="inspect-onboard"`), bez Přidat.
- `factory === null` bez problému: „Stav factory se nepodařilo zjistit.“, bez Přidat.

Odkaz zpět na `#/repos`.

### F5. Stránka `#/repos` (`views/ReposView.vue`, `components/RepoList.vue`, `components/repos/DashboardSettings.vue`)
- Hlavička „Repozitáře“ a tlačítko-odkaz `Přidat repozitář` (`data-test="add-repo-link"`, `REPOS_ADD_HREF`).
- `RepoList.vue` udělej jako tabulku `<table data-test="repo-table">` se sloupci Název, Cesta, Stav, Přidáno (`added_at` přes formátovač data) a akce. Řádek má `data-test="repo-row"` a `:data-repo="id"`. Akce jsou `Otevřít` (`data-test="repo-open"`, `repoHref(id, status === 'ok' ? 'backlog' : 'factory')`) a `Odebrat z dashboardu` (`data-test="repo-remove"`, emit `remove`). Ponech `data-test` `repo-name`, `repo-path` a `repo-status`. Pokud na `overview-repo` nebo `repo-backlog` míří existující testy (vitest i e2e: `grep -rn "repo-backlog\|overview-repo" aifactory/web/src aifactory/tests`), uprav je.
- Odebrání: `useConfirm()` + `<ConfirmDialog v-bind="dialog" @confirm="confirm" @cancel="cancel" />` s `removeConfirm(repo)`. Po potvrzení `removeRepo(id)`, pak `emit('changed')`. App na to zavolá `reloadRepos`. Při chybě ukaž text. Chyba `unknown_repo` znamená, že repo už odebral někdo jiný, takže taky jen `changed`. Když se odebírá právě otevřené repo (`id === repoId`), přejdi na `OVERVIEW_HREF`. Logiku dej do composable `useRemoveRepo(onRemoved)` v `lib/repos.ts`, ať ji sdílí F6 a F7.
- Prázdný stav (`repos.length === 0`): `EmptyScreen` „Žádné repozitáře“ s hintem a ve slotu odkaz `Přidat repozitář` (`data-test="add-repo-link"`). Sekce Dashboard (port, registr) se ukáže i tehdy.
- `DashboardSettings.vue` (`data-test="dashboard-settings"`): načte `fetchDashboardSettings()` a zobrazí:
  - pole Port (`<input type="number" min=1 max=65535 data-test="dash-port">`) s tlačítkem Uložit (`data-test="dash-port-save"`, disabled bez změny nebo mimo rozsah),
  - text „Port platí po restartu dashboardu.“,
  - po uložení s `restart_required` hlášku „Uloženo. Dashboard teď běží na jiném portu, nový port {port} platí po restartu.“ (`data-test="dash-restart-note"`),
  - u 422 text z `ApiError.issues[0].message` nebo `message` (`data-test="dash-port-error"`),
  - Registr: `registry` (`data-test="dash-registry"`) mono a Domov: `home`.

### F6. Chybějící složka a odebrání otevřeného repa
- `App.vue`: na stránce repa, když `currentRepo?.status === 'missing'`, se místo `RepoScreen` vykreslí `EmptyScreen` „Složka repozitáře {name} chybí“ s hintem „{path} neexistuje. Repo můžeš odebrat z dashboardu.“ a ve slotu tlačítkem `Odebrat z dashboardu` (`data-test="missing-remove"`). Tlačítko jde přes `useRemoveRepo` a po odebrání vede na `OVERVIEW_HREF` a znovu načte repa.
- Přehled (`OverviewView.vue`, `components/overview/RepoCard.vue`): karta se stavem `missing` dostane tlačítko `Odebrat z dashboardu` (`data-test="card-remove"`) se stejným modálem. Po odebrání se přehled obnoví a pošle `changed` do App (`reloadRepos`). Prázdný stav přehledu dostane ve slotu odkaz `Přidat repozitář` (`data-test="add-repo-link"`).

### F7. Záložka Factory (`views/FactoryView.vue`)
- Při mountu `fetchFactoryCheck()`, „Znovu zkontrolovat“ (`data-test="factory-recheck"`) zavolá `fetchFactoryCheck({fresh: true})`. Generační čítač, Spinner při načítání (`data-test="factory-loading"`) a chyba jako text (`data-test="factory-error"`, `isDbBusy` není potřeba).
- Hlavička (`data-test="factory-summary"`):
  - celkový stav (`ok` → „Factory je v pořádku“, jinak „{counts.error} chyb, {counts.warning} varování“),
  - Stav repa: `FACTORY_STATE_TEXT[state]` (`data-test="factory-state"`),
  - Manifest: „formát {manifest.format}, zapsal {manifest.written_by}“, bez manifestu „bez manifestu“ (`data-test="factory-manifest"`), u `manifest_error` text chyby,
  - Verze balíčku: `version` (`data-test="factory-version"`),
  - Base `base`@`commit` zkráceně, ahead/behind, když nejsou null,
  - u onboardovaného repa blok onboardingu (kdo, kdy, z čeho, stejné texty jako v F4),
  - zkontrolováno `checked_at` (z cache: „(z mezipaměti)“).
- Nálezy ve dvou skupinách:
  - „Repozitář: opravit a commitnout“ (`data-test="findings-repo"`, scope `repo`),
  - „Tento počítač: opravit lokálně“ (`data-test="findings-local"`, scope `machine` a `library`; u `library` štítek „knihovna“).

  Položka (`data-test="finding"`, `data-severity`) má štítek závažnosti (chyba, varování, info), `code` mono, `message` a `fix` („Oprava: …“). Prázdná skupina ukáže „Bez nálezů“. Řazení: error, warning, info. Akce oprav (M14, O5) **nejsou** v rozsahu, tlačítka install, update a commit nepřidávej.
- `sssf_leftover` a `alternate_rosters` ukaž jako poznámku, když jsou true.

### F8. Build
`just web-build` (bun) přegeneruje `aifactory/src/aifactory/web/static/` (staré hashované assety zmizí díky `emptyOutDir`). Commitni výsledek.

## Testy

### Vitest (nové a upravené soubory vedle komponent; fetch mock jako v `App.test.ts` (`vi.stubGlobal('fetch', …)`), modál přes `test/modal.ts` (`answerDialog`, `openDialog`))
- `lib/addRepo.test.ts`: `expandHome`, `splitForSuggest`, `filterEntries`.
- `views/ReposAddView.test.ts`:
  - stav `none` ukáže oba příkazy `factory init` a žádné `inspect-add`,
  - `sssf` ukáže `factory onboard --repo <root> --dry-run` a žádné Přidat,
  - `pre_library` a `working_tree` ukážou Přidat. Klik pošle `POST /api/repos` s `{path: root}` a emituje `added` s id,
  - `onboarded` ukáže kdo, kdy a z čeho a Přidat,
  - `registered` ukáže Otevřít s odkazem a žádné Přidat,
  - každý `problem.code` ukáže svůj důvod a žádné Přidat (`not_git` obsahuje „HAIFA nespouští git init“),
  - `linked_worktree` s tlačítkem hlavního checkoutu znovu volá inspect s `main_checkout`,
  - `subdir` ukáže „Použije se kořen repozitáře …“,
  - `usage_error` ukáže text,
  - pole je předvyplněné `~/`,
  - našeptávání: psaní `~/co` zavolá `/api/fs/dirs?path=<home>/` a ukáže jen položky začínající `co` se štítky git a factory. Výběr položky dosadí `~/code/`. Chyba `outside_home` nic neukáže,
  - viditelnost tlačítka Finder (`available` true ukáže, false ani chyba neukážou). Pick s cestou spustí inspect, `cancelled` nic,
  - prohlížeč složek: otevře se v domově, vstoupí do složky, Vybrat dosadí cestu.
- `views/ReposView.test.ts`:
  - tabulka (název, cesta, stav, přidáno),
  - Odebrat otevře modál s přesným textem z `removeConfirm`. Zrušit nepošle DELETE, potvrdit pošle `DELETE /api/repos/<id>` a emituje `changed`,
  - prázdný stav má `add-repo-link` s `#/repos/add`,
  - port: zobrazí hodnotu a registr, uložení pošle `POST /api/dashboard/settings {port}`, `restart_required` ukáže hlášku, 422 ukáže chybu.
- `views/FactoryView.test.ts`:
  - formát a `written_by`, nebo „bez manifestu“,
  - verze,
  - dvě skupiny podle scope (`library` ve skupině lokálně),
  - `checks_failed` obálka se vykreslí jako report,
  - Znovu zkontrolovat zavolá `…/factory/check?fresh=1`.
- `App.test.ts`:
  - `#/repos/add` vykreslí průvodce,
  - po `added` se načtou repa a hash je `#/r/<id>/factory`,
  - repo se `status: 'missing'` ukáže `missing-remove`, potvrzení pošle DELETE a vede na `#/overview`,
  - navigace má záložku Factory.
- `router.test.ts`, `api.test.ts` viz výše. Uprav existující testy, které rozbije změna `RepoList` nebo `ADD_REPO_HINT` (`grep -rn "ADD_REPO\|repo-backlog\|no-repos" aifactory/web/src`).

### Python
- `tests/web/test_obs_cli.py` (B1), `tests/web/test_web_factory.py` (B2).

### Prohlížečový test (`aifactory/tests/e2e/test_f3_browser.py`, nový test, použije fixtury `server`, `page`, `net`)
`test_add_and_remove_repo_in_browser(page, server, net, tmp_path)`:
1. `second = make_f3_repo(tmp_path / "second-repo")` (factory je commitnutá, stav `pre_library` nebo `onboarded`, obojí jde přidat). Ulož `head = git(second, "rev-parse", "HEAD")`.
2. Kontrola factory na serveru online by volala `claude`, `gh` a další nástroje a test nesmí sahat na síť ani na tripwire. Proto zaregistruj `page.route("**/api/repos/*/factory/check*", …)`, který vrátí kanonický report (`ok: true`, jeden nález `machine` a `manifest: null`, `version`), a zaznamenej, že se zavolal.
3. `page.goto("/#/repos/add")`. Do `[data-test=add-path]` napiš `str(second)` přes `fill`, stiskni Escape (zavře našeptávání; tmp mimo domov ho stejně nedá), klikni `add-inspect`. Ověř `inspect-card` se stavem (ne `problem`) a klikni `inspect-add` (timeout `SERVER_TIMEOUT_MS`).
4. `expect(page).to_have_url(re.compile(r"#/r/second-repo/factory$"))` (id ber z registru, `registered_id(server.home, second)` z `f3_repo`). Ověř viditelné `findings-local`, tedy že se kontrola spustila sama. Route z kroku 2 se zavolala.
5. `page.goto("/#/repos")`. V řádku `[data-test=repo-row][data-repo=<id>]` klikni `repo-remove`. Modál `[data-test=confirm-dialog]` obsahuje „Odebrat … z dashboardu?“ a „Ve složce“. Klikni `confirm-ok`. Řádek zmizí, řádek původního repa zůstane.
6. Registr `server.home / "dashboard.yaml"` už nemá `second`. `git(second, "status", "--porcelain") == ""` a HEAD je `head`, tedy repo zůstalo nezměněné. `net.aborted == []`.

Test nesmí volat model ani síť (`only_local` route už platí).

## Ověření
```bash
just web-build          # static build
just test               # web-test (vue-tsc + vitest) + pytest
just typecheck
just lint
just e2e
```
Všechny musí skončit s exit 0.

## Mimo rozsah
Instalace, aktualizace a commit konfigurace z UI (M14), onboarding a převzetí v UI (O5), přejmenování repa, Windows. Mimo rozsah jsou i změny `vendor/`, `prototype/` a `.factory/`.
