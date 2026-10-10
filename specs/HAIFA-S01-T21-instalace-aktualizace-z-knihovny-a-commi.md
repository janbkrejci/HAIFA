# HAIFA-S01-T21: Instalace, aktualizace a commit konfigurace z dashboardu

## Cíl a hranice

Doplnit záložku Factory o instalaci do repa bez factory, aktualizaci commitnuté kopie z knihovny, commit necommitnuté konfigurace (D4) a dorovnání lokální base. Každý zápis do repa musí předcházet aktuální náhled a samostatné potvrzení. Server sestavuje soubory a kontroluje digest; frontend posílá pouze action, povolené options, target, message a digest. Pole backlog_dir/specs_dir/docs_dir jsou deklarované volby instalace; nezavádět možnost poslat seznam zapisovaných cest nebo obsah souborů. Registrace repa nadále používá existující API s cestou vybraného repa.

Implementovat přímo v přiděleném worktree. Nespouštět nested factory workflow ani měnit hlavní checkout. Povolené změny jsou pouze aifactory/, případně justfile, tento spec a app_docs/HAIFA-S01-T21-instalace-aktualizace-z-knihovny-a-commi.md. Žádná nová frontendová závislost, změny vendor/ ani prototype/. Mimo rozsah jsou editory agentů/prompty, správa položek, onboarding/převzetí existující instalace a instalace nástrojů. Plánovací fáze neimplementuje a nespouští testovací sady.

## Ověřený výchozí stav

- aifactory/web/src/views/FactoryView.vue načítá pouze fetchFactoryCheck a ukazuje kontrolu, manifest, base a oddělené nálezy repa/stroje. Zachovat toto chování i stávající testy.
- components/repos/InspectCard.vue nabízí pro state=none jen terminálové příkazy. views/ReposAddView.vue předává added do App.vue, které po obnovení seznamu přejde na Factory. POST /api/repos umí repo bez factory registrovat; vrací repo a created. DELETE /api/repos/<id> odstraňuje pouze registraci.
- lib/api.ts obsahuje fetchFactoryCheck a ApiError.data z neúspěšného envelope, ale zatím žádné typované factory plan/apply/pull funkce.
- aifactory/src/aifactory/web/factory.py a web/app.py již poskytují POST /api/repos/<id>/factory/plan a /factory/apply pro init/update/config_commit, s povolenými options, digestem a cílem base/pr. Existuje POST /api/repos/<id>/config/pull bez náhledu a digestu. factory.exclusive serializuje apply/pull, core znovu sestavuje plán a kontroluje blokátory.
- InitPlan obsahuje base/base_sha, files, blockers, digest, provider/remote/azure, adresáře, agents/workflows/bindings, detected a available. detected.harnesses obsahuje installed; available.agents obsahuje name/purpose a výchozí harness/model/thinking. files obsahuje path/action/diff/content/binary, včetně manifestu. Nevytvářet soubory na klientovi.
- Update používá library/update.py a library/config_edit.py. Detail je v update.items (action/state, files se status/diff/ours_diff/theirs_diff) a update.migrations (id/title/path/diff/selected/applied). Výstup aktuálně nemá explicitní informaci, zda lze nabídnout merge. Selectory jsou TYPE/NAME[:FILE] pro take a TYPE/NAME pro merge.
- providers/publish.py počítá digest bez cíle a zprávy: stejný digest lze po push_failed použít pro PR. Přímý push probíhá před posunem lokální base. Plan response target používá direct/pr, request používá base/pr; nepřebírat response target přímo do requestu.
- ConfigStatusBanner.vue pouze vypisuje změny. RepoScreen.vue jej vlastní a spravuje useConfigStatus a sdílené SSE useLive. router.ts podporuje parametry screen routy, repoHref a odkazy na běhy.
- tests/web/test_web_factory.py již ověřuje instalaci s jiným harnessem, odmítnutý push a PR, digest a blokování běhy. E2E využívá Playwright, lokální bare remote, fake executable a tripwire v tests/e2e/f3_repo.py. just web-build produkuje balíček web/static; just test zahrnuje web-test, just e2e běží sériově.

## Navržené soubory a postup implementace

### 1. Typované API a řadič operací

Rozšířit aifactory/web/src/lib/api.ts o diskriminované typy init/update/config_commit plánů, plánovaných souborů, blokátorů, výsledku provedení a náhledu pull. Typy odvodit z výše uvedených Python to_json, nikoli z vymyšleného schématu. Přidat fetchFactoryPlan(request), applyFactoryPlan(request), fetchBasePullPlan() a applyBasePull(digest). Pro průvodce mimo repo URL podporovat explicitní repo ID v těchto helper funkcích; běžné použití dál vychází z apiBase(). Explicitní ID je součást serverem přidělené URL, ne cesta.

