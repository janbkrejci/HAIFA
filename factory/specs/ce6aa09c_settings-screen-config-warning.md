# Plán: obrazovka Nastavení a varování na necommitnutou konfiguraci (BACKLOG 3.6, D4)

## Cíl

1. Obrazovka **Nastavení** (`#/settings`) s formulářem:
   - sdílené hodnoty v `.factory/config.yaml`: `workdir`, `backlog_dir`, `specs_dir`, `docs_dir`,
     `worktrees_dir`, `base`, `git_provider`, `merge_strategy`, `test_command`, `protected_files`;
   - lokální hodnoty v `.factory/local.yaml`: `port`, `trace_db`.
2. Uložení hodnoty validuje. Při chybě se nic nezapíše a UI ukáže chybu u konkrétního pole.
3. Na **všech obrazovkách** pruh s varováním, když má `.factory/` necommitnuté změny proti `base`,
   se seznamem souborů. Jde o stejnou funkci jako `factory config status` (`config_changes`).
4. Testy API nad dočasným git repem, unit testy formuláře a pruhu. Projdou `just test`,
   `just typecheck` a `just lint`.

Mimo rozsah: tlačítko commit a editory agentů, promptů a workflow (F4). Soubory se nesledují
(watch/SSE je úkol 3.7).

Pevná omezení:
- `.factory/local.yaml` se nikdy necommituje (žádný `git add`, a navíc se zajistí ignore, viz níže).
- `vendor/` a `prototype/` se nemění.
- Měnit se smí jen `aifactory/src/aifactory/web/`, `aifactory/web/src/` a `aifactory/tests/web/`.
  **`aifactory/src/aifactory/config/` se nemění.** Validace se tedy opírá o existující modely
  `ProjectSettings` a `LocalSettings` a doplňkové kontroly patří do webového modulu.

## Co už existuje (nepsat znovu)

- `aifactory/src/aifactory/config/settings.py`: `ProjectSettings` (pydantic, `extra="forbid"`,
  validátory cest, `base`, `test_command` přijímá string → `shlex.split`), `LocalSettings`
  (`port` strict int 1–65535, `trace_db` neprázdný), `CONFIG_FILE`, `LOCAL_KEYS`, `parse_mapping`,
  `validation_issues`, `load_local`.
- `aifactory/src/aifactory/config/source.py`: `LOCAL_FILE = ".factory/local.yaml"`, `git()`.
- `aifactory/src/aifactory/config/status.py`: `config_changes(root, sha)`, `change_warnings(...)`.
- `aifactory/src/aifactory/config/run.py`: `worktree_base(root)`; `resolve_commit` v `source.py`.
- `aifactory/src/aifactory/web/backlog.py:423` `_config_status(root)`: vrací přesně data
  `factory config status --json` (`base`, `commit`, `clean`, `changes`) + warnings. Používá ho
  `run_check`.
- `aifactory/src/aifactory/run/gitops.py`: `main_root(repo)`, `ensure_excluded(root, lines)`
  (zápis do `info/exclude`, idempotentní).
- `aifactory/src/aifactory/skill/envelope.py`: `envelope_ok`, `envelope_fail(code, message, path=, id=, issues=)`.
- Frontend: `web/src/lib/api.ts` (`getApi`, `postApi`, `ApiError` s `issues: ApiIssue[]`,
  kde `ApiIssue = {code, message, path, id}`), `web/src/views/SettingsView.vue` je zatím
  `EmptyScreen`, `web/src/App.vue` drží topbar a `<main>`. Vzor formuláře:
  `web/src/components/backlog/TaskForm.vue` (+ test), vzor varování: `RunDialog.vue` (`.warning`).

## Backend

### 1. Nový modul `aifactory/src/aifactory/web/settings.py`

```python
SHARED_FIELDS = ("workdir", "backlog_dir", "specs_dir", "docs_dir", "worktrees_dir", "base",
                 "git_provider", "merge_strategy", "test_command", "protected_files")
LOCAL_FIELDS = ("port", "trace_db")
```

