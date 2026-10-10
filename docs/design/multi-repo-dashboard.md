# Dashboard pro více repozitářů: výsledný návrh

Cesty backendu jsou relativní k `aifactory/src/aifactory/`, `fe/` je `aifactory/web/src/`. T1 až T17 jsou úkoly plánu 14 bodů, C, I, U, O a R1 až R13 kódy mapy kódu, M1 až M15 úkoly níže a D14 až D28 otevřená rozhodnutí.

## 1. Verdikt

| Kritérium | A | B | Co rozhodlo |
|---|---|---|---|
| Věrnost zadání | 5 | 4 | A má celý průvodce, Zrušit bez zápisu a živý přehled. B nechá nenainstalované repo trvale v registru a přehled obnovuje po 5 s. |
| Bezpečnost | 3 | 5 | B pushuje dřív, než posune lokální base, staví commit bez checkoutu, čte git bez `index.lock`, logy drží mimo repo, inspect nespouští hooky a procházení omezí na domov. A dává logy do `.factory/data/` (hlídač), `fs/dirs` pustí kamkoli a plán drží jen v paměti serveru. |
| Postupné dodání | 3 | 5 | A přepne `factory obs` na registr (BL1) dřív, než to umí frontend (BL6), a mění `fe/lib/api.ts` v backendovém úkolu. B drží jednorepový dashboard funkční po každém úkolu. |
| Testovatelnost bez modelu | 4 | 5 | B dokládá záruky G1 až G9 testy a spouštěč testuje stub procesem. A má lepší opravu falešného harnessu. |
| Soulad s kódem | 3 | 4 | A přepisuje živé aktualizace na jeden sloučený stream. B znovu použije `LiveHub` pro každé repo a opravuje mapu kódu (X1, X8, X9). |

Základem je B. Z A se přebírá UX: průvodce přidáním s českými texty, přehled řazený podle toho, co potřebuje pozornost, přepnutí repa se zachovanou obrazovkou a Zrušit, které nic nezapíše.

Oba návrhy porušují T16. Podle T16 `factory init` nic necommituje a existující soubory přeskočí. A i B z něj dělají příkaz, který commituje a pushuje, B navíc i aktualizuje. Výsledný návrh T16 ponechává, commit přidává jako volbu `--commit` a aktualizaci dává do samostatného `factory update`. T1 řeší `test_command` (A BL0, B OD10), T14 a T15 zakládání projektu a stepu po instalaci (A D21).

## 2. Zásady

- Z1. Do repa se nezapíše nic, dokud uživatel nepotvrdí náhled plánu. Provedení plán přepočítá a jiný digest odmítne.
- Z2. Stav repa (`.factory/`, backlog, trace DB) zůstává v repu. Registr v domově drží jen seznam repozitářů a port.
- Z3. Dashboard volá tytéž funkce core jako CLI (backlog/phase-03-dashboard.md:10). Každá schopnost má nejdřív příkaz s `--json`.
- Z4. Id repa je jen v URL, dvě záložky můžou ukazovat dvě repa.
- Z5. Po každém úkolu funguje dashboard pro jedno repo jako dnes.
- Z6. Factory posune hlavní checkout repa jen tehdy, když v repu neběží žádný běh (R2).

## 3. Toky

**W1 První start.** `factory obs` běží v jakékoli složce i mimo git a nic nezapíše. Port: `--port`, registr, 4700. Prohlížeč otevře `#/overview` s prázdným stavem (fe/components/EmptyScreen.vue): „Žádný repozitář“, Přidat repozitář a nápověda `factory obs --repo <cesta>`. Registr vznikne při prvním přidání nebo uložení portu.

