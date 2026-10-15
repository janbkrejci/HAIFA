# HAIFA-REFINEMENT-T27 — Úpravy stránky Factory (Vybavení továrny, čip konfigurace, nálezy)

Záložka **Factory** v dashboardu dostala pět úprav z praxe. Agenti jsou nově uvedení jen jednou, v sekci **Vybavení továrny**, a každou hodnotu jde přepsat i vrátit na zděděnou. Commit konfigurace se otevírá z horní lišty. Necommitnutá konfigurace dává v kontrole jeden souhrnný nález. Panel řešení nálezů se otevírá přímo u nálezů.

## Co se změnilo

### 1. Hláška o dědění z knihovny
`RepoItems.vue` dřív lepil celý SHA knihovny k textu bez mezery. Nově se zobrazí věta `Bez vlastní kopie v .factory/ se položka dědí z knihovny „<název>“ (<krátký hash>).` Bez knihovny se zobrazí `… dědí z vestavěné výchozí sady.` Název knihovny přidává endpoint `GET /api/repos/<id>/factory/items` jako nové pole `library_name`. Hodnotu čte `_library_name()` v `web/factory.py` přes `library.store.read_meta`. Když metadata nejdou přečíst, je pole `None` a UI místo názvu napíše „knihovna“.

### 2. Čip „Necommitnutá konfigurace“ místo tlačítek
- Tlačítka a odkazy „Commitnout konfiguraci“ jsou pryč z těchto míst:
  - v `FactoryView.vue` z akcí i z „Co dál“ (z „Co dál“ zbyla jen textová nápověda),
  - v `RosterEditor.vue` z hlášky „Uloženo“,
  - z textu v `RepoSettings.vue`,
  - z textu v `FactoryFindingRepair.vue`.
- Z `RepoScreen.vue` zmizel i pruh konfigurace v těle stránky.
- `App.vue` zobrazuje v horní liště druhý `UncommittedBanner` s `kind="config"`, a to za stejné podmínky jako čip backlogu (`showBacklogChip`). Data bere z `useConfigStatus()`.
- `UncommittedBanner.vue` má dvě nové props:
  - `chipText` je vlastní text čipu,
  - `panel` je ve výchozím stavu `true`. Při `panel=false` klik na čip neotevře panel, ale rovnou vyšle `commit`, a seznam souborů je v tooltipu.
- Na commit vede `openConfigCommit()` (nově v `lib/factory.ts`, přesunuto z `RepoScreen.vue`). Funkce otevře `#/r/<repo>/factory/config_commit`. Když je tato adresa už otevřená, vyšle událost `factory-commit-preview`.

### 3. „Položky repa“ → „Vybavení továrny“
- `RepoItems.vue` je nově sekce **Vybavení továrny**:
  - Každý typ položky má nadpis s počtem.
  - Workflow, skilly a rozšíření pi jsou karty.
  - Na místě agentů je vložený `RosterEditor`, takže samostatný seznam „Definice agentů“ ve `FactoryView.vue` zmizel.
  - Sekce se zobrazuje jen při nainstalované factory (`report.state !== 'none'`).
- `RosterEditor.vue` ukazuje každého agenta jednou: harness, model, thinking a původ (`vlastní kopie` / `z knihovny`). U knihovního agenta je u každé hodnoty štítek `zděděno`, nebo `přepsáno`. U štítku `přepsáno` ukáže tooltip zděděnou hodnotu.
  - **Upravit** přepne řádek do editace.
  - **Vrátit na zděděné** pošle `reset`.
  - **Přesunout do knihovny** (jen u vlastní kopie) vyšle `move` a sekce otevře plán přesunu.
  - Náhled změny (dry run s diffem) se zobrazí pod řádkem agenta. **Uložit** zapíše změnu do pracovního stromu a obnoví stav konfigurace, takže se objeví čip.
  - Tlačítka presetů pro všechny agenty a volba „Podle výchozích“ v selectech z UI zmizely.
- Backend v `config/roster.py`:
  - `roster(..., reset=(...))` odebere z `.factory/agents.yaml` přepisy `harness` (včetně starého `coding_agent`), `model` a `thinking`. Když u knihovního agenta zbyde v záznamu jen `name`, odebere i celý záznam.
  - `reset` nejde kombinovat s presetem ani s hodnotami. Neznámé pole nebo neznámý agent je chyba `ConfigError`.
  - Zápis (atomický, přes tempfile) je vyčleněný do `_finish()`.
  - `inherited_bindings(root)` vrací pro každého agenta `overridden` (pole, která přepisuje `agents.yaml`) a `inherited` (hodnoty bez přepisů; u vlastní kopie `None`).
- `GET /api/repos/<id>/factory/roster` přidává ke každému agentovi `overridden` a `inherited`. `POST` přijímá `reset: ["harness"|"model"|"thinking", ...]`, jiná hodnota je `usage_error` (`parse_roster_body`).
- Typy `RosterField`, `RosterBindingValues` a `RosterChange.reset` jsou v `lib/api.ts`.

### 4. Jeden souhrnný nález `config_uncommitted`
Pravidlo `config` v `check/repo_rules.py` vrací pro necommitnutou konfiguraci jediný warning místo jednoho na soubor. Text skládá nová funkce `change_summary()` v `config/status.py`, kterou exportuje `aifactory.config`. Text uvádí počet souborů, base a krátký SHA a vyjmenuje cesty se stavem. `change_warnings()` zůstává.

### 5. Řešení nálezů u nálezů
Ve `FactoryView.vue` se `FactoryFindingRepair` vykresluje hned pod tlačítkem **Vyřešit vybrané nálezy**, před skupinami nálezů, a po otevření se do něj stránka posune (`scrollIntoView`, `block: 'nearest'`). Dřív byl panel až pod sekcemi stránky. Panel nově vypisuje řešené nálezy (`data-test="repair-findings"`).

## Průvodce
Texty v průvodci jsou upravené podle nového UI: `03-prvni-spusteni.md`, `04-dashboard.md`, `08-konfigurace-repa.md` (popis sekce Vybavení továrny, čipu a souhrnného nálezu) a `12-tym.md` (Upravit / Vrátit na zděděné). Statický frontend v `web/static` je přebuildovaný.

## Ověření
- Python:
  ```
  cd aifactory && uv run pytest -n0 tests/config/test_config_roster.py tests/config/test_config_status.py tests/check/test_factory_check.py tests/web/test_web_factory.py tests/web/test_web_factory_roster.py
  ```
  Nové testy: `test_several_uncommitted_files_give_one_finding`, `test_reset_returns_an_inherited_agent_to_the_library`, `test_invalid_reset_is_a_config_error`, `test_inherited_bindings_list_overrides_and_library_values`, `test_summary_lists_every_change_once`, `test_roster_reset_returns_an_override_to_the_inherited_value`.
- Frontend: `just web-test`. Testy pokrývají `RepoItems`, `RosterEditor`, `UncommittedBanner`, `App`, `RepoScreen` a `FactoryView`. Browser test `tests/e2e/test_workflow_advice_browser.py` je upravený.
- Ručně v dashboardu:
  1. Změň soubor v `.factory/`. V horní liště se objeví červený čip „Necommitnutá konfigurace · N“ a klik na něj otevře náhled commitu.
  2. V kontrole je jen jeden nález `config_uncommitted`.
  3. Ve Vybavení továrny agenta přepiš a pak ho vrať na zděděné. Pokaždé ověř diff `.factory/agents.yaml`.
