# HAIFA-REFINEMENT-T27: Factory – úpravy stránky Factory (Vybavení továrny, chip konfigurace, nálezy)

## Cíl

Pět úprav stránky Factory v dashboardu:

1. Opravit hlášku o dědění z knihovny: chybí mezera a ukazuje se celý SHA.
2. Nahradit tlačítka a odkazy „Commitnout konfiguraci“ červeným chipem v topbaru.
3. Přejmenovat „Položky repa“ na „Vybavení továrny“ a sloučit do ní roster agentů. Každý agent bude uveden jen jednou, s harnessem, modelem a thinking levelem, u kterých jde hodnotu přepsat nebo vrátit na zděděnou.
4. `config_uncommitted` bude jeden souhrnný nález, ne jeden na soubor.
5. Řešení nálezu se zobrazí hned u nálezů.

Cesty jsou relativní k `aifactory/`, pokud není uvedeno jinak. Commituje workflow, builder necommituje.

---

## 1. Hláška o dědění z knihovny (RepoItems.vue + `GET factory/items`)

**Příčina chybějící mezery:** v šabloně je `<template v-if="library"> {{ library }}</template>`. Vue v režimu `condense` zahodí textový uzel, který obsahuje jen mezeru a je prvním potomkem `<template>`. Hodnota je `cfg.library`, tedy celý commit SHA.

### Backend: `src/aifactory/web/factory.py::items`
- Přidat do odpovědi `library_name: str | None`, tedy název knihovny z její metadat. Když `cfg.library` není None, použít `read_meta(library_root(), cfg.library).get("name")` (`aifactory.library.store`: `read_meta(root, commit)`, `library_root(environ=None)`). Celé volání obalit `try/except Exception` → `None`, aby nečitelná knihovna nerozbila výpis. Pro seed (`cfg.library is None`) vracet `None`.
- Docstring doplnit o `library_name`. Upravit i docstring modulu `web/app.py` (řádek ~105), pokud tam jsou popsaná pole `factory/items`.
- `web/src/lib/api.ts`: typ `fetchFactoryItems` rozšířit na `{ library: string | null; library_name?: string | null; items: FactoryRepoItem[] }`.

### Frontend
Text sestavit v `computed` (`inheritText`), ne mezerou v šabloně:
- s knihovnou: `Bez vlastní kopie v .factory/ se položka dědí z knihovny „<library_name ?? 'knihovna'>“ (<shortSha(library)>).`
- bez knihovny (seed): `Bez vlastní kopie v .factory/ se položka dědí z vestavěné výchozí sady.`

Pro zkrácený hash použít `shortSha` z `@/lib/format` (výchozí délka 7). Plný 40znakový SHA se nikde nezobrazuje.

---

## 2. Chip „Necommitnutá konfigurace“ v topbaru

### `web/src/components/UncommittedBanner.vue`
Komponenta dostane dvě volitelné props. Výchozí chování chipu backlogu se nemění.
- `chipText?: string`: text chipu bez počtu souborů. Výchozí je dnešní `Necommitnutý ${title.toLocaleLowerCase('cs')}`. Konfigurace pošle `Necommitnutá konfigurace`, aby seděl rod.
- `panel?: boolean` (výchozí `true`). Při `false` klik na chip rovnou vyvolá `emit('commit')` a panel se neotevře. Chip pak dostane `title` se seznamem souborů (`change.path` oddělené `\n`), `aria-expanded` vynechat a `aria-haspopup` nedávat.

Styl je stejný jako u chipu backlogu, tedy třídy `.chip-wrap` a `.chip`. Hlavičkový komentář komponenty upravit, protože konfigurace už nemá banner, ale chip, který otevře commit na stránce Factory.

### Sdílená navigace na commit konfigurace
Funkci `commitConfig()` přesunout z `RepoScreen.vue` do `web/src/lib/factory.ts` jako `export function openConfigCommit(repoId: string): void`. Logika zůstává stejná: když už je hash `repoHref(id,'factory','config_commit')`, vyvolá `window.dispatchEvent(new Event('factory-commit-preview'))`, jinak nastaví `window.location.hash`.

