# HAIFA-S01-T18: Frontend pro více repozitářů, `factory obs` bez repa a port jen v registru

Dashboard už neběží nad jedním repem. `factory obs` spouští aplikaci nad registrem
(`create_multi_app`, `dashboard.yaml` v `HAIFA_HOME`). Repo, které se zobrazuje, je jen
v adrese (`#/r/<id>/…`) a server si ho nepamatuje. Port dashboardu je jen v registru (D22).
`.factory/local.yaml` nese už jen `trace_db`.

## `factory obs` (`aifactory/src/aifactory/cli.py`)

- Funguje v jakékoli složce i mimo git, protože už nevolá `repo_root`.
- Port se bere v tomto pořadí: `--port`, potom `port` ze snapshotu registru, a když chybí, 4700.
- `--repo CESTA` repo zaregistruje přes novou funkci `register_repo` v
  `web/repos.py`, kterou sdílí s `POST /api/repos`. Prohlížeč pak otevře `#/r/<id>/backlog`.
  Když repo má `port` v `local.yaml`, příkaz vypíše varování `local_port_ignored`.
- Port je obsazený:
  - Když na něm odpovídá HAIFA (`server.probe_dashboard` čte `/api/health`, kde je
    `app == "haifa-dashboard"`), příkaz jen zapíše registr, otevře běžící dashboard,
    nastaví `reused: true` a skončí s 0.
  - Jiná služba na portu dál vrátí `port_in_use` s kódem 2.
- `--json` vrací stejné klíče jako dřív (`url`, `host`, `port`, `repo`, `version`) a k nim
  `repo_id`, `home` a `reused`. Bez `--repo` jsou `repo` a `repo_id` `null`.
- `server.serve` má nový parametr `open_path`, tedy fragment, který se připojí k otevírané URL.
  `APP_NAME` se přesunul do `server.py`.
- Multi-app teď obsluhuje i `GET /api/code` a `POST /api/restart`.

## Port mimo `local.yaml` (`config/settings.py`, `config/run.py`, `web/settings.py`, `check/machine_rules.py`)

- `LocalSettings` už nemá pole `port` a `LOCAL_KEYS` je jen `("trace_db",)`.
- Nová funkce `load_local_checked(root)` vrací dvojici `(settings, warnings)`. Starý klíč
  `port` zahodí ještě před validací a přidá varování `local_port_ignored`. Funkce
  `load_local` ji jen obaluje.
- `load_run_config` připojí tato varování k ostatním a `RunConfig.to_dict()["local"]` vrací
  jen `trace_db`. `factory config show` už nevypisuje řádek `port`.
- `port` v `.factory/config.yaml` je teď chyba konfigurace s odkazem na registr.
- API nastavení: `local` ve `GET /api/settings` nese jen `trace_db` a starý port se hlásí ve
  `warnings`. POST s `local.port` vrátí `invalid_value` s issue pro pole `port`. Při ukládání
  zůstane starý řádek `port` v souboru beze změny a nevaliduje se.
- `factory check` hlásí `local_port_ignored` jako varování s opravou
  „smaž řádek port z .factory/local.yaml“. Kód je zapsaný v `skill/codes.py`.

## Frontend (`aifactory/web/src/`)

- **Adresy** (`lib/router.ts`):
  - Platné adresy jsou `#/overview` (výchozí), `#/repos`, `#/repos/add` a
    `#/r/<id>/<obrazovka>/…`.
  - Cokoli jiného, včetně starého `#/backlog…`, přesměruje přes `replaceState` na přehled.
    Samotné `#/r/<id>` vede na `…/backlog`.
  - Nové funkce: `currentRepoId()` (čte hash v okamžiku volání), `repoHref()`, `usePage()`
    a `useRepoId()`.
  - `hrefFor`, `taskHref`, `runHref`, `reviewHref`, `graphHref` a `newContainerHref`
    doplní repo z aktuální adresy, takže se místa volání nemění.
- **API** (`lib/api.ts`):
  - `getApi` a `postApi` volají `apiBase()`, tedy `/api/repos/<id>`. Bez repa v adrese
    vyhodí `ApiError('no_repo')`.
  - Globální endpointy volají `getGlobal` a `postGlobal`. Patří sem `fetchHealth`,
    `fetchRepos`, `/code` a `/restart`.
  - `Health` má tvar `{app, version, home}`.
