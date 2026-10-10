# HAIFA-S01-T22 — Akceptační test více repozitářů v prohlížeči

## Cíl a rozsah

Přidat jeden souvislý Playwright test nad skutečným `factory obs`: prázdný domov → přidání A s factory → instalace factory do B s lokálním bare origin → přepínání obrazovky → spuštění tasku A a zobrazení fáze i čekajícího PR v Přehledu → odebrání B bez změny jeho obsahu. Uživatelské mutace provádí prohlížeč, nikoli přímé API či dodatečné zápisy do repozitářů. Pomocné API GET a čtení Git slouží jen synchronizaci, důkazům a diagnostice.

Neměnit vendor/, prototype/, chráněné soubory ani backlog. Implementace zůstane v aifactory/ a dokumentu `app_docs/HAIFA-S01-T22-akceptacni-test-vice-repozitaru-v-prohli.md`. Změna justfile není potřebná: `just e2e` již sbírá celý tests/e2e a běží s -n0. Nevolat skutečný model, GitHub, Azure ani vzdálené služby. Lokální HTTP server a lokální filesystemový Git remote jsou součástí testu.

## Zjištěný stav a opětovné použití

- `aifactory/tests/e2e/f3_repo.py`: make_f3_repo vytváří main s lokálním providerem, workflow plan-commit a prázdným krokem M01-S01. fake_script poskytuje planner edit, tripwire hlídá skutečné CLIs. obs_server dnes vyžaduje repo, vždy předává --repo a získá registered_id. Uklízí proces serveru a běžící tasky jediného repa.
- `aifactory/tests/e2e/test_f3_browser.py`: browser launch s HAIFA_E2E_CHANNEL, blokování externích požadavků, zachycení dialogů, timeouty 15/60 sekund, start 90 sekund a běh 240 sekund, diagnostika API/server/home logs, vytvoření a spuštění tasku. Stávající přidání/odebrání používá canned factory/check.
- `aifactory/tests/e2e/test_factory_install_browser.py`: čerstvé B, lokální bare origin, skutečná instalace s commit/push, factory-plan, factory-message, factory-perform, confirm-dialog, factory-verdict. Používá falešnou CLI diagnostiku; nedovoluje modelový příkaz.
- `aifactory/validation/worker.py`: HAIFA_VALIDATE_FAKE instaluje fake a nastaví launcher prefix na tentýž worker. To již pokrývá samostatný proces tasku; zachovat.
- `aifactory/validation/fake.py`: guarded skutečné adaptéry claude/codex/pi i alias claude_code, JSON skript a calls.jsonl. Nyní vrací výsledek okamžitě.
- CLI obs bez --repo neregistruje aktuální cwd; výchozí UI je Přehled. RepoSwitcher zachovává screen, odstraňuje parametry.
- OverviewView a RepoCard mají no-repos, overview-refresh, overview-card/data-repo, row-running/data-run, row-phase, row-review/data-task, total-running a total-review. Klidná repa jsou calm-repo, nikoli overview-card.
- tests/tiers.py nyní uvádí pouze F3 v BROWSER_FILES a SLOW_FILES; doplnit nový scénář.

## Soubory a implementační kroky

### 1. Sdílený start serveru a testové prostředí

Upravit `aifactory/tests/e2e/f3_repo.py` tak, aby obs_server podporoval start bez repozitáře při zachování stávajících volání. Použít `repo: Path | None`; --repo připojit pouze pro konkrétní cestu. ObsServer.repo_id může být pro prázdný server prázdný řetězec, jeho api property musí na tuto situaci výslovně upozornit; stávající konkrétní repo vrací stejné ID/API jako dosud. Nový test pracuje nejprve se server.url a po přidání s registered_id/home.

Zajistit úklid také nově registrovaných rep: před ukončením serveru načíst cesty z jeho izolovaného dashboard.yaml, po ukončení aplikovat existující _kill_running_runs na všechny tyto cesty plus původní repo, je-li zadané. Selhání čtení registru nesmí zabránit ukončení serveru. V fixture nového scénáře mít A rovněž jako explicitní cleanup fallback, aby neúspěch testu nezanechal zablokovaný worker.

