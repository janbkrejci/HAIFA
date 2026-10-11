# Plán: odstranění vlastníka modulu (`owner` v `index.md`)

Rozhodnutí engineera z 2026-10-01: institut vlastníka modulu/stepu se nepoužívá. Odstraň pole
`owner` z dědění, z API backlogu a Review, z UI a ze skillu. Existující soubory s `owner`
zůstávají platné a pole se tiše ignoruje.

Všechny cesty níže jsou relativní k `aifactory/` (kořen repa je `/Users/jbk/Documents/HAIFA`).

## Pevná omezení (NEMĚNIT)

- `owner` ve významu vlastníka fáze: `phases.owner`, `roles.yaml`, `missing_owner` v
  `engine/role_registry.py`, `review/prbody.py`, `web/runs.py`, `web/src/lib/runs.ts`,
  `web/src/test/runsFixtures.ts` (tam je `owner: 'tests'` / `'planner'` – fáze, nechat),
  testy enginu/harnessu/workflow (`tests/engine`, `tests/harness`, `tests/workflow`).
- `owner/name` GitHub repa ve validaci.
- `vendor/`, `prototype/`, `docs/product-brief.md` beze změny.
- Žádný test nesmí volat model.

## 1. Backend – model a loader

### `src/aifactory/backlog/model.py`
- Z `INHERITED_KEYS` odeber `"owner"`. Výsledek:
  `("source", "target", "test", "workflow", "writes", "auto_continue")`.

Důsledky (ověřeno čtením kódu, není potřeba nic dalšího měnit):
- `loader.py` (ř. ~143): klíč kontejneru, který není v `INHERITED_KEYS`, jde do
  `container.extra` → žádný issue, `check_backlog` ho neodmítne. `extra` se nikam neserializuje
  (`render.container_to_json` posílá jen `defaults`).
- `loader.load_task` (ř. ~196): `own` bere jen klíče z `INHERITED_KEYS` → `owner` v tasku se
  ignoruje, žádný issue.
- `skill/render.py` vyplňuje `{{inherited_keys}}` z `INHERITED_KEYS` → `owner` zmizí ze skillu
  automaticky.

## 2. Backend – web API

### `src/aifactory/web/backlog.py`
- Smaž funkci `_owner(task)`.
- `_task_json`: odstraň `data["owner"] = _owner(task)`.
- `_container_json`: odstraň `owner = container.defaults.get("owner")` a klíč `"owner"` ve
  vráceném dictu.
- `backlog_view`: odstraň parametr `owner` (signatura `backlog_view(repo, *, status=None)`),
  `keep()` filtruje jen podle statusu, `filtered = status is not None`, smaž výpočet `owners`,
  z `data` odstraň klíč `"owners"` a `filters` bude `{"status": status}`. Uprav docstring
  („The tree, the flat task list for the kanban, workflows and steps.“).

### `src/aifactory/web/review.py`
- Docstring modulu: věta o vlastníkovi → backlog hlavního checkoutu se čte kvůli názvu tasku
  a modulu („the title and module of each task from the backlog of the main checkout“).
- `_context`: varování `"owners are not shown: {exc}"` přejmenuj na
  `"task titles and modules are not shown: {exc}"` (zkontroluj, že žádný test nehledá starý
  text – grep `owners are not shown` v `tests/` nic nenašel).
- Smaž `_owner`, `_owners`, `_git_value`, `_me`. Pokud po smazání nebude `os` použito, odeber
  `import os` (ruff to nahlásí). `subprocess` se dál používá v `_git` – nechat.
- `_pr_summary`: odstraň klíč `"owner"`. (Detail PR staví na `_pr_summary` → zmizí i z detailu;
  ověř grepem v `review.py`, že nikde jinde `owner` není.)
- `review_list(repo)`: odstraň parametr `owner`, filtrování podle vlastníka, klíče `owners`,
  `me`, `filters` z výstupu. Docstring: „Open task PRs with mergeability and costs.“

