# T72 — Výběr bindingu nového vlákna podle obrazovky

## Cíl a rozsah

POST `/api/assistant/threads` přijme `{title?, screen?: {repo?, task?, run?}}`. Nové vlákno získá harness, model a thinking z tasku v registrovaném repozitáři, nebo z tasku odpovídajícího běhu. Samotné repo a chybějící kontext použijí nastavení počítače. Výsledek nadále podléhá omezení průvodce a uloží se jednou při vytvoření vlákna.

T69 je v checkoutu implementováno: použít `backlog.derived.harness_values(node)` a `harness.settings.context_binding(values)`. Nekopírovat jejich algoritmus ani neměnit priority dědění. Frontend řeší T73 a do této změny nepatří.

Měnit pouze:

- `aifactory/src/aifactory/web/assistant.py`
- `aifactory/src/aifactory/web/app.py`
- `aifactory/tests/web/test_web_assistant.py`
- tento spec na předepsané cestě
- `factory/docs/HAIFA/REFINEMENT-upravy-opravy-a-vylepseni-z-praxe/HAIFA-REFINEMENT-T72-ai-pruvodce-nove-vlakno-prebira-harness.md`

Žádné další writes nejsou potřeba.

## Závazné výklady zadání

Produkční `GUIDE_HARNESSES` zůstává `("claude",)`. Požadavek na převzetí Codex bindingu a současné zachování tohoto omezení znamená: resolver nejprve správně vybere Codex binding, ale produkční vlákno přejde přes `claude_fallback`. Převzetí Codex harness/model/thinking prokázat v testu s lokálním monkeypatchem allowlistu; produkční fallback prokázat samostatně bez monkeypatche. Nezpřístupňovat Codex produkčně.

Task nebo run vyžaduje neprázdné `screen.repo`; identifikátory jsou lokální repozitáři. Repo se hledá jen v `self.repos()`, nikdy se nepovažuje za cestu. Neznámé repo, task nebo run a nesoulad tasku a běhu vrátí HTTP 400 `usage_error`. Obsahuje-li kontext task i run, dohledat běh a ověřit shodu tasku; nepřeskakovat validaci běhu. U run použít dnešní backlog jeho tasku, nikoli historický roster, snapshot nebo ruční override běhu.

Chybějící `screen`, `null` a `{}` znamenají žádný kontext. Prázdná či null pole screen se vynechají stejně jako u zpráv; neprázdný task/run bez repa je chyba. Jiné hodnoty screen než objekt/null jsou neplatné, včetně `false`, `0`, `""` a `[]`. Při neplatném vstupu nevytvářet thread na disku ani v paměti.

## 1. Validace a výběr v assistant.py

1. Z dosavadního `parse_message` vyjmout malou společnou funkci pro syntaktické zpracování screen. Zachovat `SCREEN_KEYS`, `MAX_SCREEN`, trimování řetězců, ignorování null/prázdných polí, kontrolu typů, délky a nového řádku. Rozlišit absent/null od jiných falsy neobjektových hodnot. `parse_message` nadále validuje text a povolené klíče zprávy a volá tuto funkci. Nezavádět zprávám požadavek na existenci tasku/repa: dosavadní screen zprávy je popisek obrazovky.
2. `AssistantManager.create` povolí pouze `title` a `screen`; zachová dosavadní validaci titulku. Validuje screen ještě před sestavením a uložením Thread.
3. Přidat malý pomocný resolver v assistant.py pro hodnoty kontextu. Bez task/run vrátí `{}`; je-li repo uvedeno, ověří ho i při repo-only kontextu. Repo-only nevyžaduje existující backlog.
4. U task/run vybrat registrovanou cestu repa z jednoho snapshotu `self.repos()`. Pro task načíst backlog pomocí `aifactory.backlog.load_backlog(repo, create_missing=False)` (oproti původnímu plánu: `load_for_edit` může vytvořit chybějící backlog) a dohledat jej přes `find_task` (včetně ochrany proti duplicitním ID). Chyby neplatného kontextu převést na `AssistantError("usage_error", ...)`, ne na neobslouženou výjimku. Nevytvářet backlog ani nic necommitovat.
5. Run dohledat read-only: využít existující `web.repos.trace_db_of(repo)` a `web.overview._trace_view(db)`; z `trace.runs` najít přesný `run_id` a vzít `task_id`. Chybějící DB/běh odmítnout jako neplatný kontext; při nečitelném pohledu uvést v chybě skutečný důvod. Nevytvářet `TaskRunStore`, jehož konstrukce může měnit schéma, a nevolat metody reapující běhy. Existující overview pohled již zavírá spojení a podporuje nastavení trace DB. Dohledaný task validovat v aktuálním backlogu stejně jako explicitní task.
6. Z tasku vrátit `harness_values(task)`. Výběr v create provést přes `harness_settings.context_binding(values)`; bez tasku předat `{}`. `ValueError` z nastavení nadále převést na HTTP 409 `harness_unavailable` a nezamlčovat chybu konfigurace jako guide fallback.
7. Nemá-li binding harness, použít dosavadní `guide_defaults()`. Má-li task explicitní harness bez nastavení počítače, jeho binding platí; guide defaults jsou fallback pro nerozhodnutý výběr. Zachovat canonicalizaci a kontrolu `GUIDE_HARNESSES` následovanou `claude_fallback`. Fallback musí vzít model a thinking Claude, nepřenést Codex model do Claude.
8. Zachovat současnou konstrukci a persistenci `Thread`, včetně thinking a session_id. Není třeba rozšiřovat thread summary/detail o thinking ani ukládat screen jako trvalou vazbu. `send` a `_answer` nesmějí přepočítávat binding podle další obrazovky nebo změn backlogu/počítače.

