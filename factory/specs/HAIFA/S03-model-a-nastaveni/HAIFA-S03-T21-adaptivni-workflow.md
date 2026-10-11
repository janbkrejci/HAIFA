# HAIFA-S03-T21: adaptivní workflow

## Cíl a rozsah

V definici nového i existujícího tasku přidat tlačítko „Navrhnout workflow“. Spustí agenta, který z aktuálního zadání, kontextu projektu/stepu, vazeb a dostupných workflow vybere vhodné existující workflow, nebo navrhne nové validní YAML workflow. Výsledek obsahuje odůvodnění a vyplní výběr ve formuláři. Uživatel uloží task běžným tlačítkem Založit/Uložit; samotná analýza nemění task ani sdílenou konfiguraci. Je to explicitní pomoc při definici tasku, nikoli automatické rozhodování při každém běhu.

Implementace smí měnit pouze `aifactory/`, případně `justfile`, tuto specifikaci a `app_docs/HAIFA-S03-T21-adaptivni-workflow.md`. Neměnit skutečnou `.factory/`, backlog, CLAUDE.md, vendor ani prototype v tomto implementačním worktree. Produktový kód samozřejmě bude při uživatelském uložení umět vytvořit workflow v `.factory/workflows/` obsluhovaného repozitáře. Fixtures musí používat dočasná repa.

## Zjištěná architektura

- `web/src/components/backlog/TaskForm.vue` obsluhuje založení a editaci; `TaskDetail.vue` má také přiřazení workflow mimo editaci. `views/BacklogView.vue` vlastní načítání a ukládání tasků.
- `src/aifactory/web/backlog.py` používá core `backlog.add_task/edit_task`; zápisy jsou validované a journalované. API je v `web/app.py`, frontendové kontrakty v `web/src/lib/backlog.ts`.
- `run/task.py:named_workflow` řeší přednost repo workflow před packaged defaults; `prepare_cfg` materializuje konfiguraci a prompty. `config.load_run_config` čte konfiguraci z base commitu.
- `workflow.parse.parse_workflow` a `workflow.check.check_agents` již validují role, code kroky, podmínky, omezené smyčky a agentní override.
- Harness určuje roster; nepředpokládat Claude, konkrétní model ani pi. `engine.agents.execute` / `Run.phase().call(AgentCall(...))` poskytují typovaný výstup, retries a trace.
- `engine.session.ensure` registruje signal handlers, takže ho nelze použít z threadpoolu. Existující launchery tasků vytvářejí implementační běhy/PR; doporučení nesmí být `task run` a nesmí vyžadovat již přiřazené workflow.
- Nové workflow uložené na disku není dostupné běhům, dokud není v base. Existuje Factory UI s operací `config_commit` a review plánem/digestem, také `factory config commit`. Backlog commit bere pouze backlog; nesmí být rozšířen o libovolné změny konfigurace.

## Chování UI

1. U výběru workflow v TaskForm zobrazit tlačítko „Navrhnout workflow“ (`type=button`). Funguje i pokud task workflow už má; nedokončený nový task musí mít step a neprázdný titulek. Pro nový task není nutné nejprve uložit task nebo získat id.
2. Odeslat aktuální hodnoty formuláře, nikoli původní props: title, vybraný workflow, writes/inherit_writes, step, body a depends_on pro nový task. U editace načíst aktuální uložené body/vazby z detailu, protože formulář je nyní needituje. Zahrnout původní task_id pro editaci; vztahy se doplní ze serveru.
3. Po spuštění spinner a text „Agent vybírá workflow…“; zabránit dvojímu spuštění a uložení během analýzy. Rušení formuláře je možné a odpojí polling. Nezamykat ostatní tasky ani celý dashboard.
4. Úspěch zobrazí název, zda jde o existující nebo nové workflow, krátké odůvodnění a přehled kroků. U nového umožnit rozbalit YAML jako escapovaný text. Výsledek vyplní hodnotu workflow, uživatel ji může ručně změnit. Novou volbu přidat pouze lokálně do selectu až do uložení.
5. Pokud uživatel při běhu změní vstupy, odpověď označit za zastaralou a neaplikovat ji. Nová analýza zneplatní starý výsledek. Při přepnutí tasku/repa, zrušení a unmountu ignorovat pozdní odpovědi a zrušit timer/request; respektovat stávající repo scope API.
6. Selhání má čitelnou chybu, retry a zachová ruční výběr i ostatní draft. Není-li dostupný konfigurací určený agent, sdělit důvod, žádná náhrada heuristikou vydávanou za agenta.
7. V TaskDetail přidat u přiřazení workflow vstup do stejné editace s možností návrhu. Sdílet komponentu/panel, neimplementovat druhý algoritmus. U hotových/zrušených, běžících tasků a tasků v review doporučení deaktivovat; server také kontroluje uložený task. Běžný ruční editor zachová dosavadní chování.
8. Po uložení nového workflow obnovit seznam i detail a zobrazit „Nové workflow je uložené. Zveřejni konfiguraci před spuštěním tasku.“ s repo-aware odkazem do existující Factory operace `config_commit`. Existující preflight dál blokuje neznámé workflow v base. Žádný automatický commit, push, PR nebo spuštění tasku po analýze/uložení.