**W2 Přidání repa** (`#/repos/add`).
1. Složka: pole s cestou (`~/`) a našeptáváním podsložek se štítky git a factory, Procházet… (prohlížeč složek pod domovem), Vybrat ve Finderu… (nativní dialog, jen když je dostupný). Zkontrolovat zavolá inspect, který jen čte.
2. Karta repa: kořen repa (u podsložky „Použije se kořen repozitáře …“), větev, remote, stav factory (`none`, `working_tree`, `base`) a trace DB. Bez tlačítka Přidat odmítne: složka neexistuje, není git (HAIFA nespouští `git init`, první commit by vzal všechny soubory), holé repo, propojený worktree (nabídne hlavní checkout), worktree běhu, repo bez commitu, trace DB jiného registrovaného repa (R9). Registrované repo nabídne Otevřít.
3. Factory v base: Přidat zaregistruje repo a otevře záložku Factory. `factory check` se spustí sám, nálezy jsou ve skupinách „Repozitář: opravit a commitnout“ a „Tento počítač: opravit lokálně“. Jde-li něco aktualizovat, záložka nabídne Aktualizovat (W4).
4. Factory jen v pracovním stromu: totéž a záložka nabídne Commitnout konfiguraci (D4).
5. Bez factory: Pokračovat k instalaci zaregistruje repo dočasně a otevře plán instalace (W3). Zrušit registraci odebere a do repa nic nezapíše. Opuštěný průvodce nechá repo se štítkem nenainstalováno, jde odebrat.

**W3 Instalace.** Formulář předvyplní detekce: base z `refs/remotes/<remote>/HEAD`, jinak aktuální větev, provider z URL remote (`github`, `azure` s organizací, projektem a repem, bez remote `local`), harness z nainstalovaných CLI, model podle T16 a adresáře backlogu, specs a docs. Změna přepočítá plán. Plán ukáže každý soubor s obsahem (`config.yaml`, `agents.yaml` se čtyřmi agenty z T16, 8 promptů, `manifest.yaml`, `<backlog_dir>/.gitkeep`, řádky `.gitignore`, při jeho necommitnutých změnách `info/exclude`), varování (adresář s cizím obsahem, R7), nálezy stroje (neblokují), blokátory a souhrn „1 commit na main (a6f3e1c → nový), push na origin/main“. Provést potvrdí modál. Odmítnutý push: „V repozitáři se nic nezměnilo“ a Otevřít jako PR se stejným digestem. Po PR běhy počkají na merge a Dorovnat base. Úspěch spustí kontrolu znovu a nabídne Otevřít backlog, kde se první projekt a step založí přes T15.

**W4 Aktualizace.** Skupiny Přidá se (prompty deklarovaných agentů, `.gitkeep`, řádky `.gitignore`, manifest), Nahradí se novou výchozí verzí (soubory, které uživatel nezměnil) a Vaše úprava, ponechá se (volba Převzít, diff změny výchozí verze a diff uživatelových změn). Doručení jako W3. Dokud v repu běží běh, je Provést zakázané s odkazy na běhy.

**W5 Přepínání.** Přepínač nahradí čip repa (fe/App.vue:110-112): Přehled, repozitáře (název, nadřazená složka, štítky nenainstalováno a chybí, počty běží, review a selhalo), Přidat repozitář…, Spravovat…. Výběr repa zachová obrazovku bez parametrů (`#/r/haifa/review` → `#/r/sandbox/review`). Titulek záložky `<repo> · <obrazovka> · HAIFA`. Neznámé id: „Repo X v dashboardu není“.

**W6 Přehled** (`#/overview`, výchozí). Součty Běží, Čeká na review, Selhalo a Problémy s filtrem. Karta na repo, řazení: problémy, selhání, review, běží, klid (sbalené). Řádky vedou tam, kde jde jednat: Běží (task, název, workflow, fáze a pokus, čas, náklady) na běh, Čeká na review (task, PR, stáří, „podle trace“) na Review, Selhalo (nejnovější běh `failed` nebo `aborted`, task není `done` ani `cancelled`, chyba, „proces skončil“) na běh, Konfigurace (nenainstalováno, neplatná, necommitnutá) na Factory, Poslední aktivita. Obnova každé 2 s při viditelné záložce, při fokusu a tlačítkem (slib 2 s z úkolu 3.7). Nic nezapisuje.

**W7 Odebrání** (`#/repos`). Modál: „Odebrat <name> z dashboardu? Ve složce <path> se nic nezmění: .factory/, backlog, trace DB, worktree a větve zůstanou. Běžící běhy doběhnou.“ Odebere jen záznam v registru. Stránka nese i port dashboardu (platí po restartu) a cestu k registru.

