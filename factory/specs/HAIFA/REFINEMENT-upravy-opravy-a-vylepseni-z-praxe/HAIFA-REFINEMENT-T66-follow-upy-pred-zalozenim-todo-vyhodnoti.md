# HAIFA-REFINEMENT-T66 — triáž follow-upů před zápisem

## Cíl a rozsah

Zapojit existující read-only triáž do dokončování běhu. Novou práci nejprve porovnat s celým neudělaným backlogem; použít `covered`, bezpečné aditivní `extend`, lidské `decide`, nebo dosavadní `new`. Agent nikdy nezúží ani zásadně nezmění existující zadání. Dlouhé volání agenta nesmí držet zámek běhů.

Plán je obnoven podle větve po rebase v pokusu 2. T64, T65 a T67 jsou sloučené; nejsou blokátory. T64 již přidává `CreatedFollowUp.assignee`, `TaskRunStore.queue_front()` a volání fronty v `_record_follow_ups`. T65 obsahuje `Decision`, `TriageOutput`, `ask_triager`, `TriageUnavailable` a validační pravidla. Tyto závislosti nepřepisovat.

Implementace smí změnit jen:

- `aifactory/src/aifactory/run/followups.py`
- `aifactory/src/aifactory/run/task.py`
- `aifactory/tests/run/test_followups.py`
- `aifactory/tests/run/test_followups_queue.py`
- nový `aifactory/tests/run/test_followups_triage.py`
- `docs/decisions.md`
- tento předepsaný spec a `factory/docs/HAIFA/REFINEMENT-upravy-opravy-a-vylepseni-z-praxe/HAIFA-REFINEMENT-T66-follow-upy-pred-zalozenim-todo-vyhodnoti.md`

Neměnit triagerovy typy/prompty, UI, `.factory/`, backlog ani společné testovací fixture mimo tyto cesty. Pokud ověřování prokáže nutnost upravit jinou fixture, před editací vrátit strukturované `needs_writes` s konkrétní cestou a důvodem, jak vyžaduje zadání. Nezakládat na to follow-up.

## Doložená rozhraní a úskalí

`triage.context()` čísluje předané follow-upy `f1`, `f2`, …; `Decision.action` nese druh výsledku. `extend` vyžaduje `addition` a `addition_writes`, `decide` vyžaduje `proposal`. `collect(wf, settings)` deduplikuje podle normalizovaného titulku a efektivního lidského přiřazení; bez settings se mohou počty lišit. Stejné deduplikované položky proto musí projít přípravou i aplikací.

`triage.py` importuje `Reported` z followups a pomocné funkce z task. Runtime import triáže provést lokálně po inicializaci modulů; anotace řešit přes `TYPE_CHECKING`, aby nevznikl cyklický import.

`record()` vytváří dočasný stage, `_record()` upravuje backlog a `_publish()` publikuje jen změněné soubory. Tento postup zachovat. `_record_follow_ups()` dnes drží `store.serialized()` kolem zápisu a za úspěšné publikace posouvá nové agentní tasky přes `queue_front()`.

Čerstvý stav cíle se ověřuje přes `store.running(target_id)` pod již získaným zámkem. Kontrola zahrnuje i pozastavené tasky evidované jako running a před vyhodnocením uklízí mrtvé běhy.

`backlog.edit.edit_task(body=...)` využívá `taskfile.replace_body()`, který zvlášť přesouvá/uchovává `## Běhy` a normalizuje konce těla. Samotné slepé připojení do `Task.body` proto není zárukou zachování původního textu.

## Navržené změny

### 1. Příprava mimo zámek a explicitní předání výsledků

V `_record_follow_ups()` oddělit přípravu triáže od existujícího serializovaného zápisu:

1. Načíst backlog a settings z hlavního repozitáře stejným způsobem jako zápis; sestavit `collect(wf, settings)`. Nevolat agenta pro samotné `blocked_by` bez follow-upů.
2. Zavolat `triage.ask_triager(main, reported, backlog)` mimo `store.serialized()`. Vstup obsahuje celý backlog pro T65, nikoli jen závislosti nebo TODO step zdrojového projektu.
3. Zachytit `TriageUnavailable`, uchovat vysvětlující varování a pokračovat dosavadní cestou pro všechny položky. Běžné chyby vyvolání triáže nesmí spolknout follow-upy; oddělit chybu triáže od chyby zápisu. Nezachytávat uživatelské přerušení jako úspěšnou triáž.
4. Pod `store.serialized()` znovu načíst aktuální settings/backlog. Předat rozhodnutí mapovaná na připravené položky a callback `store.running` do `record()` / `_record()` pomocí keyword parametrů. Stage a zápis se vytvářejí až nyní, nikoli ze staré kopie před agentem.
5. Udržet mapování `fN` na stejné `Reported`: přenést připravený seznam a jeho stabilní identity. Pokud aktuální settings změnily efektivní lidské přiřazení nebo deduplikaci, staré rozhodnutí nesmí zasáhnout jinou položku; dotčenou položku zpracovat dosavadní cestou.

Přímé stávající volání `record()` bez rozhodnutí ponechat kompatibilní a deterministické: provede dosavadní zápis bez implicitního volání modelu. Triáž orchestruje `_record_follow_ups()`, používané běhy, retry i resolve.

### 2. Čerstvá validace a bezpečnost aplikace

Před použitím každého doporučení načíst aktuální cílový task ve stage. `covered`, `extend` a `decide` platí jen pro existující `todo` task, který právě neběží. Zdrojový task nikdy nesmí být svým vlastním cílem. Neplatné doporučení převést na dosavadní `new` a uvést stručné varování.

U `extend` znovu ověřit efektivní `writes`, `addition_writes`, cesty uvedené v doplnění, lidské přiřazení cíle i lidský charakter původní práce včetně `_for_human`. Znovu použít T65 validační logiku z `triage._violations` (správně sestavený `TriageOutput` nad stejným seznamem), aby se neoslabila konzervativní kontrola globů a důkazů rozsahu. Pracovat po položkách, aby jedna zastaralá odpověď nezrušila ostatní platné výsledky. Neměnit T65. Neplatné rozšíření se nesmí tiše použít ani měnit front matter.

U blokujícího reuse před zápisem zajistit, že přidání `source.depends_on -> target` nevytvoří self-reference nebo cyklus; zohlednit i kontejnerové závislosti přes existující backlog validaci. Nebezpečný reuse převést na nový follow-up, nikoli zapsat cyklus nebo nesmyslný blocker. Zachovat dosavadní varování a blokovací placeholdery při odmítnutém zápisu. Existující fallback podle titulku nesmí po tomto odmítnutí znovu zvolit stejný nebezpečný cíl.

### 3. Aplikace čtyř rozhodnutí v `followups.py`

- `covered`: nevytvářet TODO step ani task. Přidat cílový task do `outcome.created` s `existed=True`, skutečným assignee a `decision='covered'`. Je-li položka blokující, přidat bezpečnou závislost na cíl.
- `extend`: doplnit pouze samostatný oddíl `### Doplnění z běhu <run_id> tasku <source_id>` s textem `addition` a stabilním markerem. Původní obsah, titulek a všechny front matter klíče zachovat. Výstup ukáže existující cíl, `existed=True`, `decision='extend'`; blokování míří na něj.
- `decide`: založit lidský task v TODO stepu projektu zdroje. Tělo vysvětlí původní hlášení, `proposal`, důvod triáže a důvod předání člověku; nebude jen přejmenovanou agentní prací. `related` obsahuje zdroj i navrhovaný cíl, marker je markerem follow-upu zdroje. Vynutit `assignee: human` nezávisle na původním `for_human`. Cílový soubor se vůbec nezmění. Blokuje nový lidský task, nikoli cíl návrhu. Retry využije již založený lidský task.
- `new`: zachovat stávající zakládání, dědění/vlastní writes a workflow, lidské přiřazení chráněných cest, marker, původ, fallback reuse otevřených závislostí a deduplikaci již založených tasků. Explicitní validní rozhodnutí triáže nesmí přepsat pouhá shoda titulku. Při nedostupné triáži se chování včetně starého reuse nezmění.

