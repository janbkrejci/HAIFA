# HAIFA-S01-T13: Registr repozitářů v domově a API pro více repozitářů

## Co se změnilo

Dashboard teď umí obsloužit víc repozitářů najednou. Seznam repozitářů a port dashboardu jsou v registru `dashboard.yaml` v domovském adresáři HAIFA. Nová aplikace `create_multi_app` dává globální endpointy a API každého repa pod `/api/repos/{id}/`. Relativní cesty i obálky zůstaly stejné jako dnes. `create_app(repo)` dál obsluhuje jedno repo pod `/api/` a `factory obs` se nemění.

## Registr (`aifactory/src/aifactory/web/registry.py`)

```yaml
version: 1
port: 4700
repos:
  - {id: haifa, name: HAIFA, path: /abs/path/HAIFA, added_at: "2026-10-04T10:00:00+00:00"}
```

- Domovský adresář se vytvoří s právy 0700 a soubor s právy 0600. Registr je jediným místem portu dashboardu (D22). Výchozí port je `DEFAULT_PORT = 4700`, nová konstanta v `config/settings.py`.
- Zápis (`add`, `remove`, `set_port`) drží `flock` na `dashboard.lock`. Pod zámkem soubor znovu načte, upraví surové mapování a nahradí soubor atomicky (dočasný soubor a `os.replace`). Neznámé klíče zachová, a to na nejvyšší úrovni i v jednotlivých záznamech.
- Čtení (`Registry.snapshot`) načte soubor znovu, když se změní mtime, velikost nebo inode. U poškozeného souboru zůstane poslední platný stav a čtení vrátí varování. Zápis do poškozeného souboru selže s kódem `registry_invalid` a soubor se nepřepíše.
- `id` je slug názvu složky (`[a-z0-9-]{1,32}`). Při kolizi dostane příponu `-2`, `-3` atd. a později se nemění. `inspect` je rezervované.
- Duplicitu pozná `same_repo` podle reálné cesty nebo podle zařízení a inode. Opakované přidání téhož repa vrátí existující záznam.

## Globální endpointy (`aifactory/src/aifactory/web/app.py`)

| Endpoint | Co dělá |
|---|---|
| `GET /api/health` | `app: haifa-dashboard`, `version`, `home` |
| `GET /api/repos` | repa se `status` (`ok`, `uncommitted`, `not_installed`, `missing`, `not_git`) a polem `factory` ze stavu O1 (`onboard.state.repo_state`) |
| `POST /api/repos {path}` | idempotentní: HTTP 201 při přidání, 200 když repo už v registru je |
| `POST /api/repos/inspect {path}` | jen čte a vrací `root`, `subdir`, `registered`, `addable`, `problem`, `branch`, `remote`, `trace_db` a `factory` |
| `DELETE /api/repos/{id}` | odebere jen záznam v registru a zavře `LiveHub` repa |
| `GET`/`POST /api/dashboard/settings` | `port`, `home`, `registry`, `restart_required` (port v registru se liší od portu, na kterém server běží) |

`not_installed` znamená stav factory `none` nebo `sssf`. `uncommitted` znamená stav `working_tree` nebo necommitnutou sdílenou konfiguraci podle `web_settings.config_status`. Pole `factory` je `repo_state(root).to_json()`. Podle něj dashboard pozná onboardované repo. Stavy, akce a blok `onboarding` v tomto poli tedy pocházejí z O1 a tento diff je nemění.

## Kontrola cesty (`aifactory/src/aifactory/web/repos.py`, `run/gitops.py`)

`examine`/`vet_path` rozbalí `~`, vyžadují absolutní cestu k existujícímu adresáři a vezmou kořen repa (`subdir` řekne, odkud se šlo). Cesta se odmítne s jedním z těchto kódů:

`path_not_found` (404), `not_a_directory`, `not_git` (žádný `git init`), `bare_repo`, `linked_worktree` (v `data.main_checkout` nabídne hlavní checkout), `run_worktree` (cesta pod `.factory/worktrees/`), `no_commits` (všechny 422) a `trace_db_shared` (409, trace DB podle `.factory/local.yaml` už používá jiné registrované repo).

Git se volá přes nové `gitops.read_git` s `GIT_OPTIONAL_LOCKS=0`. Rozložení repa zjistí `gitops.repo_layout` a `RepoLayout` (`bare`, `linked`, `main_checkout`) jen pomocí `rev-parse`. Do repa se při kontrole ani při přidání nic nezapisuje.

## API jednoho repa pod `/api/repos/{id}/`

- Trasy jednoho repa jsou v `_repo_routes()` (všechny kromě `/health`). `create_app` je montuje pod `/api` a `create_multi_app` pod `Mount("/repos/{repo_id}")`.
- ASGI obal `RepoScope` vloží `RepoContext` (`id`, `root`, `live`) do scope pod klíč `haifa.repo`. Handlery čtou repo přes `_repo(request)` a `_ctx(request)` místo `app.state.repo` a `app.state.live`.
- `RepoContexts` vytvoří kontext s vlastním `LiveHub` při prvním požadavku. Při změně registru zahodí a zavře kontexty odebraných nebo přesunutých rep. Neznámé id vrátí 404 `unknown_repo`, chybějící složka 404 `repo_missing`.
- `guard.py` má nové `is_restart_path`: `StaleCodeMiddleware` pouští kromě `/api/restart` i `/api/repos/{id}/restart`. Write guard z M1 platí i pro nové zápisové endpointy.
- Nové kódy chyb jsou v `skill/codes.py`. `RepoError` je mezi chybovými třídami v `tests/test_skill.py`. `web/__init__.py` exportuje `create_multi_app`, `Registry`, `RepoEntry` a `RepoError`.

## Testy

- `aifactory/tests/web/test_web_registry.py` ověřuje práva souborů, souběžné zápisy dvou procesů, duplicitu přes symlink a inode, kolizi a stálost id, zachování neznámých klíčů, poškozený a neplatný soubor a znovunačtení po vnější změně.
- `aifactory/tests/web/test_web_repos.py` ověřuje health, nastavení dashboardu a všechny odmítnuté případy inspectu. Dál stavy `sssf`, `pre_library` a `onboarded`, sdílenou trace DB a to, že se v cizím repu spouštějí jen čtecí příkazy gitu. Pokrývá i idempotentní přidání bez zápisu do repa, stavy v seznamu, odebrání, `unknown_repo` a `repo_missing`, izolaci dvou rep (backlog, běhy, nastavení, `/live`), write guard a stale code na nových endpointech a to, že `create_app` nemá registrové endpointy.
- `aifactory/tests/web/multi_repo.py` je pomocník testů: zakládá git repa a klienta `create_multi_app`.
- `tests/validation/test_validation_template.py` mění poskytovatele testovacího pi modelu z `nousresearch` na `nous-portal`. Úprava s tímto taskem nesouvisí.

Ověření: `just test`, `just typecheck`, `just lint`. Cíleně `cd aifactory && uv run pytest tests/web/test_web_registry.py tests/web/test_web_repos.py`.
