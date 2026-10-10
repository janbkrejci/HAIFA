# HAIFA-S01-T01 — Vlastní modální dialog a tooltip místo systémových

Dashboard (`aifactory/web/src/`) už nevolá systémové dialogy (`window.confirm`, `alert`, `prompt`)
a nemá nativní tooltipy (atribut `title`, SVG `<title>`). Nahrazují je dvě sdílené komponenty
v `components/ui/`, které vypadají jako zbytek dashboardu a fungují i z klávesnice.

## ConfirmDialog + useConfirm

- `components/ui/ConfirmDialog.vue` — modální dialog teleportovaný do `<body>`
  (`role="dialog"`, `aria-modal`, `aria-labelledby`/`aria-describedby`). Props: `open`, `title`,
  `message` (víceřádkový), `confirmLabel` (výchozí „Potvrdit“), `cancelLabel` (výchozí „Zrušit“),
  `tone` (`default` | `danger`). Emituje `confirm` a `cancel`.
- Klávesy a fokus: Esc a klik mimo panel (`mousedown` na pozadí) ruší, Enter potvrzuje
  (Enter na tlačítku Zrušit ruší). Po otevření má fokus Potvrdit, Tab/Shift+Tab cyklí uvnitř
  a fokus mimo panel se vrátí dovnitř. Po zavření se fokus vrátí na prvek, který dialog otevřel.
- `lib/confirm.ts` — `useConfirm()` vrací `{ dialog, ask, confirm, cancel }`.
  `await ask({ title, message, tone })` vrací `true`/`false`; nové `ask` při otevřeném
  dotazu ten předchozí zruší (`false`). Zapojení v šabloně:
  `<ConfirmDialog v-bind="dialog" @confirm="confirm" @cancel="cancel" />`.
- Použití:
  - Schválit v `components/review/ReviewActions.vue` — titulek „Schválit a mergovat PR … do …?“,
    zpráva = `approve_note`.
  - Zastavit v `components/runs/RunDetail.vue` — titulek „Zastavit běh … tasku …?“, `tone: 'danger'`.

## Tooltip

- `components/ui/Tooltip.vue`, prop `text`, volitelně `placement` (`bottom` | `top`;
  překlopí se, když se nevejde do okna).
- Obalový režim: `<Tooltip text="…"><button …/></Tooltip>` — ukáže se při najetí myší
  i při fokusu z klávesnice (`focusin`), skryje se při odchodu myši, ztrátě fokusu, Esc,
  scrollu a změně velikosti okna. Neinteraktivní kotvy dostaly `tabindex="0"`.
- Řízený režim: `<Tooltip :text="…" :anchor="el" />` — viditelný, dokud je `anchor` nastaven.
  Používá ho `DependencyGraph.vue`: jeden tooltip mimo `<svg>` pro všechny uzly, plněný
  z `mouseenter`/`focus` uzlu.
- Bublina je teleportovaná do `<body>` s `position: fixed`, takže leží nad sticky horní
  lištou a neořízne ji rolovací kontejner ani SVG.
- `style.css` přidává vrstvy `--z-modal: 1000`, `--z-tooltip: 1100` (lišta má 10) a stín `--shadow-pop`.
- Kde je nasazen (atribut `title` odstraněn, místo něj `Tooltip`, případně `aria-label`):
  - `App.vue` — přepínač motivu (+ `aria-label`) a cesta k repu (`health.repo`);
  - `components/backlog/TreeNode.vue` — odznak auto;
  - `components/backlog/TaskDetail.vue` — tlačítka Odebrat vazbu (+ `aria-label`);
  - `components/runs/PhaseDots.vue` — tečky fází (`název — stav`, + `aria-label`);
  - `components/runs/StatChip.vue` — statistiky;
  - `components/backlog/DependencyGraph.vue` — uzly grafu (SVG `<title>` nahrazen, + `aria-label`,
    externí uzly mají `tabindex="0"`).

## Pojistky a testy

- `lib/noNativeUi.test.ts` — projde všechny zdroje (`*.vue`, `*.ts` mimo testy) a selže na
  `window.confirm/alert/prompt`, `alert(`/`prompt(`, SVG `<title>` a atributu `title`
  (povolen jen jako prop `DetailSection`, která ho nevykresluje).
- `components/ui/ConfirmDialog.test.ts`, `components/ui/Tooltip.test.ts`, `lib/confirm.test.ts` —
  potvrzení i zrušení, Esc/Enter, klik mimo, past na fokus a jeho návrat, tooltip při hover/focus,
  řízený režim.
- `test/modal.ts` — helper `answerDialog(ok)` (a `openDialog()`) pro dialog teleportovaný do `<body>`.
  Testy, které dřív podvrhovaly `window.confirm` (`ReviewActions`, `RunDetail`, `ReviewView`,
  `RunsView`), teď odpovídají v modálu; testy `App`, `BacklogTree`, `DependencyGraph`, `TaskDetail`
  ověřují tooltipy.
- E2E `aifactory/tests/e2e/test_f3_browser.py` — handler `dialog` každý systémový dialog
  zaznamená do `net.dialogs`, odmítne ho a test pak selže. `_approve` potvrzuje v modálu
  (kontroluje text „Schválit a mergovat“ a fokus na Potvrdit) a `_nav` na každé obrazovce
  ověřuje, že žádný prvek nemá `[title]`.

## Build

Přestavěný frontend v `aifactory/src/aifactory/web/static/` (`index.html` odkazuje na nové
`assets/index-BGzuJMh_.js` a `assets/index-Dvaw4xo7.css`, staré bundly odstraněny).
Bez nových závislostí.

## Ověření

`just test`, `just typecheck`, `just lint`, `just e2e`. Ručně: Review → Schválit otevře modál,
Esc/klik mimo zruší, Enter potvrdí; najetí nebo Tab na přepínač motivu, tečky fází či uzel grafu
ukáže tooltip nad lištou.
