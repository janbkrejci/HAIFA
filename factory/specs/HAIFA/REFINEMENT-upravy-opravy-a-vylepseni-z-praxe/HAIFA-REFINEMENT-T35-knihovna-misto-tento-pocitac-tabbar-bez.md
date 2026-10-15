# HAIFA-REFINEMENT-T35: Knihovna instead of "Tento počítač", tabbar without a scrollbar, library dialogs, library refresh on install

Eight small changes to the dashboard and the library. Frontend: `aifactory/web/src/`. Backend: `aifactory/src/aifactory/`. Tests: `aifactory/web/src/**/*.test.ts`, `aifactory/tests/`. Code and comments are in English; UI texts and the guide are in Czech.

Finish with `just web-build`, because `aifactory/src/aifactory/web/static` is committed and must match the source.

`docs/decisions.md` is **outside the allowed paths**, so do not touch it. The change of seed semantics (item 7) is recorded in the module docstring of `library/reseed.py`, in the guide, and in the follow-up for decisions.md that the planner filed.

---

## 1. Tabbar without a vertical scrollbar

File: `web/src/components/RepoScreen.vue`, scoped style `.screen-tabs`.

Cause: `.screen-tabs` has `overflow-x: auto`, which turns `overflow-y` into `auto` as well. Each `a` has `margin-bottom: -1px`, so the content sticks out 1 px past the box and a vertical scrollbar appears on every repo screen (Backlog, Běhy, Review, Factory, …). They all share this nav.

Change:
- Add `overflow-y: hidden` to `.screen-tabs`. Keep `overflow-x: auto` for narrow windows and add `scrollbar-width: thin`.
- Remove `margin-bottom: -1px` from `.screen-tabs a`. Replace the nav's `border-bottom: 1px solid var(--border-soft)` with `box-shadow: inset 0 -1px 0 var(--border-soft)`. The active tab's 2 px `border-bottom` then paints over the inset line without overflowing.
- Check that there is no other horizontal tab strip with the same pattern: `grep -rn "overflow-x: auto" web/src` and look at the ones used as a tab bar. In particular, check the library `[role=tablist]` (it has no overflow, so it is fine).

Test: in `tests/e2e/test_limits_layout.py`, or the closest existing layout browser test, add an assertion at 1280×800 on `#/r/<id>/backlog` and `#/r/<id>/runs`: `nav.screen-tabs` has `scrollHeight <= clientHeight` (`page.evaluate`). Vitest cannot check layout.

## 2. "Tento počítač" → "Knihovna"; remove it from the repo switcher

The route stays `#/setup` / `#/setup/library` (`SETUP_HREF`, `LIBRARY_HREF` in `lib/router.ts` keep their values; no route change).

- `components/RepoSwitcher.vue`:
  - Delete the `<a … data-test="switch-setup">Tento počítač</a>` item. Drop `SETUP_HREF` from the import if it is no longer used.
  - `current` for `page === 'setup'` returns `'Knihovna'`.
  - Update the header comment.
- `App.vue`: `document.title = 'Knihovna · HAIFA'` for `setup`.
- `views/SetupView.vue`:
  - `<h1>Knihovna</h1>`.
  - Reorder so the library comes first: `<LibrarySection>` directly under the h1. Then a section `<section data-test="machine-check">` with `<h2>Kontrola počítače</h2>` and the `Znovu zkontrolovat` button (keep `data-test="machine-refresh"`), the summary (`machine-summary`, `machine-verdict`), the error/busy lines and the machine finding groups. Then `<DashboardSettings />`.
  - Update the top comment.
- `components/setup/LibrarySection.vue`: the section's own `<h2>Knihovna</h2>` would duplicate the h1. Rename it to `<h2>Obsah knihovny</h2>` and keep the header buttons. Update the header comment ("The library section of #/setup (page Knihovna)").
- `components/setup/DashboardSettings.vue`: comment only ("#/setup (Knihovna)").
- `lib/readiness.ts`:
  - The hint `'Otevři Tento počítač a oprav uvedený problém.'` becomes `'Otevři stránku Knihovna a oprav uvedený problém.'`.
  - The action `'Otevřít Tento počítač'` becomes `'Otevřít stránku Knihovna'`.
