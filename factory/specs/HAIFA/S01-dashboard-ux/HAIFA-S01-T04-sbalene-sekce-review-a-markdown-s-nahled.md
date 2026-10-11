# HAIFA-S01-T04: Sbalené sekce Review a markdown s náhledem a zdrojem

## Cíl

1. Detail PR na obrazovce Review: všechny skládací sekce (Popis PR, Běhy, Gates a testy, Verdikt revieweru, Diff) i každý soubor diffu začínají sbalené a po přechodu na jiný PR se znovu sbalí. Tichá obnova téhož PR (polling v `ReviewView.refreshDetail`) stav rozbalení **nemění**.
2. Akce (Schválit, Vrátit, Vyřešit konflikt, Dorovnat s base) nejsou v `DetailSection`, jsou vždy vidět nad sekcemi.
3. Nová sdílená komponenta `MarkdownView` se záložkami **Náhled** / **Zdroj** (výchozí Náhled), použitá v Zadání detailu tasku a v Popisu PR.
4. Renderer převzatý z `vendor/sssf/apps/visualizer/src/lib/markdown.ts` + `highlight.ts`, rozšířený o vynechání HTML komentářů.

Rozhodnutí v `docs/decisions.md` už existuje (řádek „Výchozí sbalení (2026-10-02)": „Akce v Review (Schválit, varování o konfliktu) jsou vždy vidět"). `docs/` NENÍ v povolených cestách — **needitovat**. V app_docs dokumentaci na rozhodnutí jen odkázat.

Pevná omezení: žádná nová závislost (package.json / bun.lock beze změny), `vendor/` a `prototype/` se nemění, testy nevolají model. Měnit jen `aifactory/`, `justfile`, spec a `app_docs/HAIFA-S01-T04-sbalene-sekce-review-a-markdown-s-nahled.md`.

## Soubory a změny

Všechny cesty frontendu relativně k `aifactory/web/src/`.

### 1. `lib/highlight.ts` (nový) — port z vendoru

Zkopírovat `vendor/sssf/apps/visualizer/src/lib/highlight.ts` (stačí `escapeHtml` a `highlightJsonText`; `highlightJson` může zůstat). Hlavičkový komentář: „Port of the sssf visualizer's lib/highlight.ts". CSS třídy `.j-*` už jsou v `style.css` (ř. ~115) — nic nepřidávat.

### 2. `lib/markdown.ts` (nový) — port z vendoru + komentáře

Zkopírovat `vendor/sssf/apps/visualizer/src/lib/markdown.ts` (import `./highlight`), hlavička „Port of the sssf visualizer's lib/markdown.ts; adds HTML-comment stripping." Bezpečnostní model zachovat beze změny: celý vstup se escapuje dřív, než vzniknou tagy; odkazy jen `https?://` (regex v `inline`).