Přidat lib/factory.ts pro stav a bezpečné sestavení requestů, inicializaci formuláře a řízení operace. Stav: action, options, target, message, aktuální plán, načítání, potvrzení, provádění, výsledek a strukturovaná chyba. Potvrzení vždy váže snapshot repo ID + action/options/target + digest. Změna voleb ihned zneplatní možnost provést starý plán a zavře dřívější potvrzení. Každá změna přepočítá plán (krátký debounce je přípustný); generation token zahodí opožděné odpovědi. První předvyplnění nesmí vytvořit nekonečný watch cyklus a pozdější odpověď nesmí přepsat uživatelské volby.

Apply není možné bez načteného plánu, při načítání, blokátorech, neověřeném stavu běhů, prázdné změně nebo druhém probíhajícím apply. Potvrzení modálu odesílá snapshot; ještě před odesláním ověřit jeho platnost. Server zůstává autoritou při závodu s novým během nebo změnou repa. Na unmount/repo switch zneplatnit pending odpovědi a potvrzení. Requesty sestavovat explicitně z povolených klíčů, nikdy spreadem celého response plánu.

Zachovat envelope warnings v náhledu i výsledku (pokud jsou mimo data, helper je musí zpřístupnit). ApiError.data použít pro nový plán u plan_changed a chyby s blokátory. Nevydávat chybu not_onboarded za úspěšný plán.

### 2. Sdílený náhled a potvrzení

Přidat components/factory/FactoryOperation.vue (formulář/volby + náhled + provedení), FactoryPlanView.vue, InstallForm.vue a UpdateChoices.vue. FactoryView vlastní kontrolu a spouští tuto sdílenou operaci; průvodce přidáním využije tutéž komponentu s explicitním repo ID. Samostatný renderer celého obsahu nebo patch lze vyjmout do components/review/DiffContent.vue z DiffView.vue; rozšířit lib/review.ts jen o potřebné obecné typy/helpery. Review zachová kontrakt i sbalené sekce. Factory musí používat stejný renderer a diffLines, ne kopii barvení diffů.

Náhled vypíše všechny soubory včetně .factory/manifest.yaml, přidání/změny/smazání a celý obsah nebo nezkrácený patch, prázdné soubory, binární informaci a mode-only změny. Pro obsah použít textovou interpolaci/pre, nikoli v-html. U konfliktu ukázat oba pojmenované diffy proti původní verzi. Obsah od serveru je pouze k prohlížení.

Oddělit varování (např. existující adresář s cizím obsahem), nálezy stroje a blokátory. Nálezy stroje samy nezakazují instalaci; blokátory plánu ano a musí být vidět důvod zakázání. Souhrn pro běžný direct plán: „1 commit na main (a6f3e1c → nový), push na origin/main“. Použít skutečnou base, SHA a remote, žádné hardcoded main/origin. Bez remote netvrdit, že se pushne; u PR popsat větev a PR. Počet v potvrzení vychází z files.

Použít existující components/ui/ConfirmDialog.vue a lib/confirm.ts. Provést otevře vlastní modál „Commitnout N souborů do main a pushnout na origin?“ se skutečnými hodnotami. Zrušení modálu neodešle apply. Pro PR a pull upravit text podle operace. Žádné window.confirm/alert/prompt.

### 3. Instalace a dočasná registrace

InstallForm inicializovat prvním init plánem bez options. Base, provider, azure a adresáře převzít z plánu/detected. Nabídnout local/github/azure; při azure zobrazit organizaci, projekt a repository, při přepnutí pryč neposílat azure. Výchozí agenti planner, builder, reviewer a documenter a workflow simple-sdlc vycházejí z available/default a z počátečního agents/workflows plánu. Další dostupné položky zobrazit podle serveru; neimplementovat jejich editory.

Každý vybraný agent má vlastní {harness, model, thinking}; výchozí hodnoty z available a aktuální bindings. Změna buildera nesmí měnit ostatní. Harnessy nabídnout z detected.harnesses včetně nenainstalovaných a zobrazit varování podle installed. Nehádat model/thinking univerzálně pro všechny harnessy; podporovat hodnoty konkrétní položky a ruční výběr/vstup pro každého agenta, včetně null/nezadané hodnoty. Změny agentů/workflow mohou serverem přidat potřebné agenty (added_agents); zobrazit je a jejich vazby, neztratit už zadané overrides. Každá editace base/provider/azure/adresáře/agenta/vazby/workflow přepočítá plán.