TODO step vytvořit teprve pokud je nutný nový nebo rozhodovací task. Po jednotlivých zápisech aktualizovat pracovní backlog, aby dvě rozšíření téhož cíle nepřepsala první změnu.

Zápis rozšíření musí projít `aifactory.backlog.edit`. Preferovat existující `edit_task` jen tam, kde prokazatelně zachová celý originál. Pro přesné aditivní vložení bez změny historie a dalších sekcí lze v lokálním helperu použít existující `edit._write_checked(backlog, baseline, {path: original_plus_section}, command)` s baseline z `check_backlog`, stejně jako validační/zapisovací vrstvu editoru. Tím se zachová validace, žurnál a publikace; nepoužívat samostatný přímý `write_text` na backlog. Původní soubor včetně front matter a všech sekcí musí zůstat doslovně zachován, přibude jen nový oddíl.

### 4. Idempotence, JSON a fronta

Marker rozšíření musí identifikovat jednotlivý follow-up, ne jen zdrojový task a ne run id. Použít např. `extended-by=<source_id>` spolu se stabilním digestem identity `(normalizovaný title, efektivní human)`, odpovídající deduplikaci `collect`. Digest nesmí záviset na pořadovém `fN`, formulaci agentova doplnění ani run id. Dvě různé položky stejného zdroje rozšiřující stejný cíl musí mít dva markery a dva oddíly; opakování obou i v jiném běhu či s přeházeným pořadím nic nezdvojí. Před opakováním mutace kontrolovat marker. Rozhodovací task musí obdobně zachovat stabilní identitu hlášení a cíle při opakování. Již doloženou aplikaci rozšíření při replay nepřepisovat ani z ní nevytvářet duplicitní práci jen kvůli novému slovnímu návrhu agenta. Marker se hledá v celém čerstvém backlogu před aplikací jakéhokoli nového doporučení i fallbacku. Potvrzení uloženého doplnění vrací původní `extend` s `existed=True` i při novém `new`, jiném cíli či nedostupné triáži, bez mutace cíle. Změna stavu, assignee, rozsahu nebo běžící task nevyvolá opětovné doplnění; kontroly způsobilosti se uplatňují na nové aplikace. Nová blokující závislost i při potvrzení musí projít kontrolou cyklu; nelze-li ji bezpečně zapsat, varování a neuložený blokátor zachovají blokování bez duplicitního tasku.

Přidat `CreatedFollowUp.decision` s literálovým typem čtyř hodnot a kompatibilní výchozí hodnotou `new`. Zachovat `assignee`, `existed` a ostatní pole. `to_json()` přidá `decision` pro každou položku; `FollowUpOutcome.to_json()` tím rozšíří své `created`, protože výsledek může obsahovat směs rozhodnutí. Hodnota popisuje skutečně provedenou akci po validaci a fallbacku.

V `_record_follow_ups()` zachovat existující T64 volání `queue_front()` po úspěšném publish a pod zámkem. Filtr explicitně vyžaduje `decision == 'new'`, `not existed` a `assignee != 'human'`. Covered/extend/decide, již existující tasky a nepublikované zápisy se neposunují. Zachovat pořadí nových agentních tasků, ostatní preference fronty a varování při chybě fronty. Neměnit samostatnou prioritu skutečných blokátorů v queue/store.

`blocking=False` nadále vypne všechna blocks_task a ignoruje blocked_by pro resolve, i u všech nových rozhodnutí. Chyba samotného record nadále neztratí ohlášený blocker.

## Testy a ověření

Nový `test_followups_triage.py` použije dočasná lokální repa a mock `aifactory.run.triage.ask_triager`. Otestuje orchestrace přes `_record_follow_ups()` i výsledné publikované soubory; žádné živé harnessy/modely ani síť.

