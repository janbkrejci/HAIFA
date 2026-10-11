# HAIFA-S05-T12: API položek repa, onboardingu a operací ve více repech

## Cíl a hranice

Rozšířit existující API Factory o stavy položek, add/set/remove/export/revert/onboard/adopt a plán add/update pro vybraná registrovaná repa. API musí volat existující core jako CLI. Zachovat init/update/config_commit, M10 obálky, bezpečnost zápisů, plán/digest/provedení, cíle base/pr a per-repo busy. Frontend ani nová logika core nejsou součástí úkolu.

Implementovat pouze v `aifactory/`; dokumentaci v `app_docs/HAIFA-S05-T12-api-polozek-repa-onboardingu-a-operaci-v.md`. Tento spec má předepsanou cestu. `justfile` měnit jen pokud je skutečně potřebné; existující příkazy již stačí. Nezasahovat do vendor/, prototype/, adws/, .factory/, CLAUDE.md ani engineer-owned dokumentů. Sssf fixture smí kopírovat snapshot do dočasného testovacího repa.

## Zjištěná rozhraní

- `web/app.py`: `factory_plan`, `factory_apply`, `_repo_routes()`, `create_app(repo)`, `create_multi_app(home=...)`. RepoScope sdílí `_repo_routes()` mezi `/api/` a `/api/repos/{repo_id}/`. Apply již drží `factory.exclusive(ctx.factory)`, má threadpool, write guard a `_failure`.
- `web/factory.py`: striktní parsery, Request, OPTIONS, `_call`, `_core_errors`, STATUS, plan/apply, FactoryState s lockem a check cache. Dnes jen init/update/config_commit. `_call` nepředává dashboardové prostředí; plan předpokládá jednotný `remote` a apply zahazuje většinu result polí. Tyto předpoklady rozšířit pro nové typy výsledků.
- `library/state.py::repo_items(path, base=None, environ=None, save_cache=True)` vrací CLI JSON včetně manifest/library/items a verzí. Bez base porovnává working tree; base="" znamená nakonfigurovanou base. `save_cache=False` nic nezapisuje.
- `library/config_edit.py::run_config(command, path, type, name, dry_run, commit, pr, expect, message, environ, **options)` řeší všechny item akce. Plan/result již serializují digest, blockers, změny, bindingy, validaci a export `library_plan`/`library_commit`.
- `library/update.py::run_update` a `plan_update` přijímají `item`, `take`, `merge`, `migrate` jako sekvence. Stávajícímu API chybí `item`; přidat jej pro cílené aktualizace i bulk apply.
- `onboard/onboard.py::run_onboard(path, commit=False, pr=False, expect=None, message=None, keep_local=(), names=(), workflows=False, environ=None)`: bez commit plánuje; s commit znovu plánuje a kontroluje expect. JSON obsahuje repo publish část, `library_plan`, `report` s kódy, text `message`, remote (objekt), exclude a warnings. Library se zapisuje první; chyba repa může již nést `library_commit` a fix.
- `onboard/adopt.py::adopt_repo(path, dry_run=False, environ=None)` zapisuje jen knihovnu; nemá expect/pr/message. AdoptResult má repo commit jako zdroj, `plan` knihovny (nebo null), items, warnings, library_commit a repo_changed=false.
- `library/multi_repo.py::run_repos(command, selection, dry_run, commit, pr, expect, message, environ, **options)` používá registry z HAIFA_HOME, plánuje sekvenčně a izoluje chyby po repech. Výstup má command/repos/dry_run/partial, řádky repo/plan/result/status/error. S `dry_run=True, commit=True` vrací committed-target plány a jejich blockers; blocker v platném dry-run plánu nemusí nastavit partial.
- `web/library.py::environment(home)` poskytuje dashboard HAIFA_HOME při zachování ostatních env voleb, `exclusive(GlobalState)` používá existující globální lock knihovny a invalidate pro machine cache. `create_multi_app` toto state již má; `create_app` dnes home/library state nemá.

## API smlouva

### Stavy

Přidat `GET /api/repos/{id}/factory/items` a přes společné repo routes také `GET /api/factory/items` v create_app. Vrátit `envelope_ok(repo_items(...))`, beze změny state názvů a verzí core. Volitelný query parametr `base`: nepřítomný = working tree, prázdný = configured base, jinak reference přijatá existujícím core. Nevyvozovat žádné cesty z requestu. Volat s dashboard environ a save_cache=False přes threadpool, chyby překládat stejně jako ostatní Factory volání.

