# HAIFA-S01-T05: Tooltip u Blokováno, odkaz zpět na středu, „ID: Název“

## Cíl

Tři drobné UI úpravy dashboardu (`aifactory/web/src/`), bez změny API a bez nové závislosti:

1. Badge **Blokováno** (StateChip) ve stromu backlogu a v hlavičce detailu tasku má tooltip dashboardu (`components/ui/Tooltip.vue`) se seznamem z `blocked_by`.
2. Odkaz zpět (`← backlog`, `← všechny běhy`, `← všechny PR`) je jedna sdílená komponenta: ikona `ArrowLeft` (lucide) + text, obojí svisle na středu nadpisu `h1`.
3. Kód a název tasku mají formát `ID: Název` (např. `M01-S01-T02: Loader`) v seznamu běhů, hlavičce běhu, nákladech po tascích, seznamu PR a hlavičce PR. Bez názvu jen kód.

Pak rebuild frontendu do `aifactory/src/aifactory/web/static/`.

## Kontext (ověřeno)

- `Unmet` v `src/lib/backlog.ts`: `{ id: string; reason: string; missing: string[] }`. `TaskNode.blocked_by: Unmet[]`; `TaskDetail.task: TaskNode`.
- Důvody z backendu (`aifactory/src/aifactory/backlog/derived.py::unmet`):
  - `unknown` – závislost neexistuje (`missing=[dep]`)
  - `cancelled` – task zrušený
  - `not_done` – task není hotový
  - `empty` – kontejner (step/projekt) nemá aktivní tasky (`missing=[]`)
  - `incomplete` – kontejner má nehotové tasky (`missing` = seřazené kódy nehotových tasků)
- `Tooltip.vue` má `white-space: pre-line`, takže víceřádkový text přes `\n` funguje. Prázdný `text` = bublina se nezobrazí. Zobrazí se na `mouseenter`/`focusin` na `[data-test="tip-anchor"]`, bublina je teleportovaná do `body` (`[data-test="tooltip"]`). Vzor testu viz `src/components/ui/Tooltip.test.ts`.
- Guard `src/lib/noNativeUi.test.ts`: v `.vue` šablonách nesmí být atribut `title=`/`:title=` (kromě `DetailSection`). **Nové props proto nepojmenovávej `title`** (použij `label`).
- Odkazy zpět dnes: `views/BacklogView.vue:397`, `views/RunsView.vue:182`, `views/ReviewView.vue:234`, každý `<a ... class="back" data-test="back">← …</a>` + lokální CSS `.back { color: var(--dim); }`. `.view-head` je `display:flex; align-items:center; gap:18px`, `h1` 24px/700.
- Ikony: `lucide-vue-next` už je závislost (`ArrowLeft` existuje).
- Místa s kódem a názvem (dnes `<span class="task-id">ID</span><span v-if="title" class="dim"> Název</span>`):
  - `components/runs/RunsList.vue:96-98` (uvnitř `<a class="task-link">`)
  - `components/runs/RunDetail.vue:54-57` (uvnitř `<h2>`)
  - `components/runs/CostTotals.vue:28-31` (uvnitř `<td>`)
  - `components/review/ReviewList.vue:57-59` (uvnitř `<a class="task-link">`)
  - `components/review/ReviewDetail.vue:49-52` (uvnitř `<h2>`, ID je `<a class="task-id">`, název `<span>` bez třídy)
- StateChip použití: `TreeNode.vue` (task řádek), `TaskDetail.vue:114` (`task.board_state`), `TaskDetail.vue:236` (seznam „blokuje“ – `BlocksRef`, nemá `blocked_by`, nech beze změny), `KanbanBoard` (neměň, mimo zadání; pokud tam StateChip je s TaskNode, smíš předat `blocked-by` také, ale není nutné).
- Vite: `outDir` = `../src/aifactory/web/static`, `emptyOutDir: true` → build sám smaže staré hashované assety.

## Změny

### 1. Text tooltipu – `src/lib/backlog.ts`

Přidej a exportuj čisté funkce:

```ts
/** Czech noun for a container dependency: one-segment ids (M01, HAIFA) are projects, longer ones steps. */
export function containerNoun(id: string): 'step' | 'projekt' {
  return id.split('-').length > 1 ? 'step' : 'projekt'
}

/** One line of the Blokováno tooltip: `<kód> – <důvod>`. */
export function unmetLine(u: Unmet): string {
  switch (u.reason) {
    case 'not_done': return `${u.id} – task není hotový`
    case 'cancelled': return `${u.id} – task je zrušený`
    case 'unknown': return `${u.id} – položka neexistuje`
    case 'empty': return `${u.id} – ${containerNoun(u.id)} je prázdný`
    case 'incomplete': return `${u.id} – ${containerNoun(u.id)} má nehotové tasky: ${u.missing.join(', ')}`
    default: return `${u.id} – ${u.reason}`
  }
}

/** Tooltip text of the Blokováno badge; '' when nothing blocks. */
export function blockedTooltip(blockedBy: readonly Unmet[] | undefined): string {
  if (!blockedBy?.length) return ''
  return ['Blokuje:', ...blockedBy.map(unmetLine)].join('\n')
}
```