Upravit InspectCard.vue: místo terminálového pokynu pro none nabídnout pokračování instalací. ReposAddView.vue vlastní pending registraci a přechod na druhý krok, vyvolá addRepo a zaznamená created. Může ponechat průvodce na #/repos/add a sdílené operaci předat explicitní repo ID; nevyžaduje další router ani backendový systém dočasných repo záznamů. Dočasnost je vlastnictví průvodce nad nově vytvořenou registrací.

Zrušit/vrátit se před úspěšným provedením odstraní jen registraci created=true, počká na DELETE a poté ukončí krok. Pokud DELETE selže, ukázat chybu a nabídnout opakování; netvrdit, že je repo odebrané. created=false nikdy neodregistrovat existující repo. Zrušení ani generování plánů nesmí vytvořit factory soubory ani commit/push. Při interním opuštění průvodce zajistit stejný cleanup; pending stav držet v App nebo sdíleném modulu, aby unmount neztratil vlastnictví. Po úspěšném commitu nebo PR přestat registraci považovat za dočasnou, emitnout added a obnovit seznam v App. Při reloadu nepoužívat automatický destructivní cleanup neověřené registrace.

### 4. Aktualizace

FactoryView nabídne Aktualizovat z knihovny a požádá o update plán. Formulář zobrazí skupiny „Aktualizuje se z knihovny“, „Ponechá se změna v repu“, „Změněno v obou“ a „Migrace“. Zařazovat soubory podle statusů (take/taken/merged/restore, keep, conflict/unknown); smíšenou položku nezobrazovat jen v jedné zavádějící skupině. same lze uvést úsporně. V konfliktu výchozí volba ponechává repo, Převzít používá serverový selector TYPE/NAME[:FILE]. Sloučit používá celý TYPE/NAME a nesmí být současně v take.

V library/update.py přidat do položky explicitní merge_available, vypočtené ze skutečné dostupnosti původní verze a podporovaných textových jednotek. Je-li nutné ověřit čisté sloučení/validaci, použít existující merge funkce v dočasném prostoru; nic nezapisovat do repa a nespouštět model. Sloučit nabídnout jen při true. Nepředpokládat, že všechny nebinarni soubory jdou sloučit. Neúspěšné zvolené sloučení ukáže merge_conflict a neumožní potvrdit zastaralý plán. Zachovat core semantics a doplnit testy library/update.

Migrace jsou checkboxy dle id s diffem; zaškrtnutí posílá options.migrate a přepočítá plán. Bez zaškrtnutí se migrace neaplikuje. Manifest bez onboarding v base vrací not_onboarded: zobrazit jako blokátor s odpovídajícím vysvětlením; neimplementovat onboarding. Při manifestu pouze v pracovním stromu zachovat skutečný config_not_committed a nabídnout commit konfigurace.

### 5. Commit konfigurace, banner, běhy a výsledky

FactoryView nabídne Commitnout konfiguraci pro necommitnuté změny; načte config_commit plán a otevře stejný náhled/modál. ConfigStatusBanner.vue dostane tlačítko a emit commit. RepoScreen.vue přesměruje do repoHref(id, 'factory', 'config_commit'); FactoryView zpracuje parametr pouze jako otevření náhledu, nikdy jako automatické provedení. Takto banner ze všech záložek používá stejnou cestu. Po úspěchu obnovit fresh factory check, useConfigStatus a seznam/stav repa.

Pro přesný počet a odkazy na běhy použít fetchOverview, vybrat pouze aktuální repo a jeho aktivní běhy (process=alive/unknown, ended nepovažovat za aktivní). Aktualizovat při mount, focus a useLive trace.runs_changed/resync, s kontrolou repo ID a generation. Pokud stav nelze ověřit, nepovolit zápis do base. Text „V repu běží N běhů, počká se, až doběhnou“ doplnit odkazy repoHref(id, 'runs', run_id). Zakázat přímé provedení/zápis a pull; plánování dál funguje. PR lze nabídnout jen pokud ho serverový plán povolí, nepřepisovat serverové run_in_progress blokátory. Běh spuštěný mezi náhledem a apply zachytí server, UI obnoví stav bez automatického opakování.

plan_changed: převzít validní nový plán z ApiError.data nebo jej znovu načíst s aktuálními options, vysvětlit změnu a vyžádat nové ruční Provést + potvrzení. Nikdy neopakovat apply automaticky.

