# HAIFA-S01-T22 — Prohlížečový test více repozitářů

`aifactory/tests/e2e/test_multi_repo_browser.py` spouští skutečný `factory obs`
bez `--repo` a s novým, prázdným `HAIFA_HOME`. V jednom prohlížečovém toku:

1. Ověří prázdný dashboard i registry a napsáním cesty přidá A s factory.
2. Přidá B bez factory, prohlédne instalační plán s lokálním providerem a potvrdí
   commit i push. Ověří jediný nový commit se zadaným subjectem v B a bare origin,
   shodná SHA a instalační manifest.
3. Přepne A → B → A přes switcher a ověří zachování obrazovky Běhy.
4. Vytvoří a spustí task v A. V globálním Přehledu ověří jeho běh, fázi `plan`,
   správný odkaz a součet; B zůstane v klidu. Po dokončení ověří skutečný otevřený
   lokální PR, shodu s run API a Přehledem a součet PR čekajících na review.
5. Odebere B interním potvrzovacím dialogem a ověří registry, seznam i switcher.
   Snapshot kolem odebrání porovnává přesný Git status, HEAD, seřazené refy B
   i bare origin a všechny soubory B včetně ignored a `.factory`: hash obsahu,
   módy, symlinky a existenci adresářů. Vynechává pouze interní `.git` metadata.

Repozitáře, bare remote, credentials a falešný script vznikají v dočasném prostředí.
Po startu serveru test mění repozitáře jen přes UI. Pomocné GET a Git čtení slouží
k synchronizaci a ověření výsledků. Používá stock knihovnu bez děděného `HAIFA_LIBRARY`.

Harness běží přes existující `validation.worker`, který instaluje fake i v procesu
spuštěného tasku. Jediný planner call má `wait_for_file` mimo repozitáře: fake zapíše
call a drží fázi do DOM důkazu běhu. Test gate uvolní také v `finally`; konečný
`wait_timeout_s` brání neomezenému čekání. Unit testy pokrývají existující release,
uvolnění během čekání, timeout a odmítnutí nekladných či nekonečných limitů.

CLI tripwire dovoluje pouze offline diagnostické sondy z instalačního vzoru;
jakýkoli jiný příkaz vytvoří marker a selže. Skutečné adaptéry navíc hlídá fake guard.
Pouze automatický `factory/check` má canned odpověď; registry, instalace, task,
běh, PR i Přehled používají skutečný server. Požadavky mimo server se blokují a
počítají jako selhání, stejně jako systémové dialogy a filechooser. Kontroluje se
jeden planner call ve worktree A, nepřítomnost markeru a real-harness zprávy v logách.
Úklid server helperu zahrnuje všechna registrovaná repa; A má navíc explicitní fallback.

Cílené spuštění z kořene worktree:

```sh
cd aifactory
uv run pytest tests/e2e/test_multi_repo_browser.py -n0
uv run pytest tests/validation/test_validation_unit.py tests/test_tiers.py -n0
```

Používá stejný Playwright launch jako F3 (Chrome, případně `HAIFA_E2E_CHANNEL`
a bundled Chromium). Scénář je v `SLOW_FILES` i `BROWSER_FILES`, takže jej vybírá
check-scoped při změnách dashboardu a sbírá jej běžné `just e2e`.

Ověření implementace: nový browser scénář prošel třikrát po sobě (poslední běh 66,55 s).
Cílená sada nového scénáře, původního F3, instalačního scénáře,
validation unit testů a tier testů prošla (56 testů); samostatná unit sada prošla
(51 testů). `just typecheck` a `just lint` prošly. Celé `just test` a `just e2e`
spouští navazující testovací fáze podle instrukcí builderu; v této fázi neběžely.