- `lib/gettingStarted.ts`: step `machine`: `title: 'Počítač'` (it is the machine check step; the page is now Knihovna). Href and action stay.
- `views/FactoryView.vue` line ~227: `Otevřít Tento počítač` becomes `Otevřít stránku Knihovna`. The group title `'Tento počítač: potřebné pro toto repo'` (line ~125) is a findings group about this machine, not the page name. Rename it to `'Počítač: potřebné pro toto repo'` and update `FactoryView.test.ts` line ~200 to match. Keep "Další nálezy tohoto počítače a knihovny".
- Leave "Harnessy tohoto počítače" (MachineHarnessesDialog) and other "tohoto počítače" phrases alone; they are not the page name.
- Guide (`src/aifactory/guide/*.md`): every mention of the *page* "Tento počítač" becomes the page "Knihovna". Files: 02, 03, 04, 08, 10, 11, 12, 13, 15 (grep `Tento počítač`).
  - `04-dashboard.md` line 16: the switcher menu offers **Přehled** and the repo list. The page Knihovna opens only from the library chip (line 12).
  - Rename the section heading `## Tento počítač` (line 32) to `## Knihovna`. Check `tests/test_guide.py` and any `#/guide/...` anchors for the old heading.
  - Phrases like "sekce **Knihovna** na stránce **Tento počítač**" become "stránka **Knihovna**".
  - `03-prvni-spusteni.md` table row: `| Počítač | Zkontrolovat počítač | …`.
- Tests:
  - `App.test.ts` ~line 197: the expected menu list loses `'Tento počítač'`. Add `expect(menu.find('[data-test="switch-setup"]').exists()).toBe(false)`. Add or extend a test: on `#/setup/library`, `document.title === 'Knihovna · HAIFA'` and `switcher-current` is `Knihovna`.
  - `LibraryChip.test.ts`: assert both chip variants link to `#/setup/library`; add it if missing.
  - `SetupView.test.ts` line 36: the h1 is `Knihovna`; the library section comes before `[data-test="machine-check"]`.
  - `lib/gettingStarted.test.ts` and `readiness` tests: update the texts.
  - `tests/e2e/test_library_browser.py` lines 63 and 77: `to_have_text("Knihovna")`.

## 3. Confirm button of the re-seed dialog

Dialog: `ConfirmDialog` with title "Obnovit výchozí agenty a workflows" in `LibrarySection.vue`.

1. **Reproduce first**: `just web-dev` against a `just dash` with a library, or the existing e2e fixture. Open the dialog in dark and light mode. Read `getComputedStyle` of `[data-test="confirm-ok"]` (background, border, color, opacity) and compare it with another ConfirmDialog, for example "Přesunout … do knihovny" or a run delete (`tone: 'danger'`).
2. Likely causes, which you must confirm:
   - the button is disabled (`!seedPlan.files.length`), so it renders at opacity .5;
   - or a style leaks into the dialog slot (`PlanView`, `library.css` rules on `button`/`input`).
   Fix the root cause in the library code, not in `ConfirmDialog.vue`, unless ConfirmDialog itself is wrong for every dialog.
3. Destructive variant: with item 7, re-seeding replaces team changes when items are ticked. Set `:tone="take.length ? 'danger' : 'default'"` on the seed dialog, and `confirm-label="Obnovit"` / `"Přepsat a obnovit"` accordingly.
4. When the plan has nothing to do, do not show a disabled green button that looks broken. Keep it disabled (the existing `seed-nothing` text explains why). If the faded look is what the user saw, use `cancel-label="Zavřít"` and keep the same ConfirmDialog styles as everywhere else.
5. Check dark and light mode (`data-theme='light'` on `<html>`) with screenshots and describe what you checked in your report.

Test: `LibrarySection.test.ts`. The seed dialog's `confirm-ok` has class `ok` and no `danger` without a take. With a ticked `seed-take-agent/builder` it has class `danger`.

## 4. Import dialog uses the repo path browser

Reuse `components/repos/PathField.vue` (typed path with folder suggestions) and `components/repos/FolderBrowser.vue` (modal browser), as on `views/ReposAddView.vue`.

