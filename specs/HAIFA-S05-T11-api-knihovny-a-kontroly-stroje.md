# HAIFA-S05-T11 — API knihovny a kontroly stroje

## Cíl a rozsah

Doplnit globální API více-repozitářového dashboardu o kontrolu stroje a týmovou knihovnu. HTTP adaptéry volají existující core stejně jako CLI; vracejí obálku `ok/data/error/warnings` z `aifactory.skill.envelope`. Žádný endpoint nepotřebuje vybrané repo ani nainstalovanou Factory v repu.

Implementovat pouze backend, pytest testy a dokumentaci. Neměnit frontend, položky konfigurace repa, Factory tab ani knihovní pravidla core. Povolené cesty jsou `aifactory/`, `justfile`, tento spec a `app_docs/HAIFA-S05-T11-api-knihovny-a-kontroly-stroje.md`; justfile není třeba upravovat. Chráněné adresáře a hlavní checkout se nemění. Builder neprovádí git workflow.

## Zjištěné stavební bloky

- `web/app.py:create_multi_app` má globální routes pod `/api`, `app.state.home`, `registry`, `user_home` a `check_machine`. Repo routes jsou oddělené přes `RepoScope`; nové routes patří přímo do globálního seznamu, nikoli do `_repo_routes()`.
- `_starlette` již používá `WriteGuardMiddleware` (M1: Origin, Sec-Fetch-Site, JSON) i `StaleCodeMiddleware`. Nové POST routes budou automaticky chráněné. Zachovat oba middleware.
- `web/factory.py` ukazuje existující vzor neblokujícího `threading.Lock`, 60s cache rozlišené podle offline, validace whitelistů a převodu výjimek do obálek. Nepoužívat jeho repo check, manifest nebo repo zámek pro globální knihovnu.
- `check.run_check(start, offline=..., machine=..., require_repo=False)` mimo git repo vrací stroj a knihovnu. Samotné `require_repo=False` mimo-repozitářový režim nevynucuje: předaná cesta musí skutečně být mimo repo. `CheckReport.to_json()` a zpráva z `cli._check` určují datový kontrakt.
- `library.remote.library_status(fetch=False, environ=...)`, `store.list_items`, `store.show_item` a `library.multi_repo.where` poskytují požadovaná čtecí data. `where` používá registr v HAIFA_HOME a `repo_items(save_cache=False)`, rozpoznává aliasy slotů a zachovává chybové stavy jednotlivých rep.
- Zápisy: `store.init_library(name, environ, remote=...)`, `remote.clone_library(url, branch, environ)`, `store.import_item(source, type, name, dry_run=..., environ=...)`, `reseed.seed_library(take, dry_run=..., environ=...)`, `remote.pull_library`, `remote.push_library`.
- Import a seed mají dry-run plán s digestem a `WriteResult.to_json()`. Init a clone dry-run nemají. Žádný z těchto čtyř knihovních zápisů nemá parametr `expect`. Proto plánování init/clone a porovnání digestu patří do web adaptéru, nikoli do nové implementace knihovního core.
- Core drží blokující `$HAIFA_HOME/library.lock`; zachovat jej. Web zámek je samostatná ochrana před souběhem HTTP zápisů. Neobalovat volání core dalším držením stejného flocku: hrozí deadlock.
- `store.import_item` vyhodnocuje domov přes `Path.home()` a kontroluje i symlinky uvnitř stromu. HAIFA_HOME je úložiště aplikace, nikoli hranice importu.

## Soubory a organizace

1. Přidat `aifactory/src/aifactory/web/library.py`: globální stav, striktní parsování requestů, čtecí kompozice, read-only plány a dispatch zápisů, překlad chyb a CLI warnings.
2. Přidat `aifactory/src/aifactory/web/machine.py`: mimo-repozitářová kontrola a cache. Pokud společný stav/cache lépe vychází v `web/library.py`, ponechat machine modul malý; knihovní a strojová kontrola musejí sdílet invalidaci.
3. Upravit `aifactory/src/aifactory/web/app.py`: imports, tenké async handlers, globální routes a inicializace jednoho globálního stavu na `create_multi_app`. Blokující core/git běží přes `run_in_threadpool`. Doplnit modulový popis API.
4. Upravit `aifactory/src/aifactory/skill/codes.py`: rozšířit popis existujícího `busy` o globální knihovní zápis a popis `plan_changed` podle nového použití. Nevytvářet nové kódy, pokud stačí stávající.
5. Přidat `aifactory/tests/web/test_web_library.py` a `test_web_machine.py`; případně malý sdílený fixture helper v `tests/web/`. Čerpat ze stávajících `multi_repo.py`, `test_web_factory.py`, knihovních testů a `tests/fake_exe.py`.
6. Popsat API a ověření v `app_docs/HAIFA-S05-T11-api-knihovny-a-kontroly-stroje.md`.