Funkce (všechny berou `repo: Path` a pracují nad `root = gitops.main_root(repo)`, tj. nad hlavním
checkoutem, jako ostatní zápisy dashboardu):

- `config_status(root) -> tuple[JsonDict | None, list[str]]`: **přesunout** sem `_config_status`
  z `web/backlog.py` beze změny chování (`worktree_base` → `resolve_commit` → `config_changes`
  → `change_warnings`). V `backlog.py` ho importovat a používat (`run_check`) — jedna funkce
  pro RunDialog i pruh. Odstranit z `backlog.py` importy, které tím přestanou být potřeba.

- `settings_view(repo) -> tuple[JsonDict, list[str]]` (pro GET):
  - Přečte `config.yaml` a `local.yaml` z disku (`WorktreeSource`/`Path.read_text`, **ne** z commitu).
  - Sdílené: `parse_project_settings(text, CONFIG_FILE, issues)`. Když je soubor platný, hodnoty
    z modelu. Když ne, hodnoty = výchozí `ProjectSettings()` překryté tím, co jde z raw mapy
    (jen klíče z `SHARED_FIELDS`), a do odpovědi `shared_issues` (list `{path, message}`).
  - Lokální: stejně s `LocalSettings` a `local_issues`.
  - Serializace pro formulář: `test_command` jako string `shlex.join(...)` nebo `null`;
    `protected_files` jako list stringů; ostatní skaláry.
  - Tvar `data`:
    ```json
    {
      "shared": {"workdir": ".", "backlog_dir": "backlog", ..., "test_command": "uv run pytest" | null,
                 "protected_files": [".factory/"]},
      "local": {"port": 4700, "trace_db": ".factory/trace.db"},
      "files": {"shared": ".factory/config.yaml", "local": ".factory/local.yaml"},
      "options": {"git_provider": ["local", "github", "azure"], "merge_strategy": ["squash", "merge"]},
      "shared_issues": [], "local_issues": [],
      "status": <config_status data nebo null>
    }
    ```
    Možnosti vzít z `typing.get_args` anotací `ProjectSettings` (ne natvrdo), aby se nerozešly.

