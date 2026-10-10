# HAIFA-REFINEMENT-T01 — Refaktoring web UI: ergonomie, úklid a řízení výroby

Web UI (Vue frontend `aifactory/web/src` a API `aifactory/src/aifactory/web/`) vede uživatele
čtyřmi cestami: první návštěva, tvorba backlogu, řízení výroby a schvalování PR. Mrtvé
a duplicitní obrazovky, komponenty a endpointy jsou pryč. Auto continue bere tasky podle
fronty z kanbanu a vynechá tasky z kanbanu vyloučené. Limity Claude se znovu ukazují.

## Řízení výroby

### Fronta pro auto continue (kanban)

- **Úložiště:** pořadí a vyloučení jsou provozní preference operátora, ne obsah tasku.
  Ukládají se proto do trace DB, tabulka `task_queue (task_id, rank, excluded, updated_at)`,
  a nepotřebují commit backlogu. `TaskRunStore` k tomu má:
  - `queue_prefs() -> QueuePrefs(order, excluded)`,
  - `set_queue_order(ids)` (duplicitní id dává `ValueError`),
  - `set_excluded(id, bool)`.

  Řádky bez pořadí a bez vyloučení se mažou. Starší DB dostane tabulku při otevření.
- **Výběr dalšího tasku** (`run/queue.py`):
  - `candidates(after, order)` nejdřív vezme tasky ve frontě kanbanu (i přes hranici
    kroku), pak zbytek kroku, pak zbytek projektu.
  - `select_next(..., prefs=)` vyloučený task přeskočí s důvodem `excluded`
    („vyloučeno z auto continue v kanbanu“), a to i s `--auto`.
  - Sekvenční řetěz i paralelní `fill` načítají preference při každém výběru.
  - Ruční `factory task run` (i tlačítko Spustit) vyloučení neřeší, takže vyloučený task jde
    spustit dál.
- **API:**
  - `POST /api/repos/{id}/backlog/queue/order` přijímá `{order: [task id]}` a vrací
    `{order}`. Neznámý task dává 404 `unknown_task`, špatný typ nebo duplicita 400
    `invalid_value`.
  - `POST /api/repos/{id}/backlog/tasks/{task_id}/auto-exclude` přijímá `{excluded: bool}`.
  - `GET /api/backlog` vrací u tasků `queue_rank` a `auto_excluded` a řadí tasky podle fronty.
- **Kanban** (`KanbanBoard.vue`):
  - Ve sloupci „Připraveno“ jsou pořadová čísla, tlačítka ↑/↓ a drag & drop.
  - Nový sloupec „Odloženo“ je hned za Připraveno. Přetažení mezi těmito dvěma sloupci
    task vyloučí, nebo vrátí.
  - Na čekajících kartách je přepínač PauseCircle/PlayCircle.
  - Pod hlavičkou je vysvětlující text.
  - `BacklogView` mění pořadí optimisticky a při chybě ho vrátí.
  - V `TaskDetail` je řádek „Auto continue: ve frontě / odloženo“.

### Ad-hoc harness a příprava běhu

- **CLI:** `factory task run ID --harness NAME --model NAME --thinking LEVEL` přepne
  všechny agenty rosteru jen pro tento běh. Nic se nezapisuje
  (`run/task.py apply_agents_override`).
  - Přepnutí harnessu bez `--model` vezme model presetu daného harnessu.
  - Přepisy na krocích workflow mají dál přednost, takže jeden workflow může míchat
    harnessy.
  - S `--auto` platí přepis jen pro první běh řetězu.
  - Neznámý harness, neznámá úroveň thinking nebo model, který harness odmítne, končí
    chybou `invalid_override`.
  - Přepis se připíše do poznámky běhu („[přepis rosteru: …]“).
- **Launcher a API:** launcher předává `--harness/--model/--thinking/--auto`.
  `POST .../backlog/tasks/{id}/run` přijímá `harness`, `model`, `thinking` a `auto`.
  `run-check` vrací efektivní `workflow`, `writes` a `test` z base.