### `src/aifactory/web/app.py`
- Docstring modulu (ř. ~14 a ~29–31): `GET /api/backlog?status=` (tree, kanban tasks,
  workflows, steps); `GET /api/review` (open task PRs with mergeability and costs) – zruš
  zmínku o `owners`, `me`, git `user.email`/`user.name`/`$USER`.
- `backlog_list`: nevolej s `owner=`.
- `review_list`: nečti `owner` z query; volej `review.review_list(repo)`; docstring „Open task
  PRs.“. Parametr `?owner=` se tak tiše ignoruje.

## 3. Skill – `src/aifactory/skill/skill.md`
- V příkladu `index.md` modulu (ř. ~141) smaž řádek `owner: alice`.
- Ř. ~251: „Put shared defaults (`workflow`, `writes`, `test`) into the module or step index.“
- Po úpravě: `grep -n -i owner src/aifactory/skill/skill.md` nesmí nic najít. Ověř i výstup
  `uv run factory --skill | grep -i owner` (exit 1 = nic nenalezeno = OK).

## 4. Frontend – `web/src/`

### `lib/backlog.ts`
- `TaskNode`: smaž `owner`. `ContainerNode`: smaž `owner`.
- `BacklogFilters`: jen `status?: BoardState`.
- `BacklogData`: `filters: { status: BoardState | null }`, smaž `owners`.
- `fetchBacklog`: smaž řádek s `query.set('owner', …)`.

### `lib/review.ts`
- `ReviewBase`: smaž `owner`.
- `ReviewList`: smaž `owners`, `me`, `filters`.
- `fetchReviews()` bez parametru: `return getApi<ReviewList>('/review')`.

### `components/backlog/BacklogFilters.vue`
- Smaž prop `owners`, computed `owner`, `setOwner` a celý `<label>Vlastník…</label>`.

### `views/BacklogView.vue`
- Smaž `const owners = computed(...)` a `:owners="owners"` u `<BacklogFilters>`.
  Zkontroluj typ `Filters` (ř. ~62) – pokud je to alias/rozšíření s `owner`, odeber.

### `components/backlog/TreeNode.vue`
- Smaž `<span v-if="node.owner" class="owner dim">…` a případné CSS `.owner` (pokud existuje).

### `components/backlog/KanbanBoard.vue`
- Smaž `<span v-if="task.owner" class="dim">@{{ task.owner }}</span>` (ř. ~34); pokud tím
  zůstane prázdný obalový element, odeber i ten / jeho styl.

### `components/backlog/TaskDetail.vue`
- Smaž `const owner = computed(...)` a `<dt>Vlastník</dt><dd data-test="owner">…`.

### `components/review/ReviewList.vue`
- Props jen `{ list: ReviewList }`, žádné `emit`. Smaž `owners`, `me`, `mineOnly`, `onSelect`,
  `toggleMine`, celý blok `<div class="filters">…</div>` (select „Vlastník“, tlačítko „Jen moje
  moduly“, hláška `me-hint`), sloupec `<th>Vlastník</th>` i `<td data-col="owner">`.
- Sekce: `{ key: 'awaiting', title: 'Čeká na review', … }`.
- Úklid CSS: `.filters`, `.filters label`, `select`, `.mine*` – odeber nepoužité. `computed`
  import zůstává (prs/awaiting/other/sections).

### `components/review/ReviewDetail.vue`
- Smaž `<span>vlastník <strong data-test="owner">…</strong></span>`.

### `views/ReviewView.vue`
- Smaž `OWNER_KEY`, `ALL`, `readOwner`, `saveOwner`, `initialOwner`, `owner`, `ownerChosen`,
  `onOwner`. localStorage se v tomto view nesmí číst ani zapisovat (`factory.review.owner`).
