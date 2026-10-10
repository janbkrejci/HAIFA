# Backlog: graf závislostí, spuštění tasku a přepínač auto-continue

Session `70e41add` · spec `specs/70e41add_backlog-graph-run-toggle.md`

## Co se změnilo

Obrazovka Backlog v dashboardu umí tři nové věci. Každá volá stejnou funkci core jako odpovídající CLI příkaz:

| Funkce | UI | API | Core / CLI ekvivalent |
|---|---|---|---|
| Graf závislostí modulu/stepu | `#/backlog/graph/<id>`, odkaz „Graf“ u každého kontejneru ve stromu | `GET /api/backlog/containers/{id}/graph` | — (čte backlog + runtime stav) |
| Kontrola před spuštěním | dialog „Spustit task“ v detailu tasku | `GET /api/backlog/tasks/{id}/run-check` | `factory config status` (D4) + `core.unmet` |
| Spuštění tasku | tlačítko **Spustit** / **Spustit přesto (--force)** | `POST /api/backlog/tasks/{id}/run` `{note?, force?}` → HTTP 202 | `run_queue.run_chain` = `factory task run [--note] [--force]` |
| Auto-continue | přepínač Zděděno / Zapnuto / Vypnuto v hlavičce grafu | `POST /api/backlog/containers/{id}/auto-continue` `{mode: on\|off\|inherit}` | `core.set_auto_continue` = `factory backlog auto-continue ID --on\|--off\|--inherit` |

### Backend (`aifactory/src/aifactory/web/`)

- **`launcher.py`** (nový): `RunLauncher` spouští `run_chain` na daemon vlákně. `start()` čeká (v thread poolu, ne v event loopu), dokud se v `task_runs` neobjeví nový řádek. Pak ho vrátí, nebo vrátí `None` po 30 s (`pending: true`). `TaskRunError` vyhozený před vznikem běhu (`unmet_dependencies`, `no_writes`, …) se propaguje do odpovědi. `run_task` mění cwd procesu, proto server pouští **jen jeden dashboardový běh najednou**. Druhý start dostane `already_running` (409). Běhy spuštěné z CLI v jiných procesech se tím neomezují. Stdout enginu jde do terminálu serveru. Když server skončí, běh skončí s ním a jeho řádek zůstane `running`, dokud ho neuklidí `factory task clean`.
- **`backlog.py`**:
  - `run_check`: vrací stav konfigurace (D4: `base`, `commit`, `clean`, `changes`), `in_base` a `unmet`. Obojí se počítá proti backlogu extrahovanému z base commitu. Dál vrací `running` (živý řádek ze store) a `launcher_busy`.
  - `start_run`: přijímá jen klíče `note` a `force`.
  - `container_graph`: uzly jsou tasky podstromu kontejneru s `board_state` a hrany jsou `depends_on` (`from` = závislost, `to` = task). Závislosti mimo kontejner se přidají jako uzly s `external: true`. U kontejnerů je `board_state: null` a `state` obsahuje text typu `"1/3"`.
  - `auto_continue`: zapisuje `index.md` a necommituje.
  - JSON každého kontejneru ve stromu má nově pole `auto_continue`. Info o kontejneru v grafu přidává `effective_auto_continue`, což je první bool nalezený směrem k rodičům, jinak `false`, a `can_toggle`.
- **`app.py`**: 4 nové routy a `app.state.launcher`. Nová mapování chybových kódů na HTTP: `already_running`/`unmet_dependencies`/`task_not_in_base` → 409, `unknown_task`/`unknown_container` → 404, `no_writes`/`*_workflow` → 422, `worktree_failed` → 500.

### Frontend (`aifactory/web/src/`)

- `lib/backlog.ts`: typy (`RunCheck`, `RunStart`, `RunPanel`, `ContainerGraph`, `AutoMode`, …) a volání `fetchRunCheck`, `startRun`, `fetchGraph`, `setAutoContinue`, `autoMode`. `flattenIssues` nově přenáší `code`.
- `lib/graph.ts`: vrstvené rozložení bez dalších závislostí. Vrstva uzlu je nejdelší cesta k němu. Cyklus nezpůsobí zacyklení, protože relaxace proběhne nejvýš N průchodů. Hrany vedoucí k chybějícím uzlům se zahodí. Hrany se kreslí jako S-křivky (`edgePath`).
- `lib/router.ts`: `GRAPH` a `graphHref(id)` → `#/backlog/graph/<id>`.
- `components/backlog/DependencyGraph.vue`: SVG graf. Barva uzlu odpovídá stavu. Uzel tasku je odkaz na `taskHref` (detail tasku), externí uzly jsou vizuálně odlišené, graf má legendu.
- `components/backlog/RunDialog.vue`: varuje na necommitnutou konfiguraci, na task, který není v base, a na nesplněné závislosti. Informuje o běžícím běhu nebo obsazeném launcheru; v takovém případě je start zablokovaný. Obsahuje pole pro poznámku. „Spustit přesto (--force)“ se ukáže při nesplněných závislostech nebo po chybě `unmet_dependencies`. Po startu nabídne odkaz na běh.
- `components/backlog/AutoContinueToggle.vue`: třípolohový přepínač a text „efektivně: zapnuto/vypnuto“.
- `TaskDetail.vue`: tlačítko **Spustit** a vložený `RunDialog`. `TreeNode.vue`: štítek „auto“ a odkaz „Graf“.
- `views/BacklogView.vue`: nová route grafu a stav běhového panelu (`RunPanel`). Po přepnutí auto-continue graf znovu načte, po startu běhu znovu načte detail tasku.
- `static/`: přebuildovaný bundle (`index.html` ukazuje na `index-BiAmb-gV.js` / `index-DoPxViMM.css`).

## Jak ověřit

```sh
just test        # pytest (vč. tests/web) + web-test (vitest)
just typecheck
just lint
```

Klíčové testy:
- `aifactory/tests/web/test_web_task_run.py` používá falešné harnessy (`run_repo.fake_env`) a model nevolá:
  - spuštění z API vytvoří řádek v `task_runs` s poznámkou, který doběhne do stavu `succeeded`;
  - během běhu server odpovídá na `/api/health`, `/api/runs` a `run-check`;
  - druhý dashboardový běh dostane 409 `already_running`;
  - `unmet_dependencies` vrátí 409, s `force: true` běh projde;
  - necommitovaný workflow se objeví v `config.changes`.
- `aifactory/tests/web/test_web_backlog_graph.py` ověřuje:
  - uzly a hrany grafu stepu a modulu, včetně externí závislosti;
  - že auto-continue z API zapíše `index.md` byte po bytu stejně jako `factory backlog auto-continue --on`;
  - dědění `effective_auto_continue`;
  - odmítnutí chybného vstupu.
- Vitest: `graph.test.ts`, `RunDialog.test.ts`, `DependencyGraph.test.ts`, `AutoContinueToggle.test.ts`, `BacklogView.test.ts` a další.

Ruční ověření v dashboardu: Backlog → „Graf“ u stepu → klik na uzel otevře detail → **Spustit**.
