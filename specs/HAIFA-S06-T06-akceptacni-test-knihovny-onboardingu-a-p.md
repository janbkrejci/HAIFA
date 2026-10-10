# HAIFA-S06-T06 — Akceptační test knihovny, onboardingu a převzetí

## Cíl a rozsah

Přidat jeden souvislý prohlížečový akceptační scénář týmového toku přes skutečný `factory obs`, dva izolované `HAIFA_HOME`, dvě různé pracovní kopie repa a dva lokální bare remote. Test dokáže první start, jednorázový onboarding sssf, publikování knihovny před repem, přidání skillu builderovi a jeho přítomnost v uloženém promptu build fáze, převzetí beze změn repa a přenos nové verze promptu přes export a Pull.

Implementovat test a jeho pomocné fixtury; nereorganizovat produkt. Žádný GitHub/Azure, skutečný model ani `factory upgrade`. Změny jen v `aifactory/`, případně `justfile`, tomto specu a `app_docs/HAIFA-S06-T06-akceptacni-test-knihovny-onboardingu-a-p.md`. `vendor/`, `prototype/`, `.factory/`, `.claude/`, `adws/`, CLAUDE.md a engineer-owned dokumenty v checkoutu neměnit. Kopírování read-only sssf šablon do dočasného testovacího repa je v pořádku. Tento plán nic neimplementuje.

## Existující vzory a skutečné chování

- `aifactory/tests/e2e/f3_repo.py`: `obs_server(None, script, wire, log, home)` spustí prázdný dashboard přes `validation.worker`; `registered_id`, `api_get`, `task_runs`, `run_state`, `wait_for` a diagnostické logy lze znovu použít. ObsServer s prázdným registrem nemá repo API; po přidání repa sestavit prefix z jeho registrovaného ID.
- `test_f3_browser.py`: `_launch`, `_choose`, UI spuštění tasku `_start_run`, čekání na konec a diagnostika. Zachovat omezené čekání na proces/API; žádné pevné sleep pro synchronizaci.
- Vzor M15 je `test_multi_repo_browser.py` a `multi_repo_e2e.py`: prázdný dashboard, více rep, zákaz externích požadavků/dialogů/filechooser a `repo_snapshot`, který zachycuje status, HEAD, refy, obsah, módy, symlinky, adresáře i ignorované soubory a remote refy.
- `test_library_browser.py` pro první `#/setup`, založení semínka a historii Knihovny; `test_factory_items_browser.py` pro skill, náhled a potvrzený commit; `test_onboarding_browser.py` pro sssf onboarding. Poslední dnes používá stejnou pracovní kopii na obou strojích a knihovnu připravuje mimo UI: nové pokrytí tyto mezery odstraní, existující testy zachovat.
- `tests/onboard/onboard_repo.py`: `sssf_repo`, `patch_omnibus`, `bare_origin`, `commit_all`, `worktree_snapshot`. Sssf fixture nemá backlog a `haifa_backlog` přidává tři tasky, proto pro nový scénář vytvořit vlastní backlog s jediným taskem.
- `validation/worker.py` již nastavuje prefix run podprocesů na sebe; `validation/fake.py` nahrazuje všechny skutečné harnessy a ukládá `.calls.jsonl`. Souběžné běhy nad jedním fake skriptem nejsou podporované. Pro tento scénář stačí jediný run, servery mohou být spuštěné postupně A → B → A se stejným home A.
- `engine/agents.py` ukládá auditní prompt na `<session>/builder/prompts/phases/build/system.md`; session získat přes `aifactory.run.task.session_dir_of(repo, run_id)`. Nestačí kontrolovat zdrojovou šablonu nebo poslední agent-level prompt.
- `SetupView.vue` posílá při init prázdné options, ačkoli backend `web/library.py` podporuje `name` a `remote`. Nezavádět novou produktovou funkci jen pro fixture: semínko založit přes UI a pak fixture připojí/pushne lokální remote. B klonuje knihovnu přes existující UI.

## Soubory a rozdělení práce

1. Přidat `aifactory/tests/e2e/team_flow_e2e.py`: typované pomocníky pro lokální sssf repo, jediný backlog task, bare remotes, ověření pořadí pushů a fake script. Reuse existujících helperů, nekopírovat server/harness ani celý F3 test.
2. Přidat `aifactory/tests/e2e/test_team_onboarding_browser.py`: jeden kompletní acceptance test označený `pytest.mark.browser` a `pytest.mark.xdist_group("e2e")`. Rozdělit jeho UI etapy do malých helperů, pokud by tělo bylo nepřehledné.
3. `f3_repo.py` nebo `multi_repo_e2e.py` měnit pouze pokud je prokazatelně třeba doplnit obecný helper. Stávající kontrakty a cleanup zachovat.
4. `validation/worker.py` a `validation/fake.py` přednostně bez změn: současné možnosti stačí. Pokud je nutná malá oprava infrastruktury, doplnit její cílenou regresi a zachovat chování ostatních scénářů; auditní prompt načítat z produkčního uloženého souboru.
5. Přidat požadovaný `app_docs/HAIFA-S06-T06-akceptacni-test-knihovny-onboardingu-a-p.md`: popsat pokrytí, izolaci, přípravu remotes, spouštění, diagnostiku a skutečné výsledky ověření.
6. `justfile` neměnit, automatické sbírání `tests/e2e` již zahrne nový test. Produktové opravy jen pokud nový test odhalí reálnou chybu, v nejmenším příslušném modulu s odpovídající regresí. Neoslabovat aserce ani mockovat výsledky onboardingu, Factory check nebo stavy položek.