## Domov, prostředí a globální stav

Vytvořit stav pro celou aplikaci: jeden neblokující write lock a cache kontrol podle offline. Nesmí být per-repo ani per-action; apply, pull a push soutěží o stejný zámek. Získat jej před přepočtem apply a držet až do ukončení core operace, uvolnit vždy v `finally`. Nezískání znamená HTTP 409 `busy`, bez čekání na dokončení první operace. Čtení/plánování nezískává write lock.

Pro knihovní volání sestavovat explicitní mapping prostředí z aktuálního prostředí serveru s HAIFA_HOME nastaveným na `app.state.home`. Respektovat existující HAIFA_LIBRARY override jako CLI. Tím se registr a knihovna nerozejdou při `create_multi_app(home=...)`. Nikdy kvůli requestu neměnit `os.environ`, cwd ani `Path.home` globálně. Request nesmí přepsat HAIFA_HOME, HAIFA_LIBRARY nebo cílový adresář knihovny.

Kontrola stroje musí používat stejný HAIFA_HOME: použít tenký delegující `Machine` adaptér nad `app.state.check_machine` nebo `SystemMachine`, který sjednotí `environment()` i `env()` pro HAIFA_HOME a ostatní metody deleguje. Předat existujícímu core. Testy ověří explicitní home odlišný od procesního prostředí.

## Čtecí kontrakty

### GET /api/machine/check?offline=&fresh=

Použít `_flag` a stejné hodnoty jako Factory tab; chybná hodnota je HTTP 400. Start kontroly zvolit nezávisle na cwd dashboardu a registrovaných repech: skutečně nerepozitářovou cestu (např. ověřený systémový temp adresář, s fallbackem na kořen filesystemu). Nezakládat trvalý adresář v HAIFA_HOME a nepoužívat knihovnu, která sama je git repo. Test musí běžet i když cwd leží v repo nebo HAIFA_HOME je umístěný pod repo.

Volat `check.run_check(..., require_repo=False)` a vracet celý report s `in_repo=false`, repo/state/base/commit null a nálezy pouze scope machine/library. Přidat `checked_at` v UTC a `cached`. HTTP 200 jak pro úspěch, tak pro `checks_failed`; neúspěšná obálka nese report v data a stejnou zprávu jako CLI (`N error(s): codes`). Ne přidávat repo manifest či registry finding trace_db_shared.

TTL 60 sekund měřit monotónními hodinami. Oddělit online a offline položku cache, cachovat i report s chybami. `fresh=1` přepočítá daný režim. U cache nevracet sdílený mutovatelný dict. Po úspěšném apply/pull/push cache vyprázdnit; při výjimce po pokusu o mutaci ji také bezpečně invalidovat.

### GET /api/library

Bez fetch spojit `library_status(fetch=False)` a `list_items()`. Data pro existující knihovnu: `{exists: true, ...status, items: [...]}`. Zachovat všechna status pole CLI a metadata položek (`type`, `name`, `version`, `short_version`, `commit`, `date`, `author`). Přidat každé položce `repo_count`.

Použití získávat přes `multi_repo.where(type, name, environ=...)`; počet je počet unikátních `repo.id` s řádkem používající položku (`slot != null`), nikoli počet slotů, ani počet všech registrovaných rep. Započítat i modified/outdated/diverged/missing položky s existujícím slotem. Řádky repo_missing či chyby bez slotu neznamenají prokázané použití. Žádné nové rozhodování o item_state.