### `web/src/App.vue`
Vedle chipu backlogu (`v-if="showBacklogChip"`) přidat:
```vue
<UncommittedBanner v-if="showBacklogChip" kind="config" title="Konfigurace" chip-text="Necommitnutá konfigurace"
  commit-label="Commitnout konfiguraci" chip :panel="false" :status="configStatus.status.value"
  @commit="openConfigCommit(repoId ?? '')" />
```
Zdrojem stavu je `const configStatus = useConfigStatus()` (z `@/lib/configStatus`, bez argumentu, tedy repo z URL). Stav dál obnovuje `RepoScreen.vue` (`refreshConfig`) a zápisy ho obnovují přes `useConfigStatus().refresh()`. Chip se zobrazí, jen když `status && !status.clean`, o to se postará logika `dirty` v komponentě.

### `web/src/components/RepoScreen.vue`
- Odstranit `<UncommittedBanner kind="config" …>` a funkci `commitConfig`. Import `UncommittedBanner` odebrat, pokud už není potřeba. Obnovování `configStatus` (watch route, live, focus) zůstává.
- Hlavičkový komentář upravit (už žádný banner konfigurace).

### Odstranit „Commitnout konfiguraci“ ze stránky Factory
- `views/FactoryView.vue`:
  - Odebrat tlačítko `data-test="factory-open-config_commit"` z `.actions`.
  - V „Co dál“ odebrat tlačítko `next-commit`. Text položky nahradit textem bez tlačítka a odkazu: `Commitni konfiguraci červeným čipem „Necommitnutá konfigurace“ v horní liště, běhy čtou jen commitnutou base.`
  - Ponechat `openConfig`, watch na parametr `config_commit` a listener `factory-commit-preview`, protože přes ně chip otevírá `FactoryOperation` s `config_commit`.
- `components/factory/RosterEditor.vue`: odkaz `roster-commit` po uložení nahradit textem `Uloženo. Běhy použijí změnu až po commitu konfigurace (červený čip v horní liště).`. Emit `commit` odstranit.
- `components/factory/RepoSettings.vue` (řádek 74): `(Commitnout konfiguraci nahoře)` → `(červený čip „Necommitnutá konfigurace“ v horní liště)`.
- `components/factory/FactoryFindingRepair.vue` (řádek 128) obsahuje odkaz „stránce Factory“, ne text „Commitnout konfiguraci“. Změnit na `Nové nebo upravené workflow nejprve commitni čipem „Necommitnutá konfigurace“ v horní liště.` (bez odkazu).

Mimo stránku Factory zůstávají beze změny: `RunDialog.vue`, `readiness.ts`, `gettingStarted.ts` a `overview.ts`, tedy odkazy na `…/factory/config_commit` z jiných obrazovek.

---

## 3. „Vybavení továrny“: jeden seznam agentů s přepisem a návratem na zděděnou hodnotu

### 3a. Backend: zděděné a přepsané hodnoty v rosteru
`src/aifactory/web/factory.py::roster` vrací u každého agenta navíc:
- `overridden: list[str]`: podmnožina `["harness","model","thinking"]`, kterou nastavuje záznam agenta v `.factory/agents.yaml` pracovního stromu. Klíč `coding_agent` se počítá jako `harness`. Načíst raw `agents.yaml` přes `yamlload.safe_load` (chybějící nebo prázdný soubor znamená žádné přepisy).
- `inherited: {harness, model, thinking} | null`: efektivní hodnoty bez přepisů tohoto agenta. Platí jen pro `origin == "library"`, u vlastní kopie je `null`. Spočítat jedním voláním: z raw dat odstranit klíče `harness/coding_agent/model/thinking` ze všech záznamů, které mají jméno knihovního agenta, výsledek serializovat (`yaml.safe_dump`) a předat helperu z `config/roster.py`. Do `config/roster.py` přidat veřejnou funkci `inherited_bindings(root: Path) -> dict[str, dict[str, str]]`, která použije `_effective` a vrátí `{name: {harness, model, thinking}}` pro knihovní agenty. Roster `defaults` se zachovají, protože jsou to výchozí hodnoty projektu, nad kterými stojí přepis agenta. Když `_effective` selže (`ValueError`), vrátit `{}`, aby výpis rosteru nespadl. Raw `overridden` lze spočítat ve stejné funkci; výsledkem pak bude `dict[name, {"overridden": [...], "inherited": {...}|None}]`.

