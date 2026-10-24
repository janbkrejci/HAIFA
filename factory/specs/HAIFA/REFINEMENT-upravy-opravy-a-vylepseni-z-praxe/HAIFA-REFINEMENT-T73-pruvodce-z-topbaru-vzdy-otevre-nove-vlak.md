# T73 — Nové vlákno průvodce při otevření z topbaru

## Cíl a rozhodnutí

Otevření zavřeného panelu přes `assistant-toggle` nebo explicitní `setOpen(true)` vždy přepne na nové, dosud neuložené prázdné vlákno. Kliknutí na topbar při otevřeném panelu jej dál zavírá. Historie uchovává existující konverzace; reload stránky s otevřeným panelem obnoví vybrané vlákno včetně rozpracované odpovědi. Pouhá změna obrazovky otevřenou konverzaci nepřepíná.

Vlákno se dál vytváří až první zprávou, nikoli otevřením panelu. Při vytvoření dostane stejný efektivní `screen`, který panel přikládá ke zprávě: aktuální kontext po zohlednění odebraného chipu. Na Přehledu a po odebrání chipu se klíč `screen` neposílá. Harness, model a thinking vybírá a uchovává backend z T72; klient je nepřebírá z globálních nastavení ani neposílá jejich vlastní override.

## Rozsah souborů

Implementace a testy smějí měnit pouze:

- `aifactory/web/src/lib/assistant.ts`
- `aifactory/web/src/lib/assistant.test.ts`
- `aifactory/web/src/components/assistant/` (pro tuto změnu zejména `AssistantPanel.vue` a `AssistantPanel.test.ts`)
- `aifactory/web/src/App.vue` pouze pokud je nezbytná úprava zapojení; nynější `@click="toggleOpen"` a `restoreOpen()` při mountu již odpovídají cíli
- `aifactory/web/src/App.test.ts`
- `aifactory/tests/e2e/test_assistant_browser.py`
- generovaný obsah `aifactory/src/aifactory/web/static/`
- tuto specifikaci a výslednou dokumentaci `factory/docs/HAIFA/REFINEMENT-upravy-opravy-a-vylepseni-z-praxe/HAIFA-REFINEMENT-T73-pruvodce-z-topbaru-vzdy-otevre-nove-vlak.md`

Nejsou potřeba další writes. Backend ani konfigurace sestavení se nemění. T72 je v checkoutu implementováno: POST threads přijímá `screen`, uložený binding obsahuje thinking a produkční guide zatím povoluje Claude s existujícím fallbackem. Nezavádět závislost na živém modelu.

## Zjištěný stav

`setOpen(true)` v `assistant.ts` dnes jednorázově načte id ze sessionStorage pomocí příznaku `restored`; `restoreOpen()` volá právě tuto funkci. `newThread()` již invaliduje asynchronní otevření přes `generation`, zavírá stream a odstraňuje uložené id. `send()` ale zakládá vlákno pomocí `createThread()` s prázdným body; kontext se posílá až ve zprávě.

`AssistantPanel.vue` už vypočítává efektivní `context`, předává jej do `send()` a zobrazuje harness/model skutečného vlákna přes `harnessLabel`. Typ `ThreadSummary` zatím thinking nemá. Několik testů panelu načítá fixture pouhým uložením id do sessionStorage před `setOpen(true)`; to je očekávání, které tento task záměrně mění.

## Postup implementace

### 1. Oddělit explicitní otevření od obnovy

V `assistant.ts` upravit `setOpen` tak, aby nastavil stav panelu a při každém `true` zavolal `newThread()`; nesmí načítat uložené id. Při `false` zachovat id aktuálního vlákna pro historii a persistovat zavřený panel. `toggleOpen()` zůstane delegací na `setOpen(!assistant.open)`.

`restoreOpen()` musí samostatně obnovit panel pouze při uloženém `haifa.assistant.open === '1'`. Otevře jej bez volání nové větve `setOpen(true)` a přes `openThread(id)` obnoví uložené id, pokud existuje. Zachovat jednorázovost obnovy, příznak `restored` spravovat na této cestě; explicitní otevření musí zabránit pozdějšímu opožděnému obnovení starého id. Před případným zápisem storage nejprve přečíst potřebné hodnoty. Zavřený panel se při reloadu neotvírá ani nenačítá vlákno. Chybějící či již smazané id dál končí prázdným panelem podle existujícího zpracování `unknown_thread`.

Ponechat `openThread` pro historii a replay streamu. Při resetu na nové vlákno vynulovat také `assistant.loading`: staré načítání po změně `generation` jinak nemůže tuto hodnotu uklidit. Zachovat generační ochranu a zavírání streamu; opožděná odpověď starého načtení nesmí nové prázdné vlákno přepsat. Nezavádět nový stavový framework ani mazání historických vláken.

### 2. Předat kontext při založení a ukázat binding

Rozšířit `createThread` o parametr `screen: ScreenContext | null` (volitelný s výchozím null je přípustný kvůli kompatibilitě). Body je `{ screen }` jen pro neprázdný kontext, jinak `{}`, obdobně jako `sendMessage`. `send(text, screen)` při prvním odeslání zavolá `createThread(screen)`. Další zprávy existujícího vlákna jej znovu nezakládají a nemění jeho binding.

V `ThreadSummary` přidat kompatibilní `thinking?: string | null`; `ThreadDetail` jej zdědí. V panelu rozšířit `harnessLabel` o thinking a předávat skutečnou hodnotu vlákna do `answering`. Formát: `claude · claude-opus-5-5 · medium`; bez thinking zachovat dosavadní `harness · model` bez prázdného oddělovače. Stejný helper použít s thinking také v již existujícím metadatu položky historie. Prázdný panel dál nemá známý binding a ponechá nynější obecný popisek; nepředstírat binding z předchozí konverzace.