Pokud knihovna chybí (`library_missing`), vrátit HTTP 200 úspěšnou obálku s data přesně `{exists: false}`. Nepřekládat ostatní chyby na neexistenci. Při dosud neexistujícím registru vracet nulové počty a prázdné použití, registr nezakládat. Ošetřit pouze `registry_missing`, jiné core chyby zachovat. Nedělat fetch, init nebo migraci při GET. Vrátit warnings kompatibility a seed_update_available ve stejném znění jako `cli._library_remote`.

### GET /api/library/items/{type}/{name}?version=

Data jsou `store.show_item(type, name, version, environ)` doplněná o `repos` ze `multi_repo.where(...)["repos"]`. Zachovat CLI soubory včetně content/binary/executable, historii a chybové issues. Verze určuje zobrazované soubory; použití ukazuje aktuální stavy rep jako CLI where. Alias slotu musí být zachovaný. Bez registru repos=[]; chybějící knihovna či položka není úspěšný prázdný detail.

`show_item` má existující odvozenou history cache; nezavádět kvůli ní nový režim core. Kontrola stroje a plánování knihovnu, její refs ani persistentní home soubory nezapisují.

## Requesty a plány

Plan přijímá pouze `{action, options?}`. Apply pouze `{action, digest, options?}`; digest je neprázdný string. Whitelist akcí a jejich options:

| action | options | core při apply |
| --- | --- | --- |
| init | `name?: string`, `remote?: string` | `store.init_library` |
| clone | `url: string`, `branch?: string` | `remote.clone_library` |
| import | `path: string`, `type: ItemType`, `name?: string` | `store.import_item` |
| seed | `take?: string[]` | `reseed.seed_library` |

Odmítat neznámá pole/options, neobjektové options, nesprávné typy, prázdné povinné stringy a neznámé akce jako HTTP 400 `usage_error`. Použít core ITEM_TYPES. Seed take ověřuje existující core. Nelze přijímat soubory, contents, patch, plan, prostředí, commit, target ani libovolné kwargs; nepředávat neověřený dict do core. Pull/push mohou mít prázdné tělo nebo `{}`, jiné options odmítnout.

### POST /api/library/plan

Výsledná data obsahují `action`, normalizované `options` (URL redigované pro výstup), `library`, `head`, `digest`, `items`, `files`, `blockers` a příslušná core pole. Import a seed jsou přímo dry-run `WriteResult.to_json()` s warnings; zachovat jejich obsah a původní core digest jako `core_digest`. API digest musí být vázaný i na action/options, cílovou knihovnu, core digest a relevantní pozorovaný stav, aby nebyl zaměnitelný mezi akcemi či cestami. Hashovat kanonicky serializovanou strukturu SHA-256 s pevnou doménou/verzí. Nehashovat časy, cache flag, nahodilé UUID, warnings nebo volný text chyb.

Init: read-only plán připravit v web adaptéru z `store.packaged_seed()`, seed_versions a existujících `PlanItem`/`PlannedFile` serializací. Nevytvářet git repo a nevolat init_library kvůli náhledu. Ukázat create soubory seedu a záměr vytvořit library.yaml se jménem, formátem a seed verzemi. UUID vznikne až v core při apply: v náhledu metadata výslovně označit jako generovaná, nepředstírat identické UUID ani identický core digest initu. Digest svázat s názvem, remote, seed verzemi/módy, cílem a stavem obsazení cíle. Pro existující neprázdný cíl blocker library_exists; identitu ověřit existujícím check_identity nad existujícím rodičem bez založení home. Pro remote číst refs a ověřit prázdnost jako CLI, žádný fetch/push.

Clone: náhled je read-only operační plán (`items/files` prázdné, informace o remote, požadované/vybrané větvi a remote_head). `git ls-remote --symref` přes existující `providers.git.run_bytes`, s argumenty jako seznam, poskytne HEAD/větev/OID bez lokálního clone/fetch. Digest zahrne vybranou remote větev/OID a stav cíle; helper ls_remote_refs sám nestačí, vrací jen jména refs. Prázdný remote nebo chybějící vybraná větev odpovídá invalid_library/clone_failed; obsazený cíl library_exists. Bez stažení objektů nelze ověřit library.yaml: tuto validaci provede stávající clone_library při apply a zachová jeho cleanup. Neklonovat dočasně jen pro plán a nepřidávat druhou implementaci validace remote knihovny.