(Pomlčka je `–` U+2013 s mezerami. Přesné řetězce drž takto – testy je kontrolují.)

### 2. `components/backlog/StateChip.vue`

- Nový volitelný prop `blockedBy?: Unmet[]`.
- `const tip = computed(() => props.state === 'blocked' ? blockedTooltip(props.blockedBy) : '')`.
- Šablona: když `tip` není prázdný, obal chip do `<Tooltip :text="tip">` a chipu dej `tabindex="0"` (klávesnicový focus) a `data-test="blocked-chip"`; jinak renderuj chip jako dosud (beze změny DOM pro ostatní stavy, ať se nerozbijí existující testy).
  ```vue
  <Tooltip v-if="tip" :text="tip">
    <span class="chip" :class="cls" :data-state="state" tabindex="0" data-test="blocked-chip">{{ label }}</span>
  </Tooltip>
  <span v-else class="chip" :class="cls" :data-state="state">{{ label }}</span>
  ```
  kde `label = STATE_LABELS[state] ?? state`. Volitelně `cursor: help` pro `.state-blocked[tabindex]`.

### 3. Předání `blocked_by`

- `TreeNode.vue`: `<StateChip :state="node.board_state" :blocked-by="node.blocked_by" />`.
- `TaskDetail.vue:114`: `<StateChip :state="task.board_state" :blocked-by="task.blocked_by" />`. Řádek 236 (`b.board_state`) nech.

### 4. Sdílený odkaz zpět – nový `components/ui/BackLink.vue`

```vue
<script setup lang="ts">
import { ArrowLeft } from 'lucide-vue-next'
defineProps<{ href: string; label: string }>()
</script>

<template>
  <a :href="href" class="back" data-test="back">
    <ArrowLeft :size="16" aria-hidden="true" data-test="back-icon" />
    <span>{{ label }}</span>
  </a>
</template>

<style scoped>
.back {
  display: inline-flex;
  align-items: center;
  align-self: center;
  gap: 6px;
  line-height: 1;
  color: var(--dim);
}
.back svg { flex: none; }
</style>
```

(Pokud by `data-test` atribut na lucide komponentě nepropadl na `<svg>`, test ať hledá `a[data-test="back"] svg`. Ověř si v testu.)

Ve třech view nahraď `<a ... class="back">← …</a>`:
- `BacklogView.vue`: `<BackLink v-if="target" :href="hrefFor('backlog')" label="backlog" />`
- `RunsView.vue`: `<BackLink v-if="runId" :href="hrefFor('runs')" label="všechny běhy" />`
- `ReviewView.vue`: `<BackLink v-if="taskId" :href="hrefFor('review')" label="všechny PR" />`
- Import `BackLink from '@/components/ui/BackLink.vue'` a v každém view smaž lokální `.back { … }` CSS.
- `h1` v těch view: přidej `line-height: 1.2` (nebo ponech), aby `align-items:center` v `.view-head` zarovnal opravdu na střed – hlavní je, že odkaz je `inline-flex` s `align-items:center` a `line-height:1`.

### 5. Formát `ID: Název`

Na každém z pěti míst použij stejný vzor (dvojtečka hned za kódem, mezera, název; bez názvu nic):

```vue
<span class="task-label" data-test="task-label">
  <span class="task-id">{{ X.task_id }}</span><span v-if="X.task_title" class="dim">: {{ X.task_title }}</span>
</span>
```

Obě vnitřní spany **na jednom řádku bez mezery mezi nimi**, aby `.text()` dalo přesně `M01-S01-T02: Loader` (Vue `condense` jinak může vložit mezeru). Alternativně stačí přidat `data-test="task-label"` na existující obal (`a.task-link`, `td`, `h2`), pokud tento obal neobsahuje nic dalšího – v `RunDetail` je `h2` jen pro ID+název, v `ReviewDetail` také; v `RunsList`/`ReviewList` je to `a.task-link`; v `CostTotals` `td`. Důležité je, aby element s `data-test="task-label"` měl `text()` přesně `ID: Název` resp. jen `ID`.

Konkrétně:
- `RunsList.vue:96-98` – `run.task_id` / `run.task_title`
- `RunDetail.vue:55-56` – `run.task_id` / `run.task_title`
- `CostTotals.vue:29-30` – `t.task_id` / `t.task_title`
- `ReviewList.vue:58-59` – `p.task_id` / `p.task_title`
- `ReviewDetail.vue:50-51` – ID zůstává odkazem: `<a :href="taskHref(detail.task_id)" class="task-id">{{ detail.task_id }}</a><span v-if="detail.task_title">: {{ detail.task_title }}</span>` (jeden řádek), `data-test="task-label"` dej na `h2`.