- `save_settings(repo, body) -> tuple[JsonDict, list[str]]` (pro POST):
  - Body: `{"shared"?: {...}, "local"?: {...}}` — obě sekce volitelné, v každé jen měněné klíče.
    Jiný top-level klíč, klíč mimo `SHARED_FIELDS`/`LOCAL_FIELDS` nebo sekce, která není objekt
    → `backlog.UsageError` (HTTP 400 `usage_error`), stejná třída jako jinde ve webu.
  - Pro každou sekci: načíst stávající raw mapu souboru (`parse_mapping`; neplatný YAML v souboru →
    začít od `{}` jen pokud soubor neexistuje, jinak chyba `invalid_settings` s issue bez pole
    `id` — nepřepisovat nečitelný soubor naslepo), **sloučit** poslané klíče (ostatní klíče
    jako `levels`, `remote`, `azure` zůstanou beze změny). Hodnota `null` klíč odstraní (návrat
    k výchozí hodnotě; hlavně `test_command`).
  - Validace sloučené mapy: `ProjectSettings.model_validate(merged)` a
    `LocalSettings.model_validate(merged_local)`. Chyby převést na issues **po polích**:
    `field = str(err["loc"][0])` pokud `loc` neprázdné, jinak `"git_provider"` (jediný
    model-level validátor je `_provider_section`). Pro sdílenou mapu navíc zkontrolovat, že
    neobsahuje `LOCAL_KEYS` (jako `parse_project_settings`).
  - Doplňková webová kontrola `protected_files` (model ji nemá): každá položka po `strip()`
    neprázdná, relativní, bez `..` (znovu použít `aifactory.config.settings._relative`, nebo
    stejnou logiku lokálně — importovat privátní funkci je v pořádku, jen ji neměnit). Stripnuté
    hodnoty ukládat.
  - Když je jakákoli chyba v kterékoli sekci → **nezapsat nic** a vyhodit
    `SettingsError(code="invalid_settings", issues=[...])`. Issue tvar:
    `{"code": "invalid_value", "message": "<msg>", "path": ".factory/config.yaml" | ".factory/local.yaml", "id": "<field>"}`
    (`id` nese jméno pole — frontend podle něj páruje chybu k inputu; `api.ts` `toIssues` mapuje
    `code/message/path/id`, nic dalšího měnit netřeba).
  - Zápis: `yaml.safe_dump(merged, sort_keys=False, allow_unicode=True, default_flow_style=False)`
    atomicky (tmp soubor ve stejném adresáři + `os.replace`), `mkdir(parents=True, exist_ok=True)`
    pro `.factory/`. Zapisovat jen sekce, které byly v body a mají aspoň jeden klíč. Do YAML
    ukládat `test_command` jako string, jak přišel (validátor ho při čtení rozdělí).
    Známé omezení (zdokumentovat v docstringu): pyyaml při přepisu zahodí komentáře v souboru.
  - Po zápisu `local.yaml`: zajistit, že se nikdy necommitne —
    `git check-ignore -q .factory/local.yaml` (přes `aifactory.config.source.git` v `try`,
    exit≠0 = neignorováno) a pokud není ignorován, `gitops.ensure_excluded(root, [".factory/local.yaml"])`.
    Pokud je `local.yaml` přesto trackovaný (`git ls-files --error-unmatch`), přidat warning
    „.factory/local.yaml is tracked by git; remove it with git rm --cached“. Nikdy nevolat `git add`.
  - Návratová hodnota: stejná data jako `settings_view` (čerstvě načtená) + `"saved": ["shared", "local"]`
    podle zapsaných souborů; warnings = warnings z `config_status` (uložení `config.yaml` typicky
    vytvoří necommitnutou změnu → uživatel ji vidí hned).

- `class SettingsError(Exception)` s `code`, `message`, `issues: list[dict]`.

### 2. `aifactory/src/aifactory/web/app.py`

- Nové routy v `Mount("/api", ...)`:
  - `GET /api/settings` → `settings_get` (`run_in_threadpool(settings.settings_view, repo)`).
  - `POST /api/settings` → `settings_save` (`_json_body`, `run_in_threadpool(settings.save_settings, repo, body)`).
  - `GET /api/config/status` → `config_status` — vrací `envelope_ok(data, warnings)` s daty
    `{base, commit, clean, changes}`. Když `config_status` vrátí `None` (chyba gitu, neznámá base,
    repo bez commitu), vrátit `envelope_fail("invalid_config", "; ".join(warnings))` se statusem 500.
- Mapování chyb: `UsageError` → `_usage_error` (400); `SettingsError` → 422 s
  `envelope_fail(code, message, issues=issues)`; `TaskRunError` z `main_root` → `_run_error`;
  `ConfigError` → `_edit_error`.
- Rozšířit modulový docstring o tři nové endpointy (styl jako ostatní odstavce).

### 3. Testy backendu `aifactory/tests/web/test_web_settings.py`

Nad `make_backlog_repo(tmp_path / "repo")` z `backlog_fixture.py` (má commit s
`.factory/config.yaml`, `base: main`; `.gitignore` obsahuje jen `.factory/trace.db*`, takže
`local.yaml` **není** ignorovaný — dobré pro test exclude). Klient jako v `test_web_backlog.py`
(`create_app(root, static_dir=tmp_path / "nostatic")`, `base_url="http://127.0.0.1:4700"`,
kontrola `envelope_problems(body) == []`). Pozn.: default větev po `git init` může být `master`;
ověřit, jak to řeší stávající testy (`test_web_backlog.py` nad stejným fixture s `base: main`) a
postupovat stejně.