## Backend: služba a agent

Přidat `src/aifactory/workflow/adaptive.py` s typy vstupu, `WorkflowRecommendationOutput(EnvelopeBase)` a čistými funkcemi sestavení kontextu/validace. Výstup: `decision: existing|new`, `workflow_name`, neprázdné `reason`, `workflow_yaml: str|None`. Existing vyžaduje známé jméno a null YAML; new vyžaduje YAML a shodu top-level name s workflow_name. Status musí být success. Žádné agentem zadané souborové cesty.

Použít nastavení agenta role `plan` v načteném registru rolí a rosteru; zachovat jeho harness/model/thinking a ověřit dostupnost přes dosavadní harness API. Vytvořit kopii konfigurace pro tuto operaci s vlastním system/user promptem v session runtime, `writes=[]`, popisem role výběru workflow a výše uvedeným output_type. Nepoužívat stávající planner prompt: ten přikazuje psát spec a má jiné výstupní schema. Nepřidávat povinného nového agenta do uživatelského rosteru ani neměnit seed planner.

Kontext obsahuje aktuální draft, plné zadání, rodičovské popisy a effective nastavení (writes, test, source/target), závislosti/related s id, titulkem, stavem a zadáním, a dostupná workflow s obsahem a validačním stavem. Katalog z base konfigurace plus packaged defaults sestavit se stejnou předností jako named_workflow; nepředkládat necommitnuté workflow jako připravené k běhu. Nevalidní kandidáty popsat jako nedostupné. Roster předat jako jména/purpose/harness/model/thinking, registry rolí jako podporované kroky; neposílat .env, local.yaml ani credentials. Vstupy omezit velikostí; příliš velký payload vrací usage_error. Rozsáhlý kontext deterministicky omezit s poznámkou o zkrácení; samotné zadání nesmí být potichu useknuto.

Prompt ukládá preferovat vhodné existující workflow; nové tvořit pouze při vysvětlené mezeře. Zohlednit typ a rozsah tasku, potřebu plánu, implementace, testů, review a dokumentace. Nabídnout skutečnou syntax a příklady existujících workflow. Výstup je návrh, jeho kroky se nespouštějí. Reuse ani nové workflow nemusí vždy mít builder (např. research). Nevymýšlet role, modely ani neomezené repeat.

Agent může číst kontext repa v izolované dočasné git kopii připnuté na base commit; explicitně mu předat draft a dosud necommitnuté související popisy. Nepoužívat process-wide chdir, env mutations ani sys.argv. Použít existující engine Run + Tracer, ale životní cyklus vytvořit přímo bez `session.ensure` a jeho signal handlers. `prepare_cfg` lze reuse s absolutními cestami; override promptů pouze v kopii cfg. Nastavit `run.repo_root` na izolovanou kopii a read-only guard (`TaskWriteGuard` s prázdným TaskScope a writes=[]); chránit i main podle dosavadních pravidel a zachovat cizí journalované změny. Žádné změny konfigurace/globalů engine. Session/trace/logy patří do `.factory/data` nebo existujícího runtime umístění, nikdy mezi sdílenou konfiguraci. Ukončit trace a uklidit kopii i při výjimce.