Zkontroluj CSS (`.task-id` margin apod.), aby za kódem nevznikla mezera před dvojtečkou.

### 6. Fixtures – `src/test/backlogFixtures.ts`

Blokovaný task `t3` (M01-S01-T03) v `backlogData` dostane:
```ts
blocked_by: [{ id: 'M01-S01-T02', reason: 'not_done', missing: ['M01-S01-T02'] }],
```
Pokud je v souboru další blokovaný TaskNode (např. detail fixture s `board_state: 'blocked'`), doplň mu `blocked_by` také. Ověř, že stávající testy (počty, kanban, graf) nepočítají s prázdným `blocked_by`.

## Testy (vitest, žádné volání modelu)

1. **`src/lib/backlog.test.ts`** (nový nebo rozšířit existující, pokud je): `unmetLine`/`blockedTooltip`
   - `not_done` → `M01-S01-T02 – task není hotový`
   - `cancelled` → `M01-S01-T02 – task je zrušený`
   - `unknown` → `X99 – položka neexistuje`
   - `empty` step → `M01-S02 – step je prázdný`; `empty` projekt → `M02 – projekt je prázdný`
   - `incomplete` step → `M01-S01 – step má nehotové tasky: M01-S01-T02, M01-S01-T03`; projekt varianta `M01 – projekt má …`
   - `blockedTooltip([])` → `''`; více položek → `'Blokuje:\n…\n…'`.
2. **`src/components/backlog/StateChip.test.ts`** (nový): `state='blocked'` + `blockedBy` → existuje `[data-test="tip-anchor"]`; po `trigger('mouseenter')` (mount s `attachTo: document.body`) je v `document.body` `[data-test="tooltip"]` s textem obsahujícím `M01-S01-T02 – task není hotový`. `state='ready'` → žádný tip-anchor. `blocked` s prázdným `blockedBy` → žádný tip-anchor.
3. **Strom a detail**: v `BacklogTree.test.ts` (nebo BacklogView.test) – řádek `[data-task="M01-S01-T03"]` má tip-anchor a tooltip s textem důvodu. V `TaskDetail.test.ts` – detail s blokovaným taskem (`taskNode({ board_state: 'blocked', blocked_by: [...] })`) ukáže tooltip.
4. **`src/components/ui/BackLink.test.ts`** (nový): renderuje `a[data-test="back"]` s `href`, obsahuje `svg` (ikona), text je přesně label (žádné `←`). Ve `views/*.test.ts` stačí jeden assert na každou obrazovku, že `[data-test="back"]` obsahuje `svg` a text `backlog` / `všechny běhy` / `všechny PR` (nebo aspoň v jednom view; zadání: „odkaz zpět obsahuje ikonu“).
5. **`ID: Název` na pěti místech** – přesný text `M01-S01-T02: Loader`:
   - `RunsList.test.ts` – řádek běhu `r-run` (runsFixtures ho už má s M01-S01-T02/Loader): `[data-test="task-label"]` `.text()` === `M01-S01-T02: Loader`.
   - `RunDetail.test.ts` – run s `task_id: 'M01-S01-T02', task_title: 'Loader'` (override fixture).
   - `CostTotals.test.ts` – řádek `[data-task="M01-S01-T02"]`.
   - `ReviewList.test.ts` – položka s override `task_id: 'M01-S01-T02', task_title: 'Loader'`.
   - `ReviewDetail.test.ts` – detail s override stejně.
   - Plus jeden test „bez názvu jen kód“ (např. v RunsList nebo CostTotals s `task_title: null`/`''` → text === `M01-S01-T02`).
6. Uprav existující asserty, které by kvůli změně formátu/odkazu zpět padaly (např. `toContain` je ok; přesné `toBe('M01-… Schema')` přepiš).

## Build

`just web-build` (bun install --frozen-lockfile && vue-tsc && vite build) → přepíše `aifactory/src/aifactory/web/static/` (staré hashované `index-*.js/css` zmizí, nové vzniknou). Výsledek nech v pracovním stromu (necommituj – to dělá workflow).

## Ověření

Spusť z kořene worktree:
- `just web-test` (typecheck + vitest) během vývoje
- `just test` (web-test + pytest)
- `just typecheck`
- `just lint`
- `just web-build` na konci; `git status` ukáže změny v `aifactory/src/aifactory/web/static/`.

Hodnoť podle exit statusu.

## Omezení

- Měň jen `aifactory/`, `justfile`, tento spec a `app_docs/HAIFA-S01-T05-tooltip-u-blokovano-odkaz-zpet-na-stredu.md`.
- Žádná nová npm závislost (lucide už je), `bun.lock` beze změny.
- `vendor/` a `prototype/` neměnit. Backend/API neměnit.
- Žádné nativní `title` atributy (guard test).
- Out of scope: názvy blokujících položek v tooltipu, tooltipy u ostatních kódů.