**W8 Terminál.** `factory obs --repo .` zaregistruje repo a otevře `#/r/<id>/backlog`, u repa mimo stav `ok` záložku Factory. Když na portu běží dashboard (`/api/health` s `app: haifa-dashboard`), příkaz jen zapíše registr, otevře běžící dashboard a skončí s 0. Ctrl+C: „Dashboard ukončen. N běhů spuštěných z dashboardu pokračuje.“

## 4. Architektura

**AR1 Registr.** `$HAIFA_HOME/dashboard.yaml`, jinak `$XDG_CONFIG_HOME/haifa/`, jinak `~/.config/haifa/`. Adresář 0700, soubor 0600, obsah `version`, `port`, `repos: [{id, name, path, added_at}]`, bez `last_repo`. Zápis drží `flock` na zámkovém souboru a nahrazuje atomicky (web/settings.py:268-278), neznámé klíče zůstanou. Server soubor načte znovu po změně mtime nebo velikosti, poškozený soubor nechá poslední platný stav. Id je slug složky `[a-z0-9-]{1,32}`, při kolizi `-2`, nemění se a `inspect` je rezervované. Duplicita podle reálné cesty a `(st_dev, st_ino)` kořene. Registr čtou jen dashboard a `factory obs`, CLI ani běhy ho nepotřebují.

**AR2 Směrování.** Aplikace pro více repozitářů má globální trasy E1 až E9 a `Mount` na `/api/repos/{repo_id}` s dnešními trasami bez `/health` (web/app.py:588-622). 24 handlerů čte repo z požadavku místo `app.state.repo`, resolver vrátí 404 `unknown_repo` nebo `repo_missing`. Kontext repa (cesta, `LiveHub`, zámek zápisu) vznikne při prvním použití, zanikne při odebrání a nahradí singletony z web/app.py:640-642. `create_app(repo)` dál mountuje tytéž trasy pod `/api`, takže testy nemění cesty. Produkce ho od M11 nepoužívá.

**AR3 Běhy jako procesy** (C4, D15). Spouštěč pustí `factory task run ID --repo kořen --json` (+ `--note`, `--force`), `task return ID --note` a `task resolve ID` (cli.py:632-712) s `cwd` v kořeni, `start_new_session`, zavřeným stdin a prostředím serveru. Obálka a výpis jdou do `logs/` v domově, ne do repa: rostoucí log v `.factory/data/` by hlídač při jiném `data_dir` vzal jako zápis do hlavního checkoutu (run/task.py:169-205). Čekání na zabraný řádek zůstává (web/launcher.py:130-149), chyba před zabráním přijde z obálky a dostane dnešní HTTP stav. Vlákno na proces volá `wait()`, jinak by zombie držela `_alive` (run/store.py:224-233). Výsledek: souběh v repu i mezi repy, Zastavit i `factory task stop` míří na proces běhu, běh přežije restart serveru a signály enginu fungují na hlavním vlákně potomka. `validation.worker` nastaví prefix příkazu na sebe a falešný harness bere pozici ve skriptu z `<script>.calls.jsonl`. Potomci dědí prostředí serveru (R12 beze změny).

**AR4 Živé aktualizace.** Každé repo má svůj `LiveHub` na `/api/repos/{id}/live` beze změny protokolu a hub se dotazuje jen, když někdo poslouchá. Záložka drží jeden `EventSource` pro otevřené repo, ve skryté záložce ho zavře (6 spojení na hostitele) a po návratu otevře a načte obrazovku. Přehled se dotazuje E6 každé 2 s.

**AR5 Přehled** (C6). Trace DB jen přes `mode=ro` (web/live.py:212-214), nikdy přes `TaskRunStore`, který DB zakládá, přepíná na WAL a v `_reap` zapisuje. Mrtvý proces běžícího řádku se ukáže jako „proces skončil“ bez zápisu. Žádná volání provideru ani `git fetch`. Stav konfigurace se drží 15 s, názvy tasků 60 s, repa se počítají souběžně s limitem 2 s.

**AR6 Čtení gitu.** Čtecí volání konfigurace (diff, ls-files, ls-tree, cat-file, rev-parse) běží s `GIT_OPTIONAL_LOCKS=0`. `git diff` jinak bere `index.lock` a může shodit hlídač běžícího tasku (stejný problém řešil commit 9502796). Inspect neregistrovaného repa spouští jen `rev-parse`, `cat-file`, `for-each-ref` a `remote get-url`, které nespouští hooky ani `core.fsmonitor`.