Validovat odpověď přes Pydantic a YAML safe_load + parse_workflow + check_agents; pro existing znovu validovat skutečný katalogový obsah. Vyžadovat bezpečný slug `[a-z][a-z0-9-]{0,63}`, odmítnout separator, tečky, traversal a kolizi packaged/repo názvů pro new. Nevytvořit soubor při invalidním výstupu. Uchovat outline pro UI. Validace nikdy nespouští command/test kroky navrženého workflow.

## Asynchronní API a uložení

Přidat `src/aifactory/web/workflow_advice.py`: app-owned job manager s omezeným threadpoolem (max. 2 práce), synchronizovanými stavy a injectable runnerem pro testy. Klíč je canonical repo root + job id, nikoli task id samotné. POST vrací rychle, žádné dlouhé HTTP čekání na model. Duplicitní totožný aktivní draft stejného repa sdílí job; přeplněná fronta vrací existing busy kód. Stavy `queued|running|succeeded|failed`, uchovat kontextový fingerprint a validační výsledek. Hotové joby expirovat po 30 minutách; server restart znamená ztrátu rozpracovaného návrhu, UI nabídne nový pokus. Toto omezení dokumentovat. Ukončení manageru nesmí blokovat event loop; dořešit konec procesů harnessu a cleanup při shutdown, bez signal handlers v threadu.

V `web/app.py` registrovat v `_repo_routes()`:
- `POST /backlog/workflow-advice`: body `{task_id?: string, draft: {...}}`; kontrola klíčů/typů, existence rodiče/tasku, povoleného stavu; odpověď 202 `{job_id,state}` v standard envelope.
- `GET /backlog/workflow-advice/{job_id}`: repo-scoped stav, po dokončení recommendation/outline/warnings, nebo chyba; cizí či expirovaný job -> 404. Neserializovat stdout ani citlivé tracebacky.

Nové chyby přidat do `skill/codes.py` a mapování HTTP; reuse existing usage_error/invalid_workflow/unknown_task tam, kde mají stejný význam. Obě app constructors musí inicializovat a uklízet službu. Zachovat origin/content-type/stale-code middleware.

Rozšířit pouze web `ADD_KEYS`/`EDIT_KEYS` a TS AddTaskInput/EditTaskInput o volitelný `workflow_advice_id`. Standard core CLI edit schema neměnit. `web/backlog.py:add/edit` při ukládání reference získá serverem validovaný návrh stejného repa a draft fingerprintu. Pokud je ručně zvolen jiné workflow, frontend referenci neposílá a nic nevytváří. Chybějící/stale job odmítnout bez částečného zápisu. U editace se generated workflow může uložit i když workflow_name odpovídá lokální hodnotě, musí vzniknout normální změna tasku.

Pro new vytvořit výhradně `.factory/workflows/<workflow_name>.yaml`, nikdy nepřepsat existující soubor. Znovu ověřit aktuální role/roster, jméno, task a kontext pod repo write lockem. Použít bezpečný exclusive-create/temp-file postup s kontrolou symlinků/containment. Validovat task edit/add před perzistencí; při selhání uložení tasku odstranit pouze soubor vytvořený touto operací. Reuse core zápisů a `mainwrites` journalu; po úspěchu zaznamenat i konkrétní nový workflow jako autorizovaný produktový zápis, aby paralelní guard uživatelskou změnu nevrátil. Rozšíření nesmí umožnit agentu zapsat workflow vlastním factory příkazem. Opakované save stejného úspěšného návrhu je idempotentní jen při shodném obsahu; nesmí přepsat cizí úpravu. Vrátit vytvořené jméno/cestu a příznak `requires_config_commit`. Nezveřejňovat jiné neuložené config změny.

## Soubory implementace

