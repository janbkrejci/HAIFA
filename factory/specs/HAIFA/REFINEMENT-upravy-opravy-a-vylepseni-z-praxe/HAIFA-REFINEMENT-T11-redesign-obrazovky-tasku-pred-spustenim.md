# HAIFA-REFINEMENT-T11 – Redesign of the task detail screen (before a run)

## Goal

Make the task detail page (`#/r/<repo>/backlog/<task-id>`, component
`aifactory/web/src/components/backlog/TaskDetail.vue`) clearer, easier to scan and
nicer to use. Today it is one long column: a header with a loose `dl` of metadata,
then Zadání, Vazby (3 cramped columns), a separate Workflow box with three
unrelated controls, Běhy and PR. Nothing tells the user at a glance whether the
task can run and what is stopping it.

This is a **frontend-only** change. Do not touch the API, the Python code or
`BacklogView.vue`'s contract with the component (props and emits stay exactly the same).

## Constraints (do not break)

- Keep every existing `data-test` / `data-*` hook and its text, because the vitest
  tests (`TaskDetail.test.ts`, `BacklogView*.test.ts`, `FactoryView.test.ts`) and the
  Playwright e2e tests (`aifactory/tests/e2e/test_f3_browser.py`,
  `test_workflow_advice_browser.py`) use them:
  `task-id`, `task-title`, `data-state` (StateChip), `run`, `edit`, `cancel-task`,
  `path`, `workflow` (must contain `(zděděno)` when inherited), `writes`, `auto-merge`,
  `auto-queue`, `auto-queue-state` (`ve frontě` / `odloženo`), `auto-queue-toggle`
  (texts `Vrátit do auto continue` / `Vyloučit z auto continue`), `task-issues`, `body`,
  `depends`, `data-dep`, `dep-state`, `unlink-<id>`, `link-input`, `link-add`,
  `blocks`, `data-block`, `related`, `data-related`, `unrelate-<id>`, `related-input`,
  `related-add`, `workflow-select`, `assign`, `runs`, `data-run`, `no-runs`
  (`Žádné běhy`), `prs`, `data-pr`, `pr-state`, `pr-link`, `pr-review`, `no-prs`
  (`Žádné PR`), `blocked-chip`, `run-dialog` (inside RunDialog).
- The button text `Upravit a navrhnout workflow` must stay exact (tests find it by text).
- No `title` attributes (a test asserts `[title]` does not exist); use `Tooltip`.
- Run button: keep the `Tooltip` wrapper, the disabled logic
  (`busy || run?.busy || run?.open || runBlocked`), the spinner, `aria-busy`, and the
  `no-workflow` class with `pointer-events: none` so the tooltip anchor still gets hover.
- All UI text in Czech, use `useLevels()` / `levelNoun` / `levelLabel` for level nouns
  (never hard-code "task"/"step"), code comments in English.
- Use existing CSS tokens from `src/style.css` (`--panel`, `--panel-2`, `--surface`,
  `--border`, `--border-soft`, `--dim`, `--faint`, `--blue`, `--green`, `--amber`,
  `--red`, `--mono`). No new dependencies. Icons from `lucide-vue-next`.

## New layout

```
┌ header ───────────────────────────────────────────────────────────────┐
│ M01-S01-T02  Loader                [StateChip]   [▶ Spustit] [Upravit] [Zrušit] │
│ path/to/task.md (mono, faint, small)                                   │
├ readiness banner (data-test="run-readiness") ─────────────────────────┤
│ ✓ Připraveno ke spuštění · workflow plan-build   |  ⚠ reasons list      │
└───────────────────────────────────────────────────────────────────────┘
┌ main column (1fr) ─────────────────┐ ┌ side column (320px) ────────────┐
│ [TaskForm when editing]            │ │ Card "Spuštění"                  │
│ Card "Zadání"  (MarkdownView)      │ │   Workflow: name (zděděno)       │
│ Card "Běhy" (n)  table / empty     │ │   [SelectMenu][Přiřadit]         │
│ Card "PR" (n)    list / empty      │ │   [Upravit a navrhnout workflow] │
│                                    │ │   Auto-merge: zapnuto (zděděno)  │
│                                    │ │   Writes: chips                  │
│                                    │ │   Auto continue: state + toggle  │
│                                    │ │ Card "Vazby"                     │
│                                    │ │   Závisí na (n) list + add       │
│                                    │ │   Blokuje (n) list               │
│                                    │ │   Související (n) list + add     │
└────────────────────────────────────┘ └──────────────────────────────────┘
```