**AR7 Plán a digest.** Instalace, aktualizace a commit konfigurace vrací plán: soubory s akcí (`create`, `unchanged`, `replace_default`, `keep_custom`, `take_new`, `add_lines`), lokální akce (`info/exclude`), blokátory, varování a digest. Blokátory: `not_on_base` a `run_in_progress` jen u přímého cíle, `base_behind`, `base_diverged`, `no_commits`, `dirty_paths`, `already_installed`, `not_installed`, `config_not_committed`, `newer_manifest`. Digest je sha256 přes režim, base, sha base, starý blob a nový obsah každé cesty a lokální akce. Cíl a zpráva v něm nejsou, takže odmítnutý push jde přepnout na PR bez nového plánu. Digest nepotřebuje stav serveru, proto funguje i v CLI (`--expect`). Plán se ověří zdrojem konfigurace z base doplněným o plánované soubory přes `load_config` (config/loader.py:183) a `preflight` workflow `simple-sdlc`.

**AR8 Zveřejnění commitu.**
1. Commit bez checkoutu: dočasný index nad sha base, `hash-object`, `update-index`, `write-tree`, `commit-tree`. Obsahuje přesně plánované cesty a bajty, cizí staged i unstaged práce zůstane.
2. Přímý cíl s remote: `git fetch` base, posunutý nebo rozejitý remote je blokátor, pak push bez force. Odmítnutí je `push_failed` a lokálně se nic nezmění.
3. PR (`github`, `azure`): větev `factory-config/<n>` (mimo prefix `factory/`, jako `factory-sync/` v review/sync.py:40-41), push a `create_pr`. Base a checkout zůstanou.
4. Bez remote: jen commit.
5. Lokální base se posune až po kroku 2 nebo 4, pod zápisovým zámkem trace DB a jen bez běžícího běhu s živým procesem (Z6). Cesty, které v pracovním stromu už mají plánovaný obsah, se nejdřív stagnou, pak `advance_branch` (providers/git.py:98-112). Selže-li posun po push, výsledek jen varuje.

Proč ne `git commit -- paths` jako backlog/commit.py:105-106: odmítnutý push tam nechá na lokální base nepushnutý commit a ten se dostane do každého dalšího PR tasku, protože běhy forkují z lokální base.

**AR9 Manifest a aktualizace** (U3, U4). `.factory/manifest.yaml` drží `factory_version`, volby instalace a sha256 každého souboru z výchozích dat. Je to samostatný soubor, loadery a varování D4 ho ignorují a `config.yaml` ani `local.yaml` nedostanou nový klíč (R6). Soubor je výchozí, když se hash shoduje s manifestem, bez manifestu, když se rovná současnému výchozímu obsahu (update ho převezme). Výchozí soubor dostane novou verzi, upravený zůstane, dokud uživatel nezvolí převzetí. Starou výchozí verzi pro diff update najde v historii base podle hashe. Prompty se nikdy neslučují automaticky. Balíčková workflow a `roles.yaml` se mění s balíčkem (R13) a do repa se nekopírují. Na HAIFA update dnes přidá jen manifest. Migrace klíčů nejsou (D26).

**AR10 Kontrola.** `factory check` jen čte. Repo: git stav (checkout na base, base je commit, náskok a zpoždění z lokálních refů), stav instalace, `load_config` z pracovního stromu i base, D4, souhrn `backlog check`, workflow backlogu v base, spustitelnost testovacího příkazu podle T1, řádky `.gitignore`, `update_available` a `newer_manifest`. Stroj: harnessy rosteru, `just`, `gh auth status` nebo `az` (vynechá `--offline`). Dashboard přidá `trace_db_shared`. Nález má `code`, `scope`, `severity`, `message`, `fix` a `action`, které řídí tlačítka. Návratový kód 0, 1 (`checks_failed`), 2.

**AR11 `factory obs`.** Port: `--port`, registr, 4700. `port` v `.factory/local.yaml` zůstává platný klíč (`LocalSettings` je `extra=forbid`, config/settings.py:146), dashboard ho ignoruje a `factory obs --repo` na něj upozorní. Nastavení repa nese jen `trace_db`. `--json` zachová dnešní klíče a přidá `repo_id`, `home` a `reused`.

