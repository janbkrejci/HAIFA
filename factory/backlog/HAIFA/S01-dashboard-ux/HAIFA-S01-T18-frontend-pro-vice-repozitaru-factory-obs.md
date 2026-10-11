---
id: HAIFA-S01-T18
title: "Frontend pro více repozitářů, factory obs bez repa a port jen v registru"
status: done
workflow: simple-sdlc
depends_on: [HAIFA-S01-T13, HAIFA-S01-T01, HAIFA-S01-T02, HAIFA-S03-T05]
---

## Zadání
Přepni dashboard na více repozitářů: `factory obs` spustí aplikaci nad registrem z M3, adresy obrazovek nesou id repa a přepínač repozitářů nahradí čip repa v horní liště. Při prvním startu bez repozitářů dashboard ukáže prázdný stav. Port dashboardu zůstane jen v registru (D22).

Where: `aifactory/src/aifactory/cli.py`, `aifactory/src/aifactory/config/` (`settings.py`, `run.py`), `aifactory/src/aifactory/web/` (`app.py`, `server.py`, `settings.py`), registr z M3, kontrola z M6, `aifactory/web/src/` (`App.vue`, `lib/router.ts`, `lib/api.ts`, `lib/live.ts`, `lib/configStatus.ts`, `lib/settings.ts`, `components/EmptyScreen.vue`, `components/ConfigStatusBanner.vue`, `components/settings/SettingsForm.vue`, `test/settingsFixtures.ts`, `views/` a testy), `aifactory/tests/web/test_obs_cli.py`, `aifactory/tests/e2e/` (`f3_repo.py`, `test_f3_browser.py`), build v `aifactory/src/aifactory/web/static/`.

Done means:
- `factory obs` funguje v jakékoli složce i mimo git. Port je `--port`, jinak `port` z registru, jinak 4700. Když `--repo` ukazuje na repo s `port` v `.factory/local.yaml`, příkaz upozorní, že ho dashboard nepoužívá.
- `factory obs --repo CESTA` repo zaregistruje stejnou validací jako `POST /api/repos` a otevře `#/r/<id>/backlog`. Když na portu běží dashboard (`/api/health` s `app: haifa-dashboard`), příkaz jen zapíše registr, otevře běžící dashboard a skončí s 0. Jiná služba na portu dál vrátí `port_in_use`. `--json` zachová dnešní klíče a přidá `repo_id`, `home` a `reused`.
- Adresy jsou `#/overview` (výchozí), `#/r/<id>/<obrazovka>/…`, `#/repos` a `#/repos/add`. Staré `#/backlog…` vedou na přehled. Funkce odkazů (`hrefFor`, `taskHref`, `runHref`, `reviewHref`, `graphHref`) berou repo z aktuální adresy, takže místa volání zůstávají.
- `getApi` a `postApi` volají `/api/repos/<id>` aktuálního repa, globální endpointy mají vlastní funkce. Obrazovky repa se vykreslí v komponentě s klíčem podle id repa, takže přepnutí zahodí data, kurzory běhů, stav konfigurace i živý stream. Stav konfigurace (D4) se drží pro každé repo zvlášť.
- Záložka drží jeden `EventSource` na `/api/repos/<id>/live`. Ve skryté záložce se zavře, po návratu se otevře a obrazovka se načte znovu.
- Přepínač v horní liště nabídne Přehled, repozitáře (název, nadřazená složka, štítek `nenainstalováno` nebo `chybí`), Přidat repozitář… a Spravovat…. Výběr repa zachová obrazovku bez parametrů. Titulek záložky je `<repo> · <obrazovka> · HAIFA`. Neznámé id ukáže „Repo <id> v dashboardu není“ s odkazem na přehled.
- Bez repozitářů je prázdný stav (EmptyScreen) s návodem `factory obs --repo <cesta>`. Přehled zatím ukáže seznam repozitářů se stavem a odkazem na Backlog.
- `LocalSettings` nemá `port`. Klíč `port` ve starém `.factory/local.yaml` se ignoruje s varováním `local_port_ignored` a kvůli němu neselže žádný příkaz. `factory config show` ani API nastavení port nevrací a `factory check` hlásí `local_port_ignored` s opravou „smaž řádek port z .factory/local.yaml“.
- Nastavení repa v API i ve formuláři nese jen `trace_db`. POST s `local.port` vrátí `invalid_value`.
- Unit testy (vitest): routy a přesměrování, API base, znovuotevření streamu při přepnutí a skrytí záložky, reset obrazovek, přepínač, prázdný stav, neznámé id a formulář nastavení bez portu. Testy `factory obs`: bez repa, mimo git, `--repo`, pořadí portů, běžící dashboard, cizí služba na portu a staré `local.yaml` s `port` (každý příkaz projde s varováním).
- Prohlížečový test F3 běží s `HAIFA_HOME` v dočasném adresáři a s adresami `#/r/<id>/…`.
- Build frontendu v `aifactory/src/aifactory/web/static/` odpovídá změnám.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: aktivita v přehledu, přidání a odebrání repa v UI, záložka Factory, port v UI, recept `just dash` (upraví engineer).

Pevná omezení:
- Repo je jen v adrese, server si poslední repo nepamatuje.
- Žádná nová závislost frontendu.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-06 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/66 · náklady $10.83