Doplnit vynechání HTML komentářů `<!-- … -->` (i víceřádkových) **mimo** fenced code bloky (v kódu zůstávají doslovně). Doporučená implementace: exportovaná pomocná funkce `stripComments(lines: string[]): string[]` volaná na začátku `renderMarkdown` nad `src.replaceAll('\r\n','\n').split('\n')`:
- stav `inFence` (přepíná řádek odpovídající `/^\s*```/`, jen když nejsme v komentáři) a `inComment`;
- mimo fence: v cyklu na řádku — je-li `inComment`, hledej `-->`; nenalezeno → zbytek řádku zahodit; nalezeno → odřízni po `-->` a `inComment=false`. Jinak hledej `<!--`; nalezeno → ponech text před ním, `inComment=true`, pokračuj zbytkem;
- řádek, který byl celý komentář (po odstranění prázdný a původně neprázdný), z výstupu vypusť úplně (aby nevznikal falešný odstavcový zlom navíc — prázdný řádek je ale i tak neškodný; hlavní je, že text komentáře se nikde neobjeví);
- neuzavřený komentář zahodí zbytek dokumentu (stejně jako prohlížeč).

Pozor na seznamy: regex markerů pracuje nad `raw`, tak zachovat. V `renderMarkdown` nic dalšího neměnit. Tabulky out of scope.

### 3. `lib/markdown.test.ts` (nový, vitest)

- `<script>alert(1)</script>` v odstavci → výstup neobsahuje `<script`, obsahuje `&lt;script&gt;`. Pozor: `noNativeUi.test.ts` skenuje jen ne-testové soubory, takže `alert(` v testu nevadí; přesto raději `<script>x()</script>`.
- `<img src=x onerror=y>` → escapováno (žádné `<img`).
- `<!-- doplňuje HAIFA -->` (jednořádkový) i víceřádkový komentář → text komentáře ani `&lt;!--` ve výstupu nejsou; text okolo zůstane.
- Komentář uvnitř ```` ``` ```` bloku zůstane (escapovaný) v `<pre class="md-code">`.
- `## Nadpis` → `<h2>Nadpis</h2>`; `- a\n- b` → `<ul><li>a</li><li>b</li></ul>`; `1. x` → `<ol>`; fenced blok → `<pre class="md-code"><code>…</code></pre>`; inline `` `k` `` → `<code>k</code>`.
- `[x](https://a.b)` → `<a href="https://a.b" …>`; `[x](javascript:alert(1))` → žádné `<a`.

### 4. `components/ui/MarkdownView.vue` (nový) — sdílená komponenta

```ts
const props = defineProps<{ source: string; empty?: string }>()  // empty default '—'
const mode = ref<'preview' | 'source'>('preview')
const html = computed(() => renderMarkdown(props.source))
```
Šablona (kořen `div.mdview`, aby fallthrough atributy jako `data-test="body"` / `data-test="pr-body"` padly na kořen):
- `div.md-tabs[role="tablist"]` se dvěma `<button type="button" role="tab">`: „Náhled" (`data-test="md-tab-preview"`, `:aria-selected`) a „Zdroj" (`data-test="md-tab-source"`). Aktivní má třídu `active`. **Žádný atribut `title`** (hlídá `noNativeUi.test.ts`).
- Je-li `source.trim()` prázdný: `<p class="faint" data-test="md-empty">{{ empty ?? '—' }}</p>` (záložky lze schovat).
- `mode==='preview'`: `<div class="md" data-test="md-preview" v-html="html" />` (globální styly `.md` v `style.css` už existují).
- `mode==='source'`: `<pre class="md-source" data-test="md-source">{{ source }}</pre>` (white-space pre-wrap, mono).
- Stav záložky se při změně `source` neresetuje není nutné; ale doporučeno: `watch(() => props.source, …)` NE — nechat jednoduché. (ReviewDetail/TaskDetail jsou při změně tasku znovu vykreslené, viz níže `:key`.)

Styly záložek dát do `style.css` (globálně, sekce „Markdown view tabs": `.md-tabs`, `.md-tabs button`, `.md-tabs button.active`, `.md-source`) nebo scoped — obojí OK; zadání zmiňuje `style.css`, takže preferovat globální. Vzhled v duchu stávajících `.btn` (border `var(--border)`, `var(--panel-2)`, aktivní `color: var(--text)` + spodní border `var(--blue)`/`var(--purple)`).

### 5. `components/ui/MarkdownView.test.ts` (nový)

- mount se `source: '## Zadání\n\nText <!-- c -->\n'` → existuje `[data-test="md-preview"]`, obsahuje `h2` s textem „Zadání", neexistuje `md-source`, text neobsahuje „c" komentáře (použij unikátní slovo, např. `skryté`); tab preview má `aria-selected="true"`.
- klik na `md-tab-source` → `md-source` text obsahuje `## Zadání` i `<!-- skryté -->`, `md-preview` zmizí; klik zpět na preview → vrátí se.
- prázdný source → `md-empty` s „—".

### 6. `components/review/ReviewDetail.vue`

- `open` reactive: všechny klíče `false`, odstranit klíč `actions`. Přidat funkci `collapseAll()` a `watch(() => props.detail.task_id, collapseAll)` (bez `immediate` — výchozí je už sbalené). Tichá obnova stejného PR nemění `task_id`, takže stav zůstane.
- Akce: odstranit `<DetailSection title="Akce">` obal; `ReviewActions` vykreslit přímo pod `<header>` v `<div class="actions-bar" data-test="actions">` (volitelně nadpis `<h3>Akce</h3>` jako statický text, ne tlačítko). Musí být nad všemi `DetailSection`.
- Popis PR: `<MarkdownView :source="detail.pr.body ?? ''" data-test="pr-body" />` místo `<pre class="body">`; odstranit nepoužitý `.body` styl.
- Diff: `<DiffView v-if="detail.diff" :key="detail.task_id" :diff="detail.diff" />` (klíč zaručí reset stavu souborů při změně PR i kdyby Diff zůstal otevřený — což nezůstane, ale je to pojistka).

### 7. `components/review/DiffView.vue`

Nahradit `closed` mapou `open = reactive<Record<string, boolean>>({})`; `:open="!!open[f.path]"`, `@toggle="open[f.path] = !open[f.path]"`. Soubory tedy začínají sbalené. Přidat na `DetailSection` souboru atribut `data-test="diff-file-section"` a `:data-path="f.path"` (fallthrough na `<section>`), aby testy a e2e mohly soubor najít i sbalený.

### 8. `components/runs/DetailSection.vue`

Funkčně beze změny. Volitelně přidat `:aria-expanded="open"` na `button.dsec-head` a `data-test="section-toggle"` (usnadní testy). Nesmí přibýt `title` atribut. Pozor: DetailSection používá i detail běhu (PhaseDetail/RunDetail) — změna nesmí měnit jejich chování (detail běhu je out of scope).

### 9. `components/review/ReviewActions.vue`

Obsah beze změny; jen ověřit, že funguje bez obalu (žádné závislosti na DetailSection). Případně přidat do `.actions` spodní oddělení (`margin-bottom: 18px; padding-bottom: 14px; border-bottom: 1px solid var(--border-soft)`) — nebo to udělat v `ReviewDetail` na `.actions-bar`.

### 10. `components/backlog/TaskDetail.vue`

Sekce Zadání: `<pre class="body" data-test="body">…</pre>` → `<MarkdownView :source="detail.body" data-test="body" />`. Odstranit nepoužitý `.body` styl (ř. ~404). Pozor, `TaskForm` má vlastní `textarea[data-test="body"]` — to se nemění.

### 11. Unit testy — úpravy existujících

- `ReviewDetail.test.ts`:
  - Pomocná funkce `async function openSection(wrapper, title)` — najde `button.dsec-head` s textem obsahujícím `title` a klikne.
  - Nový test „sections start collapsed": po mountu `wrapper.findAll('.dsec-body')` má délku 0, `[data-test="pr-body"]`, `[data-test="run-link"]`, `[data-test="check"]`, `[data-test="verdict-state"]`, `[data-test="diff-stat"]` neexistují; `[data-test="approve"]` a `[data-test="return-note"]` existují (akce vidět); `[data-test="actions"]` je v DOM před první `.dsec` (porovnat pořadí např. přes `wrapper.html().indexOf`).
  - Nový test „collapses again on PR change": otevřít Popis PR a Diff (+ jeden soubor), `await wrapper.setProps({ detail: reviewDetail({ task_id: 'T-other' }) })` (ověř tvar fixture v `test/reviewFixtures.ts`; `reviewDetail(overrides)` už bere přepisy), pak `.dsec-body` délka 0. Plus kontrola, že `setProps` se stejným `task_id` (nový objekt, např. jiné `cost`) nechá otevřenou sekci otevřenou.
  - Stávající test „shows the body, runs…": nejdřív otevřít všechny sekce (Popis PR, Běhy, Gates a testy, Verdikt revieweru, Diff) a oba soubory diffu; `pr-body` teď vykresluje náhled → očekávat `wrapper.find('[data-test="pr-body"] h2').text()).toBe('Zadání')` místo `toContain('## Zadání')`.
  - „handles no checks and no verdict": otevřít Gates a testy a Verdikt revieweru před aserty.
  - „forwards actions": beze změny (akce jsou vidět).
- `DiffView.test.ts`: files začínají sbalené → test ověří `[data-test="diff-file"]` délku 0 a `[data-test="diff-file-section"]` délku 2 s `data-path` `['specs/x.md','img/logo.png']`; pak klik na oba `.dsec-head` a stávající aserty. Truncated test: otevřít soubor před asertem.
- `TaskDetail.test.ts` ř. 26: `[data-test="body"]` teď obsahuje náhled; `text()` stále obsahuje „Načíst backlog." — ověřit, případně přidat `find('[data-test="body"] h2').text() === 'Zadání'`.
- Spustit `noNativeUi.test.ts` (součást vitest) — nové `.vue` soubory nesmí mít `title=` mimo `<DetailSection`.

### 12. `aifactory/tests/e2e/test_f3_browser.py` — `_approve`

Po `row.click()` a před klikem na Schválit přidat ověření, že detail je sbalený a schvaluje se bez otevírání sekcí:
```python
expect(page.locator('[data-test="actions"]')).to_be_visible(timeout=SERVER_TIMEOUT_MS)
expect(page.locator(".dsec-body")).to_have_count(0)
expect(page.locator('[data-test="pr-body"]')).to_have_count(0)
```
(Žádné klikání na `.dsec-head`.) Zbytek beze změny. Projít `ruff check` a `ruff format --check`.

### 13. Build frontendu

`just web-build` (vite s `emptyOutDir: true` přepíše `aifactory/src/aifactory/web/static/`; staré hashované `assets/index-*.js|css` zmizí, nové vzniknou). Výsledek nechat v pracovním stromu (smazané i nové soubory). Nespouštět `bun add`; `bun install --frozen-lockfile` nesmí měnit lockfile.

### 14. `app_docs/HAIFA-S01-T04-sbalene-sekce-review-a-markdown-s-nahled.md`

Krátce česky: co se změnilo (sbalení, akce mimo sekce, MarkdownView, renderer a jeho bezpečnostní model, vynechání komentářů), odkaz na rozhodnutí „Výchozí sbalení" v `docs/decisions.md`, seznam souborů, jak testovat.

## Ověření

Z kořene worktree:
1. `just web-test` (vue-tsc + vitest) — nové i upravené testy zelené, včetně `noNativeUi`.
2. `just web-build` — build do `aifactory/src/aifactory/web/static/`.
3. `just test`, `just typecheck`, `just lint`, `just e2e` — vše exit 0 (`just test` už spouští web-test).
4. `git status` — změny jen v povolených cestách; `vendor/`, `prototype/`, `docs/`, `aifactory/web/package.json` a `bun.lock` beze změny.
5. Ruční kontrola (volitelně `just dash`): otevřít PR → vše sbalené, akce nahoře; otevřít Diff a soubor; přepnout na jiný PR → sbaleno; Popis PR a Zadání tasku ukazují náhled, záložka Zdroj ukáže surový markdown včetně `<!-- -->`.
