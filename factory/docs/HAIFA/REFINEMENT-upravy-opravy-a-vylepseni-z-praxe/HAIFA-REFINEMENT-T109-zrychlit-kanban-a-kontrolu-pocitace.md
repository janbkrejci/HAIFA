# T109: Čtení kanbanu a readiness

Kanban načte aktuální merge policy jednou do svého requestového `_Runtime`. Stejný snapshot používají strom, seznam, kontejnery, filtry i součty a rozhodnutí, zda otevřené PR čeká na automatický merge. Schválená PR a chyby automatického merge si zachovávají původní význam. Další request znovu validuje identitu i soubor nastavení. `RepositorySettings` ani rozhodování o spuštění a merge nemají novou trvalou cache. Detail, graf a ukládání advice nadále používají aktuální čtení.

Readiness používá `GET /repos/{id}/backlog/summary`, který vrací `{projects: number}`. Počet odpovídá původnímu počtu kořenových kontejnerů včetně archivovaných. Endpoint načte model backlogu, ale nesestavuje kanban, runtime, stavy ani merge policy. Chyby konfigurace procházejí stejným obalem jako ostatní backlog endpointy. SetupView nadále používá vlastní kontrolu počítače.

Machine kontrola uchovává v `GlobalState` pouze názvy harnessů používaných jednotlivými registrovanými repozitáři. Při každém requestu znovu ověří hlavní checkout, jméno a commit base, obsah pracovních konfiguračních souborů, promptů a workflow a identitu a HEAD zdrojové knihovny. Změněný klíč vyvolá nové načtení rosteru; smazaná registrace zmizí i z cache. Nečitelný vstup neposkytne starý počet. Cache není založena na TTL ani pouze na čase změny souboru. Nastavení a výsledky testů harnessů se dále čtou aktuálně v `check_view`. Koordinace jobů, deadline a invalidace knihovních kontrol z T108 zůstávají zachovány.

## Lokální měření

Měřeno 2026-11-10 na macOS ve stejném checkoutu, 322 tasků; přímé volání `backlog_view(Path.cwd())` a `check_view(haifa_home(), state, offline=False, fresh=..., machine=None)` přes `uv run --project aifactory python`. Každá varianta před/po běžela v novém procesu, fresh a cached machine sdílely jeden `GlobalState`. Počty jsou počet volání `subprocess.run` zaznamenaných pomocí `unittest.mock.patch(..., wraps=original)`, čas pomocí `time.perf_counter`.

| Volání | Před: sekundy / subprocessy | Po: sekundy / subprocessy |
| --- | --- | --- |
| Kanban | 4,949 / 677 | 0,108 / 2 |
| Machine fresh | 2,496 / 50 | 1,453 / 51 |
| Machine cached | 0,315 / 38 | 0,231 / 27 |
| Další machine cached | neměřeno | 0,190 / 27 |

Kanban vrací stejných 322 tasků. Machine po změně vrací počty `claude=4, codex=0, pi=0`. Fresh kontrola má navíc ověření HEAD pro klíč roster cache; kratší fresh čas je pozorování včetně proměnlivých CLI probes, nikoli garantované zrychlení. Výsledky nejsou příslib času na Windows ani CI limitem.

## Regresní pokrytí

Nové deterministické testy používají 120 syntetických otevřených PR a kontrolují konstantní počet policy/identity čtení, shodu stromu a seznamu, filtry, pořadí, součty, chybu merge a schválené PR. Další scénáře pokrývají změnu policy během requestu a mezi requesty, smazaný soubor, poškozený JSON a nepodporovanou verzi po úspěšném čtení, souhrn prázdného a archivovaného backlogu a chybu konfigurace. Test roster cache ověřuje změny konfigurace, base, knihovny a registru. Frontendové a browser testy ověřují souhrn a absenci druhého plného kanban requestu.

Builder spustil jediný cílený diagnostický test `test_roster_cache_follows_config_base_library_and_registry`: prošel (1 test). Kompletní ověření změny, sestavení shipped frontendu a browser test patří samostatnému testovacímu kroku workflow.
