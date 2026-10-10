# HAIFA-S03-T20 — Adaptivní testování

## Výsledek a rozsah

Implementovat dvě propojené věci: obecný krok workflow, který převezme strukturovaný testovací plán od deterministického selektoru a vykoná jeho příkazy, a konkrétní úsporný selektor pro HAIFA používaný současným `just check-scoped`. Přidat explicitní možnost odložit část či všechny testy na existující souhrnný task. Zachovat stávající pevné testovací příkazy a prioritu task → index.md → konfigurace → `just test` u workflow bez selektoru.

Volba pro tuto implementaci je deterministický selektor, nikoli další povinný agent: zadání agenta nevyžaduje a pravidla jsou levná, opakovatelná a testovatelná. Není potřeba implementovat nový agentní harness, automatický scheduler, novou obrazovku ani obecnou analýzu importů. Dokumentace vysvětlí možnost budoucího agentního producenta stejného plánu, ale funkční dodávkou je selektor spuštěný kódem.

Měnit pouze `aifactory/`, `justfile`, tento spec a `app_docs/HAIFA-S03-T20-adaptivni-testovani.md`. `.factory/`, backlog, CLAUDE.md, vendor a prototype jsou mimo rozsah. Nepřepisovat aktivní konfiguraci ani workflow v `.factory/`; opt-in YAML příklady uvést v dokumentaci. Existující konfigurace HAIFA `[just, check-scoped]` získá úsporu změnou stejnojmenného receptu.

## Zjištěný stav

- `aifactory/tests/tiers.py` vybírá none/fast/full. Prakticky všechny změny run/review/workflow/engine/providers/config/backlog/harness a cli spouštějí full. Fast stále pouští téměř všechny rychlé backendové testy a následně úplný mypy a Ruff.
- `justfile:check-scoped` měří diff proti merge-base HEAD/main, přidává untracked soubory, podmíněně pouští frontend. `HAIFA_TEST_TIER=full` povyšuje pouze fast, takže dokumentační změna při resolve může zůstat none.
- `just full-check` již ověřuje izolovaný checkout main, ukládá poslední zelené SHA a při selhání zakládá opravný task s `test: just check`. Upozornění po 15 commitech je nyní pouze orientační.
- `workflow/model.py` a `parse.py` nemají volby pro testovací plán. `interpreter.py:EngineCodeRunner.test` volá `engine/quality.py:run_tests`; ten vykonává jeden příkaz přes `_run`, sloty a timeout. `test` a `retest` sdílejí výsledek pod klíčem test, což zachovat.
- `run/task.py` řeší efektivní příkaz a timeout, zná pinned `fork_sha` a při resolve nastavuje full. `engine/quality.py` již zajišťuje logy, exit kódy, timeout i ukončování procesů. `review/prbody.py` a proměnná `test_result` nesou výsledky do PR/review/repair.

## 1. Kontrakt testovacího plánu

Přidat `aifactory/src/aifactory/testing/` s `__init__.py`, `model.py`, `context.py` a `executor.py`. Pydantic modely mají strict validaci, extra=forbid a verzi kontraktu 1.

Plan JSON:

```json
{
  "version": 1,
  "coverage": "scoped",
  "reason": "Změna workflow parseru a jeho testů",
  "checks": [
    {"name": "workflow", "argv": ["uv", "run", "--project", "aifactory", "pytest", "aifactory/tests/workflow", "-n", "2", "--maxfail=1"], "timeout": 300}
  ]
}
```

`coverage`: full/scoped/none/deferred. `reason` musí být neprázdný. `checks` obsahuje jedinečná neprázdná jména, neprázdné argv seznamy neprázdných řetězců a volitelný kladný celočíselný timeout. Full/scoped musí mít alespoň jeden check, none/deferred nesmějí mít žádný. Limit 32 checků. Pracovní adresář příkazů je vždy kořen aktuálního worktree, ne hlavní checkout; žádný shellový string, shell=True ani interpretace stdout jako příkazu.

Selektor obdrží na stdin JSON kontextu: version, absolutní repo_root, pinned baseline SHA, aktuální HEAD, changed_paths, force_full, efektivní fallback_argv, test_timeout a případný defer_to. Cesty relativní ke kořeni jsou seřazené a bez duplicit. Zachytit committed, staged, unstaged, untracked, deletion a oba názvy rename (např. diff --no-renames); git výstup parsovat s NUL oddělovači. Baseline neodvozovat od posledního testu ani posledního commitu plánovače. Při chybě git/selektoru nesmí vzniknout prázdný plán.

