# HAIFA-S01-T02: Vlastní dropdown místo nativního selectu

## Co se změnilo

Dashboard už nepoužívá žádný nativní `<select>`. Všech devět míst teď používá jednu sdílenou komponentu `SelectMenu`. Otevřený seznam má vzhled dashboardu (panel, stín, modré zvýraznění), ne systémový.

| Místo | Soubor | `data-test` |
|---|---|---|
| Filtr stavu v Backlogu | `components/backlog/BacklogFilters.vue` | `state-filter` |
| Filtr stavu a tasku v Bězích | `components/runs/RunsList.vue` | `state-filter`, `task-filter` |
| Step, status, workflow ve formuláři tasku | `components/backlog/TaskForm.vue` | `step`, `status`, `workflow` |
| Workflow v detailu tasku | `components/backlog/TaskDetail.vue` | `workflow-select` |
| Git provider, merge strategie v Nastavení | `components/settings/SettingsForm.vue` | `git_provider`, `merge_strategy` |

(Cesty jsou relativní k `aifactory/web/src/`.) Atributy `data-test` zůstaly na stejných polích. Z těchto komponent zmizela CSS pravidla pro `select`.

## Komponenta `components/ui/SelectMenu.vue`

Komponenta implementuje vzor WAI-ARIA „select-only combobox“. Spouštěč je `<button role="combobox">` a fokus zůstává na něm. Aktivní položku oznamuje `aria-activedescendant`.

- **Props:** `modelValue` (string, `v-model`), `options: SelectOption[]` (`{ value, label }`), `label` (dává `aria-label` spouštěči i seznamu), `disabled`, `invalid` (červený okraj a `aria-invalid="true"`), `placeholder` (zobrazí se, když hodnota neodpovídá žádné položce).
- Používá `inheritAttrs: false`. Ostatní atributy (např. `data-test`) jdou na spouštěč. Spouštěč nese i `data-value` s aktuální hodnotou.
- **Umístění:** `<ul role="listbox" data-test="select-list">` se teleportuje do `<body>` s `position: fixed` a vrstvou `z-index: var(--z-dropdown)`. Díky tomu leží nad horní lištou a rolovací kontejner ho neořízne. Komponenta ho otevře pod spouštěčem, nebo nad ním, když je tam víc místa. Výška je nejvýš 320 px a seznam se drží 8 px od okraje okna.
- **Zavření:** klik mimo spouštěč i seznam (`mousedown`), rolování stránky (rolování samotného seznamu ho nezavře), změna velikosti okna, ztráta fokusu, přechod do stavu `disabled`.
- **Myš:** klik seznam otevře nebo zavře. Najetí myší položku zvýrazní, klik ji vybere. Výběr už zvolené položky nevyvolá `update:modelValue`.
- **Klávesnice, zavřený seznam:** `↓`/`↑`/`Enter`/`Space` ho otevřou. Tisknutelný znak rovnou vybere položku podle prvních písmen, jako to dělá nativní select.
- **Klávesnice, otevřený seznam:** `↑`/`↓`, `Home`/`End` a `PageUp`/`PageDown` (po 10 položkách) posouvají aktivní položku. `Enter`/`Space`/`Alt+↑` ji vyberou. `Esc` seznam zavře a událost dál nešíří, takže nezavře okolní dialog. `Tab` vybere aktivní položku a pustí fokus dál. Písmena skáčou na položku.

Čistá logika vyhledávání podle písmen je v `lib/select.ts`. Ten soubor obsahuje i typ `SelectOption`.
- `typeaheadIndex(labels, query, from)` hledá od `from + 1` dál a na konci pokračuje od začátku. Na velikosti písmen nezáleží (locale `cs`), diakritika se ale zachovává. Bez shody vrací `-1`.
- `typeaheadQuery(buffer)`: buffer z jednoho opakovaného znaku („tt“) prochází položky na stejné písmeno. Buffer se vynuluje po 500 ms.

## Další úpravy

- `style.css` přidává proměnnou `--z-dropdown: 1050`. Seznam tak leží nad modálním oknem (1000) a pod tooltipem (1100).
- `SettingsForm.vue`: když soubor obsahuje hodnotu, kterou server nenabízí, zůstane vidět jako vlastní položka na začátku seznamu (`choiceOptions`). Stejně se to chovalo i dřív.
- `TaskForm.vue`: status `done` je v nabídce jen u hotového tasku a pole je tehdy zakázané.

## Testy

- `components/ui/SelectMenu.test.ts` testuje přístupný spouštěč, myš, klik mimo, rolování, šipky, Home/End, Enter, Esc, Space a Tab. Ověřuje také, že Enter neodešle formulář a Esc nezavře dialog. Dál pokrývá výběr podle písmen v otevřeném i zavřeném seznamu, vázanou hodnotu s placeholderem, zakázaný stav a chybový stav.
- `lib/select.test.ts` je unit test typeahead funkcí.
- `test/select.ts` obsahuje pomocné funkce pro testy komponent: `openSelect`, `chooseOption`, `selectLabels`, `listOptions` a `optionLabels`. Seznam se hledá v `<body>` přes `aria-controls`.
- Testy všech devíti míst jsou upravené na tyto pomocné funkce: `BacklogFilters`, `TaskForm`, `TaskDetail`, `RunsList`, `SettingsForm`, `views/BacklogView` a `views/RunsView`.
- Pojistka v `lib/noNativeUi.test.ts` ověřuje, že žádná šablona `.vue` neobsahuje `<select>` ani `<option>`.
- `aifactory/tests/e2e/test_f3_browser.py`: nový helper `_choose()` vybírá step novým dropdownem. Otevře ho kliknutím, ověří `listbox` a `aria-expanded`, klikne na položku podle `data-value` a ověří, že se seznam zavřel a hodnota se změnila.

## Build

Build frontendu v `aifactory/src/aifactory/web/static/` je přegenerovaný. Soubor `index.html` teď odkazuje na `assets/index-BSKY7hY8.js` a `assets/index-B_FLYPw0.css`, staré soubory zmizely.

Patří sem i specifikace `specs/HAIFA-S01-T02-vlastni-dropdown-misto-nativniho-selectu.md`.

## Ověření

```sh
just test && just typecheck && just lint && just e2e
```

Ruční ověření: v dashboardu otevři filtr stavu v Backlogu nebo formulář nového tasku. Seznam má mít vzhled dashboardu, reagovat na šipky a písmena, zavřít se klikem mimo a ležet nad horní lištou.
