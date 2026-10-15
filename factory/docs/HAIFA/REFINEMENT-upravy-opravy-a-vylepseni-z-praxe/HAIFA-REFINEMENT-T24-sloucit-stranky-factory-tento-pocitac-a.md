# HAIFA-REFINEMENT-T24: Sloučení stránek Factory, Tento počítač, Knihovna a Nastavení

## Rozhodnutí o uspořádání

Dřív měl dashboard čtyři stránky a jejich obsah se překrýval:

| Stránka | Překryv |
|---|---|
| Factory (`#/r/<id>/factory`) | ukazovala i nálezy knihovny a nálezy počítače nezávislé na repu, které byly i na Tento počítač |
| Nastavení (`#/r/<id>/settings`) | jen polovina úkonu „změnit konfiguraci a commitnout“, commit byl na Factory |
| Tento počítač (`#/setup`) | synchronizace knihovny (byla i na Knihovně), Začínáme (bylo i v readiness a Problémech), info bez akce |
| Knihovna (`#/library`) | synchronizace knihovny (byla i na Tento počítač) |

Teď jsou **dvě stránky, každá pro jeden rozsah**. Obě vycházejí ze stránky Factory: hlavička s tlačítkem „Znovu zkontrolovat“, verdikt, jen akční nálezy a pod nimi sekce s akcemi.

1. **Factory** (`#/r/<id>/factory`) obsahuje vše o factory jednoho repa: kontrolu repa, instalaci, commit a stažení konfigurace, roster, sekci **Nastavení repozitáře** a položky repa. Nastavení patří sem, protože uložená sdílená hodnota se na téže stránce hned objeví jako `config_uncommitted` a commitne se tlačítkem **Commitnout konfiguraci**.
2. **Tento počítač** (`#/setup`) obsahuje vše o tomto počítači: kontrolu počítače, sekci **Knihovna** (knihovna leží v `$HAIFA_HOME` tohoto počítače) a nastavení dashboardu. Je to jediné místo, kde se knihovna synchronizuje.

Horní lišta (readiness chip, `#/problems`, chip knihovny) problémy jen počítá a odkazuje na jediné místo, kde se řeší. Obsah tedy neduplikuje.

## Kam se co přesunulo

| Dřív | Teď |
|---|---|
| záložka Nastavení repa (`views/SettingsView.vue`) | sekce na Factory, `components/factory/RepoSettings.vue`, adresa `#/r/<id>/factory/settings`. Zobrazí se jen s nainstalovanou factory, protože bez ní `config.yaml` neexistuje. |
| stránka Knihovna (`views/LibraryView.vue`): sync, PR, remote, reseed, import, prohlížeč, kopie rep, přesun do knihovny | sekce na Tento počítač, `components/setup/LibrarySection.vue`, adresa `#/setup/library` |
| založení nebo naklonování knihovny na Tento počítač | sekce Knihovna (formulář je tam, dokud knihovna neexistuje) |
| nálezy knihovny (na Factory i na Tento počítač) | jen v sekci Knihovna |
| nálezy počítače nezávislé na repu na Factory | jen na Tento počítač. Factory místo nich ukáže jeden řádek „Další nálezy tohoto počítače a knihovny: N“ s odkazem na Tento počítač. |
| nálezy počítače, které plynou z repa | dál na Factory ve skupině **Tento počítač: potřebné pro toto repo** |
| položka **Knihovna** v menu přepínače rep (`RepoSwitcher.vue`) | chip knihovny v horní liště a sekce Knihovna |

Factory skryje nález počítače, pokud machine check (`GET /api/machine/check`) má nález se stejným `code` a `message`. Skryje také každý nález se `scope: library`. Když se machine check nenačte, Factory nic neskryje. Verdikt a počty na Factory se počítají jen z viditelných nálezů (`FactoryView.vue`, funkce `elsewhere`).

## Přesměrování a odkazy

