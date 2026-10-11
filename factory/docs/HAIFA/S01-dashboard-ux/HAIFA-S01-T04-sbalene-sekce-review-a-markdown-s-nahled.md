# HAIFA-S01-T04: Sbalené sekce Review a markdown s náhledem a zdrojem

## Co se změnilo

- **Detail PR na obrazovce Review začíná sbalený.** Sekce Popis PR, Běhy, Gates a testy, Verdikt revieweru a Diff i každý soubor v diffu jsou po otevření PR zavřené. Když se změní `detail.task_id` (přechod na jiný PR), sbalí se znovu. Tichá obnova téhož PR (`task_id` zůstává stejné) otevřené sekce nechá otevřené.
- **Akce už nejsou skládací sekce.** `ReviewActions` (Schválit, Vrátit, Vyřešit konflikt, Dorovnat s base) se vykresluje v `div.actions-bar[data-test="actions"]` hned pod hlavičkou, nad všemi sekcemi. Odpovídá to existujícímu rozhodnutí „Výchozí sbalení (2026-10-02)“ v `docs/decisions.md`, které tento úkol nemění.
- **Nová sdílená komponenta `MarkdownView`** má záložky **Náhled** a **Zdroj**, výchozí je Náhled. Pro prázdný vstup ukáže `—`, případně text z volitelné prop `empty`. Používá ji Zadání v detailu tasku (`data-test="body"`) a Popis PR (`data-test="pr-body"`). Tyto atributy dostane kořenový `div.mdview`.
- **Renderer markdownu** (`lib/markdown.ts` a `lib/highlight.ts`) je port z visualizeru sssf, bez nové závislosti:
  - Celý vstup se escapuje dřív, než vzniknou tagy, takže HTML z textu se nevykoná. Ve výstupu jsou jen tagy, které vytvoří renderer.
  - Odkazy vzniknou jen pro `http(s)://`. U jiného schématu, například `javascript:`, zůstane prostý text.
  - Renderer zvládá nadpisy `#`–`####`, odstavce, seznamy `-`/`*` a `1.`, bloky kódu ``` (u `json` se zvýrazní syntaxe), inline kód, tučné písmo, citace a `---`. Tabulky nepodporuje.
  - Oproti originálu přibyla funkce `stripComments`. Ta mimo bloky kódu vynechá komentáře `<!-- … -->`, i víceřádkové. Řádek, který obsahoval jen komentář, zmizí celý. Neuzavřený komentář pohltí zbytek dokumentu. Uvnitř bloku kódu komentář zůstane doslovně a escapovaný. Záložka Zdroj ukazuje surový text včetně komentářů.

## Kde to je

| Soubor | Změna |
|---|---|
| `aifactory/web/src/lib/markdown.ts` | `renderMarkdown`, `stripComments` |
| `aifactory/web/src/lib/highlight.ts` | `escapeHtml`, `highlightJsonText`, `highlightJson` |
| `aifactory/web/src/components/ui/MarkdownView.vue` | záložky Náhled/Zdroj (`md-tab-preview`, `md-tab-source`, `md-preview`, `md-source`, `md-empty`) |
| `aifactory/web/src/components/review/ReviewDetail.vue` | všechny klíče `open` jsou `false`; `watch(task_id, collapseAll)`; `actions-bar` místo sekce Akce; `MarkdownView` v Popisu PR; `DiffView` má `:key="detail.task_id"` |
| `aifactory/web/src/components/review/DiffView.vue` | mapa `closed` nahrazena mapou `open`, takže soubory začínají sbalené; sekce souboru má `data-test="diff-file-section"` a `data-path` |
| `aifactory/web/src/components/backlog/TaskDetail.vue` | Zadání se vykresluje přes `MarkdownView`; odstraněn styl `.body` |
| `aifactory/web/src/style.css` | globální styly `.md-tabs` a `.md-source` |
| `aifactory/src/aifactory/web/static/` | nový build: `index-ChP6tFSh.js` a `index-DIyxj2nw.css` nahrazují staré soubory; upravený `index.html` |

## Testy

- `lib/markdown.test.ts`: escapování `<script>` a `<img onerror>`; vynechání jednořádkového i víceřádkového komentáře; komentář uvnitř bloku kódu zůstane; nadpis, seznamy, blok kódu a inline kód; odkazy jen http(s); okrajové případy `stripComments`.
- `components/ui/MarkdownView.test.ts`: komponenta začíná v náhledu a komentář není vidět; přepne se na zdroj a zpět; prázdný vstup ukáže `—`.
- `components/review/ReviewDetail.test.ts`: po načtení je vše sbalené a akce leží v DOM před první `.dsec`; obnova téhož PR stav zachová, jiný PR sekce i soubory diffu znovu sbalí. Starší testy si sekce nejdřív otevřou.
- `components/review/DiffView.test.ts`: soubory začínají sbalené a otevírají se klikem na `button.dsec-head`.
- `aifactory/tests/e2e/test_f3_browser.py` (`_approve`): po otevření PR ověří, že jsou akce vidět a že na stránce není `.dsec-body` ani `pr-body`. Potom schválí PR bez otevírání sekcí.

## Jak ověřit

```sh
just web-test     # vue-tsc + vitest
just test && just typecheck && just lint && just e2e
just web-build    # znovu sestaví aifactory/src/aifactory/web/static/
```

Ručně přes `just dash`: otevřete PR na Review a ověřte, že jsou všechny sekce sbalené a akce nahoře. Přepněte na jiný PR a ověřte, že se sekce znovu sbalily. V Popisu PR a v Zadání tasku je výchozí Náhled a záložka Zdroj ukáže surový markdown včetně `<!-- … -->`.