Případy:
1. GET vrátí sdílené hodnoty z `config.yaml` (`backlog_dir: backlog`, výchozí ostatní),
   lokální výchozí (`4700`, `.factory/trace.db`), `options` a `status.clean is True`.
2. POST `{"shared": {"base": "develop", "test_command": "uv run pytest -q", "protected_files": [".factory/", "justfile"]}}`
   → 200; `config.yaml` obsahuje nové hodnoty **a zachovaný `levels`**; `ProjectSettings` ze
   souboru jde načíst (`parse_project_settings`); `factory config status` ekvivalent
   (`GET /api/config/status`) hlásí `.factory/config.yaml` jako `modified`, `clean: false`.
3. POST `{"local": {"port": 4811, "trace_db": "var/t.db"}}` → `local.yaml` zapsán, `load_local`
   vrátí 4811; `git status --porcelain` soubor neukazuje (je v `info/exclude`); `config/status`
   zůstává `clean` (local.yaml není sdílená konfigurace).
4. Neplatné hodnoty → 422 `invalid_settings`, issue `id` = pole, soubor beze změny (porovnat
   bajty před/po):
   - `backlog_dir: "."`, `workdir: "../x"`, `specs_dir: "/abs"`, `base: "  "`;
   - `git_provider: "gitlab"`, `merge_strategy: "rebase"`;
   - `git_provider: "azure"` bez sekce `azure` → issue `id == "git_provider"`;
   - `test_command: "a 'b"` (neuzavřená uvozovka);
   - `protected_files: ["", "../x"]`;
   - `port: 0`, `port: 70000`, `port: "4700"` (strict), `trace_db: ""`.
5. Atomičnost přes sekce: platný `shared` + neplatný `local.port` → nezapíše se **ani** `config.yaml`.
6. `null` u `test_command` klíč ze souboru odstraní.
7. Neznámý klíč (`{"shared": {"levels": [...]}}`, `{"foo": {}}`) a ne-objekt body → 400 `usage_error`.
8. `local` klíče (`port`) poslané v `shared` → 400 `usage_error` (nejsou v `SHARED_FIELDS`).
9. Nevalidní `config.yaml` na disku (např. `merge_strategy: nope` zapsané ručně): GET vrátí 200 s
   neprázdným `shared_issues` a hodnotou `nope` ve formuláři.
10. `GET /api/config/status` na čistém repu → `clean: true`, `changes: []`; po přidání
    `.factory/workflows/new.yaml` → `untracked`; data shodná s `config_changes` (porovnat s přímým
    voláním `aifactory.config.config_changes`).
11. `run-check` v `test_web_task_run.py` dál projde (regrese po přesunu `_config_status`).

## Frontend (`aifactory/web/src/`)

### 4. `lib/settings.ts` (+ `lib/settings.test.ts`)

- Typy `SharedSettings`, `LocalSettings`, `SettingsData`, `SettingsSaveInput`
  (`{shared?: Partial<...>, local?: Partial<...>}`), `ConfigStatus`
  (`{base: string, commit: string, clean: boolean, changes: {path, status}[]}`).
- `fetchSettings()` = `getApi('/settings')`, `saveSettings(input)` = `postApi('/settings', input)`,
  `fetchConfigStatus()` = `getApi('/config/status')`.
- `toConfigStatus(raw: unknown): ConfigStatus | null` — tolerantní parsování (chybějící `changes`
  → prázdný seznam, chybějící `clean` → odvodit z `changes.length`). Důvod: `App.test.ts` stubuje
  `fetch` tak, že neznámé URL vrací data backlogu.
- `fieldErrors(issues: ApiIssue[]): Record<string, string[]>` podle `issue.id`; issues bez `id`
  → klíč `''` (obecná chyba formuláře).