- **RunDialog** ukazuje:
  - souhrn (workflow, writes, testovací příkaz, base, sbalitelné zadání),
  - sekci „Harness pro tento běh“ s aktuálním rosterem,
  - checkbox auto continue,
  - blokaci startu tasku, který není v base,
  - odkaz na commit konfigurace.

  Po startu otevře detail běhu.
- **Editor rosteru** (`RosterEditor.vue` v záložce Factory) nabízí:
  - presety Claude/Codex,
  - tabulku agentů (harness, model, přemýšlení),
  - přepisy na krocích workflow,
  - náhled diffu, uložení a odkaz na commit konfigurace.

  Backend: `POST /api/repos/{id}/factory/roster`. GET rosteru navíc vrací `presets`,
  `thinking_levels` a `workflow_overrides`.
- **Sledování běhů:** v RunDetail a ChainPanel jsou task id odkazy do backlogu a PR mají
  odkaz na Review a stav česky.

## První návštěva

- **Průvodce:** `GettingStarted.vue` s logikou v `lib/gettingStarted.ts` má 7 kroků: stroj,
  knihovna, harnessy, repozitář, factory, harnessy a modely repa, projekt. Je na Přehledu
  i v Setup. Bez repozitářů vede aplikace na Přehled s průvodcem.
- **SetupView** obsahuje i nastavení dashboardu (přesunuté z `#/repos`), knihovnu
  Stáhnout/Odeslat a tlačítko „Další krok“.
- **Přidání repozitáře:** po přidání ukáže kartu „Repozitář X přidán“ s „Otevřít repo“
  a „Přidat další“.
- **Instalace:** InstallForm má testovací příkaz předvyplněný návrhem instalátoru (backend
  `options.test_command`) a české labely.
- **Factory:** po instalaci ukáže box „Co dál“.
- **Limity:** jsou v horní liště na každé stránce.

## Tvorba backlogu

- Prázdný backlog a prázdný výsledek filtru mají různé hlášky. U filtru je „Zrušit filtr“.
- TaskForm předvyplní krok z kontextu (`#/r/<id>/backlog/new/<stepId>`). Bez kroků nabídne
  jeho založení. Parametry jsou dostupné vždy. Tlačítka AI vysvětlí, proč jsou zakázaná.
- Testovací příkaz má v TaskForm i ContainerSettings stejnou sémantiku: jeden příkaz na
  jednom řádku, převedený na argv (`parseTestField`/`formatTestField`).
- ContainerSettings má viditelné české labely a třístavové Zděděno/Zapnuto/Vypnuto.
- Problémy backlogu se zobrazují seznamem `IssueList` místo odkazu na CLI.

## Schvalování PR

- Po sloučení se ukáže box „Sloučeno“ s tlačítky „Další PR ke schválení“ a „Zpět na seznam“
  a větou o auto continue a frontě v kanbanu.
- Vrácení PR se potvrzuje dialogem. Poznámka se po úspěšném vrácení smaže.
- Prázdný seznam ukazuje „Žádné PR ke schválení“ s odkazy na Backlog a Běhy.

## Co bylo odstraněno a proč