Below 1100px width (`@media (max-width: 1100px)`) the grid collapses to one column,
side column after the header and before the main column is NOT needed — just stack
main then side (simple `grid-template-columns: 1fr`).

### 1. Header (`<header class="head">`)

- Title row: `span.id[data-test=task-id]` (mono, dim), `h2[data-test=task-title]`,
  `StateChip`, then `.head-buttons` pushed right (`margin-left: auto`), with
  `flex-wrap: wrap` on the row so long titles wrap instead of squashing the buttons.
- Buttons in order: **Spustit** (primary: filled background
  `color-mix(in srgb, var(--blue) 18%, var(--panel))`, blue border and text, slightly larger
  padding), **Upravit** (secondary, with `Pencil` icon), **Zrušit** (ghost/danger: red
  text, red-tinted border on hover, `Ban` icon). Keep existing v-if conditions.
- Under the title row: the file path as `div.path.mono[data-test=path]` (13px, `--faint`),
  wrapped in `CodeTip` is not needed; plain text is fine. Removed from the old `dl`.
- `task-issues` (issues from the loader) move right under the path as an amber warning
  box (`AlertTriangle` icon, amber border, amber-tinted background, list of
  `code: message`).

### 2. Readiness banner (new, `data-test="run-readiness"`)

A single line/box between header and the grid that answers "can I run it?". Add a
computed `readiness` in `TaskDetail.vue`:

```ts
type Readiness = { tone: 'ok' | 'warn' | 'muted'; title: string; reasons: string[] }
```

Rules (first match decides tone/title; reasons collects everything applicable):
- `finished` (done/cancelled) → tone `muted`, title = existing `runTooltip` text
  (`… je hotový, znovu se nespouští.` / `… je zrušený, nespouští se.`), no reasons.
- `running` / `in review` board state → tone `muted`, title `Běží` / `Čeká na review`
  (use `STATE_LABELS` from `@/lib/backlog` for the label to stay consistent:
  title = `` `${levelLabel(level.task.value)} je ve stavu ${STATE_LABELS[state]}.` ``),
  plus link to the latest run when `detail.runs[0]` exists (`runHref`).
- otherwise collect reasons:
  - `noWorkflow` → `NO_WORKFLOW_HINT`
  - every `task.blocked_by` entry → `unmetLine(u, names.value)` (import `unmetLine`
    from `@/lib/backlog`, `useNames` from `@/lib/names`, same way `StateChip.vue` does)
  - `task.invalid` or `detail.issues.length` → `Soubor má chyby – oprav je před spuštěním.`
  - if reasons empty → tone `ok`, title `Připraveno ke spuštění`, plus
    `· workflow <b>{{ task.workflow }}</b>`.
  - if reasons non-empty → tone `warn`, title `Před spuštěním je potřeba:` and a `ul`
    of reasons (`data-test="readiness-reason"` on each `li`).
  Note: blocked deps don't disable the Spustit button today (the run dialog handles
  `force`), so the banner is informational only — do NOT change `runBlocked`.
- Icons: `CheckCircle2` (ok, green), `AlertTriangle` (warn, amber), `Info` (muted, faint).
- Styling: rounded 10px box, left border 3px in tone colour, tinted background
  (`color-mix(in srgb, var(--green|--amber) 8%, var(--panel))`).

### 3. Two-column body (`div.body-grid`)

`display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 18px; align-items: start;`

Introduce a tiny local card style (no new component needed): `.card` with
`background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
padding: 14px 16px;` and `.card > h3` header row (`display:flex; align-items:center;
gap:8px`, 15px, `--dim`, uppercase-ish letter-spacing 0.04em, icon 16px `--faint`, an
optional `span.count` in `--faint`). Icons: Zadání `FileText`, Běhy `History`, PR
`GitPullRequest`, Spuštění `Settings2`, Vazby `Link2`.

**Main column** (`div.main`):
1. When `editing`: `TaskForm` (unchanged props/events) rendered at the top of the main
   column **instead of** the Zadání card (the form already edits the body, so showing
   both is redundant). `IssueList` for `error` stays where it is now (`v-else-if`).
2. Card Zadání with `MarkdownView[data-test=body]`. If `detail.body.trim()` is empty
   show `p.faint` `Zadání je prázdné.` (keep `data-test="body"` on MarkdownView when shown).
3. Card Běhy with count `(detail.runs.length)`; same table (`data-test=runs`) and
   `no-runs` empty text. Table: compact, `Začátek` column right-aligned, branch cell
   `text-overflow: ellipsis` with `max-width`.