Selektor spuštěný subprocess s argv má stdout vyhrazený pro jediný JSON dokument a stderr pro diagnostiku. Limit výstupu 1 MiB, timeout nejvýše 30 sekund a současně nejvýše limit kroku. Log selektoru a přijatý normalizovaný plán ukládat k artefaktům právě běžící testovací fáze, mimo soubory produktu. V této fázi není cache; po každém fix/revise se plán vypočítá znovu z aktuálního diffu.

## 2. Zapojení do workflow a vykonávání

Rozšířit `CodeStep`, `parse.py`, `outline()` a kontrolní testy o volby pouze pro test:

```yaml
- test:
    selector: [uv, run, --project, aifactory, python, aifactory/tests/select_checks.py]
    full_argv: [just, check]
    allow_skip: true
```

`selector` a `full_argv` jsou neprázdná argv; allow_skip je strict boolean, default false. `full_argv` lze uvést pouze se selector. Bez selector je původní chování beze změny. Není třeba přidávat nové globální konfigurační pole, aby nevzniklo několik soupeřících způsobů nastavení.

Interpreter předá právě aktivní nastavení testovacího kroku do executor; preferovat samostatnou metodu pro plánované testy, nepřepisovat trvale run.test_argv. Stávající CodeRunner fake a staré testy dál obsluhují obyčejný test. Potřebné atributy engine runneru doplnit s komentářem `# aifactory ...:` podle existujícího stylu.

`run_workflow` doplnit o nepovinný test_baseline a kontext potřebný pro defer_to. Task runner předá fork_sha; pokračování existujícího PR musí zahrnout celý diff PR proti jeho připnutému základu. Samostatný workflow použije SHA zachycené před prvním agentem. Stejný pinned základ exportovat jako HAIFA_TEST_BASE pro legacy check-scoped; prostředí po běhu obnovit stejným způsobem jako HAIFA_TEST_TIER. Existující baseline pro changes zachovat. Při rebase/resolve mít force_full; full příkaz používá full_argv, jinak dosavadní efektivní příkaz s prostředím full.

Po výběru získat jeden stávající test slot pro celou sadu checků. Spouštět sekvenčně přes existující quality subprocess primitivum, zastavit na prvním selhání. Timeout testovacího kroku je společný rozpočet všech vykonávaných checků; limit konkrétního checku je minimum jeho timeoutu a zbývajícího rozpočtu. Čekání na slot se do tohoto rozpočtu nepočítá, stejně jako dnes. Selektor má samostatný výše uvedený krátký limit. Timeout, chybějící binárka a nenulový exit jsou selhání skutečných testů a vstupují do stávající repair smyčky, nepřeklasifikovat je na green.

Nenulový exit selektoru, timeout, nevalidní JSON/model, nepovolené none/deferred nebo chyba získání kontextu vyvolají zalogovaný fallback na full_argv, pokud je definované, jinak efektivní stávající test příkaz. Jakmile platný plán začne vykonávat testy, selhání nevyvolává další širokou sadu. Force_full má přednost před selektorem i všemi možnostmi přeskočení; vykonat full_argv nebo legacy příkaz, nikoli none/deferred. Rozsah legacy fallbacku bez full_argv označit jako legacy, netvrdit, že neznámý uživatelský příkaz testuje vše.

None je povolené pouze s allow_skip=true a ověřeným dokumentačním/bezkódovým diffem. Pro obecné projekty může kontrola používat konzervativní dokumentační whitelist; nerozpoznaný soubor nesmí být automaticky dokument. Prázdný skutečný diff může mít none. Přeskočení nevytváří falešný subprocess check; zaznamenat nula provedených checků a důvod. Výsledek passed=true znamená splnění explicitní politiky workflow a musí nést coverage/executed, nikoli tvrzení o provedené sadě.

## 3. Konkrétní výběr pro HAIFA a check-scoped

Přidat `aifactory/tests/select_checks.py` jako tenký CLI vstup a sdílená pravidla do `aifactory/tests/tiers.py` nebo sousedního modulu. Oddělit obecný executor produktu od specifických map cest HAIFA. Selektor čte kontext na stdin; pro samostatný check-scoped executor vytvoří stejný kontext s baseline z HAIFA_TEST_BASE, jinak merge-base HEAD/main. Nenalezený main nebo neplatný baseline znamená plný fallback, ne odhad z HEAD a none.

Změnit just check-scoped na tenké volání tohoto stejného executor/selektoru (např. `uv run --project aifactory python -m aifactory.testing.executor --selector-script aifactory/tests/select_checks.py --fallback just check --allow-docs-skip`). Samostatný CLI runner nesmí otevírat nový workflow ani čekat na druhý slot, pokud už běží uvnitř test kroku. Použít společnou implementaci procesu/logů bez duplikace jejich timeout/kill chování. Udržet existující dočasný pytest basetemp a cleanup; nevykonávat vnořený check-scoped jako fallback.