- `#/r/<id>/settings` přesměruje na `#/r/<id>/factory/settings` a Factory sjede na sekci Nastavení repozitáře.
- `#/library` přesměruje na `#/setup/library` a Tento počítač sjede na sekci Knihovna.
- Konstanty a helpery jsou v `lib/router.ts`: `SETUP_HREF`, `LIBRARY_HREF` a `repoSettingsHref`. Typ `Screen` už nemá `settings` a `Page` nemá `library`.
- Chip knihovny (`LibraryChip.vue`) vede v obou stavech na `#/setup/library`. Krok „Knihovna“ v `lib/gettingStarted.ts` vede tamtéž. Readiness (`lib/readiness.ts`) posílá nálezy knihovny na `LIBRARY_HREF` a ostatní nálezy na `SETUP_HREF`.
- Problémy repa na Přehledu (`lib/overview.ts`) vedou takto: `not_installed` a `invalid` na `#/r/<id>/factory`, `uncommitted` rovnou na náhled commitu `#/r/<id>/factory/config_commit`.

## Výslovně odstraněno

- **Začínáme** na Tento počítač (`components/GettingStarted.vue` a jeho test jsou smazané). Hotové kroky jsou jen informace. Nehotové kroky dál ukazuje readiness chip a stránka Problémy a řešení, se stejnými akcemi. `lib/gettingStarted.ts` zůstává.
- Text „HAIFA je spuštěná na tomto počítači.“ a prázdné skupiny „Bez nálezů“. Prázdná skupina se nevykresluje.
- Seznam harnessů s počty rep. Počty dál počítá server, aby věděl, který chybějící harness je potřeba.
- Patička „Další krok“ na Tento počítač. Šlo jen o navigaci, kterou nabízí přepínač rep a readiness.
- Náhradní text u nálezu bez opravy. Takové nálezy server dashboardu neposílá. Nález počítače teď vykresluje `components/setup/MachineFinding.vue`.

## Jen akční nálezy (server)

Filtr je ve webové vrstvě. `factory check` v CLI se nemění.

- `web/factory.py`: `is_actionable` propustí nález s `fix` nebo `action`, který není v `DASHBOARD_HIDDEN` (`{"hosting_skipped"}`, protože dashboard nemá přepínač offline). `actionable_findings` vždy ponechá `error`, takže `ok` platí beze změny, a přepočítá `counts`. Funkci používá `check_view` repa. Tím zmizí `repo_installed` („factory is installed in … come from library …“), jediný nález bez `fix` a bez `action`.
- `web/machine.py`: `check_view` vrací `actionable_findings(view, _needed)`. `_needed` navíc vyřadí info `harness_missing` pro harness, který žádné registrované repo nepoužívá. Nové pole `missing_harnesses` vrací všechny chybějící harnessy. Podle něj `lib/roster.ts` (`detectedHarnesses`) a krok Harnessy dál poznají, co na počítači chybí. Typ pole je v `lib/api.ts`.
- Docstringy endpointů v `web/app.py` popisují nové chování.

## Příručka

Kapitoly `guide/03`, `04`, `08`, `10`, `12` a `15` popisují nové uspořádání. Soubor `docs/decisions.md` není mezi změněnými.

## Ověření

- Backend: `cd aifactory && uv run pytest tests/web/test_web_factory.py tests/web/test_web_machine.py -n0`. Nové testy jsou `test_check_shows_only_actionable_findings` a `test_missing_harness_info_only_for_harnesses_repos_use`.
- Frontend: `just web-test`. Pokrývá `router.test.ts` (přesměrování, čtyři obrazovky), `FactoryView.test.ts` (skrývání nálezů, sekce nastavení), `SetupView.test.ts`, `LibrarySection.test.ts`, `RepoSettings*.test.ts`, `App.test.ts`, `LibraryChip.test.ts`, `overview.test.ts` a `gettingStarted.test.ts`.
- Prohlížeč: `cd aifactory && uv run pytest tests/e2e/test_library_browser.py -n0`. Test klikne na chip knihovny a čeká `#/setup/library` s nadpisem „Tento počítač“.
- Ručně: `just dash`, pak otevřít `#/library` a `#/r/<id>/settings` (obě adresy musí přesměrovat) a ověřit, že na Factory není `repo_installed`.
- `web/static` je přebuildovaný (`just web-build`, nové hashe assetů v `index.html`).