4. Card PR with count; same list and hooks. Each PR row as a flex row: state badge
   (`pr-state`, keep purple uppercase), link, `Review` link styled as small button-link,
   branch mono faint pushed right.

**Side column** (`aside.side`), `position: sticky; top: <topbar height + 12px>` is
optional — only add if it doesn't clip on short screens (skip if unsure).
1. Card **Spuštění** – a definition list styled as rows (`dl.props`,
   `grid-template-columns: max-content 1fr; gap: 8px 12px`):
   - `Workflow` → `dd[data-test=workflow]` name (mono) or `bez workflow` (amber) and
     `(zděděno)` faint when inherited. Below it, the former Workflow section controls:
     `SelectMenu[data-test=workflow-select]` + `button[data-test=assign]` Přiřadit in one
     row, then the full-width `Upravit a navrhnout workflow` button (same disabled
     condition as now). Delete the old standalone Workflow section.
   - `Auto-merge` → `dd[data-test=auto-merge]` unchanged text.
   - `Writes` → `dd[data-test=writes]`: each path as a small mono chip; `—` when empty.
     Keep `dd.text()` containing the paths (tests may check `', '`-joined text — grep
     `writes` in tests first; if any test asserts the exact joined string keep the
     `join(', ')` text instead of chips).
   - `Auto continue` (only `queueable`) → `dd[data-test=auto-queue]` with
     `auto-queue-state` and the `auto-queue-toggle` button on its own line below
     (full width small button), same texts and icons.
2. Card **Vazby** – the three link groups stacked vertically (not 3 columns), each with
   `h4` + count, the list, and the add row (`input` flex 1, `Přidat` button). Keep all
   hooks. Dependency rows: id link mono, title truncated with ellipsis, `dep-state` as
   faint small text, remove button at the right (`margin-left: auto`). The `Blokuje`
   rows keep `StateChip`. Pressing **Enter** in `link-input` / `related-input` calls
   `addLink(...)` (`@keydown.enter.prevent`) – small ergonomic gain.

### 4. Misc

- `ConfirmDialog` and `RunDialog` stay as they are (position in template irrelevant,
  they are modals) — keep them outside the grid.
- Remove now-unused CSS (`.links`, `.section`, old `.meta`, `.add` if renamed). Keep the
  `button` local style but don't fight the global `:where(button)` style.
- Root `article.task-detail` keeps `:data-task`.

## Files to change

1. `aifactory/web/src/components/backlog/TaskDetail.vue` – template, script additions
   (`readiness`, `names`, Enter handlers, imports) and styles as described.
2. `aifactory/web/src/components/backlog/TaskDetail.test.ts` – add tests:
   - readiness `ok` for the default fixture task with a workflow and no blockers
     (text contains `Připraveno ke spuštění`); check the fixture in
     `src/test/backlogFixtures.ts` (`taskDetail()`), override fields via its overrides
     param as other tests do.
   - readiness `warn` when `workflow: null` (contains the NO_WORKFLOW hint) and when
     `blocked_by` is non-empty (one `readiness-reason` per unmet entry).
   - readiness `muted` for `board_state: 'done'`.
   - editing hides the Zadání card (`[data-test="body"]` absent while form open).
   - Enter in `link-input` emits `link` with `{ depends_on: [id] }`.
   Existing tests must pass unchanged (adjust only if a test relied on removed DOM
   structure, never by deleting an assertion on a hook).
3. `aifactory/src/aifactory/web/static/` – regenerate with
   `just web-build` (committed build output).
4. `factory/docs/HAIFA/REFINEMENT-upravy-opravy-a-vylepseni-z-praxe/HAIFA-REFINEMENT-T11-redesign-obrazovky-tasku-pred-spustenim.md`
   – short Czech description of the new layout (header, banner připravenosti, dva
   sloupce, co se kam přesunulo).

No change to `docs/decisions.md` (no design decision replaced) and no Python change.

## Verification

1. `just web-test` – vitest incl. new TaskDetail tests; `just typecheck` frontend part
   via `just check`.
2. `just check` – full gate must pass.
3. `just e2e` – especially `tests/e2e/test_f3_browser.py` and
   `test_workflow_advice_browser.py` (they click `run`, `edit`, `link-input`, …).
4. `just web-build` and make sure `aifactory/src/aifactory/web/static` is updated.
5. Optional visual check: `just dash`, open a task detail at ~1400px and ~900px width;
   header buttons must not overlap a long title, side column collapses under 1100px.