1. Všechny čtyři akce, různé titulky hlášení a cílů a cíl mimo otevřené závislosti. Covered nevytvoří TODO step; extend mění pouze přidaný oddíl; decide vytvoří human task se dvěma related a nezmění cíl; new zachová dosavadní obsah/přiřazení.
2. Parametrizované blokování covered/extend/decide a `blocking=False`; výsledné depends_on a outcome odpovídají skutečnému blokátoru. Self-target a nepřímý cyklus nevytvoří neplatný backlog.
3. Extend zachová raw front matter, původní text, historii `## Běhy` a sekce za ní. Dva různé follow-upy stejného zdroje na stejný cíl zůstanou oba. Opakované volání v témže i jiném run id a přeházení pořadí nezvýší počet oddílů ani nevytvoří task.
4. Mock triáže během návratu změní cíl na done/cancelled, odstraní ho, změní assignee na human nebo zúží vlastní/zděděné writes. Další varianta simuluje nově běžící cíl. Pod zámkem nastane fallback new bez změny cíle. Otestovat odmítnutí rozšíření lidské/chráněné práce.
5. `TriageUnavailable` pro chybějícího agenta i neúspěšný výsledek: stejné tasky a blokování jako dosud plus konkrétní warning v outcome i varováních běhu. Bez hlášených follow-upů agent není volán.
6. Instrumentovaný `store.serialized()` eviduje hloubku zámku: mock ask_triager vyžaduje hloubku nula, aplikace a čerstvá kontrola běžících tasků kladnou. Nepoužívat časovací test se sleep.
7. JSON směsi výsledků zachová stará pole včetně assignee a přidá správné decision, včetně fallbacku.

V existujících `test_followups.py` a `test_followups_queue.py` zachovat dosavadní assertions. V místních fixtures těchto povolených souborů pro staré scénáře mockovat triáž deterministickým `new`, aby reálný běh/retry/resolve nespotřeboval scénář fake harnessu na dalšího agenta. Nové testy explicitně přepíší mock pro daný scénář. Přímé `record()` testy nemají volat agenta. Rozšířit queue test o směs covered/extend/decide/new včetně human new a ověřit, že vpředu jsou jen nové agentní tasky. Zachovat testy PR režimu, selhání publish/fronty, retry a resolve.

Ověření implementace používá cílené příkazy podle pravidel builder fáze (lint a typecheck pouze změněných souborů):

- Ruff check a format check pěti změněných Python souborů.
- Mypy stejných souborů s `MYPYPATH=tests:tests/run:tests/workflow`.
- `just pytest tests/run/test_followups_triage.py tests/run/test_followups_queue.py -n 4`
- `just pytest tests/run/test_followups.py tests/run/test_triage.py tests/run/test_task_resolve_generated.py::test_missing_test_in_a_bundle_only_resolve_becomes_a_follow_up tests/run/test_follows_prompt.py tests/review/test_prbody_summary.py -n 4`

Výsledek: všech 162 vybraných testů prošlo, stejně jako scoped Ruff a mypy. Ověření nespotřebovalo živý model ani nevyžadovalo změnu společných fixture mimo povolené cesty.

Web ani browser testy nejsou potřeba. Při plánování se implementační testy nespouštějí. Výsledek příkazů posuzovat podle exit status, ne podle slov v logu.

## Dokumentace a dokončení

Rozšířit bod **Follow-upy** v `docs/decisions.md`: triáž nad neudělaným backlogem; čtyři výsledky; aditivní doplnění pouze do nebežícího agentního todo v jeho writes; zadání se bez člověka nezužuje ani zásadně nemění; lidské decide; fallback s varováním; idempotence a filtr T64. Zachovat dosavadní vysvětlení lidských follow-upů a chráněných cest.

Do předepsané taskové dokumentace zapsat skutečné výsledné chování, ověření a případné praktické omezení, bez seznamů nedokončené práce. Dokončení znamená zelené cílené kontroly, zachované offline testy a změny jen v povolených souborech. Git commit/push/PR řeší workflow, nikoli tato plánovací fáze.