- `PathField.vue`: add optional props so it is not tied to the repo page. Defaults keep the current behaviour and the existing tests:
  - `label` (default `'Cesta ke složce repozitáře'`, used as `aria-label`),
  - `dataTest` (default `'add-path'`, used as `data-test` of the input),
  - `autofocus` (default `true`; `onMounted` focuses only when true),
  - `disabled` (default `false`).
  Update the file comment.
- `LibrarySection.vue` import dialog:
  - `path` starts as `'~/'`. Load `home` with `fetchDirs()` (from `@/lib/api`) when the dialog opens; once is enough.
  - Replace the raw `<label>Složka <input …>` with a `.folder-row`: `<PathField v-model="path" :home="home" label="Složka pro import" data-test="import-path" …>` (the prop `dataTest`). Pass `dataTest="import-path"` so the existing test selector `[data-test=import-path]` still finds the input. Next to it, a button `Procházet…` (`data-test="import-browse"`, `FolderOpen` icon) opens `<FolderBrowser :open="browsing" @choose="…" @close="…">`. PathField `@submit` calls `planImport`.
  - FolderBrowser is its own teleported modal, and ConfirmDialog traps focus (`focusin` handler). So while browsing, hide the import dialog: `:open="importing && !browsing"`. On `choose`, set `path` and `browsing = false`, which reopens the import dialog. On `close`, just `browsing = false`. Make sure the cancel handler of the import dialog does not fire on that transition. ConfirmDialog only emits cancel on Esc, backdrop or Zrušit, so hiding it is safe.
  - Enter in PathField is already `preventDefault`ed, and ConfirmDialog ignores `defaultPrevented` keys. Confirm that Enter picks a suggestion and does not submit the dialog.
  - Keep the hint "Složka musí být pod domovskou složkou uživatele." and the Typ SelectMenu. Lay the fields out vertically: label above the control, full width, the same 8 px radius and `--panel-2` input look as PathField. Do not use the bare `.global-page input` style; the dialog is teleported anyway.
- Tests (`LibrarySection.test.ts`):
  - The import input is a PathField: role combobox, aria-label "Složka pro import".
  - `import-browse` opens `[data-test="folder-browser"]` (stub `fetchDirs`). Choosing a folder fills `import-path` and the import dialog is back.
  - Keep the existing preview/apply import test working.
  - `PathField` default props keep `ReposAddView.test.ts` green.

## 5. Tidier list of library items

`LibrarySection.vue`, the `.list` part (and `views/library.css` for shared rules, or a scoped style in LibrarySection).

Replace the 4-column table with a compact list. Keep the contract the tests use: container `data-test="library-items"`, rows `data-test="library-item"` with one `button` (the name) that opens the item, `aria-current` on the selected row, and `data-test="override-count-<name>"`.

- Use a `<ul data-test="library-items" class="item-list">` with one `<li data-test="library-item">` per item. The whole row is the button (`<button class="item-row">` spanning the row, left-aligned, no `.global-page button` margin or border look; scope styles to override them).
- Line 1: **name** (bold, mono) and, on the right, the badge with the count of repo copies: `override-count-<name>`, text = number, `title="Repa s vlastní kopií"`. Show it only when > 0. The test expects text `'1'` when 1; when 0, render the element empty or with `—` in faint colour. Keep `text()` as `'—'` for 0 so existing assertions (if any) hold; check the tests.
- Line 2: purpose/description, `--dim`, clamped to 2 lines (`-webkit-line-clamp: 2`).
- Line 3: small faint meta `versionLabel(item) · date · author`. Tests look for `'v2 · 12345678'` and the e2e `"v1 ·"`, so keep the `versionLabel` text intact.
- Selected row: `background: var(--panel-2)` and a 3 px left accent `var(--cyan)`. Hover: `--panel-2`.
- Rows separated by `border-bottom: 1px solid var(--border-soft)`. No table header.
- Empty state stays "Žádné položky tohoto typu".
- Give the tablist (`role=tablist`) a bottom border and spacing consistent with the list.

Update `LibrarySection.test.ts` selectors that relied on `table`/`td`; most use `[data-test="library-item"] button`, which stays. Check `tests/e2e/test_library_browser.py` too (it uses `library-item button` and `library-items` text, so it should still pass).

## 6. Right panel: delete the repo's custom copy

