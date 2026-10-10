# HAIFA-S06-T06 — Akceptační test týmového toku

`aifactory/tests/e2e/test_team_onboarding_browser.py` provádí jeden souvislý test přes skutečný `factory obs`, dva nové `HAIFA_HOME`, dvě pracovní kopie repa a lokální bare remote repa i knihovny.

Test otevře první start na obrazovce Tento počítač a potvrdí založení semínka. UI zakládá knihovnu bez remote: fixture následně připojí lokální remote, přidá sdílený skill `team-check` a publikuje obsah. Sssf fixture má změněný builder prompt, právě jeden backlog task s workflow `simple-sdlc` a lokální deterministický testovací příkaz. Ostatní sssf workflow UI standardně nepřevádí.

Po náhledu a potvrzení onboardingu `pre-receive` hook remote repa ověří, že knihovna již publikovala nový commit a přesnou obsahovou verzi vytěženého buildera z přijímaného manifestu. Důkaz zapisuje do `publication.json`. Náhled nemění obsah ani HEAD a původní `adws/` zůstává stejný.

Na záložce Factory test přidá skill builderovi a potvrdí commit. Kontroluje manifest, roster, source i mirror skillu a stav `synced`. Task spouští přes backlog a run dialog; falešný harness skriptuje planner, builder, reviewer i documenter. Test vyžaduje úspěšný běh a build fázi, jejíž skutečně uložený `builder/prompts/phases/build/system.md` obsahuje rejstřík skillů, jméno, popis a cestu `team-check`.

Nový klon repa v B převezme již onboardované repo po naklonování knihovny v UI. Úplný snapshot před interakcí a po převzetí porovnává status, HEAD, všechny refy, remote refy, soubory včetně ignorovaných, adresáře, módy a symlinky. Teprve potom fixture upraví a commitne builder prompt. Export stejné položky z Factory vytvoří novou verzi v remote knihovny. A provede skutečný Pull, Knihovna ukáže další verzi a její obsah, Factory i API ukážou `outdated`. Prompt, manifest a HEAD A zůstávají stejné; runtime databáze dřívějšího běhu se při otevření dashboardu může aktualizovat.

Test odhalil chybějící rejstřík skillů v engine promptech. Engine nyní zachová pole `skills` v konfiguraci agenta a před uložením auditní kopie i předáním harnessu připojí metadata pouze přiřazených skillů. Obsah SKILL.md se do promptu nevkládá. Regrese v `tests/engine/test_phase_prompts.py` kontroluje build i revise a vyloučení nepřiřazeného skillu.

Všechny fixture, hooky, konfigurace Gitu, logy a screenshoty jsou v `tmp_path`. Nepřebírá se osobní Git konfigurace ani `HAIFA_LIBRARY`. Browser povoluje pouze přesný origin serveru, blokuje service workers, eviduje externí požadavky, systémové dialogy i filechooser. Skutečné machine/factory check používají `offline=1`. Tripwire pro harnessy a hosting spolu s `validation.fake` brání skutečnému modelu nebo službě.

Cílené spuštění:

```sh
cd aifactory
uv run pytest tests/e2e/test_team_onboarding_browser.py -n0
uv run pytest tests/engine/test_phase_prompts.py tests/harness/test_repo_skills.py tests/config/test_config_loader.py -n0
```

Při selhání se vypíší serverové a běhové logy, fake calls a remote důkaz. Screenshoty úspěšných etap jsou `a-run.png`, `b-export.png` a `a-pull.png` v adresáři testu. Při selhání startu/běhu se použije také API diagnostika F3.

Ověření: nový browser test prošel (1 test, finální běh 32,04 s), cílené kontroly engine promptů, synchronizace skillů a loaderu prošly (23 testů) a související browser testy knihovny, přidání skillu a onboardingu prošly (3 testy). `just typecheck`, `just lint` a `git diff --check` skončily s exit statusem 0. Celé sady `just test` a `just e2e` jsou ponechány testovací fázi workflow podle omezení buildera.