### 3b. Backend: návrat na zděděnou hodnotu (`reset`)
`src/aifactory/config/roster.py::roster` dostane nový keyword `reset: tuple[str, ...] = ()`. CLI se nemění: `cli.py` je mimo povolené cesty a parametr má výchozí hodnotu.
- Validace: `reset` vyžaduje `agent`. Nesmí se kombinovat s `preset`, `harness`, `model` ani `thinking`. Prvky musí být z `{"harness","model","thinking"}`. Jinak `ValueError` (→ `ConfigError`, HTTP 422).
- Když agent nemá záznam v `agents.yaml` nebo záznam nemá žádné z resetovaných polí, nic se nemění (`changed: false`, prázdný diff).
- Úprava textu: `aifactory.config.yamledit.edit_yaml(text, change)` s `roster_set(doc, agent, {k: None ...})`. Pro `harness` odstranit i `coding_agent`. Pokud po úpravě záznam obsahuje jen `name` a agent je knihovní (`origin == "library"` v `before`), celý záznam odstranit přes `roster_remove(doc, agent)`. Komentáře zachová ruamel (`comments_preserved: True`).
- Dál pokračovat stejně jako dnes: `after = _effective(root, rendered)`, diff, `dry_run` a atomický zápis. Nejčistší je zápis a výpočet výsledku vytáhnout do lokální funkce `_finish(root, path, original, rendered, before, dry_run, preserved)` a použít ji pro set i reset.

`src/aifactory/web/factory.py`:
- `ROSTER_KEYS` rozšířit o `"reset"`. `RosterChange.reset: tuple[str, ...] = ()`.
- `parse_roster_body`: `reset` musí být seznam řetězců, jinak `UsageError("reset must be a list of strings")`. Prvky mimo `harness/model/thinking` znamenají `UsageError`.
- `roster_change` předá `reset=change.reset`.
- Docstring modulu `web/app.py` (řádky ~107–110) doplnit o `reset` a o pole `overridden` a `inherited`.

`web/src/lib/api.ts`:
- `FactoryRosterAgent` rozšířit o `overridden?: ('harness'|'model'|'thinking')[]` a `inherited?: RosterBindingValues | null`, kde nový typ je `{ harness: string; model: string; thinking: string }`.
- `RosterChange` rozšířit o `reset?: ('harness'|'model'|'thinking')[]`.

### 3c. Frontend: sekce „Vybavení továrny“
**`components/factory/RepoItems.vue`** se stane sekcí „Vybavení továrny“ (`<h2>Vybavení továrny</h2>`, `data-test="repo-items"` zůstává kvůli e2e):
- Úvodní hláška podle bodu 1.
- Podsekce podle `ITEM_TABS`, v nadpisu počet položek, například `Agenti (8)`.
  - **Agenti:** místo prostého `<ul>` vložit `<RosterEditor ref="roster" :repo-id :disabled="disabled || working || !!moving" :movable="…" @move="name => preview(agentItem(name))" @busy="…" @saved="emit('success')" />`. Agenti se tak vypisují jen jednou. `RosterEditor` u agenta s `origin === 'repo'` ukáže tlačítko `Přesunout do knihovny` s `data-test="item-move-agent-<name>"`, aby zůstala kompatibilita s testy přesunu. Kliknutí emituje `move`. Po úspěšném přesunu (`apply`) zavolat i `roster.value?.reload()`.
  - **Workflow, Skilly, Rozšíření:** položky zobrazit jako mřížku karet (`display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr))`). Každá karta má název (`.mono`), štítek původu (`z knihovny` / `vlastní kopie`) a případně tlačítko `Přesunout do knihovny`. `data-test` zachovat (`item-<type>-<name>`, `item-move-<type>-<name>`).
  - Prázdná podsekce: `Bez položek`.
