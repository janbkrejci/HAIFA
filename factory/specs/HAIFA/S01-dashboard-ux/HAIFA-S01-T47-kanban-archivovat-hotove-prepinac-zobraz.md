# HAIFA-S01-T47 — Archivace karet kanbanu

## Cíl a rozsah

V kanbanu Backlogu standardně skrýt archivované tasky ve sloupcích Hotovo a Zrušeno, umožnit jejich samostatné zobrazení a ruční archivaci/obnovení hotových karet. Stav obou přepínačů si pamatuje prohlížeč; výchozí hodnota je vypnuto. Strom, graf a detail tasku zachovat funkčně beze změn, včetně dosavadního přepínače Skrýt hotové.

Implementace smí měnit jen tyto soubory a adresář:

- `aifactory/web/src/lib/backlog.ts`
- `aifactory/web/src/lib/backlog.test.ts`
- `aifactory/web/src/components/backlog/KanbanBoard.vue`
- `aifactory/web/src/components/backlog/KanbanBoard.test.ts`
- `aifactory/web/src/views/BacklogView.vue`
- `aifactory/web/src/views/BacklogView.test.ts`
- `aifactory/src/aifactory/guide/04-backlog.md`
- `aifactory/src/aifactory/web/static/`
- tento spec a výsledná dokumentace `factory/docs/HAIFA/S01-dashboard-ux/HAIFA-S01-T47-kanban-archivovat-hotove-prepinac-zobraz.md`.

Další zápisové cesty nejsou potřeba. Sdílené testovací fixtures a Python testy neměnit; nové tasky připravovat lokálně pomocí `taskNode({...})` v povolených testech.

## Ověřený základ a rozhodnutí

T46 je v aktuálním kódu přítomné: `aifactory/src/aifactory/web/backlog.py` v serializaci vrací `archived` pro zrušené tasky vždy true a pro hotové podle preference fronty. Funkce `archive` přijímá `{archived: boolean}`, dovoluje pouze hotové tasky a vrací `{task_id, archived}`. Backend ani databázi v tomto tasku neupravovat.

`KanbanBoard.vue` nyní seskupuje a řadí všechny předané tasky, počet hlavičky čte z `col.tasks.length`. `BacklogView.vue` již před předáním boardu aplikuje filtry projektu/stepu a Skrýt hotové. Archivované počítat uvnitř takto vybraného sloupce před filtrováním archivace, nikoli z globálních počtů backlogu. Sloupec ponechat přítomný i při nulovém počtu viditelných karet, aby byl přepínač dostupný.

Použít příznak `archived` z API; chybějící volitelné pole znamená false. Zrušené tasky server označuje true a board pro ně nikdy nenabízí obnovu. Preference jsou globální prohlížečové, stejně jako stávající `haifa.backlog.hideDone`, nikoli nové nastavení repozitáře.

## Postup implementace

### 1. Model, API a preference — `lib/backlog.ts`

- Přidat do `TaskNode` pole `archived?: boolean` se stručným komentářem o archivaci kanbanu.
- Vedle `setAutoExcluded` přidat `setArchived(taskId: string, archived: boolean): Promise<{task_id: string; archived: boolean}>`; použít `postApi`, `${taskPath(taskId)}/archive` a tělo `{ archived }`. `taskPath` zajistí existující URL encoding a `postApi` scope repozitáře.
- Vedle preference Skrýt hotové přidat úzce typované API pro dva sloupce: `showArchived(column: 'done' | 'cancelled')`, `setShowArchived(column, on)` a `resetShowArchivedForTests()`. Použít dva klíče `haifa.backlog.showArchived.done` a `haifa.backlog.showArchived.cancelled`, exportované např. jako `SHOW_ARCHIVED_KEYS`.
- Zachovat vzor lazy reactive cache z `hideDone`: každý sloupec se načte samostatně, pouze hodnota `'1'` znamená zapnuto, zápis používá `'1'`/`'0'`. Při nedostupném localStorage čtení vrací false a změna funguje v paměti. Nepřepisovat stávající implementaci hideDone do obecné abstrakce.
- Zapojit reset nové preference do existujícího `resetTreeForTests`, který už resetuje hideDone, a explicitně jej používat v nových testech s module cache. Jde pouze o izolaci testů.

### 2. Hlavičky, filtrování a ovládání — `KanbanBoard.vue`

- Do `defineEmits` přidat `archive: [id: string, archived: boolean]`.
- Výpočet sloupců rozšířit o počet archivovaných a stav jejich zobrazení. Jen pro done/cancelled filtrovat archivované při vypnuté preferenci; zachovat prioritySorted a výpočet readyIds.
- V hlavičce done/cancelled přidat malé ikonové tlačítko v existujícím `Tooltip`, s textem i přístupným názvem `Zobrazit archivované (N)`, `aria-pressed` a stabilním `data-test="show-archived"`. N zobrazit také přímo u ikony, aby byl počet dostupný bez hoveru. Přepínač ponechat dostupný i při N=0. Použít ikonu z existujícího lucide balíčku a stávající styl tlačítek.
- Klik přepíná jen preferenci příslušného sloupce. Změna nevolá backend. Viditelný počet zůstává `col.tasks.length`; prázdný sloupec nadále zobrazuje pomlčku.
- Zobrazené archivované karty označit třídou `archived` a ztlumit scoped CSS, např. opacity 0.6. Odkaz na detail i tlačítko Obnovit zůstanou funkční.
- Rozšířit podmínku `.tools` o hotové tasky. Pro done zobrazit ikonové tlačítko `data-test="archive-toggle"`, Tooltip a aria-label `Archivovat` nebo `Obnovit` podle příznaku. Emitovat `archive` s id a opačnou boolean hodnotou. Tlačítko má `:disabled="busy"`; nevkládat je do odkazu karty. Zrušené ani ostatní stavy toto tlačítko nedostanou.
- Zachovat stávající selektory karet, počtu, fronty a nástrojů. Styling hlavičky přizpůsobit malému prostoru bez změny rozložení ostatních sloupců.