- `emptyList()`: `{ prs: [], provider: '', approve_review_sent: false, approve_note: '' }`.
- `normalise`: bez `owners` a `me`.
- `loadList`: `list.value = normalise(await fetchReviews())` – bez druhého dotazu s `me`.
- `refreshList`: bez `wanted`; `const data = normalise(await fetchReviews()); if (!taskId.value) list.value = data`.
- Šablona: `<ReviewList v-else :list="list" />`. Uprav komentář „no `me` default“.

### Fixtures a unit testy frontendu
- `test/backlogFixtures.ts`: odeber `owner` z tasků a kontejnerů, `owners`, `filters.owner`;
  `effective: { workflow: 'plan-build' }`.
- `test/reviewFixtures.ts`: odeber `owner` z PR/detailu, `owners`, `me`, `filters`.
- `App.test.ts` ř. 19: odeber `owners: []`.
- `components/backlog/BacklogFilters.test.ts`: přepiš – props `{ filters: {}, mode: 'tree' }`;
  test, že změna `state-filter` emituje `{ status: 'blocked' }`; přidej assert, že
  `[data-test="owner-filter"]` neexistuje.
- `components/backlog/TaskDetail.test.ts` ř. 18: místo `toBe('alice')` assert, že
  `[data-test="owner"]` neexistuje a text neobsahuje „Vlastník“.
- `components/review/ReviewDetail.test.ts` ř. 10: totéž (`[data-test="owner"]` neexistuje).
- `components/review/ReviewList.test.ts`: mount s `{ list: reviewList() }`; sekce „Čeká na
  review“; hlavičky `['Task', 'Modul', 'Mergeabilita', 'Běh', 'Náklady', 'Tokeny', 'PR']`; smaž
  testy na emit vlastníka, „Jen moje moduly“ a `me`; přidej assert, že neexistují
  `owner-filter`, `mine-only`, `me-hint` ani `[data-col="owner"]`. Případný test s `prs: []`
  (ř. 60) jen bez `owner` propu.
- `lib/backlog.test.ts` ř. 39–41: `fetchBacklog({ status: 'in review' })` →
  `/api/backlog?status=in+review`; smaž volání s `owner`.
- `lib/review.test.ts` ř. 38–42: nahraď testem, že `fetchReviews()` volá `/api/review`.
- `views/BacklogView.test.ts` ř. 58–63: odstraň kroky s `owner-filter`; ponech/uprav status
  filtr (`/api/backlog?status=in+review`); assert, že `owner-filter` neexistuje.
- `views/ReviewView.test.ts`: ř. ~48–64 (default na `me`, uložený owner) a ~221–236 nahraď:
  první načtení volá jen `['/api/review']`; s `localStorage.setItem('factory.review.owner','bob')`
  se stále volá `/api/review` bez query a po interakcích `localStorage.getItem('factory.review.owner')`
  zůstane `'bob'` (nezapisuje se) – a/nebo spy na `Storage.prototype.getItem/setItem`, že není
  voláno s tímto klíčem. Live refresh testy upravit na `/api/review`.
- Po úpravách `grep -rn -i "owner\|Vlastník\|Jen moje\|mé review" web/src` smí najít jen
  `lib/runs.ts`, `test/runsFixtures.ts`, runs komponenty (vlastník fáze) a nové negativní
  asserty v testech.

### Build
- `cd web && bun install --frozen-lockfile && bun run build` (nebo `just web-build` z kořene).
  Výstup jde do `src/aifactory/web/static/` – commitni nové hashované assety a smaž staré
  (`git add -A src/aifactory/web/static`). Ověř, že `grep -c "Jen moje moduly" src/aifactory/web/static/assets/*.js`
  nic nenajde.

## 5. Backend testy – `tests/`

### `tests/backlog/test_backlog_load.py`
- `test_inheritance`: smaž `assert eff["owner"] == "alice"` a `effective(view)["owner"] == "bob"`;
  přidej `assert "owner" not in eff` a `assert "owner" not in effective(view)`.