Dry-run import/seed používá beze změny core validaci a souborové diffy. Zjistit read-only blockers odpovídající dostupnému lokálnímu stavu (dirty, identita, známé ahead/behind); autoritativní remote kontroly a fetch ponechat zápisu core. Externí read-only git ls-remote je dovolen pro plán init/clone; GET status ani machine check nefetchnou. Plány neobsahují klientem dodaný souborový obsah.

Běžné zjistitelné blokátory uvést v `blockers: [{code,message,...}]` v úspěšném náhledu. Nevalidní request/import zdroj vrací příslušnou chybu. Tajné údaje z URL nezahrnout do veřejné options, data, warnings ani chyb; používat stávající redakci core. Původní URL zůstává pouze vstupem core v rámci requestu.

### POST /api/library/apply

Pod jedním globálním web zámkem znovu normalizovat options a spočítat plán; nevěřit uloženému plánu ani souborům od klienta. Pokud je plán spočitatelný a digest se liší, HTTP 409 `plan_changed` s novým plánem v data. Pokud plán již nelze spočítat kvůli blockeru (např. zmizelá knihovna), vrátit blocker. Při shodném digestu odmítnout blockers HTTP 409 s původním kódem a plánem v data. Potom volat konkrétní skutečný core zápis z tabulky.

Úspěšná data zachovají celý CLI výsledek (`WriteResult.to_json()` nebo clone status) a mohou přidat action a `reviewed_digest`. Vrácený `digest` uvnitř WriteResult je digest core výsledku; nesrovnávat jej s API digestem. Preserve warnings i no-op `committed=false`. Žádné ruční commity/pushy nebo rollback mimo core.

Ochrana digestu a busy platí pro HTTP akce této aplikace. Stávající core flock dál serializuje CLI zápisy; nový web zámek jej nenahrazuje. Core nemá expect, takže nelze tvrdit atomickou ochranu před změnou provedenou externím CLI mezi web přepočtem a získáním core flocku. Nepřidávat monkeypatch core, globální přepínání funkcí ani změnu jeho zámků. Dokumentovat tento limit; v tomto tasku se core nemění. Stejně jako u CLI může remote během samotné operace pokročit a core následně odmítne push/behind.

### POST /api/library/pull a /push

Volat pull_library/push_library beze změny jejich semantiky, pod stejným web zámkem jako apply. Vrátit celý CLI dict v obálce. Pull pouze fast-forward, push nikdy force. Žádný nový požadavek na digest pro tyto dva CLI endpointy.

## HTTP chyby

Centralizovat převod LibraryStoreError a ProviderError se zachováním code/message/data/issues (`Issue.to_dict()`). Používat envelope helpers, ne Starlette detail objekty.

- 400 usage_error / invalid_value pro nevalidní API argumenty.
- 403 outside_home pro zdroj importu nebo vnitřní symlink; zachovat M1 cross_origin.
- 404 unknown_item, unknown_version a library_missing při detailu.
- 409 busy, plan_changed a provozní blokátory library_exists, library_missing při zápisu, library_dirty, library_behind, library_diverged, remote_not_empty, git_identity_missing, no_remote, invalid_library, not_in_seed a invalid_item při provedení.
- 502 push_failed, fetch_failed, clone_failed, pull_failed; commit_failed a neočekávané chyby zůstávají 500.
- Zachovat 415 unsupported_media_type a 409 stale_code z middleware.

Import path z options vyhodnotit pod `app.state.user_home.resolve()` pro web hranici a poté stejně přes core (Path.home). Použít existující store._check_source, který kontroluje realpath a vnitřní symlinky, v obou fázích. Výchozí user_home odpovídá Path.home; testy jej sjednotí. API nesmí rozšířit hranici povolenou CLI. Pokud je testovací user_home užší, uplatní se obě kontroly. Chyby outside_home mají přednost před čtením zdroje.

## Testovací plán

Nové testy jsou TestClient proti create_multi_app s temp HAIFA_HOME, bez frontend build. Každou odpověď kontrolovat přes envelope_problems a HTTP status. Git remotes výhradně lokální bare repo. Identitu a signing nastavit jen ve fixture. Importy umístit do falešného domova a `monkeypatch Path.home` pouze v testech; nedotýkat se skutečného domova. Pro fake executables použít existující make_executable.