- Nové backend moduly `workflow/adaptive.py`, `web/workflow_advice.py`; podle potřeby malý helper bezpečného uložení workflow v adaptive modulu.
- `web/app.py`, `web/backlog.py`, `skill/codes.py`; `run/mainwrites.py` jen pokud existing journal nelze přímo reuse. Engine neupravovat, pokud jde operaci sestavit z existujících Run/AgentCall API.
- `web/src/lib/backlog.ts`, případně nový `lib/workflowAdvice.ts`; `components/backlog/TaskForm.vue`, `TaskDetail.vue`, `views/BacklogView.vue`; nový sdílený `WorkflowAdvice.vue` pro progress/výsledek.
- Testy níže a `app_docs/HAIFA-S03-T21-adaptivni-workflow.md`.
- `web/static/` regenerovat pouze `just web-build`, žádné ruční editace bundle. `justfile` není očekávána změna.

## Testy a ověření

Backend `tests/workflow/test_workflow_advice.py`: kontext rodičů/vazeb/draftu, precedence repo nad packaged, existing selection, validní new, unknown name/role/agent/field, invalid YAML/condition/unbounded repeat, kolize/path traversal/symlinky, harness exception a chybějící planner. Fake harness ověřuje použité model/harness, nové prompt schema a read-only guard; nepouštět live model. Jeden integrační test skutečného engine lifecycle s fake harness ověří, že operace funguje ve worker threadu a nevolá signal.signal/chdir ani implementační task run.

`tests/web/test_web_workflow_advice.py`: rychlé 202 přes kontrolovaný blokovaný runner, polling success/failure, souběh dvou rep se stejnými task id, duplicate handling, invalid body, expiry/restart, jiné repo nevidí job, edit/add s draftem; uložení new + task, rollback po failu, stale fingerprint, name collision během analýzy, idempotence, běžné add/edit beze změny. Ověřit žádný backlog/config zápis před save, žádný commit/PR, config warnings po save. Journal test ověří zachování tohoto uživatelského zápisu při souběžném guardu. Po explicitním config/backlog commit v tmp fixture musí standardní run resolver najít nové workflow z base; samotný agent návrhu nepouští jeho kroky.

Frontend colocated `WorkflowAdvice.test.ts`, rozšířit `TaskForm.test.ts`, `TaskDetail.test.ts`, `BacklogView.test.ts`: payload aktuálního draftu, existující a nový výsledek, spinner/disabled/retry, změna vstupů během requestu, pozdní odpověď po task/repo switch, cleanup timeru, manual override, add/edit save reference, YAML render jako text, config_commit odkaz a zachování dosavadního inheritance.

Přidat jeden browser scénář `tests/e2e/test_workflow_advice_browser.py` s fake agentem: task bez workflow -> tlačítko -> existující workflow -> uložit; druhá varianta nové -> uložit -> config publication warning. Screenshot výsledného UI přiložit do implementačního reportu/artifactu. K obsluze browseru použít dostupnou browser skill dle prostředí; testy musí být nezávislé na živých službách.

Spustit `just test tests/workflow/test_workflow_advice.py tests/web/test_web_workflow_advice.py`, `just typecheck`, `just lint`, `just e2e test_workflow_advice_browser.py`, `just web-build`, nakonec požadované `just check-scoped`. Řídit se exit kódy a neopakovat celé sady bez nové změny/failu. Dokumentační plán sám testy nepotřebuje.

## Akceptace a dokumentace

Hotovo, když tlačítko v definici nového i existujícího tasku skutečně spouští nakonfigurovaného agenta, poskytuje zdůvodněnou validní volbu nebo nové workflow podle kontextu, zachovává draft při chybě a lze výsledek uložit. Nové workflow se bezpečně vytvoří, UI vysvětlí potřebný config commit a po běžném zveřejnění ho task umí používat. Analýza neimplementuje task, nevytváří jeho PR a nezveřejňuje konfiguraci.

App dokumentace česky popíše tlačítko, používaný agent/model z role plan, čtený kontext, save/discard, inherited vs own workflow, vznik nového YAML, Factory config_commit a backlog commit před během, selhání/retry a ztrátu neuloženého návrhu po restartu. Nezavádět adaptivní přepínání workflow uvnitř rozběhnutého tasku, nový editor workflow, nové CLI příkazy ani hromadnou migraci backlogu.