**AR12 Frontend.** Routy `#/overview`, `#/repos`, `#/repos/add` a `#/r/<id>/<obrazovka>/…`, staré `#/backlog…` vedou na přehled. Funkce odkazů berou repo z aktuální routy, takže místa volání se nemění. `getApi` a `postApi` přidají `/api/repos/<id>`, globální volání mají vlastní funkce. Komponenta repa s klíčem podle id nese API base, banner D4, živý stream a obrazovku, takže přepnutí resetuje kurzory a cache (fe/views/RunsView.vue). Stav konfigurace je mapa podle repa. Nové obrazovky: Přehled, Repozitáře, Přidat repozitář a záložka Factory. Seznam souborů plánu staví na `DiffView` a `diffLines` (fe/components/review/DiffView.vue, fe/lib/review.ts). Modál, dropdown, spinner a tooltip dodají T3 až T5.

## 5. API

| # | Endpoint | Vrací | Úkol |
|---|---|---|---|
| E1 | `GET /api/health` | `app: haifa-dashboard`, `version`, `home` | M3 |
| E2 | `GET /api/repos` | repa se stavem `ok`, `uncommitted`, `not_installed`, `missing`, `not_git` | M3 |
| E3 | `POST /api/repos {path}` | `{repo, created}`, idempotentní, 409 `trace_db_shared` | M3 |
| E4 | `DELETE /api/repos/{id}` | `{removed}`, jen registr | M3 |
| E5 | `POST /api/repos/inspect {path}` | kořen, podsložka, větev, remote, stav factory, base, registrace, trace DB, problémy | M3 |
| E6 | `GET /api/overview` | `{repos, totals}` podle AR5 | M5 |
| E7 | `GET /api/fs/dirs?path=` | `{path, parent, entries, truncated}` | M4 |
| E8 | `GET` a `POST /api/fs/pick` | `{available}`, `{path}` nebo `{cancelled}` | M4 |
| E9 | `GET` a `POST /api/dashboard/settings` | `{port, home, restart_required}` | M3 |
| E10 | `/api/repos/{id}/…` | dnešní trasy včetně `/live`, `run-check` vrací `launcher_busy: false`, nastavení bez `port` | M2, M3, M11 |
| E11 | `GET …/factory/check?offline=&fresh=` | zpráva AR10 + `trace_db_shared`, cache 60 s | M10 |
| E12 | `POST …/factory/plan {action, options}` | plán s digestem, u `init` zjištěné hodnoty | M10 |
| E13 | `POST …/factory/apply {action, digest, options, target, message}` | `{commit, pushed, pr, warnings}`, 409 `plan_changed`, `busy` nebo blokátor, 502 `push_failed` | M10 |
| E14 | `POST …/config/pull` | posun lokální base | M10 |

Všechny POST a DELETE projdou S2. Provedení nikdy nebere cesty ani obsah souborů z požadavku.

## 6. CLI a skill

- K1 `factory check [--repo] [--offline] --json` (M6).
- K2 `factory config commit [--repo] [--dry-run] [--pr] [--expect DIGEST] [-m TEXT] --json` a `factory config pull [--repo] --json` (M7).
- K3 `factory init` z T16 plus `--dry-run`, `--commit [--pr] [--expect DIGEST] [-m TEXT]`, `--provider azure` s `--azure-org`, `--azure-project` a `--azure-repo`, `--harness`, `--model`, `--backlog-dir`, `--specs-dir`, `--docs-dir` (M8). Bez `--commit` platí T16.
- K4 `factory update [--repo] [--dry-run | --commit …] [--take CESTA]… --json` (M9). Bez voleb zapíše do pracovního stromu jako `init`.
- K5 Postup instalace ve `factory --skill` navazuje na T17: `factory check --json`, `factory init --dry-run --json`, ukázat soubory a digest uživateli, po souhlasu `factory init --commit --expect <digest> --json`, při `push_failed` se zeptat a zopakovat s `--pr`. Nové kódy jdou do skill/codes.py, nové příkazy se ve skillu objeví samy (skill/commands.py).

## 7. Bezpečnost