## 2. Dokumentace API

V modulu `assistant.py` popsat výběr task/run → T69 binding → nastavení počítače → guide fallback a následné omezení povolených harnessů. Uvést, že vlákno drží i thinking. Zachovat popis command guardu a session.

V `app.py` aktualizovat docstring `assistant_create` a modulový přehled endpointů u řádku 203 na `{title?, screen?: {repo?, task?, run?}}`, výběr podle kontextu, HTTP 400 usage_error a dosavadní HTTP 409. Route dál deleguje manageru; resolver nepatří do HTTP vrstvy.

Po implementaci napsat krátký taskový dokument na předepsané docs cestě: chování API, priority, run přes aktuální task, produkční fallback a skutečně provedené ověření. Neuvádět neprovedené kontroly jako úspěšné.

## 3. Regresní testy

Rozšířit pouze `test_web_assistant.py`, využít `setup`, `with_task`, `machine_settings`, `default_harness_settings`, `fake_harness` a `fake_unlimited`. Pomocné fixture nastavení rozšířit lokálně, pokud je třeba odlišit model/thinking projektu od počítače. Repo helpery z `multi_repo` neměnit. Pro pytest dočasná repa použít zavedené helpery; žádné živé služby ani modely.

- Projekt nastaví `harness: codex`, konkrétní model a thinking, task sám je nemění. Vytvoření se `screen: {repo: repo_id, task: "P01-S01-T01"}` vrátí odpovídající harness/model při testově rozšířeném `GUIDE_HARNESSES`. Ověřit i thinking na `Thread` a v uloženém `thread.json`; veřejné detail API ho dnes nevystavuje. Fake Codex může ověřit skutečný request.
- Se skutečným allowlistem stejný task s Codexem skončí na Claude s jeho modelem/thinking z počítače. Zachovat existující testy fallbacku Codex/pi a odmítnutí bez dostupného Claude.
- Povolený Claude task s modelem/thinking odlišným od počítače ověřit bez rozšíření allowlistu. Poslat dvě zprávy, mezi nimi změnit nastavení počítače nebo projektu a screen. Requesty drží původní model/thinking a stejný session_id. Ověřit diskovou persistenci a načtení existujícím managerem po restartu bez přepočtu.
- Bez screen platí počítač; repo-only použije stejný počítač, i když v backlogu projektu je jiný binding. Zachovat test guide defaults bez harnesses.json a doplnit explicitní task binding bez tohoto souboru.
- `screen.run` s registrovaným repem získá binding přes task v aktuálním backlogu. V dočasné DB připravit řádek s odlišným historickým nastavením, aby test vyloučil jeho převzetí. Ověřit také chybějící DB bez jejího vytvoření.
- Parametrizovat neplatné vstupy: neznámý top-level/screen klíč, neobjektový screen (pravdivý i falsy), neřetězcové pole, příliš dlouhý nebo víceřádkový identifikátor, neznámé repo, task/run bez repa, neznámý task/run, task/run nesoulad. Očekávat HTTP 400 a `error.code == "usage_error"`; žádný vytvořený thread.
- `{}`, `null` a chybějící screen úspěšné. Běh s odpovídajícím explicitním taskem úspěšný. Stávající send screen a validace textu nadále fungují.

Nepsat nové testy algoritmu dědění T69; ty již existují. Testy zde mají prokazovat napojení endpointu, registry, běhu a uloženého bindingu.

## 4. Ověření a předání

Z kořene repa spustit `just lint`, `just typecheck` a `just pytest tests/web/test_web_assistant.py`. Pokud úprava společného parseru způsobí chybu existujících testů, opravit ji v povolených souborech a zopakovat dotčené kontroly. Celou sadu ani frontend/browser testy nespouštět: frontend se nemění a test_web_assistant.py pokrývá přímé callery manageru i route.

Zkontrolovat diff, že produkční allowlist a command guard zůstaly zachované, změny jsou jen v povolených cestách a nevznikla runtime data v repu. Builder doplní dokumentaci skutečnými výsledky kontrol. Necommitovat; commit a další workflow řídí factory.