The backend already exists: the Factory plan/apply action `remove` (`web/factory.py`, `OPTIONS["remove"] = ("type","name")`; CLI `factory config remove`). It deletes the repo's own copy (roster entry/prompts, workflow, skill in `.claude/skills` + `.agents/skills`, extension) and commits to base. The library item then applies. No backend change is needed. Read `web/factory.py`'s `plan`/`apply` for the result shape of `remove` and its blockers (`in_use`).

- `lib/api.ts`: add `previewRemove(options: MoveOptions, id): Promise<FactoryPlanCommon-like>` and `applyRemove(options, digest, id): Promise<FactoryResult>`, mirroring `previewMove`/`applyMove`, with `action: 'remove'` and `target: 'base'`. Reuse or extend the existing plan type. Check which type `factoryEnvelope` returns for set/remove (`FactoryPlan`).
- `LibrarySection.vue`, in each `override-<repo>` row: a third button **Smazat kopii z repa** (`data-test="override-remove"`). It calls `previewRemove({type,name}, o.repo)` and stores `removeFor = o`, `removePlan = plan`. That opens
  `<ConfirmDialog tone="danger" :title="`Smazat ${type}/${name} z repa ${repo_name}?`" message="Smaže vlastní kopii z repa a commitne to do base. Repo pak zdědí verzi z knihovny." confirm-label="Smazat kopii" :confirm-disabled="busy || !!removePlan.blockers?.length">`, with `<PlanView :plan="removePlan" collapsed />` in its slot so blockers and files show.
  - Cancel clears the state and **writes nothing**.
  - Confirm calls `applyRemove(…, removePlan.digest, o.repo)`. Then `importResult = "<type>/<name>: kopie v repu <repo_name> smazána, repo dědí z knihovny."` (plus the short commit if the result has one), `await loadOverrides()`, `emit('changed')`, and `window.dispatchEvent(new Event('factory-applied'))`; `changed` already does this on SetupView.
  - Errors go to `error` via `apiText`.
  - The row disappears because overrides are reloaded. Show the item as inherited: when `itemOverrides` is empty, the existing "Žádné registrované repo ji nepřepisuje." plus the hint "Repa bez vlastní kopie dědí aktuální verzi knihovny." Also update `override-count-<name>`.
  - Opening another item or tab clears the remove state (extend `closeDiff`).
- Tests (`LibrarySection.test.ts`):
  1. Clicking `override-remove` opens the danger dialog. Cancel makes no `/factory/apply` call (spy on fetch).
  2. Confirm posts `{action:'remove', options:{type,name}, target:'base', digest}` to `/api/repos/<id>/factory/apply` (check the URL format used by `factoryUrl`). The overrides refetch returns none, so `item-no-overrides` shows and the count becomes `—`/empty.
  3. Blockers disable `confirm-ok`.

## 7. Library refresh on install and upgrade

Goal: after an install or upgrade, every seed item in the library equals the installed version's seed. Items in the library that are not in the seed (team imports) stay. Repos are never touched: their `.factory/` copies are the customizations.

### Backend
- `library/reseed.py`: add `take_all: bool = False` to `seed_library` (keyword). With `take_all`, `wanted = {i.key for i in seed}`. Every team-changed seed item gets action `take` (replaced), never `kept`. Update the module docstring: "on install and upgrade, `factory library seed --all` replaces every seed item; customizations live in the repos' `.factory/`".
- `cli.py` `library seed`: add `--all` (`store_true`, help "replace every seed item with the installed seed version, also items the team changed; install and upgrade run this"). `--all` together with `--take` is a `usage_error`. Use the existing usage-error helper in cli, as for other exclusive flags. Pass it as `take_all=args.all`. Extend the parser `description`. `factory --skill` is generated from argparse; check `tests/test_skill.py` and any snapshot of the command list.
- `upgrade.py`, the non-handoff branch after a successful `uv tool install` (`result.installed = True`): call a new `refresh_library(uv, environ) -> str | None`. It:
  - finds the new `factory` executable via `subprocess.run([uv, "tool", "dir", "--bin"], capture_output=True, text=True)` → `Path(out.strip()) / ("factory.exe" if os.name == "nt" else "factory")`;
  - runs `[factory, "library", "status", "--json"]`; on `library_missing` it runs `[factory, "library", "clone", "--seed-fallback"]` first, mirroring install.sh;
  - then runs `[factory, "library", "seed", "--all"]`;
  - returns a warning text on any failure (missing exe, non-zero exit) and None on success.
  Append the warning to `result.warnings`; never fail the upgrade because of it. Add `library_refreshed: bool` to `UpgradeResult` and its `to_json`. It must run the **new** binary: the running process still has the old seed. Update the module docstring.