### Plán a apply

Zachovat klíče plan `{action, options?, target?}` a apply `{action, options?, target?, digest, message?}`. Identifikátory položek patří do options, nikoliv jako nové top-level klíče. target zůstává base (default) nebo pr; base znamená core commit=True, pr znamená commit=True/pr=True. Worktree apply nepřidávat.

| Akce | Povolené options | Volání core |
| --- | --- | --- |
| add | type, name, slot, harness, model, thinking, agent | run_config("add", ...) |
| set | type, name, harness, model, thinking, tools, writes, color | run_config("set", ...) |
| remove | type, name, prune | run_config("remove", ...) |
| export | type, name, slot | run_config("export", ...) |
| revert | type, name, to | run_config("revert", ...) |
| update | item, take, merge, migrate | run_update(...) |
| onboard | keep_local, names, workflows | run_onboard(...) |
| adopt | žádné | adopt_repo(...) + kontrola digest v adaptéru |

`slot` odpovídá CLI --as. U item akcí jsou type/name povinné neprázdné stringy; type patří do ITEM_TYPES. set může jen agent, což validuje core. `tools`/`writes` jsou CLI stringy (CSV, včetně CLI významu prázdného stringu), nikoli seznamy; ostatní bindingy a slot/to jsou stringy. `prune` a onboard `workflows` jsou skutečné bool. update hodnoty jsou seznamy stringů. Onboard `keep_local` je seznam `TYPE/NAME`, `names` seznam `TYPE/NAME=NEW`, stejně jako opakované CLI --keep-local a --name; v adaptéru převést na typované tuple pro core. Pro sémantickou validaci názvů a konfliktů použít core, nepřepisovat jeho pravidla.

Neznámé klíče, chybné JSON typy, chybějící povinné identifikátory, neobjektové options a prázdný digest jsou 400 usage_error. Sémantické invalid_value/conflicting_options atd. mají zachovat Factory 422. Odmítnout top-level i option klíče files/path/content, neinterpretovat ani neaplikovat zaslaný plán. Binding `writes` a existující init directory settings jsou deklarativní CLI volby, ne instrukce k libovolnému zápisu z requestu. Apply vždy vychází z root z RepoContext a čerstvého core plánu.

Plán vrací `action` a kompletní core JSON v data, ne vybraný podmnožinový náhled. Zachovat core digest; onboard report kódy, message, library_plan i remote objekt se nesmí poškodit obecnou normalizací remote. Pro init/update/config_commit zachovat dosavadní chování remote. Apply zachová dosavadní společná pole commit/pushed/pr/committed/advanced/branch/warnings a přidá dostupné action-specific údaje (zejména library_commit, export/revert detail a onboard report/message). Adopt výsledek ponechat celý; jeho `commit` označuje zdrojový repo commit a `library_commit` provedený zápis, nikdy netvrdit pushed/PR repa.

Adopt plán musí mít top-level digest i při no-op, kdy core plan=null. V adaptéru vytvořit SHA-256 nad kanonickým JSON s verzovanou doménou, action, root/base/source commit, library identitou/headem a kompletním stabilním dry-run výsledkem (items, library plan). Do identity nedávat čas ani apply výsledky. Při apply pod locky znovu zavolat dry_run, porovnat digest, při změně vrátit 409 plan_changed s novým plným plánem; teprve pak zavolat adopt_repo(dry_run=False). Prázdná options jsou jediná varianta. Protože CLI adopt nemá PR ani commit message, odmítnout target=pr nebo explicitní nenulovou message pomocí conflicting_options (422); target=base/default slouží jen sjednocené obálce. Nezavádět nový core parametr ani vlastní import logiku. Ochrana řeší API concurrency; nepřisuzovat adaptéru novou transakční garanci proti externím procesům.

### Více rep

Přidat `POST /api/library/repos-plan` do globálních multi routes. Tělo má pouze `{action, type, name, repos, options?}`; action add/update, povinné type/name jako library identifikátor. `repos` přijímá neprázdný seznam unikátních registrovaných ID nebo CLI string `all` / comma-separated ID. Odmítnout jiné tvary a neznámá ID bez jakéhokoli zápisu. ID nepovažovat za filesystem paths.