Pravidla:

1. Force_full vždy `just check`, včetně docs-only a prázdného diffu. Testovací infrastruktura, závislosti/locky, justfile, centrální CLI, engine veřejné datové typy/loader/runner, neznámé cesty či chybějící mapování rovněž full.
2. Dokumenty/backlog/spec/app_docs a skutečně prázdný diff: none, s explicitním důvodem.
3. U běžné změny známého subsystému vybrat jeho adresář testů a deklarované integrační sousedy. Mapu postavit podle existujících testů, nikoli jen dosazením názvu zdrojové složky. Minimální počáteční mapa: workflow → workflow + run; run → run + review; review → review + run; config → config + check + onboard; backlog → backlog + run; providers → providers + run; harness → harness + workflow; library → library + onboard; web backend → web + e2e; frontend → web-test + e2e. Engine změny zatím konzervativně full, neodstraňovat pojistku bez konkrétní mapy.
4. Přímá změna test souboru přidá tento soubor do výběru, včetně slow testu; změna samotného slow testu nevyžaduje automaticky úplnou sadu. Změna pomocného test modulu/conftest/tiers/selektoru je full. Ověřit existenci vybraných test cest; odstraněný test mapovat na zbývající adresář či full.
5. Při scoped backendu použít sjednocený deduplikovaný seznam test cest, bez globálního `-m not slow`, aby zahrnuté relevantní integrační testy skutečně běžely. Pytest scoped má explicitně omezené workery na nejvýše 2, browser/e2e samostatně -n0, full ponechá dosavadní worker konfiguraci. Společné smoke testy přidat k backendovému výběru.
6. Frontend-only nepouští celý backendový pytest, mypy ani Ruff; pouští web-test a browser acceptance. Backend-only nepouští web-test. Smíšená změna sjednotí požadavky. Backend Python změny nadále spustí just typecheck/lint pro soundness; neřešit v této fázi riskantní file-scoped mypy.

`SLOW_FILES` a `BROWSER_FILES` v tiers.py zachovat kvůli conftest markerům. Stávající tier() API lze zachovat jako kompatibilní wrapper, ale aktualizovat testy podle výsledné politiky a nepoužívat dvě různé mapy. Check-scoped musí vytisknout vybraný rozsah, důvod a příkazy; vrátí skutečný exit status. Zachovat upozornění na stáří posledního full-check. Scoped ani vynechaný běh nezapisuje full-check-green.

## 4. Souhrnné ověření většího modulu

Podporovat další explicitní volbu test kroku `defer_to: <task-id>` pouze se selector a full_argv. Selektor s ní může vrátit scoped (minimální testy nyní, širší ověření později) nebo deferred (žádné testy nyní). Deferred nesmí být možné pouhým reason ani allow_skip.

Task runner při preflight načte existující cílový task a ověří, že není aktuální task, patří do stejného projektu, není done, má platný spustitelný workflow obsahující test a jeho efektivní test příkaz je explicitně stejný jako full_argv. Cílový workflow nesmí samo mít defer_to; nesmí vzniknout řetězení odkladů. Cíl se resolve podle aktuálního backlog/config snapshotu stejně jako ostatní tasky. Neplatná reference zastaví běh před builderem s vysvětlujícím kódem; samostatné run_workflow bez resolveru reference také odmítne. Nepřidávat nový backlog frontmatter, migraci ani změny aktuálního backlogu.

I scoped plán s defer_to musí reportovat odložené širší ověření. Výslovná politika připouští vydání vývojového PR s passed=true a coverage=deferred; existující accept test.passed funguje. PR a reviewer musí vidět, že testy neběžely, a ID souhrnného tasku. Je to vědomá volba workflow, nikoli důkaz green plné sady. Full v resolve odklad vždy přebije.

Dokumentovat provozní postup: operátor předem vytvoří větší souhrnný test-and-fix task přes factory příkazy, zadá mu široký test příkaz, vymezí povolené zdrojové cesty pro opravy a zvolí existující test/fix/review workflow; vývojové tasky používají příklad workflow s defer_to. Souhrnný task se spustí nad aktuálním base po skupině změn nebo před dokončením modulu. Dokončení vývojového tasku neoznačuje souhrnný task za done ani nesplňuje odloženou povinnost. Automatické časování, závislostní scheduler a automatická blokace merge celé skupiny nejsou součástí této verze; tato mez musí být v dokumentaci výslovná.

Pro periodické celorepozitářové ověření dál používat just full-check (např. po 15 sloučených commitech nebo před vydáním). Zachovat izolovaný checkout a vytvoření opravného tasku při selhání. Opravit ošetření selhání přípravy worktree, aby se neposuzoval omylem jiný checkout a nezapisoval green stamp. Není třeba automaticky spouštět full-check v každém běhu. Dokumentovat rozdíl mezi souhrnným module taskem a full-check celého main.

