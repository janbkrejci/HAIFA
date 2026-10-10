# Obrazovka Review (seznam PR, detail s diffem, Schválit / Vrátit / Vyřešit konflikt)

Session `4b27b2b8`, porovnáno proti `a8926ff`. Plán je v `specs/4b27b2b8_review-screen_v3.md`.

## Co se změnilo

Dříve byl `ReviewView.vue` jen zástupný `EmptyScreen`. Teď je z něj funkční obrazovka Review nad endpointy `/api/review*`.

**Rozsah diffu:** diff obsahuje frontend, commitnutý build a jednu opravu v `run/backup.py`. Backendový modul `aifactory/src/aifactory/web/review.py` a jeho testy (`aifactory/tests/web/test_web_review.py`) v tomto diffu **nejsou**. Frontend tedy volá API, které už existuje mimo tuto změnu.

### Seznam PR (`#/review`)
- `ReviewList.vue` dělí otevřené PR tasků do dvou sekcí: **„Čeká na mé review“** (`awaiting_review`) a **„Ostatní otevřené PR“**.
- U každého řádku jsou sloupce Task (odkaz na detail), Modul, Vlastník, Mergeabilita (`MergeabilityChip.vue`), běžící běh (odkaz), Náklady, Tokeny a PR.
- Filtr vlastníka tvoří select („Všechny moduly“ + `owners`, u `me` přípona „(já)“) a přepínač **„Jen moje moduly“**.
  - Přepínač je vypnutý, když API nevrátí `me`. V tom případě se ukáže nápověda, ať uživatel vlastníka vybere ručně.
- `ReviewView.vue` si volbu ukládá do `localStorage` pod klíčem `factory.review.owner`. Hodnota `*` znamená „všechny“.
  - Při první návštěvě (nic není uloženo) načte seznam, a pokud API vrátí `me`, načte ho znovu filtrovaný na `me`.

### Detail PR (`#/review/<task_id>`)
`ReviewDetail.vue` obsahuje:
- **Hlavičku:** vlastník, modul, `branch → base`, mergeabilita, stav PR u provideru, náklady a tokeny, odkaz na PR. U URL `local:` se zobrazí jen jako text.
- **Sekce, které jdou sbalit:**
  - Akce
  - Popis PR (`<pre>`)
  - Běhy (odkazy na obrazovku Runs, stav, cena, poznámka a chyba)
  - Gates a testy (`ChecksList.vue`)
  - Verdikt revieweru (`ReviewVerdict.vue`: schváleno/neschváleno, agent, odkaz na běh, souhrn, blokující body, findings)
  - Diff (`DiffView.vue`)
- **Diff** se zobrazuje po souborech. Každý soubor má vlastní sbalitelnou sekci se statusem (přidán/změněn/smazán/přejmenován) a počty `+/−`. Označí se binární soubory a zkrácený patch („diff zkrácen“). Řádky obarvuje `diffLines()` z `lib/review.ts` (`add`/`del`/`hunk`/`meta`/`ctx`).

### Akce (`ReviewActions.vue`)
- **Schválit:** po `window.confirm` zavolá `POST /api/review/<id>/approve`. Pod tlačítkem je trvale vidět `approve_note` z API, tedy poznámka OB3, že se v hostingu neposílá approve review. Stejný text je i v potvrzovacím dialogu. Po úspěchu se zobrazí „Sloučeno (merge <sha7>)“.
- **Vrátit s poznámkou:** textarea a tlačítko, které je aktivní jen s neprázdnou poznámkou. Volá `POST …/return` s `{ note }`.
- **Vyřešit konflikt:** při `mergeability === 'conflict'` se zobrazí banner s tlačítkem, které volá `POST …/resolve` s `{}`. Bez konfliktu, pokud to `actions.resolve` dovolí, se nabízí slabší tlačítko „Dorovnat s base“.
- **Kdy jsou tlačítka vypnutá:** během akce (`busy`), když na PR běží běh (s odkazem na něj) a podle příznaků `detail.actions.{approve,return,resolve}` z API.
- **Po odpovědi return/resolve:** `ReviewView` ukáže odkaz na nově spuštěný běh, nebo pro `pending` hlášku „Běh se spouští…“. Po každé akci znovu načte detail.
- **Chyby:** chyba API s kódem `conflict` dostane dovětek „použij Vyřešit konflikt“. `no_pr` se zobrazí jako „Task … nemá PR“.

### Pomocné části
- `lib/review.ts` obsahuje typy odpovědí API a funkce `fetchReviews(owner)`, `fetchReview`, `approvePr`, `returnPr`, `resolvePr` a `diffLines`.
- `lib/router.ts` má novou funkci `reviewHref(taskId)` → `#/review/<id>`.

### `run/backup.py` – `_write_tree` bez `index.lock`
- `git write-tree` si zamyká index. Když souběžný git příkaz ve stejném checkoutu drží `index.lock`, tak selže.
- Nově se index (cesta z `git rev-parse --git-path index`) zkopíruje do dočasného adresáře a `write-tree` běží s `GIT_INDEX_FILE` na této kopii.
- Pokud chyba přesto zmiňuje `index.lock`, zkusí se to až 20× s rostoucí pauzou. Jiná chyba vrátí `None`.

### Build
Commitnutý build v `aifactory/src/aifactory/web/static/` je přegenerovaný:
- `index.html` ukazuje na `index-Bsh5meTG.js` a `index-BQ1z43XY.css`,
- `index-BiAmb-gV.js` je smazaný,
- CSS je přejmenované.

## Soubory
- **Obrazovka:** `aifactory/web/src/views/ReviewView.vue`
- **Komponenty** (`aifactory/web/src/components/review/`): `ReviewList.vue`, `ReviewDetail.vue`, `ReviewActions.vue`, `DiffView.vue`, `ChecksList.vue`, `ReviewVerdict.vue`, `MergeabilityChip.vue`
- **Knihovny:** `aifactory/web/src/lib/review.ts`, `aifactory/web/src/lib/router.ts`
- **Testy:**
  - `views/ReviewView.test.ts`
  - `components/review/{ReviewList,ReviewDetail,ReviewActions,DiffView}.test.ts`
  - `lib/review.test.ts`, `lib/router.test.ts`
  - fixtures `src/test/reviewFixtures.ts`
- **Backend:** `aifactory/src/aifactory/run/backup.py`
- **Build:** `aifactory/src/aifactory/web/static/index.html` + `assets/`
- **Plán:** `specs/4b27b2b8_review-screen_v3.md`

## Jak ověřit
- `just test`, `just typecheck`, `just lint`. Vitest pokrývá:
  - výchozí filtr na `me` a uloženého vlastníka,
  - Schválit s confirm a notice,
  - Vrátit s poznámkou a odkazem na běh,
  - Vyřešit při konfliktu,
  - chybu akce a task bez PR,
  - blokování akcí při běžícím běhu,
  - poznámku OB3,
  - klasifikaci řádků diffu,
  - dotaz `?owner=` a těla POST požadavků.
- **Ručně:** spusť dashboard, otevři `#/review` a vyzkoušej filtr vlastníka. Pak otevři detail PR a zkontroluj diff, gates, verdikt a akce.