## Příprava a izolace

Všechny testovací repa, knihovny, logy, hooky a snapshoty pod `tmp_path`. Odstranit vliv `HAIFA_LIBRARY`; nastavit testovací Git identitu, vypnout podepisování a použít samostatné home A/B. Osobní credentials ani konfiguraci nekopírovat. Použít `diagnostic_tripwire` pro `claude`, `codex`, `pi`, `gh` prostřednictvím server env. Dovolené diagnostické příkazy nevolají služby; machine/factory check procházejí skutečným backendem s `offline=1`.

Sssf repo založit pomocí `sssf_repo(..., origin=True)` a odstranit nepoužitelné harness extensions pomocí `patch_omnibus`. Dočasná fixture musí obsahovat smysluplnou unikátní změnu builder promptu, aby onboarding skutečně vytěžil novou položku/verzi oproti seed. Přidat projekt, step a právě jeden task s explicitním workflow obsahujícím `build` vlastněný builderem (preferovat převedený `plan-build`, je-li tak pojmenován ve skutečném náhledu). Fake skript musí odpovídat skutečným fázím: planner píše platný spec s `@output`, builder udělá jedinou povolenou změnu např. `src/app/team.py` a vrátí validní success envelope. Pokud workflow vyžaduje další agenty, scriptovat i je. Použít povolené cesty a skutečný output kontrakt, ne special-case v engine.

Testovací příkaz musí být lokální a deterministický. Pokud převod sssf dává placeholder/neexistující test command, upravit zdrojový quality fixture před onboardingem na literální `[sys.executable, "-c", "pass"]` nebo ekvivalent bez sítě; tím konverze dostane skutečný funkční příkaz. Nevytvářet běh, který končí očekávanou chybou místo success. Po přípravě vše commitnout a pushnout do repo remote.

## Etapy a povinné aserce

### A: první start a týmová knihovna

Před startem assert, že home A neexistuje. Otevřít `/`, čekat na `#/setup`, h1 `Tento počítač` a prázdný registr. Přes `library-init` a vlastní `confirm-dialog` zkontrolovat seed plán; před potvrzením knihovna neexistuje. Potvrdit, ověřit `library-path` a seed commit. Fixture nyní připojí `origin` na prázdný lokální library.git a pushne main s upstream; ověřit shodu local/remote SHA a znovunačíst obrazovku. Tento krok výslovně popsat jako fixture, bez request interception měnícího UI payload.

Přidat do knihovny jednoduchý skill `team-check` s validním SKILL.md, unikátní description a tělem; commitnout a pushnout jako přípravu sdíleného obsahu. Seed sám nemá skill. Skill musí později být vybrán v UI, ne přidán přímo do repo rosteru.

### A: jednorázové vytěžení a pořadí publikování

Přes add-path/add-inspect otevřít `inspect-onboard`. Zkontrolovat `onboarding-plan`, že zahrnuje převedeného buildera, workflow a manifest, a nabídku zachování `adws/`. Zachytit repo/library SHA po náhledu a před potvrzením; plán nesmí změnit jejich obsah/HEAD (remote-tracking fetch při náhledu může nastat).

Dokázat pořadí v bare remote: po dokončení fixture přípravy nainstalovat `pre-receive` hook na repo remote. Při přijetí onboarding commitu hook z kandidátního stromu načte manifest, ověří změněný library remote main oproti baseline a obsah/verzi právě vytěženého buildera v již publikovaném library commitu. Zapíše důkaz/SHAs do tmp logu a při chybě vrátí nenulový status. Veškeré čtení pouze lokální Git; používat bezpečné quotování a existující `fake_exe.make_executable` vzor pro cross-platform spustitelnost. Hook nenechat ovlivňovat nesouvisející pozdější pushe. Nespoléhat na čas commitu ani pouze konečnou rovnost SHA.

Potvrdit onboarding, čekat na `factory-state` s textem `Onboardováno`. Ověřit manifest na main obou rep kopií v remote/local, změnu knihovny v remote, důkaz hooku a nezměněné `adws/`. Dále nesmí být nabízena opětovná extrakce sssf.

### A: skill builderovi a běh

Na Factory přes `item-add`, `_choose` pro item-type=skill, item-name=team-check a item-agent=builder otevřít náhled. Cíl base commit. Ověřit náhled a nezměněný HEAD před potvrzením, poté `item-apply` a `confirm-ok`. Ověřit nový commit, clean status, manifest položku, vazbu skillu v builder rosteru a `synced`. Ověřit source i mirror skillu podle skutečného instalačního kontraktu.

