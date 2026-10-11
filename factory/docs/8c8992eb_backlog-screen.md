# Obrazovka Backlog v dashboardu

Dashboard dostal obrazovku Backlog: strom modul → step → task a kanban, filtr podle stavu a vlastníka, detail tasku, formulář pro založení a editaci tasku, přidání a odebrání vazeb a přiřazení workflow. Každý zápis prochází stejnými funkcemi core jako `factory task add|edit|link` (`aifactory.backlog.add_task`, `edit_task`, `link_task`). Mění se tedy jen soubory pod `backlog_dir` v hlavním checkoutu a nic se necommituje. Zápis, který by backlog rozbil, se odmítne a UI zobrazí chyby z validace.

Mimo rozsah: graf závislostí, spouštění tasků (3.4) a editor workflow (F4).

## Backend: `aifactory/src/aifactory/web/`

**`backlog.py`** (nový soubor) obsahuje logiku obrazovky:
- `backlog_view(repo, status=, owner=)` vrací `levels`, `items` (strom kontejnerů s `progress`, `owner` a `blocks`), `tasks` (plochý seznam pro kanban), `owners`, `workflows` (názvy `*.yaml` z repa a z balíčku, soubory se neparsují), `steps` (kontejnery na předposlední úrovni `levels`), `issues` z `check_backlog` a `counts`. Pokud je filtr aktivní, prázdné kontejnery se ze stromu vynechají. Neznámý `status` skončí chybou `invalid_status`.
- `board_state()` určuje sloupec kanbanu. Platí první shoda v tomto pořadí: `done`, `cancelled`, `running` (běžící run v trace DB), `in review` (otevřené PR), `blocked`, `ready` (jen pokud má task efektivní workflow), jinak `todo`. Task s neplatným `status` padne do `todo` a nese `invalid: true`.
- `task_detail(repo, id)` vrací `task`, `body`, `issues` tasku, `runs`, `prs`, `depends` (s titulkem a stavem, případně `kind: unknown`) a dopočítané `blocks`.
- `add` / `edit` / `link` ověří tělo požadavku (povolené klíče `ADD_KEYS`, `EDIT_KEYS`, `LINK_KEYS`, typy hodnot) a zavolají core. Přiřazení workflow se provádí přes `edit` s `workflow` nebo s `clear_workflow`.
- Když trace DB chybí, nevytváří se. Runtime stavy se pak nepočítají a chyba DB se vrátí jako varování „runs are not shown: …“.

**`app.py`** přidává tyto routy pod `/api`:

| Metoda | Cesta | Funkce |
|---|---|---|
| GET | `/backlog?status=&owner=` | strom, kanban, číselníky |
| GET | `/backlog/tasks/{id}` | detail tasku |
| POST | `/backlog/tasks` | `factory task add` |
| POST | `/backlog/tasks/{id}/edit` | `factory task edit` (včetně workflow) |
| POST | `/backlog/tasks/{id}/link` | `factory task link` (`remove: true` vazbu odebere) |

Mapování chyb: `backlog_invalid` → 422 s `error.issues`; `unknown_task` / `unknown_step` / `missing_backlog_dir` → 404; `file_exists` / `duplicate_id` → 409; `write_failed` → 500; nevalidní JSON nebo neznámé pole → 400 `usage_error`; ostatní kódy → 400. Zápisy běží přes `run_in_threadpool`.

**`static/`** obsahuje nově sestavený frontend: nové hashe assetů v `index.html`, staré soubory `index-CUBvdK7Y.js` a `index-YxFNbchY.css` jsou odstraněné.

## Frontend: `aifactory/web/src/`

- `lib/backlog.ts` obsahuje typy (`BoardState`, `TaskNode`, `ContainerNode`, `TaskDetail`, …), API volání `fetchBacklog`, `fetchTask`, `addTask`, `editTask`, `linkTask` a pomocné funkce `flattenIssues`, `splitIds`, `splitLines`.
- V `lib/api.ts` nese `ApiError` pole `issues: ApiIssue[]` převzaté z `error.issues`.
- `lib/router.ts` přidává konstantu `NEW_TASK` (`#/backlog/new`) a funkci `taskHref(id)` (`#/backlog/<id>`).
- `views/BacklogView.vue` obsluhuje tři režimy podle hashe: seznam (strom nebo kanban), formulář nového tasku a detail. Po úspěšném založení tasku přejde na jeho detail. Po editaci nebo změně vazby detail znovu načte. Chyba zápisu se zobrazí ve formuláři nebo v detailu.
- Komponenty v `components/backlog/`: `BacklogFilters` (stav, vlastník, přepínač strom/kanban), `BacklogTree` + `TreeNode`, `KanbanBoard` (sloupce podle stavů, počty, značka „neplatný status“), `StateChip`, `TaskDetail` (hlavička, zadání, vazby oběma směry, běhy, PR, editace, přidání a odebrání vazeb, výběr workflow), `TaskForm` (režim add i edit) a `IssueList` (výpis issues z validace).

## Testy

- `aifactory/tests/web/backlog_fixture.py` vytváří dočasné git repo se dvěma moduly (`M01` s vlastníkem alice, `M02` s vlastníkem bob). Volitelně přidá trace DB s běžícím runem a otevřeným PR.
- `aifactory/tests/web/test_web_backlog.py` ověřuje strom podle `levels` (i vlastních), stavy kanbanu, filtry, chování bez trace DB, detail tasku, to, že add zapisuje jen do backlogu a necommituje, odmítnutí zápisu, který by backlog rozbil (git status zůstane čistý), edit a přiřazení workflow, přidání a odebrání vazby i detekci cyklu, chybná těla požadavků a to, že API volá funkce core (přes monkeypatch).
- Vitest: `*.test.ts` u komponent, `lib/backlog.test.ts`, `lib/api.test.ts`, `lib/router.test.ts`, `views/BacklogView.test.ts` se sdílenými daty v `test/backlogFixtures.ts`. `App.test.ts` stubuje i volání backlogu, protože Backlog je výchozí route.

## Jak ověřit

```sh
just test && just typecheck && just lint
```

Ručně: spusťte dashboard a otevřete `#/backlog`. Přepněte na kanban a vyfiltrujte stav nebo vlastníka. Přes „Nový task“ založte task, v detailu přidejte vazbu `depends_on`, která vytvoří cyklus: zápis se neprovede, zobrazí se chyba s issues a `git status` zůstane beze změny. Spec práce je v `specs/8c8992eb_backlog-screen.md`.