Nový pomocný modul `aifactory/tests/e2e/multi_repo.py` připraví A přes make_f3_repo a B podle test_factory_install_browser: README, main, testová Git identita, vypnuté podepisování, první commit, bare origin s main, push a upstream. Vše vzniká pod tmp_path před startem serveru. HAIFA_HOME před startem neexistuje nebo je prázdný, nesmí obsahovat dashboard.yaml s repo entries. Odstranit HAIFA_LIBRARY z děděného prostředí a použít stock knihovnu, jako instalační vzor.

Ponechat tripwire pro skutečné harnesses a hosting. Pro instalační a automatickou Factory diagnostiku použít přesně omezenou falešnou CLI sondu podle instalačního testu (verze/auth status a podporovaný codex app-server probe), nikoli skutečný program. Každý neznámý příkaz vytvoří marker a skončí 97. Izolovat fake credentials pod tmp_path pomocí CLAUDE_CONFIG_DIR/CODEX_HOME. Je-li třeba pro automatický factory/check, použít stejný canned report jako F3, zachytit pouze tuto diagnostickou URL; nesimulovat inspect, registry, install plan/apply, task, runs, review ani overview. Pozitivně ověřit fake call log pro skutečný task. Není nutné měnit produkční worker jen kvůli tomuto testu.

### 2. Deterministické zachycení živé fáze

Rozšířit `aifactory/validation/fake.py` o volitelný vstup skriptu `wait_for_file` (absolutní cesta k release souboru) a `wait_timeout_s` s konečným výchozím limitem, např. 120 sekund. Bez těchto polí fake funguje jako dosud. Fake zaznamená call a pak před vrácením envelope čeká monotónně s krátkým polling intervalem na release soubor; při překročení limitu vyhodí jasnou chybu s cestou. Tím skutečná fáze plan zůstane running, zatímco UI test přejde do Přehledu. Nepřidávat pevný mnohasekundový sleep ani mock záznamu trace DB.

Script pro nový test obsahuje jediný planner call, stejný envelope/edit jako první F3 task a jedinečný wait_for_file mimo repa. Po ověření běhu a fáze v DOM test vytvoří release soubor. V finally jej vytvořit také, aby assertion failure nezablokovala proces. Přidat cílené testy do `aifactory/tests/validation/test_validation_unit.py` pro již existující release, odblokování během čekání a timeout; zachovat stávající fake bez gate. Testy nepoužívají model ani dlouhá čekání.

### 3. Souvislý browser scénář

Přidat `aifactory/tests/e2e/test_multi_repo_browser.py`, pytest browser + xdist_group("e2e"). Reuse existující browser launch/choose a lifecycle helpery F3, případně vyčlenit minimální sdílené helpery bez rozsáhlého refaktoru. Fixture drží URL, home, A/B/origin, script, marker, log a dynamická repo IDs. Report obsahuje runs_report pro A, server tail, home run logs a externí požadavky/dialogy.

Pořadí a důkazy:

1. Otevřít `/` a ověřit no-repos s textem Žádné repozitáře a odkazem Přidat repozitář. API /api/repos vrací prázdný seznam. Neexistuje skrytý control repo.
2. Přes add-repo-link napsat absolutní cestu A do add-path, Escape uzavře návrhy, add-inspect → inspect-card/root → inspect-add. Ověřit skutečný záznam A v registry a route s jeho ID. Nespoléhat na jednu předpokládanou cílovou záložku: F3 dnes u tohoto toku očekává Factory.
3. Přes UI otevřít přidání B, napsat cestu, inspect-init. Ověřit factory-plan, že provider je local a plán se týká B; před potvrzením HEAD/origin main odpovídají původnímu SHA a .factory neexistuje. Vyplnit unikátní factory-message, factory-perform → interní confirm-dialog s push na origin → confirm-ok → factory-verdict. Ověřit přesně jeden nový instalační commit se zadaným subjectem v lokálním logu B i v bare origin; SHA main obou shodné, manifest existuje. Test nezapisuje .factory ručně.
4. Otevřít jednu společnou záložku, např. Runs, a přes switcher-button/switch-repo-ID přepnout A → B → A. V každém kroku ověřit #/r/ID/runs, h1 Běhy a switcher-current. Tím stejná obrazovka znamená zachovaný typ záložky, nikoli shodná repo data či screenshot. Žádné page.goto jako náhrada samotného přepnutí.
5. V Backlogu A vytvořit jeden task prostřednictvím F3 formuláře, ověřit M01-S01-T01 a spustit plan-commit. Případný backlog commit proběhne z run dialogu jako ve F3. Čekat na nový run ID přes API s existujícími limity, nikoli na okamžité spuštění.
6. Přes menu switch-overview otevřít globální Přehled. Ve skutečné kartě A ověřit row-running pro run ID a task ID, row-phase obsahuje plan, link míří na A/run ID a total-running je 1. B nesmí obsahovat běh A. Release gate vytvořit teprve po tomto DOM důkazu.
7. Po release čekat přes API na succeeded, potom v Přehledu na row-review/task ID v A a správný review odkaz; row-running zmizí a total-review je 1. PR musí být skutečně vytvořen lokálním providerem, shodný s run_state.pr. Neprovádět schválení/merge, čekající PR je cílem.
8. Přes Spravovat otevřít seznam rep. Těsně před odebráním B získat jeho snapshot (níže), repo-remove → confirm-dialog s jménem B a informací o zachování složky → confirm-ok. B zmizí ze seznamu, registry i switcheru, A zůstává. Porovnat snapshot B/origin po operaci.
9. Zavřít browser context a zkontrolovat, že seznam externích requestů, systémových dialogů a filechooser událostí je prázdný, tripwire marker neexistuje, calls.jsonl obsahuje právě jeden planner call v worktree A. Log žádného procesu neobsahuje REAL_HARNESS_MESSAGE. Guard nasadit před první navigací; abort externího requestu je selhání, nikoli úspěšná ochrana.

### 4. Snapshot a bezpečné odebrání

Helper v multi_repo.py pořídí přesné `git status --porcelain=v1 --untracked-files=all`, HEAD a setříděné refy přes for-each-ref s refname/objectname; totéž HEAD/refy bare origin. Pro soubory B uloží mapu relativní cesta → typ, obsahový hash a relevantní mód; zahrnout tracked, untracked i ignored soubory a .factory, symlink číst jako link. Vynechat pouze interní .git metadata, jejich refy/status se ověřují zvlášť. Zahrnout existenci složek pro detekci jejich odstranění. Neporovnávat mtime či atime, které nezaručují obsahovou změnu. Snapshot se pořizuje po dokončení instalace a přepínání, těsně kolem remove; nesrovnávat s původním B bez factory. Po startu serveru nepřidávat do B další sentinely ručně.

### 5. Zařazení a dokumentace

Doplnit tests/e2e/test_multi_repo_browser.py do SLOW_FILES a BROWSER_FILES v `aifactory/tests/tiers.py`, aby scénář běžel i při změně dashboardu v check-scoped. Zachovat F3 a instalační test, neoslabovat jejich assertiony. Dokument `app_docs/HAIFA-S01-T22-akceptacni-test-vice-repozitaru-v-prohli.md` stručně popíše tok, izolaci, tripwire, řízenou gate, způsob spuštění a skutečné výsledky ověření. Screenshoty UI změn nejsou potřeba, protože se nemění produktové UI.

## Ověření a akceptace

Nejprve cíleně `just test tests/validation/test_validation_unit.py -n0` a `just e2e tests/e2e/test_multi_repo_browser.py` (pytest může dostat duplicitní výchozí directory argument; jednoznačná alternativa je `cd aifactory && uv run pytest tests/e2e/test_multi_repo_browser.py -n0`). Nový browser test zopakovat alespoň třikrát cíleným příkazem, aby se ověřilo, že živá fáze není timing race. Při změně f3_repo prověřit také F3 a instalační scénář.

Pak spustit všechny požadované gates z kořene worktree: `just test`, `just typecheck`, `just lint`, `just e2e`. Hodnotit exit status každého příkazu. Pokud frontend static assets nejsou aktuální pro UI používané testem, použít existující `just web-build`; nevytvářet ruční úpravy generovaných assets. Použít běžné nástroje z PATH. Chybějící browser řešit prostřednictvím existujícího HAIFA_E2E_CHANNEL/e2e-install mechanismu; nový test nesmí být potichu přeskočen.

Hotovo je až když souvislý scénář prokáže všechny výše uvedené kroky a všechny čtyři gates projdou. Tento plán nic neimplementuje a nesmí být použit jako tvrzení o již proběhlých testech.