## 5. Důkazy a informace pro review

V `engine/data_types.py` rozšířit QualityResult/VerifyOutput o zpětně kompatibilní nepovinné údaje test_plan: coverage (včetně legacy), reason, executed count, defer_to a fallback_reason. Přenést je přes quality.as_envelope a interpreter.report/render_input do test_result i výsledků. Staré výsledky bez metadat se zobrazují stejně jako dnes. Test plan artefakt přidat k logům; skutečné checky ponechat jako QualityCheckResult s příkazem, dobou, exit kódem a logem.

Upravit `review/prbody.py` tak, aby none/deferred označil jako „neprovedeno“/„odloženo na <id>“, scoped jako cílené ověření a full jako plné; výsledek politiky nesmí textově tvrdit „testy prošly“, když nic neběželo. Aktualizovat i agregaci trasovaných výsledků, pokud z ní PR čerpá minulé běhy. Bez nové dashboard obrazovky; existující report/artefakty postačí. Doplnit `aifactory/src/aifactory/skill/skill.md` o veřejné volby workflow a jejich význam, případné nové uživatelské chybové kódy do skill/codes.py.

## 6. Verifikace

Přidat skutečné regresní testy, bez živých modelů, s malými lokálními subprocessy a dočasnými git repy:

- model/parser: strict typy, neznámé klíče, duplicitní názvy, prázdné argv/checks, neplatné kombinace voleb, nevalidní JSON; starý YAML stále funguje;
- executor/workflow: dva příkazy skutečně vykonané v worktree, zastavení na prvním nonzero, stdout s textem error při exit 0 není selhání, selector timeout/nonzero/malformed → fallback, společný timeout, slot jednou pro celý plán a nulakrát pro skip;
- force_full přebije scoped, none i deferred, včetně dokumentační změny při resolve; skutečné selhání testu vstoupí do fix smyčky;
- změna po fix/revise mění nový plán, retest nevyužije starý; baseline zachytí dřívější commit buildera i plánovače, staged/unstaged/untracked/deleted/renamed cesty včetně mezer;
- politika HAIFA: workflow změna nevybere unrelated frontend/providers suite; frontend-only vybere web/browser bez backend typecheck/lint; docs none; neznámá cesta, infrastruktura, lock a chybné mapování full; changed slow test je explicitně zahrnut;
- deferred preflight: platný cíl, self/done/jiný projekt/neexistující cíl/nested deferral/chybný široký příkaz odmítnuty, bez resolveru odmítnuto; report a PR nikdy neskrývají nula vykonaných testů;
- full-check: selhání přípravy nepřepíše green stamp; full pouze po skutečném úspěchu všech checků.

Soubory: rozšířit `tests/test_tiers.py`, přidat `tests/workflow/test_workflow_adaptive_test.py`, `tests/run/test_task_test_deferral.py` a odpovídající focused testy executor/context a PR body. Využít stávající workflow_fakes a run_repo, nevytvářet druhý framework.

Builder nejprve spustí cílené testy nových pravidel a executor/workflow/run/review integrace, potom Ruff a strict mypy; frontend se při této backendové změně nemusí opakovaně spouštět. Pro finální ověření této změny testovací infrastruktury jednou spustit `just check` — nespoléhat na selektor, který právě měníme. Dokumentační planner fáze testy nespouští.

Úsporu doložit deterministickým porovnáním vybraných příkazů/test cest pro docs, workflow-only, frontend-only a neznámou změnu proti původním tiers; nedávat neověřená tvrzení o konkrétním zrychlení. Je-li měření wall-clock snadné, zaznamenat jeden focused a jeden full běh, bez opakovaných benchmarků.

## 7. Akceptace a dokumentace

Dodávka je hotová, když existující check-scoped vybírá relevantní subsystémy, nové workflow převezme JSON plán a vykoná jej přes stávající proces/slot/log mechanismus, selhání výběru nikdy neznamená tiché green, resolve vždy vynutí širší testování a explicitní odklad na validní souhrnný task je viditelný v review/PR.

Do `app_docs/HAIFA-S03-T20-adaptivni-testovani.md` napsat kontrakt stdin/stdout s úplným příkladem, YAML pro adaptive/docs skip/module defer, tabulku pravidel HAIFA, prioritu fixed/fallback/full, postup souhrnného tasku a full-check, omezení ručního časování a skutečné výsledky validace. Uvést, že žádná `.factory/` migrace nebyla provedena a instalované vlastní workflow musí operátor výslovně upravit, pokud chce obecný selector/defer_to. Základní úspora HAIFA funguje přes dosavadní check-scoped i bez této migrace.