Spustit jediný task přes backlog UI a run-dialog, čekat přes API na konkrétní run a success. Ověřit skutečný builder call v fake logu, úspěšnou build fázi a její uložený system.md: obsahuje rejstřík skillů, název `team-check`, unikátní description a příslušnou cestu. Nepřidávat skill text do fixture system promptu jen kvůli aserci. Po ukončení procesu pushnout lokální main s commitem skillu do repo remote, pokud jej UI operace sama nepublikovala; zaznamenat tuto přípravu klonu B. Není nutné schvalovat či mergovat task PR.

### B: skutečný klon a převzetí beze zápisů

Ukončit server A čistě; uchovat home A a repo A. `git clone` repo remote do nové cesty repo B. Home B musí být nové a prázdné. Před interakcí s dashboardem zachytit úplný `repo_snapshot(repo_B, repo_remote)`; přes status přečtený před baseline se vyhnout záměně pouhého obnovení Git index cache s produktovým zápisem.

Spustit obs bez `--repo`. Na setup vyplnit `library-url`, použít `library-clone`, zkontrolovat plán a potvrdit. Ověřit home B/library je jiná cesta než A/library a má správný remote/HEAD. Přidat repo B přes add-inspect a inspect-add. `inspect-onboard` nesmí existovat; Factory zobrazí `Onboardováno`, bez nabídky vytěžení. Po dokončení kontrol porovnat celý snapshot s baseline: status, HEAD, všechny refy, remote a všechny soubory/módy/symlinky/ignorovaný obsah beze změny. Registrační změny mohou vzniknout jen v home B. Až po této aserci pokračovat editací.

### B export → A Pull

V B změnit `.factory/prompts/builder/system.md` unikátním markerem nové týmové verze a commitnout. Tato editace je záměrná testovací akce po read-only převzetí. Přes Factory řádek `item-agent-builder` otevřít jeho `item-export`, nechat nový název prázdný (další verze téže knihovní položky), náhled, base commit, potvrdit vlastní modal. Jméno knihovní položky převzít z manifestu/onboardingu, protože slot builder nemusí být stejný jako importované jméno. Ověřit nový library commit v remote, marker a verzi i úspěšný export/repo manifest.

Znovu spustit A se stejným home a pracovním repem. Na setup stisknout skutečný Pull a čekat na úspěch. Knihovna ukáže novou verzi/historii správného builder itemu a marker v detailu system.md. Factory A po obnovení zobrazí `outdated` u téže agent položky; potvrdit i skutečným factory/items API. Repo A prompt/manifest/HEAD zůstává starý — Pull aktualizuje knihovnu, ne automaticky repo.

## Zákaz externích akcí a diagnostika

Každý browser context má `service_workers="block"`, route guard dovolující jen vlastní server origin (přesný origin, žádná obecná localhost výjimka). Externí požadavky abortovat a evidovat. Machine/factory check přidat `offline=1`, ale nepodvrhovat odpovědi. Poslouchat JS dialogy a filechooser, dialog dismissnout pro ukončení a následně selhat. Závěrečné aserce pro všechny etapy: externí URL, dialogy i filechooser prázdné; tripwire marker neexistuje; server/run logy neobsahují `REAL_HARNESS_MESSAGE`. Zavírání context/browser/server v finally, cleanup běžících tasků ponechat obs_server.

Při selhání zobrazit server log, run subprocess log, runs_report, fake call log a hook důkaz; screenshoty ukládat do tmp_path. Žádné timeouty bez vysvětlení; vycházet z F3 limitů a čekat na skutečný stav.

## Ověření a dokončení

1. `just e2e tests/e2e/test_team_onboarding_browser.py` (recipe již předává `tests/e2e`; pro skutečně úzký výběr použít `just e2e -k team_onboarding` podle názvu nového testu).
2. `just test`, `just typecheck`, `just lint`, `just e2e`, všechny s úspěšným exit statusem. Po poslední změně opakovat relevantní kontroly. Nový test musí být běžně sbírán, bez unconditional skip a bez potřeby živých credentials.
3. Pokud se mění Vue kvůli odhalenému problému, `just web-build` a související frontend testy; build assets pouze generovat, neručně editovat. Pro běžný test-only rozsah build netřeba, pokud existující assets odpovídají zdrojům.
4. Zkontrolovat diff/změněné cesty, aktualizovat app_docs skutečnými výsledky. V této planner fázi se testy nespouštěly. Builder nesmí hlásit jejich úspěch bez provedení.

Hotovo znamená, že jediný acceptance scénář prokáže všechny popsané etapy včetně pořadí remote commitů, fáze build s reálným skill indexem, úplné neměnnosti klonu při převzetí a nového library itemu versus outdated repo A. Selhání odhalující produktový zápis při převzetí řešit u jeho původu, nikoli vyloučením příslušného souboru ze snapshotu.