| Odstraněno | Proč |
|---|---|
| Stránka `#/repos` (`views/ReposView.vue`, `components/RepoList.vue`, route `repos`, `REPOS_HREF`) a jejich testy | duplikovala Přehled (seznam a odebrání repa). Odebrání je teď u každé karty na Přehledu, nastavení dashboardu je v Setup |
| Položka „Spravovat…“ v `RepoSwitcher` | vedla na smazanou stránku |
| `GET /api/repos/{id}/code`, `POST /api/repos/{id}/restart`, `guard.py _REPO_RESTART` a jejich testy | duplicita globálních `/api/code` a `/api/restart`, frontend volal jen globální |
| Volnotextová akce „Nastavit“ u agentů ve `FactoryItems` a její testy | nahrazena editorem rosteru |
| `AutoContinueToggle` a auto-merge přepínač v hlavičce grafu kontejneru | duplicita `ContainerSettings` na téže stránce (ve stromu zůstává) |
| Oznámení „Nové workflow je uložené…“ v BacklogView | stejnou informaci dává banner necommitnuté konfigurace |
| `ConfigStatusBanner.vue` + `BacklogStatusBanner.vue` a jejich testy | dvě skoro stejné komponenty, sloučeno do `UncommittedBanner.vue` |
| `toConfigStatus` + `toBacklogStatus` | duplicitní parsery, nahrazeny `toCommitStatus` (`lib/commitStatus.ts`) |
| `LibraryPlanView.vue`, `factory/FactoryPlanView.vue`, inline náhled plánu v `OnboardingPanel` | tři kopie téhož, sloučeno do `factory/PlanView.vue` |
| `lib/router.ts parseHash`, `lib/format.ts prettyJson`, `lib/events.ts dotColor`/`EVENT_DOT_COLORS`, `lib/live.ts reopenLive` a jejich testy | používaly je jen testy |
| `lib/router.ts hrefFor` | triviální obal `here` |
| `lib/repos.ts ADD_REPO_COMMAND`, `EmptyScreen` prop `code` | nikde nepoužité |
| `lib/library.ts ItemType`, whitelist v `applyRepo`, `RepoSwitcher LABELS`, trojí merge warnings v `lib/api.ts` | duplicity `FactoryItemType`, `factoryItemChoices`, `REPO_STATUS_TEXT`, helperu obálky |
| Ad-hoc `instanceof Error ? … : String(…)`, `.slice(0, 7/8)`, `JSON.parse(JSON.stringify())` | nahrazeno `errorText`, `shortSha` (`lib/format.ts`) a `structuredClone` |
| Přesměrování prvního startu na `#/setup` v App.vue | průvodce je na Přehledu |

## Opravené drobné chyby

1. Limity Claude se nezobrazovaly. Prošlý token ze `~/.claude/.credentials.json` měl
   přednost před platným tokenem v keychainu a roster repa skrýval druhého providera. Teď
   se bere platný token s nejpozdější expirací a zobrazí se harnessy rosteru i harnessy
   dostupné na stroji. Jen s prošlým tokenem se ukáže „přihlášení Claude Code vypršelo,
   spusť claude“ bez síťového volání.
2. HTTP 429 z usage API se ukazovalo jako holé „HTTP 429“ a dotaz se opakoval po minutě.
   Teď se ukáže text s minutami z `Retry-After` a cache drží `max(ttl, retry_after)`.
3. Limity byly jen na stránce repa. Přibyl globální `GET /api/limits` a lišta je všude.
4. Chyby v SetupView se hromadily.
5. Při zápisu se ukazovalo „Načítám…“ místo „Ukládám…“.
6. Kopírovat kopírovalo text i u nálezu bez příkazu.
7. RunDialog povolil start tasku, který není v base.
8. Spustit šlo u hotového nebo zrušeného tasku.
9. ContainerSettings převáděl zděděné (null) auto continue na „vypnuto“.
10. ContainerSettings bral víc řádků testu jako argv jednoho příkazu, takže nápověda
    „jeden příkaz na řádek“ byla chybná. TaskForm zadával test jinak.
11. Při editaci tasku se v parametrech nezobrazovaly jeho vlastní hodnoty.
12. Plurál „V repu běží N běhů“ a „problém(ů)“.
13. Text prázdného plánu byl stejný pro každou akci.
14. Stav běhů, který nešlo ověřit, zůstal navždy „ověřuje se“.
15. V OnboardingPanel stálo „: “ před chybou bez kódu.
16. Poznámka k vrácení PR se po vrácení nemazala.
17. Vrácení PR šlo bez potvrzení.
18. Externí odkazy (PR, hosting) se otevíraly ve stejném tabu.
19. „Otevřít“ u repa bez factory vedlo do Backlogu místo na Factory.
20. Nekonzistentní popisky „zděděné/Zděděno“ a anglické stavy tasků a PR.
21. Kolize názvů „Dorovnat base“ (Factory) a „Dorovnat s base“ (Review). Factory teď má
    „Stáhnout konfiguraci z base“, tlačítko konfliktu „Vyřešit konflikt s base“.