- `defineExpose({ reload })`: `reload` načte položky i roster (`roster.value?.reload()`).
- Emit `busy` = přesun položky nebo busy stav rosteru (`moving || rosterBusy`), aby `FactoryView` při editaci zablokovala ostatní akce jako dnes.

**`components/factory/RosterEditor.vue`** se stane tabulkou agentů uvnitř „Vybavení továrny“:
- Odstranit prop `readonly`, nadpis `<h2>` (nadpis dodá RepoItems jako `<h3>Agenti</h3>`), presety (blok `.presets`, `previewPreset` a import `PRESET_LABELS`, pokud už není použit) a emit `commit`. Nové props: `repoId`, `disabled?`. Nové emity: `busy`, `saved`, `move: [name: string]`.
- Tabulka `data-test="roster-agents"` má sloupce Agent | Harness | Model | Přemýšlení | (akce).
  - Sloupec Agent obsahuje jméno, štítek původu (`z knihovny`, `data-test="roster-origin"`, nebo `vlastní kopie`) a `purpose` jako `<small>`.
  - Každá buňka hodnoty v režimu zobrazení obsahuje hodnotu a štítek: `přepsáno` (`data-test="roster-overridden-<field>"`, zvýrazněný, s `title="Zděděno: <inherited[field]>"`), nebo `zděděno` (`data-test="roster-inherited-<field>"`, tlumený). U vlastní kopie (`inherited == null`) se štítek u hodnot nezobrazuje.
  - Akce v režimu zobrazení:
    - `Upravit` (`data-test="roster-edit"`) přepne řádek do editace. Editovat lze vždy jen jeden řádek (`editing = ref<string|null>`).
    - `Vrátit na zděděné` (`data-test="roster-reset"`) se zobrazí, jen když `overridden.length && inherited`. Spustí `preview({ agent, reset: overridden }, 'Agent X: návrat na zděděné hodnoty')`.
    - `Přesunout do knihovny` (`data-test="item-move-agent-<name>"`) jen pro `origin === 'repo'`.
  - Režim editace použije dnešní ovládací prvky (`SelectMenu` pro harness a thinking, `input` s `datalist` pro model, `data-test` `roster-harness`/`roster-model`/`roster-thinking`) a tlačítka `Náhled změny` (`roster-preview`) a `Zrušit` (`roster-cancel`). Validace „Hodnotu nejde smazat, jen změnit.“ zůstává (`rowBlank`), k návratu slouží reset.
  - Volba `Podle výchozích` (`value: ''`) se v SelectMenu už nenabízí, protože prázdnou hodnotu nejde uložit. Nahrazuje ji reset.
- Panel náhledu `roster-pending` (diff + `Uložit`/`Zrušit`) se vykreslí jako řádek tabulky hned pod upravovaným agentem (`<tr v-if="pending?.agent === agent.name"><td colspan="5">…</td></tr>`), ne až pod tabulkou. Po uložení: `load()`, `editing = null`, hláška `roster-saved` z bodu 2 a `emit('saved')`. Po uložení se obnoví i stav konfigurace: `useConfigStatus().refresh()`, aby se hned objevil chip (a `window.dispatchEvent(new Event('factory-applied'))` není nutný).
- Tabulka „Přepisy na krocích workflow“ zůstává pod agenty (`<h4>`, `data-test="roster-overrides"` / `roster-no-overrides`).