- S1. Server poslouchá jen na 127.0.0.1 a kontrola hostitele zůstává.
- S2. POST, PUT, PATCH a DELETE: `Origin`, pokud přijde, se rovná `http://<Host>` a `Sec-Fetch-Site`, pokud přijde, je `same-origin` (jinak 403 `cross_origin`), tělo jen `application/json` (jinak 415 `unsupported_media_type`). POST bez těla a bez hlaviček projde, takže Zastavit a Schválit (fe/lib/runs.ts:340, fe/lib/review.ts:165) fungují beze změny frontendu. Proxy `just web-dev` přepíše `Origin` na cíl (aifactory/web/vite.config.ts).
- S3. Zápisy jdou jen přes plán s digestem z voleb. GET nic nezapisuje ani neotvírá dialog. Bez CORS hlaviček cizí stránka odpověď nepřečte a DNS rebinding neprojde kontrolou hostitele.
- S4. Příjem cesty (inspect, přidání, výsledek dialogu): rozbalit `~`, absolutní cesta, `resolve()`, existující adresář, kořen repa, odmítnout holé repo, propojený worktree a `.factory/worktrees/`.
- S5. `fs/dirs` jen pod domovem po rozbalení symlinků (403 `outside_home`), jen adresáře, bez skrytých, nejvýš 500 položek, štítky ze `stat`. Napsaná cesta mimo domov projde přes inspect. Na macOS může první výpis Documents, Desktop nebo Downloads vyvolat dotaz na soukromí pro terminál.
- S6. Nativní dialog: pevné argv (`osascript`, `zenity`, `kdialog`) bez dat z požadavku, jeden najednou, na vlákně s limitem 300 s, bez grafického sezení nedostupný.
- S7. Procesy běhů dostávají argv bez shellu, text poznámky je vidět v `ps`, logy mají práva 0600.
- S8. Na 127.0.0.1 se dostane každý lokální uživatel, dnes i potom. Token pro spuštění je D27.

## 8. Testy bez modelu

- V1. `tests/conftest.py` nastaví `HAIFA_HOME` na dočasný adresář pro každý test a ověří, že skutečný domov zůstal. Server v e2e testech ho dostane taky (R11).
- V2. Registr: souběžné zápisy dvou procesů, duplicita přes symlink, kolize id, neznámé klíče, poškozený soubor.
- V3. Core s holým remote: odmítnutý push přes `pre-receive` hook (refy, index a soubory bajtově stejné), PR přes tests/providers/gh_fake.py, `plan_changed`, `dirty_paths`, cizí staged práce přežije, běh s živým pid blokuje a s mrtvým ne, update nahradí výchozí a nechá upravené, kopie `.factory/` HAIFA dá jen manifest.
- V4. Spouštěč: stub proces, který zabere řádek přes `TaskRunStore.claim`, a jeden skutečný `task run` přes `validation.worker`.
- V5. Web: izolace dvou rep, `unknown_repo`, matice S2, limity `fs/dirs`, přehled nezapíše a odpoví do 1 s, i když jiné spojení drží `BEGIN IMMEDIATE`.
- V6. Vitest: routy, API base, stream při přepnutí a skrytí, reset obrazovek, přepínač, řazení přehledu, stavy průvodce, blokátory plánu.
- V7. Playwright: F3 dál prochází a nový test pokryje tok více repozitářů (M15).

## 9. Rizika navíc

- R14. Schválit a Commitnout backlog posunou HEAD hlavního checkoutu, takže každá agentní fáze, která v tom repu zrovna běží, selže na „HEAD moved“ (run/guard.py:175-179). Platí to už dnes, přehled a souběžné běhy to zhorší. Doporučení: samostatný úkol, kde hlídač přijme fast-forward base provedený samotnou factory. Tento návrh to nemění.
- R15. Prohlížeč má 6 spojení na hostitele pro všechny záložky. Proto se stream ve skryté záložce zavírá a přehled SSE nepoužívá.
- R16. Commit bez checkoutu nespustí pre-commit hooky. Repo, které kontroly vynucuje na serveru, push odmítne a zbývá PR.
- R17. Instalace přes PR blokuje běhy, dokud se PR nesloučí a base nedorovná (Dorovnat base).
- R18. Souběžné procesy nemají limit, stejně jako dnes (D10).
- R19. Dialog na macOS se může otevřít za prohlížečem. Napsaná cesta funguje vždy.

