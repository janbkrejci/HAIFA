# HAIFA-REFINEMENT-T71: Kontextový binding triageru a learneru

## Cíl a rozsah

Triager follow-upů použije harness, model a thinking konkrétního běhu tasku, včetně ručního přepisu a přepnutí kvůli kvótě. Bez uloženého bindingu se nastavení odvodí z tasku sdíleným helperem z T69. Learner nad repozitářem použije výchozí nastavení počítače; bez konfigurace počítače zůstane roster.

Implementovat pouze změny v `aifactory/src/aifactory/run/triage.py`, `aifactory/src/aifactory/run/task.py`, `aifactory/src/aifactory/learn/scan.py`, odpovídající testy v `aifactory/tests/run/test_triage.py`, `aifactory/tests/run/test_followups_triage.py`, `aifactory/tests/learn/test_learn_scan.py` a dokumentaci `factory/docs/HAIFA/REFINEMENT-upravy-opravy-a-vylepseni-z-praxe/HAIFA-REFINEMENT-T71-triaz-follow-upu-s-harnessem-behu-tasku.md`. Tato specifikace má cestu určenou zadáním. Není potřeba rozšířit writes. Neměnit retry, quota mechanismus, workflow, frontend, konfiguraci počítače ani sdílené testovací helpery.

## Zjištěný stav a rozhodnutí

- `run_task` počítá binding přes `effective_override(task_harness_values(task), agents_override)`, aplikuje ho do `RunConfig` a ukládá pomocí `override_note` do `TaskRunRow.note`. `_chain_start` před uložením nahradí binding při startu na jiném harnessu.
- `run/retry.py` má existující parser `_note_override(note)`. Při přepnutí retry zapisuje nový binding do note a předává aktualizovaný řádek do `_execute`; quota fallback běží touto cestou. Uložený binding lze tedy předat triageru bez zásahu do retry nebo přenášení nového pole přes všechny vrstvy běhu.
- `_record_follow_ups` má dostupný `row.task_id` i `row.note`, ale dnes volá `ask_triager` bez kontextu. `_invoke` načítá čerstvý `RunConfig` a resolve provádí z rosteru.
- T69 již dodal `backlog.derived.harness_values` a `harness.settings.context_binding`. `task_harness_values` je wrapper nad prvním. `context_binding` při chybějícím harnessu objektu i počítače vrací `{}`; chyby skutečně nakonfigurovaného harnessu nezamlčuje.
- `_ask_learner` rovněž načítá nový `RunConfig` a resolve provádí bez override. Pro learner použít přímo požadované `effective_override({}, None)`. Absence souboru nastavení vrací `{}`; existující konfigurace s `default_harness: null` má nadále striktní chování tohoto helperu. Toto není důvod měnit `harness/settings.py`.

## Implementace

### 1. Triager: rozhraní a aplikace bindingu

V `run/triage.py` rozšířit `ask_triager` o volitelné keyword-only argumenty `task_id: str | None = None` a `binding: dict[str, str] | None = None`; předat je do `_invoke`.

Zachovat nynější návraty bez spuštění agenta pro prázdné follow-upy a backlog bez todo tasků. Stávající tříargumentová volání bez taskového kontextu musí zůstat funkční s rosterem.

V `_invoke` po načtení `rc`, před `prepare_cfg` a tedy před `agents.resolve(cfg, "triager")`:

1. Pokud `binding is not None`, použít jej přímo. Nepočítat ho znovu přes aktuální task nebo nastavení počítače. Explicitní `{}` je platný binding a nesmí spustit fallback.
2. Pokud binding chybí a `task_id` je zadané, najít tento task v předaném backlogu a spočítat `context_binding(harness_values(task))`. Task nemusí být todo; todo filtr patří pouze do vstupu triážního rozhodování. Neexistující task se zadaným ID ohlásit jako `TriageUnavailable`, nikoliv tiše použít nesouvisející roster.
3. Bez bindingu i ID zachovat prázdný override pro dosavadní samostatná volání.
4. Použít `rc = apply_agents_override(rc, effective_binding)` a z tohoto `rc` připravit `cfg`.

Použít stávající import `run.task` pro `apply_agents_override`; nevytvářet nový resolver. Ponechat stávající obalení výjimek v `ask_triager` jako `TriageUnavailable`, kontrolu dostupnosti harnessu, zákaz zápisu, izolaci, semantic correction i úklid traceru.

### 2. Předání z běhu tasku

V `_record_follow_ups` v `run/task.py` lokálně importovat existující `_note_override` z `aifactory.run.retry` a upravit pouze volání `ask_triager` na předání `task_id=row.task_id` a `binding=_note_override(row.note)`.

To je jediná potřebná věcná změna tohoto souboru, kromě souvisejícího importu. Nepřidávat binding do `_Job`, `_execute` ani retry. Nekopírovat parser poznámky a nepoužívat harness posledního workflow kroku: workflow smí mít vlastní overrides jednotlivých rolí, kdežto triager potřebuje binding celého běhu.

### 3. Learner s nastavením počítače