Options použít ze stejného Factory parseru: pro add volby add bez type/name, pro update take/merge/migrate; do update core vždy dodat `item=[f"{type}/{name}"]`. Výběr typu/názvu se nesmí ztratit a nesmí vzniknout update všech položek. Pro bulk lze v options navíc uvést target=base/pr (default base), který adaptér odebere před core voláním. Nepřijímat digest/message/commit/dry_run/files a podobné execution parametry.

Volat `multi_repo.run_repos(action, selection, dry_run=True, commit=True, pr=..., environ=dashboard_env, **core_options)`. Nepřidávat novou core multi logiku ani transakci. Výsledek zachovat se všemi řádky, chybami a blockers. Každý existující plán obohatit o `action` a oddělené `apply_options`/`apply_target`, aby jej klient mohl provést se stejným digestem přes příslušné factory/apply. Pro add apply_options obsahují type/name i bindingy; pro update item a resolve volby. Neopisovat celý plán do apply body. Digest a samotný core plan zůstanou beze změny. Řádek s blockers označit v API jako blocked a celkové partial=true, přesto zachovat ostatní dostupné plány. Per-repo chyba vrácená run_repos rovněž nastaví partial. Platný požadavek s částečným výsledkem je HTTP 200 envelope_ok; chyba celé selection/parseru je standardní chybová obálka.

Tato globální route funguje také v create_app pod stejnou `/api/library/repos-plan`: plánuje registry z HAIFA_HOME stejně jako CLI, nevytváří umělé ID ani nevyvozuje repos z explicitních cest. Při chybějícím registry vrátí registry_missing (409). Nové repo trasy fungují v create_app bez registry.

## Konkrétní změny souborů

1. `aifactory/src/aifactory/web/factory.py`: rozšířit ACTIONS/OPTIONS a typed validaci; doplnit helper pro onboard CLI selectors a items view; dispatch na run_config/run_onboard/adopt_repo, update item; environ parametr přenášet všude, kde jej core podporuje. Zachovat podpis `_call(root, req, *, dry_run)` kompatibilní s existujícími test doubles, nebo aktualizovat jejich signatury při přidání optional environ. Oddělit normalizaci nových výsledků a adopt digest. Rozšířit STATUS o relevantní konflikty slot_taken/in_use/item_exists/library_changed_since/already_onboarded/not_installed/source_not_committed/onboarded_in_remote/onboarding_pending/remote_unchecked/library_missing a ostatní skutečné core blockers; sssf_roster_invalid a unknown_version mají odpovídat Factory chybě validace 422. Nepřemapovat nové známé core chyby na náhodné 500. Zachovat issues/data/fix a action v plan_changed i v částečné publish chybě.
2. `aifactory/src/aifactory/web/library.py`: vlastní striktní parser pro repos-plan a adaptér nad run_repos; sdílet Factory option validaci, ne jeho dispatch pro každé repo místo L9 core. Chyby celého požadavku převést Factory helperem, registry výjimky dle jejich existujících kódů. Žádné libovolné kwargs z nevalidovaného requestu.
3. `aifactory/src/aifactory/web/app.py`: handlers factory_items/library_repos_plan, threadpool a obálky, registrace v obou aplikacích, aktualizace API docstringů. V create_app doplnit `home=haifa_home()` a GlobalState; v multi aplikaci používat stávající state. Předávat env z app.state.home do Factory a bulk volání bez globální změny os.environ.
4. Zápisy export/onboard/adopt použijí vedle existujícího per-repo guardu stejný globální library guard jako /library/apply/pull/push; pořadí vždy repo lock, potom neblokující library lock. Busy=409; locky se uvolní při chybě. Invalidate library cache v finally, protože knihovna mohla být zapsána před selháním repo publish; repo check cache rovněž invalidovat, pokud operace mohla změnit stav. Ostatní apply zachovají per-repo nezávislost. Plánování nemusí získávat mutation lock.
5. `aifactory/src/aifactory/skill/codes.py`: zkontrolovat pokrytí všech používaných kódů, doplnit pouze chybějící a upravit významy plan_changed/busy pro nové API. Onboard report codes jsou report řádky, ne nové error codes. Nezakládat nové error kódy bez potřeby.
6. `aifactory/tests/web/test_web_factory.py`, nový `test_web_factory_items.py`, nový `test_web_library_repos_plan.py` (případně malý shared fixture helper v tests/web): reálné core + lokální git. Zachovat stávající M10 testy. Dokumentace v předepsaném app_docs souboru uvede options, requests, plan/apply vazbu, partial a action-specific výsledky/omezení adopt.