- `hand_off` (Windows) and `upgrade_handoff.ps1`: after a successful `uv tool install`, the script resolves `& $plan.uv tool dir --bin`, runs `factory.exe library status --json`, `library clone --seed-fallback` when missing, and `factory.exe library seed --all`. It logs the outcome with `Write-Log`; a failure is logged and does not stop the restart. If the script needs anything new, add it to the plan JSON (it should not need anything beyond `uv`).
- Dashboard upgrade (UpdateChip → API calling `run_upgrade`): covered by the above. Check that the API passes the new `warnings`/`library_refreshed` through, without UI changes.

### Bundle installers
- `bundle/install.sh` (lines ~27–54):
  - Missing library: `library clone --seed-fallback` as today.
  - Then, whether the library existed or was just cloned: `"$factory" library seed --all`. A failure is a warning ("warning: the library was not refreshed; run: factory library seed --all") and not an exit.
  - Replace the message "The library exists; it is left unchanged." with "Refreshing the library to HAIFA @VERSION@".
  - Update the comment.
- `bundle/install.ps1` (lines ~131–145): the same. Replace the `seed_update_available` hint with `Invoke-Native 'factory library seed --all' { & $factory library seed --all }`, wrapped so that a failure is `Write-Warning` and not `Fail`. Check how `Invoke-Native` behaves on failure and use try/catch if it throws.
- `bundle/install.bat` only delegates; check.

### Tests
- `tests/library/test_library_reseed.py`:
  - `seed_library(take_all=True)` replaces a team-changed item (action `take`, file content = seed) and keeps a non-seed item;
  - the CLI `factory library seed --all --json` does the same;
  - `--all --take x` is `usage_error`;
  - a repo's `.factory/` copy of a seed item is unchanged after `seed --all` (use the repo helpers of `test_library_install_commit.py`; assert the repo tree and HEAD are unchanged).
- `tests/test_upgrade.py`: the fake uv (`uv_log` fixture) must answer `tool dir --bin` with a temp bin dir that holds a fake `factory` logging its argv (see `FAKE_FACTORY` in `tests/test_bundle.py` and `tests/fake_exe.py` for a cross-platform fake). Assert:
  - after a successful install the calls are `library status --json` then `library seed --all`, plus `library clone --seed-fallback` when status says missing;
  - `library_refreshed` is true;
  - a failing fake factory yields a warning and the upgrade still succeeds;
  - a dry run and a failed uv install call no factory.
  - The handoff test checks that the copied script contains `library seed --all`.
- `tests/test_bundle.py::test_install_sh_clones_a_missing_library_and_keeps_an_existing_one`: rename it, for example `…_and_refreshes_it`. Expected calls:
  - missing: `["library status --json", "library clone --seed-fallback", "library seed --all"]`;
  - ok: `["library status --json", "library seed --all"]`.
  Extend `FAKE_FACTORY` if needed. Add a case where `library seed` fails: install exits 0 with the warning.

## 8. The `factory` skill in the library

The skill rendered by `factory --skill` (`skill/render.py: render_skill()`; front matter `name: factory`) becomes a generated seed item `skill/factory`. Creating, cloning-with-fallback and refreshing the library (item 7) all write it, and it is versioned like any seed item.

- `library/seed.py`: add `SKILL_NAME = "factory"` and `def skill_seed_item() -> SeedItem` (or return the raw bytes and build the `SeedItem` in store.py to avoid an import cycle; `SeedItem`/`NewFile` live in `store.py`). It builds the bytes from `render_skill().encode("utf-8")`, calling with no parser so render builds the CLI parser lazily, and returns `SeedItem("skill", "factory", tree_version((ItemFile("SKILL.md", False, data),)), (NewFile(f"{item_library_path('skill','factory')}/SKILL.md", False, data),))`.
  - Use the `ItemFile` constructor from `library/model.py`; check its field order.
  - `item_library_path('skill', name)` is `skills/<name>` (`library/load.py`).
  - Validate the item once with the same rules as library skills (`_validate_skill` through `check_library_item` on a temp dir, or a direct call) so a broken skill fails loudly in tests.
