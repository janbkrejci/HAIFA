# HAIFA-REFINEMENT-T69 — Sdílený výběr harnessu, modelu a thinking

## Cíl a rozsah

Sjednotit výběr `harness`/`model`/`thinking` pro běh tasku, návrh workflow a „Vylepšit task“. Existující task čerpá z vlastního uzlu a předků; nový draft ze zvoleného stepu včetně jeho předků. Repo bez uzlu používá nastavení počítače (`harnesses.json`), jinak roster plan agenta. Explicitní volba v dialogu nadále vyhrává.

Implementace smí změnit pouze níže uvedené zdrojové soubory, povolené testy a dokumentaci tasku. Neměnit frontend, schéma backlogu, validační pravidla editace, nastavení počítače ani jiné AI pomocníky. Běh a retry tasku musí zůstat funkčně stejné. Nepřidávat export do `backlog/__init__.py`; importovat funkci přímo z `backlog.derived`.

## Zjištěný stav

- `run/task.py:task_harness_values` jde od nejvyššího předka k tasku, při pravdivém odlišném harnessu odstraní model a přepíše pouze pravdivé hodnoty tří klíčů. Thinking se při změně harnessu nemaže. `ancestors` má v tomto souboru ještě jiného uživatele; jeho import ponechat.
- `derived.py` již obsahuje `ancestors(node)` a `own_values(node)` pro Task i Container. Obecné `effective` a `effective_sources` neměnit.
- `harness/settings.py:effective_override` doplňuje nastavení počítače, kanonizuje harness a kontroluje zakázané harnessy či neúspěšně otestovaný výchozí model. Chybějící soubor vrací pro prázdné hodnoty `{}`. Existující settings s `default_harness=None` dnes vyvolají chybu, pokud ani vstup neurčí harness.
- `adaptive.context` slučuje defaults předků, vlastní parametry a draft nezávisle po klíčích; tím může zachovat model jiného harnessu. Ostatní pole kontextu a jejich dědění zachovat.
- `adaptive.recommend` používá `advisor` pro task advice, u workflow znovu volá `effective_override` nad `effective`.
- `AdviceManager.start` dnes vybírá advisor pouze pro task advice. `_resolve` má fallback na plan agenta, ale vrací jen harness a model. `Job.json()` již předává celý slovník `context['advisor']`.
- Workflow save přepočítává `fingerprint(context(...))`. Přidání advisoru pouze do kontextu jobu by bez úpravy výpočtu otisku znemožnilo uložit i nezměněný návrh.

## Implementace

### 1. Dědění backlogu

V `aifactory/src/aifactory/backlog/derived.py` přidat `harness_values(node: Node) -> dict[str, object]`:

1. Projít obrácené `ancestors(node)` a nakonec samotný uzel; pro hodnoty uzlu použít `own_values`.
2. Převzít přesně dosavadní algoritmus `task_harness_values`: při pravdivém harnessu odlišném od dosavadního odstranit model, poté doplnit pouze pravdivé `harness`, `model`, `thinking` tohoto levelu.
3. Nedělat zde čtení počítače, kanonizaci, validaci nebo doplňování výchozích modelů. Nemutovat vstupní slovníky.

V `aifactory/src/aifactory/run/task.py` ponechat veřejnou signaturu `task_harness_values(task)` jako tenký wrapper `return harness_values(task)`. Neměnit `effective_override`, `apply_agents_override`, start ani retry call sites.

### 2. Vazba kontextu na počítač

V `aifactory/src/aifactory/harness/settings.py` přidat `context_binding(values: dict[str, object]) -> dict[str, str]`. Běžný výsledek je `effective_override(values, None)`; pro repo volat s `{}`.

Bez nastaveného harnessu v objektu i počítači vrátit `{}` a nechat rozhodnout roster. Pokrýt chybějící soubor i existující settings s `default_harness=None`. Tento druhý případ ošetřit úzce v novém helperu, nikoli změnou chování `effective_override` pro běh tasku. Nepohlcovat ostatní `ValueError`: explicitně zakázaný harness, chybná konfigurace či selhaný test modelu musí zůstat chybou. Má-li objekt harness, funguje i bez výchozího harnessu počítače. Pokud vstup obsahuje jen model/thinking a žádný zdroj harness neurčuje, helper vrátí `{}` podle pravidla fallbacku.

### 3. Kontekst a skutečný běh poradce

V `aifactory/src/aifactory/workflow/adaptive.py`:

- V `context` po dosavadním sestavení ne-harnessových hodnot odstranit všechny tři dosavadní hodnoty harness/model/thinking a nahradit je výsledkem `context_binding(harness_values(task if task is not None else parent))`. Tím nepřežije starý model po změně harnessu. Zachovat existující tvar `effective` včetně případných `None` u chybějících klíčů.
- Převést chyby výběru na `UsageError` se zprávou původní výjimky. Hodnoty workflow/writes, draft parametrů, rodiče, vztahy a katalog zůstávají podle nynějšího chování.
- V `recommend` pro obě varianty použít vybraný `ctx['advisor']`, pokud je přítomen; pro přímé volání bez advisoru použít `context_binding(ctx.get('effective', {}))`. Výsledek aplikovat přes stávající `apply_agents_override`. Prázdná vazba zachová roster plan agenta.
- Zachovat kontroly role/agent existence, `ensure_enabled`, kontrolu harnessu, izolaci práce a tracing.

V `aifactory/src/aifactory/web/workflow_advice.py`:

- `_resolve` rozšířit o volitelné kontextové hodnoty; bez explicitní volby použít `context_binding(values)` a poté roster fallback. S explicitní volbou zachovat dosavadní prioritu dialogu: `effective_override({}, explicit)` a následně roster fallback, nikoli slučování s modelem objektu. Harness-only výběr tedy bere model vybraného harnessu z počítače stejně jako dnes.
- Do roster fallbacku doplnit `thinking`, pokud je nastaveno. Výchozí odpověď `options()` může zůstat pouze harness/model; měnit je třeba job advisor, nikoli frontendové API výběru.
- V `start` validovat ruční volbu jako dosud; pro oba typy advice určit advisor ze sdíleného výběru. Pro automatickou volbu využít opravené `ctx['effective']`; pro ruční volbu použít explicitní větev `_resolve`. `ctx['advisor']` musí obsahovat také vybrané thinking.
- Zachovat workflow save fingerprint: pro workflow spočítat digest z původního výsledku `context` před přidáním advisoru a pouze pak přidat advisor do kontextu předávaného runneru. `save` tak může dál přepočítat stejný základní context. Pro task advice ponechat zahrnutí ručního advisoru do digestu, aby se různé volby nededuplikovaly. Výpočet nepřepisovat plošně a neodstraňovat ochrany proti zastarání. Nastavení počítače jsou již zahrnuta přes opravené `effective`.

## Testy

Nové testy mají používat fake harnessy, dočasné HAIFA_HOME a existující lokální repo fixture. Společný `aifactory/tests/advice_fixture.py` není povolená write cesta; potřebné úpravy fixture udělat lokálně v povolených testech. Testy mohou samozřejmě vytvářet a commitovat dočasné testovací repozitáře podle nynějších helperů.

1. Přidat `aifactory/tests/backlog/test_backlog_harness_values.py`. Sestavit Task/Container strom a ověřit projekt, step i task: shodné zděděné hodnoty bez override, bližší harness odstraní vzdálený model, nový model ve stejném levelu přežije, stejný harness model nesmaže, bližší model/thinking přepíše předky, prázdné/null hodnoty se přeskočí, thinking se změnou harnessu zachová. Ověřit shodu wrapperu tasku a nového helperu i neměnnost vstupů. Vnořené přepnutí testovat přímo na modelu stromu, bez rozšiřování pravidel editace backlogu.
2. V `aifactory/tests/harness/test_harness_settings.py` pokrýt `context_binding`: repo default se všemi třemi hodnotami, objekt přebíjí počítač, chybějící default vrací `{}`, explicitní objektový harness funguje bez defaultu, disabled/failed model chyby se nezamlčí. Existující testy `effective_override` neměnit významově.
3. V `aifactory/tests/workflow/test_workflow_advice.py` parametrizovat existující task a nový draft ve stepu projektu s codex/model/thinking. Nastavení počítače nebo roster dát na odlišný harness a ověřit všechny tři hodnoty v `effective`. Rozšířit fake engine test tak, aby ověřil skutečně použitou codex interface, model a thinking, nejen payload. Přidat případ přepnutí harnessu na nižším uzlu s výběrem modelu počítače pro nový harness. Ověřit také roster fallback bez nastavení počítače.
4. V `aifactory/tests/web/test_web_workflow_advice.py` ověřit pro task i draft zděděné codex/model/thinking v runner contextu a v advisoru POST i GET jobu. Zachovat a podle potřeby rozšířit save/dedup test, aby job s advisorem šel uložit a změna rodičovských hodnot způsobila zastarání návrhu.
5. V `aifactory/tests/web/test_web_task_advice.py` rozšířit test automatického advisoru o projektové dědění pro existující task a nový draft; porovnat advisor v runneru a v job odpovědi včetně thinking. Přidat nižší přepnutí harnessu bez starého modelu. Ověřit ruční harness-only i harness+model volbu odlišnou od projektu a její prioritu. Zachovat stávající options a validační testy.

## Dokumentace a ověření

Zapsat skutečné výsledné chování a provedené ověření do `factory/docs/HAIFA/REFINEMENT-upravy-opravy-a-vylepseni-z-praxe/HAIFA-REFINEMENT-T69-sdileny-vyber-harnessu-modelu-a-thinking.md`. Popsat pořadí dědění, reset modelu při změně harnessu, nastavení počítače, fallback a ruční výběr. Neuvádět neprovedené testy jako úspěšné.

Builder spustí z kořene repozitáře (pytest cesty jsou relativní k `aifactory`, jak vyžaduje justfile):

```sh
just lint
just typecheck
just pytest tests/backlog/ tests/harness/test_harness_settings.py tests/workflow/test_workflow_advice.py tests/web/test_web_workflow_advice.py tests/web/test_web_task_advice.py
just pytest tests/run/
```

Poslední příkaz ověřuje přímé volající sdíleného wrapperu včetně běhu a retry bez změn jejich testů; nepouštět celou sadu. Pro lint/typecheck dát rezervu a pro pytest balíčky dostatečný timeout. Frontend se nemění, proto není potřeba web-build/web-test ani browser suite.

Úspěch: všechny uvedené kontroly projdou, task/step/projekt sdílejí stejnou dědičnost, skutečný poradce i jeho job metadata odpovídají očekávanému výběru, ruční volba vyhrává a save/dedup zůstává funkční. Diff obsahuje pouze povolené cesty. Plánovací fáze žádnou implementaci ani testy nespouští.