## Ověření a regrese

Použít TestClient, dvě registrovaná repa a dočasnou knihovnu, repo i library bare remotes na disku, provider local. Navázat na fixture/helper vzory test_web_factory.py a test_web_library.py. Zvlášť testovat create_multi_app(home=...) odlišné od procesního HAIFA_HOME; library API, item API i bulk musí použít tutéž knihovnu. Žádné modely, hosting CLI ani síťové URL; potřebné harness probes použijí existující fake_exe/FakeMachine.

- GET items odpovídá repo_items(save_cache=False), včetně stavu synced/local/modified/outdated/diverged/missing/unknown ve vhodných fixturách, aliasu a version polí; base query rozliší worktree od base. Plánování nemění files, repo/library HEAD ani remote heads.
- Add agent pod novým slotem, apply se stejnými options a digestem; dependency/skill --agent varianta. Set bindingů nechá prompt a content version nezměněné; model/tools/writes mají CLI význam.
- Export upravené kopie pod novým názvem, library_commit i manifest odkaz; následné add této položky do druhého repa. Ověřit obě bare repo main a knihovnu.
- Update vybraného item s konfliktem a take, apply změní správnou položku a ostatní ponechá. Pro update multi explicitně dvě změněné položky v knihovně, request jedné nesmí aktualizovat druhou.
- Remove nepoužívané položky a prune; použitá položka vrací 409 in_use s used_by. Revert na manifest/head funguje a unknown_version je správná obálka.
- Onboard sssf_repo fixture z tests/onboard/onboard_repo.py; nastavit provider local, lokální origin. Plan má source=sssf, library_plan, report.code a message. Apply zapíše knihovnu před repo, manifest a bare main; původní adws bytes se nezmění. Pokrýt keep_local/names/workflows převod i špatné selector tvary. `onboarded_in_remote` simulovat druhým checkoutem téhož bare remote; nečerstvý lokální repo apply odmítne 409 s blockerem/fix.
- Adopt již onboarded repa s chybějící položkou knihovny: dry-run stabilní digest, import pouze do library, repo checkout i bare HEAD beze změny. Pokrýt no-op digest, změnu library nebo repo base mezi plan/apply -> 409 plan_changed s novým digestem a bez zápisu, warnings library_mismatch/unknown a library_missing clone doporučení podle core.
- Bulk plán dvěma repům: dvě použitelná rows/digests lze provést samostatně se zpětně dodanými options; třetí varianta se zablokovaným jedním repem má partial=true a dobrý plán zůstane použitelný, plánovací call neprovede ani jeden. Pokrýt all, explicitní selection, unknown/duplicate IDs a chybějící adresář registrovaného repa.
- Bezpečnostní parametrizované testy odmítnou request paths/contents/files, neznámé options i chybné bool/list/string hodnoty, prázdný digest a neobjektový JSON. Ověřit write guard u nového POST.
- U nových item akcí regrese stale plan, blocker, push refusal ->502 push_failed, request message a target pr. U export/onboard zachovat library_commit v chybě po již provedeném library zápisu. Busy thread/event test při new apply zablokuje stejné repo a konkurenční library write, ale nezablokuje běžný apply jiného repa; ověřit uvolnění locků po chybě.
- create_app parametrizovaně ověří nové /api/factory/items a new plan/apply akce; /api/library/repos-plan se skutečným registry i bez něj. Zachovat původní solo init/pull testy.

Spouštět nejdřív focused web testy (`just test tests/web/test_web_factory.py tests/web/test_web_factory_items.py tests/web/test_web_library_repos_plan.py tests/web/test_web_library.py`), podle úprav také `tests/test_skill.py`. Poté povinně `just test`, `just typecheck`, `just lint`; řídit se exit status, nikoli slovy v outputu. Test recipe již spouští frontend testy; frontend/build assets neměnit. Pro plánovací fázi testy netřeba, změnou je jen tento dokument.

## Hotovo

Všechny požadované routes jsou dostupné v obou app režimech, výstupy a chybové obálky zachovávají core informace a M10 smlouvu, multi plán lze provést jen per repo s jeho digestem, request neposílá obsah/cesty pro execution a uvedené testy i typecheck/lint projdou. Builder do reportu uvede změněné files, výsledky těchto checks a případná konkrétní omezení; nesmí nahradit core novou implementací ani rozšířit úkol na UI.