### 3. Uložení a reload — `BacklogView.vue`

- Importovat `setArchived`, připojit `@archive="onArchive"` na KanbanBoard.
- Implementovat `onArchive(id, archived)` stejným vzorem jako ostatní zápisy fronty: pomocí `optimistic` změnit pouze `data.tasks` pro příslušné id a zavolat `queueWrite(() => setArchived(id, archived), undo)`. Úspěch použije existující `loadList`; chyba vrátí původní data a zobrazí existující `Frontu se nepodařilo uložit: …`.
- Předávané `queueBusy` již blokuje nástroje boardu během POST. Nezavádět další busy/error mechanismus, neměnit detail ani jeho handlery.
- Skrýt hotové nadále odstraní celé sloupce done/cancelled bez ohledu na archivní preference. Jeho přepnutí archivní preference nemaže.

### 4. Regresní testy v povolených třech souborech

`backlog.test.ts`:

- Výchozí false pro oba sloupce, samostatné ukládání true/false a opětovné načtení po resetu cache simulujícím refresh. Ověřit, že nastavení jednoho sloupce ani hideDone nemění ostatní preference.
- Chybějící/neplatná uložená hodnota znamená false; při vyhození výjimky storage funguje paměťový stav.
- Test `setArchived` na správnou repo URL, metodu a boolean tělo včetně false a zakódovaného id, podle existujících API testů.

`KanbanBoard.test.ts`:

- Připravit nearchivovaný done, archivovaný done, archivovaný cancelled a běžný ready task. Bez zapnutí ověřit skrytí archivovaných, ponechání ostatních karet a viditelné počty včetně prázdného cancelled.
- Ověřit přepínače pouze v done/cancelled, jejich N, aria-pressed a nezávislé zapínání/vypínání; po zapnutí ověřit třídu ztlumení a aktualizované počty.
- Klik Archivovat emituje `[id, true]`, Obnovit `[id, false]`. Cancelled tlačítko nemá. Busy deaktivuje oba typy tlačítek a zabrání emitům.
- Před/po testech vyčistit storage a novou cache, aby se nastavení nepřenášelo mezi mounty. Zachovat dosavadní testy řazení, odložení a priority.

`BacklogView.test.ts`:

- Přes skutečné ovládání boardu a stub fetch otestovat archivaci i obnovu. Assert POST `/api/repos/haifa/backlog/tasks/<id>/archive`, `{archived:true/false}`, další GET `/api/repos/haifa/backlog` a výslednou viditelnost po serverové odpovědi. Mock vrací aktualizovaný příznak; nestačí ověřit jen optimistickou změnu.
- Deferred POST ověří busy; neúspěšný POST ověří rollback, chybový text a uvolnění busy pro opakování.
- Ověřit souběh se Skrýt hotové: skryje oba sloupce i se zapnutým zobrazením archivovaných a po vypnutí obnoví uložené volby.

### 5. Příručka, dokumentace a distribuovaný build

Do sekce Strom a kanban v `guide/04-backlog.md` přidat jednu větu: „Zrušené tasky se archivují rovnou, hotové tlačítkem **Archivovat**; archivované ukáže přepínač Zobrazit archivované v záhlaví sloupce a archivace se necommituje.“ Dosavadní text zachovat a Python testy příručky neupravovat.

Do určeného dokumentačního souboru zaznamenat výsledné chování, API a prohlížečové preference i skutečně provedené ověření. Po dokončení zdrojových úprav spustit z kořene `just web-build`, který přes Vite přegeneruje distribuované soubory v povoleném static adresáři včetně odstranění starých hashovaných assetů. Soubory buildu neupravovat ručně; zachovat THIRD_PARTY_NOTICES.

## Ověření a kritéria dokončení

Před dokončením projít `rg` v `aifactory/web/src` a `aifactory/tests` pro změněné selektory/texty: `data-column`, `data-card`, `data-item`, `data-test="count"`, `show-archived`, `archive-toggle`, `Archivovat`, `Obnovit`, `Hotovo`, `Zrušeno`, `Skrýt hotové`, `.tools` a selektory hlaviček. Existující browser test dlouhých hodnot v `tests/e2e/test_f3_browser.py` očekává čtyři tools tlačítka na ready kartě; toto musí zůstat platné. Jeho dokončené nearchivované tasky mají zůstat viditelné.

Spustit z kořene repozitáře a vyhodnotit návratové kódy:

1. `just lint`
2. `just typecheck`
3. `just web-test` — celý frontend včetně tří rozšířených souborů.
4. `just pytest tests/test_guide.py tests/test_guide_consistency.py tests/web/test_web_guide.py` — existující testy obsahu a UI/CLI souladu příručky i jejího podávání.
5. `just web-build`
6. `just pytest tests/e2e/test_f3_browser.py -n0` — existující browser test soubor obrazovky Backlogu proti novému buildu.

Nepouštět celou Python sadu ani všechny e2e. Žádné testy nesmějí potřebovat živé modely či služby. Nová archivace se musí projevit po úspěšném POST a reloadu, oba přepínače přežít reset cache/obnovení, archivované karty být po zobrazení ztlumené a původní filtry a ovládání fronty dál procházet testy. Změny ponechat necommitnuté pro workflow.
