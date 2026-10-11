---
id: HAIFA-S01-T13
title: Registr repozitářů v domově a API pro více repozitářů
status: done
workflow: simple-sdlc
depends_on: [HAIFA-S01-T08, HAIFA-S01-T09, HAIFA-S06-T02]
---

## Zadání
Přidej registr repozitářů dashboardu v domovském adresáři HAIFA a aplikaci, která obslouží víc repozitářů najednou. Dnešní API jednoho repa se přesune pod `/api/repos/{id}/` se stejnými relativními cestami a obálkami. `factory obs` zatím dál používá `create_app` pro jedno repo, přepne ho až frontend pro více repozitářů (M11). Stav factory v repu bere z funkce stavu repa z O1, takže dashboard pozná onboardované repo a nikdy nenabídne jeho vytěžení.

Where: `aifactory/src/aifactory/web/` (`app.py`, `live.py`, `__init__.py`), modul domovského adresáře z M2, funkce stavu repa z O1 v `aifactory/src/aifactory/onboard/`, `aifactory/src/aifactory/run/gitops.py`, `aifactory/src/aifactory/config/settings.py`, `aifactory/src/aifactory/skill/codes.py`, testy v `aifactory/tests/web/`. Nový modul registru v `aifactory/src/aifactory/web/`.

Done means:
- Registr je `dashboard.yaml` v domovském adresáři (adresář 0700, soubor 0600) s `version`, `port` a `repos: [{id, name, path, added_at}]` a je jediným místem portu dashboardu (D22). Zápis drží `flock` na zámkovém souboru, nahrazuje soubor atomicky jako `web/settings.py` a zachová neznámé klíče. Server soubor načte znovu po změně mtime nebo velikosti. Poškozený soubor nechá poslední platný stav a dá varování.
- `id` je slug názvu složky (`[a-z0-9-]{1,32}`), při kolizi s příponou `-2`, `-3`, a nemění se. `inspect` je rezervované. Duplicitu pozná podle reálné cesty i podle zařízení a inode kořene repa.
- Globální endpointy: `GET /api/health` (`app: haifa-dashboard`, `version`, `home`), `GET /api/repos` (repa se stavem `ok`, `uncommitted`, `not_installed`, `missing` nebo `not_git` a polem `factory` se stavem z O1), `POST /api/repos {path}` (idempotentní), `DELETE /api/repos/{id}` (jen záznam v registru), `POST /api/repos/inspect {path}` (jen čte) a `GET` a `POST /api/dashboard/settings` (`port`, `home`, `restart_required`).
- Inspect vrátí stav factory z O1 (`none`, `working_tree`, `sssf`, `pre_library` nebo `onboarded`), příznaky, akci (`init`, `onboard`, `adopt`, `config_commit`) a u `onboarded` blok `onboarding` z manifestu. `not_installed` v seznamu rep znamená stav `none` nebo `sssf`.
- Inspect a přidání rozbalí `~`, vyžadují existující adresář a vezmou kořen repa. Odmítnou složku bez gitu (žádný `git init`), holé repo, propojený worktree (nabídnou hlavní checkout), cestu pod `.factory/worktrees/`, repo bez commitu a repo, jehož trace DB už používá jiné registrované repo (`trace_db_shared`). V neregistrovaném repu spouští jen `rev-parse`, `cat-file`, `ls-tree`, `for-each-ref` a `remote get-url`.
- `Mount` na `/api/repos/{repo_id}` nese dnešní trasy kromě `/health`, včetně `/live` s vlastním `LiveHub` pro každé repo. Neznámé id vrátí 404 `unknown_repo`, chybějící složka 404 `repo_missing`. Handlery čtou repo z požadavku místo `app.state.repo`. Odebrání repa zavře jeho `LiveHub`.
- `create_app(repo)` dál obsluhuje jedno repo pod `/api/` a stávající testy API projdou beze změny cest.
- Nové kódy jsou v `skill/codes.py`.
- Testy (pytest): souběžné zápisy dvou procesů, duplicita přes symlink, kolize id, zachování neznámých klíčů, poškozený soubor, inspect (složka bez gitu, podsložka, propojený worktree, worktree běhu, holé repo, repo bez commitu, sdílená trace DB, stavy `sssf`, `pre_library` a `onboarded`), izolace dvou rep (backlog, běhy, nastavení, živé události), `unknown_repo`, `repo_missing` a kontrola zápisových požadavků z M1 na nových endpointech.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: změna `factory obs` a frontendu, procházení složek a nativní dialog, přehled, kontrola, instalace a onboarding factory, přejmenování repa.

Pevná omezení:
- Registr drží jen seznam repozitářů a port. `.factory/`, backlog a trace DB zůstávají v repu.
- Přidání ani odebrání repa nic nezapíše do repa.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-04 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/60 · náklady $6.70