V `learn/scan.py` importovat `effective_override` a `apply_agents_override`. V `_ask_learner` ihned po `load_run_config(repo)` aplikovat `rc = apply_agents_override(rc, effective_override({}, None))`. `prepare_cfg` i `agents.resolve` musí dostat konfiguraci s přepisem. Zachovat stávající postup kontroly dostupnosti, read-only běh, korekce odpovědi a ukládání lekcí. Nepřidávat parametry CLI ani vlastní fallback, který by potlačoval chybnou konfiguraci počítače.

## Regresní testy

Využít existující lokální repozitáře a fake harnessy. Každý nový test musí sledovat skutečně vybraný harness a požadavek s modelem a thinking, nikoliv pouze ověřit, že byl zavolán helper. Fake pro Codex připojit lokálně v povoleném testovacím souboru; sdílené fixtures dnes patchují především Claude. Nastavení počítače izoluje `tests/conftest.py` přes `HAIFA_HOME`; nepřistupovat k reálným službám ani katalogům modelů.

### `tests/run/test_triage.py`

- Explicitní binding s Codex, platným modelem a thinking přebije odlišný roster triageru. Zachytit požadavek fake Codex harnessu, ověřit model a thinking a read-only chování.
- Explicitní binding má přednost před odlišným taskovým kontextem i nastavením počítače; rozhodování nesmí znovu odvodit původní harness.
- Bez bindingu, se zadaným task ID, použít dědění projektu/stepu/tasku přes T69 a doplnění z nastavení počítače. Použít již existující backlog fixture nebo její uzly v paměti bez rozšiřování pravidel editace backlogu.
- Bez bindingu i ID zachovat stávající roster. Explicitní `{}` se neinterpretuje jako chybějící binding. Doplnit chování neznámého task ID.
- Existující testy krátkých návratů a chyb musí dál projít.

### `tests/run/test_followups_triage.py`

- Aktualizovat lokální stuby `ask_triager`, aby přijímaly nové keyword argumenty. Testovací `SimpleNamespace` představující `TaskRunRow` musí mít `note=None`, pokud neověřuje uložený binding; neoslabovat produkční přístup k povinnému poli kvůli neúplné fixture.
- Testovat volání `_record_follow_ups` s note vytvořenou `override_note`: zachytit předaný task ID a celý binding včetně modelu a thinking.
- Přidat regresi pro změnu harnessu: task má původní Claude nastavení, ale řádek běhu obsahuje aktuální Codex binding po přepnutí. Nechat skutečný `ask_triager`/`_invoke` běžet s fake harnessy a ověřit, že žádost dorazí na Codex s novým modelem a thinking. Řádek se změněným note odpovídá kontraktu `retry_run` při quota fallbacku; otestovat průchod `_record_follow_ups` až do výběru harnessu, nikoliv jen mock vracející rozhodnutí.
- Bez tagu v note musí být předán `None` a task ID, aby fungovalo odvození z tasku. Ostatní testy aplikace rozhodnutí, blokování a fallbacku na nové follow-upy zachovat.

### `tests/learn/test_learn_scan.py`

- Nakonfigurovat v dočasném HAIFA_HOME výchozí Codex s konkrétním modelem a thinking, odlišným od Claude rosteru learneru. Spustit scan s existujícími námitkami ze dvou běhů a fake Codex harness odevzdávajícím platné lekce. Ověřit harness, model, thinking i normální výsledek scanu.
- Bez konfigurace počítače explicitně ověřit, že se dál použije learner z rosteru. Zachovat existující pokrytí obsahu lekcí, korekcí a izolace.
- Pro nastavování použít veřejné `harness.settings.write` a platná testovací data jako v `tests/harness/test_harness_settings.py`; případné získávání katalogu thinking/modelů stubovat lokálně, aby test nevolal živé služby.

## Ověření implementace

Z kořene repozitáře spustit a hodnotit podle exit status:

1. `just lint`
2. `just typecheck`
3. `just pytest tests/run/test_triage.py tests/run/test_followups_triage.py tests/learn/test_learn_scan.py`
4. `just pytest tests/run/test_task_run.py tests/run/test_task_retry.py tests/run/test_quota_fallback.py tests/run/test_quota_chain.py`
5. `just pytest tests/learn/`

Druhá skupina backend testů ověří, že čtení note a nový kontrakt nenarušily běh, retry ani kvótové přepínání. Celou sadu, web ani browser testy nespouštět. Nové testy přidat pouze do povolených souborů, existující příbuzné testy pouze spustit. Plánovací fáze tyto implementační kontroly nespouští.

## Dokumentace a akceptace

Do určeného dokumentačního souboru stručně zaznamenat původ bindingu triageru (aktuální note běhu včetně quota retry), fallback přes T69, výchozí nastavení learneru a skutečně provedené kontroly s výsledky. Neuvádět neprovedené testy jako úspěšné.

Hotovo je, když fake harnessy prokážou všechny tři hodnoty skutečně použité oběma pomocníky, triager po kvótovém přepnutí používá nový harness místo původního nastavení tasku a výše uvedené cílené kontroly projdou. V `task.py` zůstane pouze předání kontextu a nezbytný import. Žádná změna nesmí překročit povolené cesty.