**`views/FactoryView.vue`**:
- Odstranit samostatný blok `<div ref="rosterSection"><RosterEditor readonly …/></div>` a import `RosterEditor`.
- `rosterSection` přesunout na wrapper `RepoItems`. `showRoster` (tlačítko „Harnessy a modely“ v Co dál) pak scrolluje na „Vybavení továrny“. Text tlačítka změnit na `Vybavení továrny`.
- `RepoItems` zobrazit jen pro `report && report.state !== 'none'`, jako dnes roster. `@busy` dál nastavuje `itemsBusy`, `rosterBusy` odstranit, protože se sloučil do `itemsBusy`.
- Upravit hlavičkový komentář: roster je součástí Vybavení továrny.

---

## 4. Jeden souhrnný nález `config_uncommitted`

- `src/aifactory/config/status.py`: přidat
  ```python
  def change_summary(changes: list[ConfigChange], base: str, sha: str) -> str:
      """One warning for all changes: how many, where runs read from, and each path."""
  ```
  Formát: `"{n} file(s) of .factory/ changed in the working tree but not committed to {base} ({sha[:7]}); runs use the committed version: {path} ({status}), …"`. Pro jeden soubor `1 file`. `change_warnings` ponechat beze změny, používá ho CLI a `web/settings.py`. Novou funkci exportovat v `config/__init__.py` (`__all__`).
- `src/aifactory/check/repo_rules.py::config`: místo smyčky přes `change_warnings` vrátit jeden `Finding("config_uncommitted", "repo", "warning", change_summary(list(changes), ctx.base, ctx.commit), f"commit the change to {ctx.base}, or discard it", "config_commit")`, když `changes` není prázdné.
- Testy:
  - `tests/check/test_factory_check.py`: nový test se dvěma necommitnutými soubory (například upravený prompt a nový workflow) ověří, že `config_uncommitted` je v reportu právě jednou a jeho zpráva obsahuje obě cesty. Stávající testy (řádky 125–145, 400) musí dál projít.
  - `tests/config/test_config_status.py`: test `change_summary` pro jeden a dva soubory.
- Frontend nemusí nic měnit, sekce nálezů nálezy jen vypisuje. Příručka `15-reseni-problemu.md` řádek 57 platí dál.

---

## 5. Řešení nálezu u nálezů (`FactoryView.vue`)

- `<FactoryFindingRepair v-if="repair" …>` přesunout z konce stránky hned pod lištu `.repair-actions` (tlačítko „Vyřešit vybrané nálezy“), tedy nad skupiny nálezů, kterých se týká, uvnitř `<template v-if="report">`. Obalit ho `<div ref="repairSection">`.
- `openRepair()` po nastavení `repair` zavolá `await nextTick(); repairSection.value?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })`.
- V `FactoryFindingRepair.vue` přidat nad formulář seznam řešených nálezů (`<ul data-test="repair-findings">` s `code` a `message`), aby byl průběh vidět i se souvislostí. Výsledek běhu (RunDialog) zůstává uvnitř komponenty, takže je vidět na stejném místě.

---

## Průvodce (`src/aifactory/guide/`)

Texty upravit podle nového UI:
- `04-dashboard.md`:
  - řádek 23 → `**Konfigurace v .factory/ má necommitnuté změny:** v horní liště se ukáže červený čip **Necommitnutá konfigurace** s počtem souborů. Klik na čip otevře na záložce Factory náhled commitu konfigurace; běhy do té doby používají konfiguraci z base.` (Pokud je řádek v seznamu „bannerů“, upravit i úvod seznamu.)
  - řádek 53: „roster agentů … a položky repa“ → „nálezy kontroly, **Nastavení repozitáře** … a **Vybavení továrny** (agenti s harnessem, modelem a přemýšlením, workflow, skilly a rozšíření)“.
- `03-prvni-spusteni.md`:
  - řádek 51: tlačítka záložky jsou jen **Nainstalovat factory** a **Stáhnout konfiguraci z base**, konfiguraci commitne čip **Necommitnutá konfigurace** v horní liště.
  - řádek 23 (tabulka readiness) zůstává.