- `test_two_levels`: místo `effective(task)["owner"] == "carol"` assert `"owner" not in effective(task)`
  (index s `owner: carol` dál a `check_backlog(backlog) == []` zůstává – to je platnost).
- **Nový test** `test_owner_field_is_ignored(tmp_path)`: `index.md` modulu i stepu s
  `owner: alice`, task s `owner: bob` → `check_backlog(load_backlog(tmp_path)) == []`,
  `"owner" not in effective(task)`, `"owner" not in container.defaults`. Použij existující
  helpery `write`, `index_md`, `task_md` z téhož souboru.
- **CLI test** (do téhož souboru nebo k existujícím CLI testům backlogu – podívej se, jak se
  volá `factory backlog check`, např. přes `tests/cli_json.py`): repo s `owner` v `index.md`
  i v tasku → `factory backlog check` skončí exit 0 / `ok: true`, žádné issues.

### `tests/backlog/test_backlog_render.py` ř. 89
- `assert "owner" not in m01["defaults"]` (fixture `tests/backlog/fixtures/sample/.../index.md`
  s `owner:` ponech – slouží jako doklad zpětné kompatibility).

### `tests/web/backlog_fixture.py`
- `owner:` řádky v `index.md` ponech (kompatibilita), jen uprav docstring (ř. 3–4), že `owner`
  je legacy pole, které se ignoruje.

### `tests/web/test_web_backlog.py`
- ř. 70, 91, 145: nahraď `"owner" not in module/task`.
- ř. 84, 112: `"owners" not in data`.
- ř. 111: `data["filters"] == {"status": "ready"}`.
- ř. 114–120: test `?owner=` → `?owner=bob` vrací stejné tasky jako bez parametru
  (parametr se ignoruje) a `filters == {"status": None}`; `?owner=bob&status=todo` = jen status.

### `tests/web/test_web_review.py`
- Fixture (ř. 63) s `owner: alice` ponech.
- `test_list_shows_open_pr_with_owner_mergeability_cost` → přejmenuj
  `test_list_shows_open_pr_with_mergeability_cost`; `"owner" not in item`; ř. 173
  `for key in ("owners", "me", "filters"): assert key not in data`.
- `test_owner_filter` → `test_owner_query_is_ignored`: `/api/review?owner=bob` vrátí 1 PR
  (stejně jako bez parametru) a `filters`/`owners` v datech nejsou.
- ř. 192 (detail): `"owner" not in data`.

### `tests/e2e/test_f3_browser.py` ř. 185
- Smaž řádek `page.locator('[data-test="owner-filter"]').select_option("")` (filtr už neexistuje;
  seznam je vždy kompletní).

## 6. Ověření

Z kořene repa (`/Users/jbk/Documents/HAIFA`), posuzuj podle exit statusu:

1. `just test` (zahrnuje `web-test`: vue-tsc + vitest, pak pytest)
2. `just typecheck`
3. `just lint` (ruff check + ruff format --check; spusť `uv run ruff format` v `aifactory/`
   pokud je potřeba)
4. `just web-build` a commit `src/aifactory/web/static/`
5. `just e2e` (Playwright; build ve `static/` musí být aktuální)
6. Kontrolní grepy:
   - `grep -rn '"owner"' aifactory/src/aifactory/backlog aifactory/src/aifactory/web/backlog.py aifactory/src/aifactory/web/review.py aifactory/src/aifactory/web/app.py` → nic.
   - `grep -rn "user.email\|user.name" aifactory/src/aifactory/web` → nic.
   - `grep -rn "factory.review.owner" aifactory/web/src` → jen v testech (negativní assert).
   - `git diff --stat -- vendor prototype docs/product-brief.md` → prázdné.
   - `git diff -- aifactory/src/aifactory/engine aifactory/src/aifactory/review/prbody.py aifactory/src/aifactory/web/runs.py aifactory/web/src/lib/runs.ts` → prázdné.
