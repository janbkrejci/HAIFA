# Obrazovka Nastavení a pruh s necommitnutou konfigurací (D4)

Dashboard má funkční obrazovku **Nastavení**. Dřív to byl jen `EmptyScreen`. Nová obrazovka upravuje sdílené `.factory/config.yaml` a lokální `.factory/local.yaml`. Na každé obrazovce se navíc ukáže varovný pruh, když má `.factory/` necommitnuté změny proti `base`. Pruh čte stejná data jako `factory config status`.

## Proč na tom záleží

Běhy čtou konfiguraci z commitu `base`, ne z pracovního stromu. Hodnota uložená přes UI proto platí až po commitu. Pruh ukazuje, které soubory ještě nejsou commitnuté. Samotný commit tlačítkem do této změny nepatří.

## Backend (`aifactory/src/aifactory/web/`)

- **`settings.py`** (nový soubor):
  - `settings_view(repo)` čte oba soubory z hlavního checkoutu. Vrací:
    - hodnoty formuláře: `shared` (`workdir`, `backlog_dir`, `specs_dir`, `docs_dir`, `worktrees_dir`, `base`, `git_provider`, `merge_strategy`, `test_command` jako řetězec přes `shlex.join`, `protected_files`) a `local` (`port`, `trace_db`),
    - povolené volby `options` pro `git_provider` a `merge_strategy` (převzaté z `ProjectSettings`),
    - problémy souborů na disku (`shared_issues`, `local_issues`),
    - `status`.

    Když je soubor na disku neplatný, formulář stejně dostane jeho surové hodnoty.
  - `save_settings(repo, body)`:
    - přijímá `{shared?: {...}, local?: {...}}` jen se změněnými klíči. `null` klíč odstraní.
    - Změny sloučí do existujícího YAML mapování, takže ostatní klíče (`levels`, `azure`, …) zůstanou.
    - Výsledek ověří přes `ProjectSettings` / `LocalSettings`. Navíc kontroluje položky `protected_files` a to, že `config.yaml` neobsahuje lokální klíče.
    - Zápis je **všechno, nebo nic**: jakákoli chyba v kterékoli sekci vyhodí `SettingsError` s jedním issue na pole (`id` = název pole) a nezapíše se nic.
    - Soubory zapisuje atomicky (tempfile + `os.replace`). Nic nestaguje ani necommituje.
    - Po uložení `local.yaml` ho přidá do `.git/info/exclude`, pokud ho git už neignoruje. Když je `local.yaml` trackovaný, vrátí varování.
  - `config_status(root)` sem byl přesunutý z `backlog.py` (tam byl jako `_config_status`). `backlog.run_check` ho teď importuje odsud.
  - Známé omezení (uvedené v docstringu): soubory se přepisují přes PyYAML, takže se ztratí komentáře.
- **`app.py`**: nové routy.
  - `GET /api/settings`
  - `POST /api/settings`. Neplatná hodnota vrací `422 invalid_value` s `error.issues`. Neznámá sekce, neznámý klíč nebo špatný tvar těla vrací `400 usage_error`.
  - `GET /api/config/status`. Když nejde načíst konfiguraci (např. neznámé `base`), vrací `500 invalid_config`.

## Frontend (`aifactory/web/src/`)

- **`lib/settings.ts`** obsahuje typy a API volání (`fetchSettings`, `saveSettings`, `fetchConfigStatus`) a pomocné funkce:
  - `formValues`: data převede na textové hodnoty formuláře,
  - `settingsDiff`: pošle jen změněná pole. Prázdný testovací příkaz se pošle jako `null`, chráněné soubory po řádcích, numerický port jako číslo,
  - `fieldErrors`: seskupí issues podle `id`. Issues bez `id` jdou pod `''`,
  - `toConfigStatus`: tolerantní parser stavu.
- **`lib/configStatus.ts`** drží jeden sdílený stav (`useConfigStatus`) pro pruh i pro obrazovku Nastavení.
- **`components/ConfigStatusBanner.vue`**: pruh s `role="alert"`. Ukazuje `base`, krátké SHA a seznam `status path`. Když se stav nedá zjistit, ukáže místo pruhu chybový řádek.
- **`App.vue`** vykresluje pruh nad `<main>`. Stav obnovuje při startu, při každé změně routy a při `focus` okna.
- **`components/settings/SettingsForm.vue`** má dvě sekce: Sdílené a Lokální.
  - Chyba se ukazuje u pole (`aria-invalid`, třída `invalid`). Chyby bez pole se ukazují dole v obecném seznamu.
  - Nahoře je varování, když je soubor na disku neplatný.
  - U `azure` se ukáže nápověda, že sekci `azure` tady editovat nejde.
  - „Uložit“ je vypnuté, dokud se nic nezměnilo. „Vrátit“ obnoví načtené hodnoty.
- **`views/SettingsView.vue`** načte data a uloží je.
  - Po úspěchu ukáže „Uloženo“, znovu připojí formulář s novými hodnotami a obnoví stav konfigurace.
  - Po `invalid_value` ponechá vstup a rozdělí chyby k polím.

## Testy

- `aifactory/tests/web/test_web_settings.py` pracuje nad dočasným git repem. Pokrývá:
  - GET s výchozími hodnotami,
  - uložení sdílených hodnot, které zachová `levels` a nic nestaguje,
  - uložení `local.yaml` mimo git, kde se exclude nepřidá dvakrát,
  - parametrizované neplatné hodnoty, po kterých soubory zůstanou beze změny,
  - atomicitu přes dvě sekce, odstranění klíče pomocí `null`, špatné požadavky (400),
  - neplatný a nečitelný soubor na disku a `config/status`, včetně neznámého `base`.
- Vitest:
  - `lib/settings.test.ts`,
  - `components/ConfigStatusBanner.test.ts`,
  - `components/settings/SettingsForm.test.ts`,
  - `views/SettingsView.test.ts`,
  - `App.test.ts`: pruh se ukazuje i po přepnutí na `#/runs`.

  Sdílené fixtures jsou v `test/settingsFixtures.ts`.
- Plán: `specs/ce6aa09c_settings-screen-config-warning.md`.

## Ověření

```sh
just test        # pytest + vitest + vue-tsc
just typecheck
just lint
```

Ručně: `just web-build && just dash`, otevřít `#/settings`, změnit `base` a uložit. Pak se na všech obrazovkách objeví pruh s `modified .factory/config.yaml`. Když uložíš port, `git status` nesmí ukázat `.factory/local.yaml`.