- `settingsDiff(initial, current)`: vrátí `SettingsSaveInput` jen se změněnými poli (sekce bez
  změn vynechat). `test_command`: prázdný string → `null`. `protected_files`: textarea → řádky,
  `trim`, bez prázdných (stejné jako `splitLines` v `lib/backlog.ts` — znovu použít). `port`:
  pokud je vstup `/^\d+$/`, poslat `Number(...)`, jinak poslat string beze změny (backend ho
  odmítne a chyba se ukáže u pole — frontend validaci neduplikuje).
- Unit testy: diff (nic nezměněno → `{}`), prázdný test_command → null, port „abc“ → string,
  `fieldErrors`, `toConfigStatus` na neúplných datech.

### 5. `lib/configStatus.ts` — sdílený stav pruhu

- Singleton composable `useConfigStatus()` → `{ status: Ref<ConfigStatus|null>, error: Ref<string|null>, refresh(): Promise<void> }`
  (modulová `ref`, aby App i SettingsView sdílely jeden stav). `refresh` volá `fetchConfigStatus`;
  při `ApiError` nastaví `error` a `status = null`.
- Obnovení: v `App.vue` `onMounted`, při změně route (`watch(route, refresh)`) a na
  `window` `focus`. `SettingsView` volá `refresh()` po úspěšném uložení. Žádný polling (3.7).

### 6. `components/ConfigStatusBanner.vue` (+ `ConfigStatusBanner.test.ts`)

- Props: `status: ConfigStatus | null`, `error: string | null`.
- `status && !status.clean` → pruh `role="alert"` `data-test="config-banner"`:
  „Konfigurace v `.factory/` má necommitnuté změny. Běhy používají `{base}` (`{commit[0:7]}`), dokud je necommitneš.“
  + seznam `<li class="mono">{status} {path}</li>` (`data-test="config-change"`). Styl převzít
  z `.warning` v `RunDialog.vue` (barvy přes CSS proměnné, žlutá/oranžová).
- `error` → tenký neutrální řádek „Stav konfigurace nelze zjistit: …“ (`data-test="config-banner-error"`).
- Čisté → nic se nevykreslí.
- Test: čistý stav nic, 2 změny → 2 položky a base+sha, chyba → chybový řádek.

### 7. `App.vue`

- Vložit `<ConfigStatusBanner :status :error />` mezi `</header>` a `<main>` (je tedy na všech
  obrazovkách). Napojit `useConfigStatus()` (viz 5).
- `App.test.ts`: stub `fetch` rozšířit o `/api/config/status` (čistý i špinavý případ); nový test
  „ukáže pruh na všech obrazovkách“ — se špinavým stavem je `[data-test="config-banner"]` vidět
  na `#/backlog` i po přepnutí na `#/runs`. Stávající testy musí projít beze změny očekávání.

### 8. `components/settings/SettingsForm.vue` (+ `SettingsForm.test.ts`)

- Props: `settings: SettingsData`, `busy: boolean`, `errors: Record<string, string[]>`.
  Emit: `submit: [input: SettingsSaveInput]`, `reset: []`.
- Dvě skupiny (`<fieldset>`):
  - „Sdílené (`.factory/config.yaml`, commituje se)“: textové inputy `workdir` (popisek
    „Pracovní adresář agentů“, nápověda „`.` = kořen repa nebo podadresář“), `backlog_dir`,
    `specs_dir`, `docs_dir`, `worktrees_dir`, `base`; `<select>` `git_provider` a
    `merge_strategy` z `settings.options`; input `test_command` (placeholder „žádný“);
    textarea `protected_files` (jeden na řádek).
  - „Lokální (`.factory/local.yaml`, mimo git)“: `port` (`type="text" inputmode="numeric"`),
    `trace_db`.
- Každé pole `data-test="<field>"`; pod ním `<p class="field-error" data-test="error-<field>">`
  pro `errors[field]`; input dostane `aria-invalid="true"` a třídu `invalid`. Obecné chyby
  (`errors['']`) nad tlačítky.