## 10. Dodání

| Úkol | Závisí na | Potom funguje |
|---|---|---|
| M1 ochrana zápisů API | — | cizí zápis odmítnut, jinak beze změny |
| M2 běhy jako procesy | — | Zastavit, souběh, běhy přežijí restart |
| M3 registr a API více rep | M1, M2 | registr a API v testech, `factory obs` dál pro jedno repo |
| M4 výběr složky | M3 | API složek a dialogu |
| M5 API přehledu | M3 | API přehledu |
| M6 `factory check` | T1, T16, T17 | kontrola z terminálu |
| M7 commit konfigurace | M6 | `factory config commit` a `pull` |
| M8 `init` s commitem | M7, T16 | instalace z terminálu jedním commitem |
| M9 `factory update` | M8 | aktualizace z terminálu |
| M10 API záložky Factory | M3, M9 | kontrola, plán a provedení přes API |
| M11 frontend pro více rep | M3, T3, T4, po T15 | dashboard pro více rep a přepínání |
| M12 přehled | M5, M11 | přehled |
| M13 přidání a správa | M4, M10, M12 | přidání a odebrání v UI, kontrola |
| M14 instalace v UI | M13, T3 až T5, T15 | instalace, aktualizace a commit konfigurace v UI |
| M15 akceptační test | M14 | brána |

Frontendové úkoly M11 až M14 přepisují build s hashi v aifactory/src/aifactory/web/static/, proto běží po jednom a až po frontendovém řetězci plánu 14 bodů (T3 až T15, D28). Backendové úkoly M1 až M10 build nemění a můžou běžet vedle backendových úkolů plánu 14 bodů. M3, M4, M5 a M10 přidávají trasy do web/app.py, případný konflikt vyřeší `factory task resolve`.

## 11. Převzato a zamítnuto

Z B: pořadí od bezpečnosti (M1, M2), CLI před UI, registr až potom, `create_app` jako cesta pro jedno repo, `LiveHub` pro každé repo, logy mimo repo (X1), `GIT_OPTIONAL_LOCKS=0` (X9), proxy Vite (X8), commit bez checkoutu a push před posunem base (AR9, G4), digest bez cíle a zprávy (K5), záruky G1 až G9 jako testy, inspect bez hooků (S5), procházení jen pod domovem (S6), ověření plánu doplněným zdrojem konfigurace (G7), manifest jako samostatný soubor bez varování D4 a instalace bez scouta (OD9).

Z A: průvodce a texty (UX2), přehled řazený podle naléhavosti (UX4), přepnutí se zachovanou obrazovkou (UX3), Zrušit bez zápisu (zde přes dočasnou registraci), oprava falešného harnessu přes `calls.jsonl` (R19), zavření streamu ve skryté záložce (R15), samostatný `factory update` (CL3), Dorovnat base (`catch_up`), výčet kódů kontroly (CL1) a riziko R14.

Vlastní úpravy: `init` bez `--commit` podle T16, POST bez těla povolený, aby M1 nemusel měnit frontend (A i B chtěly měnit `postApi`), přehled po 2 s místo 5 s, API záložky Factory oddělené od UI.

Zamítnuto: jeden sloučený stream s `focus` (A AR5, zbytečný přepis), plán v paměti serveru (A, nefunguje v CLI), logy v `.factory/data/launch/` (A, hlídač), `fs/dirs` kdekoli (A), založení prvního projektu instalací (A D21, řeší T14 a T15), úkol na `test_command` (A BL0, B OD10, řeší T1), `init` jako aktualizace (B OD14, sémantika T16), commit jako výchozí chování `init` (A, B, T16 zakazuje), nenainstalované repo trvale v registru (B OD16).

## 12. Kroky engineera

- A1. Rozhodnout D14 až D28.
- A2. Zapsat D14 do docs/decisions.md.
- A3. Po M11 změnit `just dash` na `factory obs --repo .` (justfile patří operátorovi).
- A4. Po M15 projít tok ručně: přidat HAIFA a haifa-sandbox, pustit task v každém a sledovat přehled.