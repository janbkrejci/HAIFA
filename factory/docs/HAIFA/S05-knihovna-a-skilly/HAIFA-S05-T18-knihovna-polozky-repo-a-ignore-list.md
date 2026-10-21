# Knihovna: inventář repozitářů a ignorování

Knihovna zobrazuje sdílené položky a samostatný přehled pracovních stromů všech připojených repozitářů, i bez založené sdílené knihovny. Backlogové projekty inventář nenásobí. Typové záložky ovládají oba přehledy; inventář má navíc filtr repa a zdroje (pouze v repu / vlastní kopie sdílené položky). Detail obsahuje zdrojové soubory. Objevení položky nic neimportuje.

## Umístění

- Workflow: `.factory/workflows/*.yaml` a `*.yml`.
- Agenti HAIFA: `.factory/prompts/<jméno>/`; validní agenti mají definici v `.factory/agents.yaml`.
- Nativní agenti: rekurzivně `.claude/agents`, `.codex/agents`, `.agents/agents`, `.pi/agents`; soubory `.md`, `.toml`, `.yaml`, `.yml`. Inventář čte soubory, nepřekládá jejich formát do agenta HAIFA.
- Skilly: rekurzivně adresáře s `SKILL.md` pod `.claude/skills`, `.agents/skills`, `.codex/skills`, `.pi/skills`. Jméno je relativní cesta skillu pod tímto kořenem.
- `.claude/skills` je kanonický zdroj. Skill se stejnou relativní cestou v `.agents/skills` se vynechá, i když se obsah zrcadla liší; chybějící kanonický protějšek umožní zobrazit skill existující pouze v `.agents`. Ostatní různé cesty zůstávají samostatné.
- Rozšíření pi: `.factory/extensions/<jméno>/`.

Soubory mimo repo přes symlinky se v detailu nečtou. Detail má stejné limity velikosti a počtu souborů jako položky knihovny. Nedostupné repo a chyba jeho konfigurace se hlásí samostatně, ostatní repa fungují; u chybné konfigurace lze stále prohlížet nalezené soubory.

## Ignorování a persistence

Identita položky je **id registrovaného repa + typ + relativní POSIX cesta**. Názvy v jiných repech ani sdílené položky nejsou totožnou položkou. Nastavení je lokální pro dashboard daného počítače: `library_ignore` u repa v `$HAIFA_HOME/dashboard.yaml`, pomocí existujícího zamčeného atomického zápisu registru. Refresh i restart ho zachová. Odebrání registrace odstraní i její pravidla. Nahrazení seznamu pravidel je atomické; při souběžné úpravě platí poslední uložený seznam.

Pravidlo má `type` (`agent`, `workflow`, `skill`, `extension` nebo `*`), `mode` a `value`:

- `item`: přesná relativní cesta položky.
- `prefix`: doslovný prefix jména včetně případné relativní hierarchie, například `bmad-`. Bez globů, rozlišuje velikost písmen.
- `directory`: přesná cesta nebo její potomci oddělení `/`, například `.claude/skills/bmad`. Neskrývá `.claude/skills/bmad-other`.

Cesty jsou normalizované, relativní, bez `..` a bez zpětných lomítek. Pravidla se skládají pomocí OR, nemají výjimky. Hromadná pravidla automaticky pokryjí nové odpovídající položky. Pro BMAD lze zvolit repo a přidat prefix či adresář, se všemi nebo konkrétním typem položek. Ignorované položky standardně nejsou vidět. „Zobrazit ignorované a pravidla“ zpřístupní jejich seznam a zrušení pravidel. Obnovení vyžaduje odstranit všechna odpovídající pravidla.

Ignorování také vyřadí kopii z přehledu overrides a z nabídky importu/přesunu. **Nemaže soubory, nevypíná agenty ani skilly, nemění runtime načítání ani resolver workflow.** Přímé explicitní operace zůstávají dostupné přes dosavadní API. Platné položky v kanonickém layoutu lze přesunout dosavadním plánem, včetně položek bez protějšku v knihovně. Skilly v podporovaném importním formátu lze také explicitně importovat s náhledem plánu. Nativní agenti jiného formátu mají detail, bez automatické konverze či přesunu.

## API

- `GET /api/library/inventory`: `items` (repo, repo_name, type, name, path, ignored, movable), `repos` (id, name, rules), `errors` po repozitářích. `movable` v seznamu označuje kandidáta dle cesty; detail ověří validitu pro přesun.
- `POST /api/library/repo-item`: `{repo, type, path}`; detail musí odpovídat aktuálně nalezené položce, vrací soubory, absolutní cestu pro explicitní import a ověřené `movable`.
- `POST /api/library/ignore`: `{repo, rules}` atomicky nahradí seznam, vrátí aktualizovaný inventář. Nejvýše 1000 pravidel na požadavek.
- Dosavadní `/api/library/overrides` zachovává srovnání se sdílenou knihovnou; ignorované kopie vynechá.

Backendové testy pokrývají více repozitářů a projektů, workflow pouze v repu, nativní agenty a skilly, zrcadla, prefixy i adresáře, persistenci v novém registru, obnovení, izolaci i runtime. Frontendové testy ověřují cílení podle repa a cesty, filtry a správu pravidel. Browser test pracuje s reálným API a ověřuje detail, skrytí přes refresh a obnovení.

## Oprava PR #145 a ověření

Filtry Repo a Zdroj i volby Hromadně ignorovat a Typ používají sdílený `SelectMenu` s přístupnými názvy a ovládáním myší i klávesnicí. Původní hodnoty filtrů, pravidel a testovací identifikátory zůstávají zachované; volba typu pravidla má navíc `ignore-type`. Guard `noNativeUi` nadále kontroluje všechny komponenty bez výjimek. Integrační API fixture aplikace vrací pro inventář odpovídající pole `items`, `repos` a `errors`; navigační test ověřuje načtení inventáře a skutečné možnosti filtru Repo. Tím se předchází pádu renderu kvůli obecné odpovědi jiného endpointu.

Distribuovaný frontend byl sestaven příkazem `just web-build` přes Bun (včetně `vue-tsc`). Cílená validace builderu:

- Bun/Vitest: `App.test.ts`, `RepoLibraryItems.test.ts`, `LibrarySection.test.ts`, `SelectMenu.test.ts` a `noNativeUi.test.ts`: 420 úspěšných testů. Interakce používají skutečné položky nabídky včetně volby adresáře, typu a návratu na všechny zdroje/repa.
- Backend: `test_web_library.py`, `test_web_registry.py`, `test_web_repos.py`, `test_library_config_edit.py` a `test_task_library.py`: 99 úspěšných testů inventáře, persistence, izolace, explicitních operací a runtime.
- Cílený `vue-tsc` pro `App.test.ts` prošel. Ruff (lint i formát) a mypy upraveného browser testu prošly. Samostatný mypy používá `MYPYPATH=tests:tests/run:tests/e2e:tests/workflow` pro existující pomocné testovací moduly.
- `just pytest tests/e2e/test_library_browser.py -n0`: ověření založení knihovny, detailu repo-only workflow, filtrů, skrytí přes refresh, obnovení a adresářového pravidla pro konkrétní typ. Test před otevřením SelectMenu nechá doběhnout automatický posun stránky, protože sdílená nabídka se při scrollování zavírá.

Bun instalace i produkční build na tomto stroji fungují; npm ani dřívější omezení běhu na Windows nejsou součástí výsledné validace.