push_failed: ukázat důvod a „V repozitáři se nic nezměnilo“ pro odmítnutý přímý push podle stávající transakční záruky. Nabídnout „Otevřít jako PR“ se stejnými options a digestem. Přepnutí na PR vyžádá PR náhled a nový modál; zachová-li server digest, poslat stejný. Změní-li se, použít standardní nové potvrzení změněného plánu. Po úspěchu zobrazit SHA nebo PR odkaz, fresh kontrolu a „Otevřít backlog“. U PR připomenout, že běhy použijí změnu po merge a Dorovnat base; žádné automatické merge/pull.

### 6. Dorovnání base s náhledem

Současný config/pull zapisuje bez plánu. Doplnit nutný backendový náhled v web/factory.py, web/app.py, config/commit.py a providers/publish.py, plus odpovídající testy. Přidat GET /api/repos/<id>/config/pull/plan: base, remote, before/after SHA, změněné soubory s diffem/obsahem, blockers, digest a případná varování. Náhled načte remote stejně jako stávající operace, ale neposune lokální base ani checkout. Digest svázat s repo/base/remote a before/after; použít samostatné deterministické schéma pro pull.

POST config/pull z dashboardu přijímá pouze digest, vyžaduje jeho přítomnost a revaliduje plán před posunem. Přesun remote mezi náhledem a potvrzením vrátí plan_changed s novým plánem. Přenést expect do core pull_config/pull_base jako volitelný parametr, aby CLI bez expect zachovalo kompatibilitu; dashboardová route digest vyžaduje. Zachovat kontrolu dirty_base, divergence, no_remote a živých běhů i serialized ochranu při zápisu. Při plan_changed ani blockeru nezměnit ref/checkout. Znovupoužít existující git diff/blob a publish PlannedFile renderer, ne vlastní práci s neověřenými cestami.

Dorovnat base nabídnout při nálezu/check.behind > 0 či base_behind a po PR jako následný krok. Otevře tento náhled a vlastní potvrzení. Po úspěchu obnovit kontrolu, konfiguraci a případný otevřený plán. Divergenci neřešit automatickým reset/rebase. Přidat regresní testy pro chybějící digest, změnu remote a zákaz během běhu, aktualizovat existující route testy na novou povinnost digestu.

## Testování a akceptace