- `08-konfigurace-repa.md`:
  - řádek 27: „pruh **Commitnout konfiguraci** a záložka Factory“ → „červený čip **Necommitnutá konfigurace** v horní liště, který otevře náhled commitu na záložce Factory“.
  - řádek 93: „tlačítkem **Commitnout konfiguraci** na téže záložce“ → „čipem **Necommitnutá konfigurace** v horní liště“.
  - řádek 98 (Akce): odebrat **Commitnout konfiguraci** a doplnit, že commit konfigurace otevírá čip v horní liště.
  - řádek 99 (Nálezy): doplnit, že necommitnuté soubory konfigurace jsou jeden souhrnný nález `config_uncommitted` se seznamem souborů a že panel **Vyřešit vybrané nálezy** se otevře hned pod tlačítkem u nálezů.
  - řádky 100 a 102 (Definice agentů, Položky repa) nahradit jedinou položkou **Vybavení továrny**. Agenti jsou v ní uvedeni jednou s harnessem, modelem a přemýšlením a štítkem **zděděno** (z knihovny a výchozích hodnot projektu), nebo **přepsáno**. **Upravit** zapíše přepis do `.factory/agents.yaml`, **Vrátit na zděděné** přepis odstraní (náhled změny před uložením). Dále přepisy na krocích workflow a workflow, skilly a rozšíření pi jako vlastní kopie nebo z knihovny, vlastní kopii jde **Přesunout do knihovny**. Hláška uvádí knihovnu názvem a zkráceným commitem.
- `12-tym.md` kolem řádku 47: pokud popisuje úpravu rosteru jen přes CLI, doplnit větu, že totéž pro jednotlivého agenta jde v dashboardu v sekci **Vybavení továrny** na záložce Factory.
- Projít `grep -rn "Položky repa\|Definice agentů\|Commitnout konfiguraci" src/aifactory/guide`. Zmínky o záložce Factory opravit. Zmínky o odkazu v dialogu Spustit task (`06-behy.md:10`) a o stránce Problémy (`04-dashboard.md:44`) zůstávají, protože ty odkazy existují dál.

---

## Testy

### Vitest (`web/src/…`)
- `components/UncommittedBanner.test.ts`: chip s `panel=false` vyvolá klikem `commit`, neotevře panel a zobrazí `chipText`. Výchozí chip backlogu se nemění. Stávající test s `commitLabel: 'Commitnout konfiguraci'` upravit podle nové kombinace props.
- `App.test.ts`: na stránce repa se při necommitnuté konfiguraci zobrazí `[data-test="config-chip"]`, klik vede na `#/r/<id>/factory/config_commit` (případně vyvolá preview). Při čisté konfiguraci se chip nezobrazí. Upravit stávající test na řádcích ~100–115, který dnes kliká na banner.
- `components/RepoScreen.test.ts`: odstranit nebo přepsat očekávání `config-banner` v RepoScreen.
- `views/FactoryView.test.ts`:
  - na stránce není žádné tlačítko ani odkaz s textem `Commitnout konfiguraci` (`expect(wrapper.text()).not.toContain('Commitnout konfiguraci')` a absence `factory-open-config_commit` a `next-commit`);
  - `#/r/<id>/factory/config_commit` dál otevře `FactoryOperation` s `config_commit`;
  - sekce má nadpis `Vybavení továrny`;
  - po „Vyřešit vybrané nálezy“ je `[data-test="factory-repair"]` v DOM hned za `.repair-actions` a před první skupinou nálezů (porovnat pořadí přes `compareDocumentPosition`).
- `components/factory/RepoItems.test.ts`:
  - hláška obsahuje `z knihovny „team“ (aa8e980)`, když `library_name: 'team'`, a neobsahuje 40znakový SHA ani text slepený bez mezery;
  - pro seed obsahuje „vestavěné výchozí sady“;
  - agent je v sekci jen jednou: mockovat `fetchFactoryRoster` a ověřit, že `[data-test^="roster-agent-"]` je pro každé jméno právě jeden a starý `item-agent-*` `li` neexistuje;
  - přesun vlastní kopie agenta přes `item-move-agent-<name>` dál funguje.