- Pokud `shared_issues`/`local_issues` nejsou prázdné, nahoře upozornění „Soubor je teď neplatný“
  se seznamem zpráv.
- Upozornění u `git_provider === 'azure'`: sekce `azure` se v dashboardu needituje; pokud
  v souboru chybí, uložení selže u pole `git_provider` (zpráva z backendu).
- Submit: `emit('submit', settingsDiff(initial, current))`; tlačítko „Uložit“ `disabled` při
  `busy` nebo když diff je prázdný. Tlačítko „Vrátit“ obnoví hodnoty z props.
- Testy: vykreslení hodnot z props; změna `base` + `port` → emit jen se změnami
  (`{shared: {base: 'develop'}, local: {port: 4801}}`); prázdný `test_command` → `null`;
  `protected_files` z textarey; `errors` → text u správného pole a `aria-invalid`; tlačítko
  disabled bez změn.

### 9. `views/SettingsView.vue` (+ `SettingsView.test.ts`)

- Nahradit `EmptyScreen`. `<h1>Nastavení</h1>` (App test hledá `main h1` u jiných obrazovek;
  držet konvenci). Načte `fetchSettings()`; stav loading / chyba API / formulář.
- `onSubmit(input)`: `busy = true`, `saveSettings(input)`; úspěch → nahradit `settings` odpovědí,
  vyčistit chyby, krátká hláška „Uloženo“ (`data-test="saved"`) a `useConfigStatus().refresh()`.
  `ApiError` s `code === 'invalid_settings'` → `errors = fieldErrors(err.issues)`, hodnoty ve
  formuláři **zůstanou** (formulář se nepřemountuje — klíč komponenty měnit jen po úspěchu).
  Jiná `ApiError` → obecná chyba.
- Testy s `vi.stubGlobal('fetch', ...)`: načtení a zobrazení; uložení pošle POST s diffem;
  422 odpověď `{ok:false, error:{code:'invalid_settings', issues:[{code:'invalid_value', message:'must not be empty', path:'.factory/config.yaml', id:'base'}]}}`
  → chyba u pole `base` a hodnota v inputu zůstane; úspěch → „Uloženo“ a zavolá se
  `/api/config/status`.

## Ověření

Z kořene repa (hodnotit podle exit statusu):

```
just test        # pytest + web-test (bun install, vue-tsc typecheck, vitest)
just typecheck   # mypy
just lint        # ruff check + ruff format --check
```

Při chybě formátu spustit `cd aifactory && uv run ruff format .` a zopakovat. Ruční kontrola
(nepovinná): `just web-build && just dash`, na `#/settings` uložit `base`, pruh se objeví na
všech obrazovkách; `git status` neukazuje `.factory/local.yaml`.

Build do `aifactory/src/aifactory/web/static` se necommituje, pokud to tak není v předchozích
úkolech — řídit se stavem repa (`git status` po `just web-build`).

## Soubory

Nové:
- `aifactory/src/aifactory/web/settings.py`
- `aifactory/tests/web/test_web_settings.py`
- `aifactory/web/src/lib/settings.ts`, `aifactory/web/src/lib/settings.test.ts`
- `aifactory/web/src/lib/configStatus.ts`
- `aifactory/web/src/components/ConfigStatusBanner.vue` + `.test.ts`
- `aifactory/web/src/components/settings/SettingsForm.vue` + `.test.ts`
- `aifactory/web/src/views/SettingsView.test.ts`

Měněné:
- `aifactory/src/aifactory/web/app.py` (routy, chyby, docstring)
- `aifactory/src/aifactory/web/backlog.py` (`_config_status` → import z `web/settings.py`)
- `aifactory/web/src/App.vue`, `aifactory/web/src/App.test.ts`
- `aifactory/web/src/views/SettingsView.vue`

Nemění se: `aifactory/src/aifactory/config/**`, `vendor/`, `prototype/`, `BACKLOG.md` (stav úkolu
upraví workflow).