1. Vitest: rozšířit lib/api.test.ts o URL/explicitní repo, přesné requesty bez files/path/content, chybové data a warnings. Nové lib/factory.test.ts a components/factory/*.test.ts pokryjí předvyplnění, jednotlivé agent bindings/defaults, missing CLI varování, Azure a změny všech voleb, přidání agentů workflow, opožděné plány a neplatnost potvrzení.
2. FactoryView.test.ts: zachování kontrolních nálezů; blockers včetně not_onboarded; machine finding není blocker; manifest/full obsah/patch; vlastní modal a cancel bez apply; double-click jen jeden apply; plan_changed vyžaduje nové potvrzení; push_failed + PR se stejným digestem; success/recheck/backlog/PR instrukce; take/merge/migration; pull preview a změněný digest.
3. ReposAddView.test.ts, InspectCard testy a App.test.ts: none pokračuje do instalace, created=true registrace se na Cancel odstraní a nevolá apply, created=false se neodstraní, failed DELETE se ukáže, úspěch zachová registraci a naviguje, přepnutí repa neodešle staré potvrzení. ConfigStatusBanner.test.ts a RepoScreen testy: commit tlačítko vede na náhled bez zápisu. Ověřit aktivní běhy, přesný počet/odkazy, opožděné odpovědi, příchod/ukončení běhu a zákaz direct/pull.
4. Backend: aifactory/tests/web/test_web_factory.py pro nový pull kontrakt, stale digest a živý běh; tests/library/test_library_update.py pro merge_available (textové, binární, chybějící base a neřešitelný konflikt). Příslušné config/publish testy pro očekávaný pull digest a nezměněný stav při odmítnutí. Zachovat existující init/push rollback/PR testy.
5. Přidat aifactory/tests/e2e/test_factory_install_browser.py a případně factory_repo.py. Založit dočasné repo s README a úvodním commitem na main, bez .factory, provider local a bare origin. Dashboard spustit nad jiným fixture repem/izolovaným HAIFA_HOME, aby instalovaný target nebyl předem registrovaný, poté cílové repo přidat přes UI. Převzít server/browser/tripwire patterny z f3_repo.py bez spouštění workflow nebo modelu. Před Provést ověřit unchanged HEAD, remote SHA a absenci factory souborů; samostatně zrušit jednu dočasnou registraci a ověřit odstranění a čisté repo. Pro úspěch vybrat builder na jiném harnessu než ostatní (např. codex proti claude), model/thinking explicitně a fake CLI pro probes. Potvrdit vlastní modál, pak ověřit jeden nový commit na main, totožný SHA v bare remote, .factory/manifest.yaml a agents.yaml s odlišným builder binding. Zakázat všechny externí browser requesty, připravit fake CLI/tripwire i pro backend, ověřit nulová modelová volání a žádné systémové dialogy. Nepoužít živý Github/Azure ani globální operator home/knihovnu.
6. Spustit cílené Vitest/backend testy, poté just web-build. Sestavené soubory aifactory/src/aifactory/web/static/ musí odpovídat zdrojům, včetně odstranění nahrazených hashovaných assets podle stávajícího build procesu. E2E musí použít tento build, ne dev server.
7. Povinné finální příkazy v přiděleném worktree: just test, just typecheck, just lint, just e2e. Posuzovat exit status; selhání opravit, nikoli potlačit/skipnout. justfile standardně nepotřebuje změnu. Neinstalovat další frontend dependency a neměnit lockfile kvůli nové závislosti.
8. Napsat app_docs/HAIFA-S01-T21-instalace-aktualizace-z-knihovny-a-commi.md: průvodce a zrušení, vazby agentů, význam skupin update/migrací, commit z banneru, potvrzení a digest, odmítnutý push/PR, merge/pull a zákaz během běhu. Uvést skutečné výsledky ověření a případné materiální omezení.

## Hotovo

### Stav pokračování d4f262d7

Konečný výsledek: deterministická fáze `07_full_check` dokončila 7. 10. 2026 `just check e2e` s návratovým kódem **0** (2567,296 s). Protokol `C:/Users/jan.krejci/Documents/HAIFA/.factory/data/sessions/d4f262d7/context_handoff/quality/07_full_check/command.log` dokládá 863 průchozích frontendových testů v 76 souborech, 2190 průchozích backendových testů (30 skipped), úspěšný frontendový i backendový typecheck, lint a kontrolu formátování a všech 7 sériových e2e testů včetně instalačního scénáře. Požadované `just test`, `just typecheck`, `just lint` a `just e2e` jsou doložené tímto úplným během. Reviewer musí použít tento protokol jako konečný validační důkaz; builder v této dokumentační opravě testy neopakoval.

Předchozí čekání na úplnou akceptaci je překonané zeleným `07_full_check`. Následující odstavce jsou historické záznamy stavu před jeho dokončením; tehdejší požadavek na nový úplný protokol je již splněný.

Implementace z běhu `7fc82951` je zachovaná; builder prohlédl její diff vůči `main` a původní plán i review. Review potvrdilo 45 z 46 požadavků a nevyžaduje další změnu implementace. Zbývá doložit úplnou akceptaci. Podle zadání tohoto pokračování builder nespouští úplné testy; deterministická fáze `full_check` provede `just check e2e`, který zahrnuje frontend, celý backend, typecheck, lint a sériové browser testy. Reviewer musí po úspěchu použít protokol tohoto příkazu jako důkaz a doplnit skutečné výsledky do dokumentace. Historické cílené běhy tento důkaz nenahrazují.

Fáze `03_full_check` skončila s kódem 1: frontend 863 průchozích testů, backend 2187 průchozích, 30 přeskočených a tři selhání. Oprava aktualizuje očekávání onboarding testů o workflow `finish-test-review` a izoluje portový test od stroje operátora pomocí `FakeMachine`. Podrobnosti a cílené výsledky jsou v app_docs; pro úplnou akceptaci je stále nutný nový úspěšný protokol `just check e2e`.

Fáze `05_full_check` skončila s kódem 1 kvůli neobsloužené renderovací chybě ve frontendovém testu vytvoření projektu, přestože všech 863 testů prošlo. Oprava doplňuje správné mock odpovědi grafu a detailu a čekání na vykreslení grafu v `BacklogView.test.ts`. Cíleně prošlo všech 29 testů souboru bez neobsloužených chyb; frontendový i backendový typecheck a lint mají kód 0. Nový úplný protokol je stále nutný.

Všechny operace jsou dosažitelné z Factory a instalace navazuje na Přidat repozitář. Náhled vždy ukazuje serverový plán včetně manifestu a blokátorů, každý zápis vyžaduje vlastní modál a aktuální digest. Zrušený průvodce nezapíše do repa a odstraní jen registraci, kterou vytvořil. Update respektuje lokální změny a volbu migrací. Banner otevírá commit náhled. Běhy blokují přímý zápis a pull, stale plán vyžaduje nové schválení, odmítnutý push umožňuje PR se stejným digestem. Prohlížečový test dokazuje commit i v lokálním bare remote; build a všechny čtyři požadované sady projdou.