- `components/factory/RosterEditor.test.ts`, přepsat pro nové UI:
  - zobrazí harness, model a thinking a štítky `zděděno` / `přepsáno` podle `overridden`;
  - `Upravit` → změna modelu → `Náhled změny` pošle `{agent, model, dry_run: true}` → `Uložit` pošle `dry_run: false` a obnoví roster;
  - `Vrátit na zděděné` pošle `{agent, reset: [...], dry_run: true}` a po uložení `dry_run: false`;
  - tlačítko resetu chybí u agenta bez přepisů a u vlastní kopie;
  - nezobrazuje odkaz `roster-commit` ani presety.
- `components/factory/RepoSettings.test.ts`: případný test textu „Commitnout konfiguraci nahoře“ upravit.
- `components/factory/FactoryOperation.test.ts`: zkontrolovat, že nic nečeká tlačítko `factory-open-config_commit`. Upravit, jen pokud selže.
- `lib/noNativeUi.test.ts` hlídá nativní UI. Nové prvky nesmí používat `window.confirm`/`alert` ani nativní `<select>` (použít `SelectMenu`).

### Pytest
- `tests/config/test_config_roster.py`:
  - `reset` odstraní přepsaná pole knihovního agenta. Pokud zbyde jen `name`, odstraní celý záznam. Hodnoty se vrátí na zděděné. Reset se `dry_run` nic nezapíše.
  - `reset` bez agenta nebo spolu s `model` je `ConfigError`.
  - `inherited_bindings` vrátí hodnoty bez přepisů a `overridden` správně (včetně `coding_agent` → `harness`).
- `tests/web/test_web_factory_roster.py`:
  - `GET factory/roster` obsahuje `overridden` a `inherited`;
  - `POST factory/roster` s `reset` (preview i zápis);
  - neplatné tělo s `reset` dává `usage_error` (400).
- `tests/web/test_web_factory.py` (~řádek 365): `items["library_name"]` je název knihovny z `library_status`/metadat (testovací knihovna má `name`, například `library`). U seedu je `None`.
- `tests/check/test_factory_check.py`, `tests/config/test_config_status.py`: viz bod 4.

### E2E
- `tests/e2e/test_workflow_advice_browser.py` (ř. 44–46): místo `config-banner`/`config-commit` očekávat `[data-test="config-chip"]` viditelný. Po kliknutí ověřit `page.url` končící `/factory/config_commit`.
- `tests/e2e/test_factory_move_browser.py` používá `item-move-workflow-mine`. `data-test` zůstává, test spustit.

## Ověření (podle AGENTS.md, ne celá sada)
```
just lint
just typecheck
just web-test
just pytest tests/config tests/check tests/web/test_web_factory_roster.py tests/web/test_web_factory.py tests/web/test_web_guide.py
just pytest tests/e2e/test_workflow_advice_browser.py -n0
just pytest tests/e2e/test_factory_move_browser.py -n0
just web-build   # web/static je commitnutý; přegenerovat po změnách Vue
```
Ruff formát: `cd aifactory && uv run ruff format .`, pokud lint hlásí formát.

## Akceptace (shrnutí)
- Hláška: mezera, název knihovny a zkrácený hash, žádný 40znakový SHA.
- Na stránce Factory nezůstane tlačítko ani odkaz „Commitnout konfiguraci“. Červený chip „Necommitnutá konfigurace · N souborů“ v topbaru se zobrazí jen při změnách a otevře `config_commit`.
- Sekce „Vybavení továrny“ uvádí každého agenta jednou, s harnessem, modelem, thinking a štítky zděděno/přepsáno. Přepis i reset se zapíšou do `.factory/agents.yaml` pracovního stromu (běhy ho čtou po commitu konfigurace).
- Jeden nález `config_uncommitted` pro libovolný počet souborů.
- Panel řešení nálezů je hned u tlačítka a nálezů.
- Průvodce odpovídá novému UI.