1. Prázdný domov bez registru: library GET přesně exists=false, machine report mimo repo, žádné repo potřeba; kontrola/plány nezaloží knihovnu ani persistentní cache/lock soubory.
2. Machine: falešné binárky (včetně --version/login odpovědí) a falešný Machine pro počty volání; úspěch i checks_failed s CLI zprávou, scope machine/library, online/offline, neplatné flags. Monotónní hodiny monkeypatchnout: hit před 60 s, miss v 60 s, fresh přepočet, oddělené režimy. Žádné časové sleeps. Cwd v repu nesmí změnit globální report; explicitní app home i HAIFA_LIBRARY se projeví v nálezech.
3. Init přes plan/apply bez remote a s prázdným bare remote: opakovaný plán stejný digest, plán nezapisuje, apply vytvoří seed/library.yaml a případně remote. Existující knihovna i remote_not_empty jsou blockers; změna obsazení cíle vede k odmítnutí.
4. Clone přes plan/apply z platného lokálního remote v novém home; větev i HEAD. Změnit remote mezi plan/apply => plan_changed. Neplatná library.yaml se odmítne při apply a nenechá rozpracovaný cíl.
5. Import workflow i stromové položky: plán obsahuje diff, apply importuje, detail soubory/historie metadata, ?version vrací starší obsah, opakovaný import je no-op. Absolutní/relativní cesta ven z domova, ../ a symlink ven (včetně vnitřního) => 403 a beze změny refs.
6. Seed: dry-run/aplikace/no-op a take na týmově změněné položce. Použít známý seed fixture/monkeypatch packaged_seed, ne model ani síť.
7. plan_changed: změna importovaných bajtů, executable bitu či knihovního HEAD, změna action/options a remote OID. Vše vrací 409 s novým plánem a nezmění místní/remote refy. Testovat i nový request s novým digestem jako úspěšné pokračování.
8. busy: první core zápis pozastavit threading.Event; současný apply/pull/push musí ihned vrátit 409. Po dokončení i po výjimce je zámek znovu použitelný. Eventy s timeout/finally, žádné křehké sleep. Nezávislost na repo locku a společný zámek napříč actions.
9. Pull/push: přidat commit druhým lokálním klonem, pull fast-forward; lokální commit a push; no-op; no_remote, dirty, behind, diverged. pre-receive hook odmítne push => 502 push_failed, core chrání lokální ref při import/seed/init a remote ref se nezmění. Ověřit uvolnění busy zámku a invalidaci check cache.
10. Dvě registrovaná repa instalovat pomocí existujícího core. Jedno s alias slotem; několik slotů v jednom repu počítat jen jednou. Ověřit repo_count=2, detail repos se sloty a stavem synced/modified/outdated; chybějící repo zachová repo_missing a neznemožní detail.
11. Bez fetch GET: spy na fetch_remote / subprocess argumenty nebo snapshot FETCH_HEAD a refs. Kontrola nedělá auth v offline, GET library nezapisuje knihovní refs.
12. M1: cross-origin a non-JSON POST na plan/apply/pull/push mají existující 403/415; stale_code zůstává 409. Neznámé fields a dodaný content/files jsou odmítnuté. Ověřit redakci URL bez skutečné sítě.

## Ověření a předání

První cílený běh: `just test tests/web/test_web_library.py tests/web/test_web_machine.py tests/web/test_web_factory.py tests/web/test_web_write_guard.py tests/web/test_web_repos.py`.

Potom povinně `just test`, `just typecheck`, `just lint` z kořene worktree. Posuzovat exit status, opravit příčiny selhání. just test zahrnuje frontend typecheck/Vitest; UI se nemění, browser/E2E navíc není nutné. Nepřidávat závislosti ani měnit recipes kvůli obcházení kontrol.

Dokumentace uvede příklady requestů pro všechny čtyři actions, datové tvary čtení a plánů, rozdíl API digest/core digest, 60s cache a fresh/offline, import pod uživatelským domovem, busy/errors, omezení clone preview a souběžného externího CLI. Shrnutí buildera uvede změněné soubory a výsledky všech tří povinných příkazů. Implementace je hotová, když všechny požadované endpointy a regresní scénáře projdou a diff zůstane v povolených cestách.