22. Prázdný backlog a prázdný výsledek filtru hlásily totéž.
23. Oznámení o novém workflow se nemazalo při navigaci (odstraněno, viz výše).
24. Instalace z dashboardu nemohla nastavit `test_command`.
25. Placeholder kódu kontejneru byl natvrdo „M01“.
26. Chyby v LibraryView a FactoryItems se zobrazovaly jako „Error: …“ ze `String(e)`.
27. Zakázaná AI tlačítka a prázdný výběr agentů byly bez vysvětlení. WorkflowAdvice
    neukazoval cenu.
28. Zdravé repo nešlo z dashboardu odebrat jinde než na stránce `#/repos`.

## Testy

- **Backend:**
  - `tests/run/test_queue_prefs.py` (nový),
  - `tests/run/test_auto_continue.py`: pořadí přes hranici kroku, vyloučený task
    i s `--auto`, řetěz v pořadí kanbanu, ruční start vyloučeného tasku,
  - `tests/run/test_parallel_chain.py`: `fill` podle fronty,
  - `tests/run/test_task_run.py` a `tests/run/test_task_run_cli.py`: přepis rosteru,
    `invalid_override`, CLI argumenty,
  - `tests/web/test_web_backlog_queue.py` (nový),
  - `tests/web/test_web_task_run.py`: ruční běh vyloučeného tasku, validace, run-check,
  - `tests/web/test_web_launcher.py`: flagy,
  - `tests/web/test_web_limits.py`, `tests/web/test_web_factory_roster.py` (nový),
    `tests/web/test_web_factory.py`, `tests/web/test_web_repos.py`.
- **Frontend (vitest):** KanbanBoard, BacklogView, RunDialog, TaskDetail, TaskForm,
  ContainerSettings, GettingStarted, gettingStarted, RosterEditor, UncommittedBanner,
  commitStatus, ReviewView, ReviewActions, ReviewList, LimitsBar, format a další.
- **E2E:** browser testy upravené na odstraněné stránky a texty. Start běhu teď otevírá
  detail běhu. Tripwire F3 propouští dotaz `codex app-server` na limity, stejně jako
  `diagnostic_tripwire`.
- **Statika:** přegenerovaná `just web-build`.

## Kde to je

- **Fronta a výběr:** `run/store.py` (tabulka `task_queue`), `run/queue.py`
  (`candidates`, `select_next`), `run/task.py` (`apply_agents_override`, předání do řetězu),
  `run/members.py`.
- **CLI:** `cli.py` (`task run --harness/--model/--thinking`), kód chyby
  `invalid_override` v `skill/codes.py` a `skill/skill.md`.
- **API:** `web/backlog.py` (fronta, vyloučení, běh, run-check), `web/factory.py` (roster
  POST, `test_command` v instalaci), `web/limits.py`, `web/launcher.py`, `web/guard.py`,
  `web/app.py` (routy), `library/install_commit.py` (`test_command` při instalaci).
- **Frontend:** `KanbanBoard.vue`, `RunDialog.vue`, `RosterEditor.vue`, `GettingStarted.vue`,
  `UncommittedBanner.vue`, `factory/PlanView.vue`, `setup/DashboardSettings.vue`,
  `lib/backlog.ts`, `lib/roster.ts`, `lib/gettingStarted.ts`, `lib/commitStatus.ts`.

## Jak ověřit

```bash
just check-scoped                                   # testy podle rizika změny
factory task run ID --harness codex --thinking high # jednorázový přepis rosteru
just dash                                           # kanban: Připraveno/Odloženo, ↑/↓, limity v liště
```

V kanbanu seřaď ready tasky, jeden přetáhni do „Odloženo“ a spusť řetěz s auto continue.
Řetěz vezme tasky v pořadí fronty a odložený přeskočí. Ručně ho spustit jde dál.