### 3. Regresní testy Vitest

V `assistant.test.ts` přidat přímé testy veřejného stavového API se stubovaným fetch a podle potřeby `FakeEventSource`. Ověřit:

- uložené id se při `setOpen(true)` nenačítá; existující konverzace, listing a stream se při opětovném otevření resetují, id zmizí ze storage a otevření samo neposílá POST;
- zavření a otevření přes `toggleOpen` ukáže prázdné vlákno i podruhé;
- `restoreOpen` s oběma storage klíči obnoví detail, se zavřeným panelem neprovede GET, bez id ukáže prázdný panel; opakované volání obnovy nic nepřepíná;
- opožděný GET dřívějšího `openThread` nepřepíše nové vlákno a panel nezůstane loading;
- první `send` předá `screen` do POST threads i messages; null/prázdný screen klíč vynechá; další zpráva nevytváří další vlákno.

V `AssistantPanel.test.ts` zachovat `openPanel()` jako explicitní nové otevření. Fixture testy akcí, odmítnutí návrhu a smazání otevřeného vlákna změnit na explicitní `openThread` po otevření panelu, případně skutečný výběr z historie. Test obnovy rozpracované odpovědi použije oba storage klíče a `restoreOpen`, nikoli `setOpen(true)` s id.

Rozšířit existující test streamování o kontrolu `sent[0].body` s kontextem běhu; přidat variantu tasku. V testu odebrání chipu kontrolovat `{}` také u vytvoření vlákna. Přidat odeslání na Přehledu bez screen, zachovat obnovu chipu při změně obrazovky. Otestovat label vytvořeného i historického vlákna s thinking a kompatibilitu bez thinking/null. Historie musí stále načíst zprávy i uložený binding staršího vlákna.

V `App.test.ts` rozšířit topbar scénář na dokončenou konverzaci → zavření → nové otevření přes skutečný `assistant-toggle` → prázdné zprávy a tři návrhy → historie → otevření starší konverzace. Stub POST a GET rozlišovat metodou, nově vytvářeným vláknům přidělovat odlišná id. Ověřit aria-pressed, zachování konverzace při navigaci v otevřeném panelu a samostatně mount s otevřeným uloženým vláknem pro reload cestu. Test helper resetuje storage, proto hodnoty pro simulovaný reload nastavit až po resetu.

Před dokončením vyhledat přes `rg` výskyty `assistant-toggle`, `assistant-harness`, `haifa.assistant.thread`, `restoreOpen`, `setOpen(true)` a `createThread(` ve frontendových a browser testech a upravit pouze očekávání dotčená touto změnou.

### 4. Browser scénář a statický build

V `test_assistant_conversation_browser` zachovat fake harness, streamování, navigaci odkazem a kontext chipu. Přizpůsobit očekávání `assistant-harness` thinking vracenému skutečným API (současný výchozí binding má medium).

Po dokončení první odpovědi ověřit reload s otevřeným panelem: stejná konverzace i odpověď se obnoví. Potom panel zavřít a otevřít skutečným tlačítkem topbaru; očekávat prázdnou konverzaci s návrhy aktuální obrazovky. Historie musí stále obsahovat původní vlákno a jeho výběr obnoví odpověď. Zachovat i pokrytí tlačítka `assistant-new`, pokud se dosavadní krok nahrazuje topbarem.

U první zprávy zachytit request POST `/api/assistant/threads` pomocí Playwright a ověřit body s repo kontextem. Pro task kontext využít existující skutečný `P01-S01-T01`, případnou druhou konverzaci musí API vytvořit s jiným id; netestovat vytvoření na smyšleném run id, protože T72 ověřuje existenci. Nepoužívat pevné sleeps ani externí služby. Zbylé browser scénáře akcí mají zůstat funkční.

Spustit `just web-build` před browser testem, protože browser server servíruje zabalené statické soubory. Uchovat generované změny včetně odstranění starých hashovaných assetů a aktualizovaného indexu. Závislosti ani lockfile ručně neměnit, zachovat THIRD_PARTY_NOTICES.

## Ověření a dokončení

Z kořene repozitáře spustit:

1. `just lint`
2. `just typecheck`
3. `just web-test`
4. `just web-build`
5. `just pytest tests/e2e/test_assistant_browser.py -n0`

Pro browser test použít dostupný systémový Chrome nebo podporovaný `HAIFA_E2E_CHANNEL` podle místního prostředí; fixture `_launch` již tuto volbu podporuje. Vyhradit přiměřené timeouty (frontend testy alespoň několik minut, browser soubor alespoň několik minut). Nespouštět celý pytest ani celou e2e sadu. Při dalších změnách zdrojů znovu sestavit statický frontend před opakováním dotčeného browser ověření.

Do povoleného dokumentačního souboru zapsat výsledné chování explicitního otevření, reloadu a historie, předání kontextu a zobrazení bindingu spolu se skutečnými výsledky příkazů. Nakonec zkontrolovat diff a `git status --short`: pouze povolené cesty, zdroje a generovaný build odpovídají sobě, žádné runtime databáze, screenshoty či lokální konfigurace v repozitáři.

Hotovo je po úspěchu uvedených kontrol a po prokázání, že nové otevření nikdy nepřinese starou konverzaci, historie a reload ji stále obnovují a první zpráva vytváří vlákno s kontextem aktuálního chipu.