- `library/store.py: packaged_seed()`: return `read_seed(...)` plus `skill_seed_item()`, sorted by `(ITEM_TYPES.index(type), name)`. Keep the `functools.cache`. Import inside the function if `aifactory.skill.render` → `aifactory.cli` → library would cycle; check with `uv run python -c "import aifactory.library.store"`.
- Effects to check:
  - `init_library` and `seed_library` already iterate `packaged_seed()`, so a new library contains `skills/factory/SKILL.md`, and `library.yaml` `seed` records `skill/factory`;
  - `seed_updates` reports `skill/factory` when the version changes; that is wanted;
  - the version changes whenever the CLI or skill template changes, which is wanted too.
  - Do **not** add it to `seed.seed_items()` (the no-library fallback for inheritance), unless tests show the two must match. If something asserts `packaged_seed()` keys == `seed_items()` keys, update that assertion and explain in a comment that the skill is generated and lives only in the library.
- Tests:
  - `tests/library/test_library_seed.py`: `packaged_seed()` contains `skill/factory` whose `SKILL.md` bytes equal `render_skill().encode()`.
  - After `init_library()` (temp HAIFA_HOME fixture), `skills/factory/SKILL.md` in the library HEAD equals `render_skill()`.
  - After `seed_library(take_all=True)` on a library whose `skills/factory/SKILL.md` was edited, it equals `render_skill()` again.
  - Fix existing tests that count or list the seed items: grep `packaged_seed`, `seed_versions`, `"agent/builder"` lists, plan item counts in `tests/library/`, `tests/web/` (library API tests), `tests/check/` (seed_update_available) and `tests/e2e/test_library_browser.py`. The e2e "Založit knihovnu ze semínka" dialog now also lists `skill/factory`.
- Guide: `10-knihovna.md`, where it describes the seed: the seed includes the `factory` skill generated from `factory --skill`. `13-aktualizace.md` (lines 28–35): installing or upgrading HAIFA refreshes the library to the installed seed (`factory library seed --all`), including the `factory` skill; team edits of seed items in the library are replaced, and customizations belong in the repos' `.factory/`. Manual `factory library seed` (without `--all`) keeps working as before. `14-cli.md`: mention `--all` in the `factory library seed` row, if there is one. `02-instalace.md`: the installer refreshes the library.

---

## Verification (run all, judge by exit status)

1. `just lint`, `just typecheck`.
2. `just web-test`.
3. `just pytest tests/library tests/test_upgrade.py tests/test_bundle.py tests/test_skill.py tests/test_guide.py tests/web tests/check`. Use narrower paths if the time limit requires it, but include every file you changed tests in.
4. `just web-build` (commit the regenerated `src/aifactory/web/static`).
5. Browser:
   - `just pytest tests/e2e/test_library_browser.py -n0`;
   - the layout test you extended for the tabbar (`tests/e2e/test_limits_layout.py -n0`, or whichever file).
6. Manual or screenshot check in dark and light mode:
   - the seed dialog button (item 3);
   - the import dialog with PathField and the browser (item 4);
   - the item list (item 5);
   - the remove-copy dialog (item 6);
   - no vertical scrollbar on the Backlog and Běhy tabbar (item 1).
   Say in the report what you looked at.

## Done when
- No vertical scrollbar on the repo tabbar at a normal window width on any repo screen.
- The switcher menu has no link to the page. The library chip opens a page with h1 and `document.title` "Knihovna". Texts in the guide, getting-started and readiness are updated. Tests are updated.
- The re-seed confirm uses the shared ConfirmDialog style (danger when it overwrites ticked items), in dark and light mode.
- Library import uses PathField and FolderBrowser.
- The library item list is the new compact list.
- "Smazat kopii z repa" deletes the repo copy only after confirming, and the item then shows as inherited.
- `install.sh`, `install.ps1`, `factory upgrade` (direct and Windows handoff) run `factory library seed --all` with the new binary, without touching repos.
- The library contains `skills/factory/SKILL.md` equal to `factory --skill` of the installed version.
- Backend tests cover the refresh and the skill.