- **Živý stream** (`lib/live.ts`):
  - Na záložku je jeden `EventSource` na `/api/repos/<id>/live`.
  - Ve skryté záložce (`visibilitychange`) se zavře. Po návratu se otevře znovu a zavolá
    `resyncAll`.
  - `reopenLive()` stream otevře znovu pro aktuální repo.
- **Obrazovka repa** (`components/RepoScreen.vue`, nový soubor):
  - Obsahuje bannery konfigurace a backlogu, `useLive`, jmenné tooltipy a samotnou obrazovku.
  - `App.vue` ji vykresluje s `:key="repoId"`, takže přepnutí repa zahodí data, kurzory,
    odběry i bannery.
  - `backlogStatus.ts`, `names.ts` a `limits.ts` dostaly počítadlo generací. Pozdní odpověď
    pro předchozí repo se proto zahodí.
  - `configStatus.ts` drží stav (D4) v `Map` podle id repa.
- **Horní lišta** (`App.vue`, `components/RepoSwitcher.vue`):
  - Přepínač nahrazuje čip repa. Nabízí Přehled, repozitáře (název, nadřazenou složku a
    štítek `nenainstalováno` nebo `chybí`), „Přidat repozitář…“ a „Spravovat…“.
  - Výběr repa zachová obrazovku, ale ne její parametry.
  - Navigace obrazovek a limity se ukážou jen na stránce známého repa.
  - Titulek záložky je `<repo> · <obrazovka> · HAIFA`.
- **Stránky**:
  - `views/OverviewView.vue` ukazuje seznam repozitářů (`components/RepoList.vue`). Bez
    repozitářů ukáže `EmptyScreen` s příkazem `factory obs --repo <cesta>` (`lib/repos.ts`).
  - `views/ReposView.vue` je stejný seznam s nadpisem „Repozitáře“.
  - `#/repos/add` ukáže jen návod.
  - Neznámé id ukáže „Repo <id> v dashboardu není“ s odkazem na přehled.
  - `EmptyScreen.vue` dostal volitelný `code` a slot.
- **Nastavení**: z `lib/settings.ts` a `SettingsForm.vue` zmizelo pole port.
  `portValue` se přejmenovala na `intValue`.
- **Testy**: `src/test/setup.ts` (zapojený přes `setupFiles` ve `vite.config.ts`) nastaví
  před každým testem `#/r/haifa/backlog`. Existující testy proto mockují
  `/api/repos/haifa/…`.

## Ostatní

- `harness/codex.py`, `providers/azure.py` a `web/limits.py` čtou
  `subprocess.CREATE_NO_WINDOW` přes `getattr(..., 0)`.
- Build ve `web/static/` je přegenerovaný: nové `index-WiYEyNYh.js` a `index-_CSwGXa2.css`,
  staré soubory jsou smazané.

## Ověření

```bash
just test && just typecheck && just lint && just e2e
```

Kde jsou testy:

- `aifactory/tests/web/test_obs_cli.py`: běh bez repa, mimo git, s `--repo`, pořadí portů,
  běžící dashboard (`reused`), cizí služba na portu a starý `local.yaml` s `port`.
- `test_web_settings.py`, `test_web_repos.py`, `tests/config/*` a `test_factory_check.py`:
  odstranění portu z `local.yaml`, `invalid_value` a `local_port_ignored`.
- Vitest: `lib/router.test.ts`, `lib/api.test.ts`, `lib/live.test.ts`, `App.test.ts`
  (přepínač, prázdný stav, neznámé id, reset obrazovek) a `SettingsForm.test.ts`.
- `tests/e2e/f3_repo.py` a `test_f3_browser.py` spouštějí `factory obs --repo` s dočasným
  `HAIFA_HOME`. `ObsServer.api` míří na `/api/repos/<id>`.

Ruční ověření: v libovolné složce spusť `factory obs --repo /cesta/k/repu`. Prohlížeč se
otevře na `#/r/<id>/backlog`. Druhé spuštění téhož příkazu najde běžící dashboard, otevře ho
a skončí s 0.
