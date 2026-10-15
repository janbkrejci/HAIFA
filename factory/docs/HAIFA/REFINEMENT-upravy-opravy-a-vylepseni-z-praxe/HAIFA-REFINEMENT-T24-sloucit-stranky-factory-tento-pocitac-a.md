# HAIFA-REFINEMENT-T24: Sloučení stránek Factory, Tento počítač, Knihovna a Nastavení

## Rozhodnutí o uspořádání

Dřív byly čtyři stránky a jejich obsah se překrýval:

| Stránka | Překryv |
|---|---|
| Factory (`#/r/<id>/factory`) | ukazovala i nálezy knihovny a nálezy počítače nezávislé na repu (jsou i na Tento počítač) |
| Nastavení (`#/r/<id>/settings`) | jen polovina úkonu „změnit konfiguraci a commitnout“, commit byl na Factory |
| Tento počítač (`#/setup`) | synchronizace knihovny (i na Knihovně), Začínáme (i v readiness / Problémech), info bez akce |
| Knihovna (`#/library`) | synchronizace knihovny (i na Tento počítač) |

Teď jsou **dvě stránky podle rozsahu**. Obě vycházejí ze stránky Factory: hlavička s „Znovu zkontrolovat“, verdikt, jen akční nálezy a pod nimi sekce s akcemi.

1. **Factory** (`#/r/<id>/factory`) obsahuje vše o factory jednoho repa: kontrolu repa, instalaci, commit a stažení konfigurace, roster, **Nastavení repozitáře** a položky repa. Nastavení patří sem, protože uložená sdílená hodnota se na téže stránce hned objeví jako `config_uncommitted` a commitne se tlačítkem **Commitnout konfiguraci**.
2. **Tento počítač** (`#/setup`) obsahuje vše o tomto počítači: kontrolu počítače, sekci **Knihovna** a nastavení dashboardu. Knihovna leží v `$HAIFA_HOME` tohoto počítače. Proto je její sekce tady a je to jediné místo její synchronizace.

Horní lišta (readiness chip, `#/problems`, chip knihovny) problémy jen počítá a odkazuje na jediné místo, kde se řeší. Nejde o duplicitní obsah.

## Kam se co přesunulo

| Dřív | Teď |
|---|---|
| záložka Nastavení repa | sekce **Nastavení repozitáře** na Factory, `#/r/<id>/factory/settings` (jen s nainstalovanou factory, bez ní `config.yaml` neexistuje) |
| stránka Knihovna (sync, PR, remote, reseed, import, prohlížeč, kopie rep, přesun do knihovny) | sekce **Knihovna** na Tento počítač, `#/setup/library` |
| založení / naklonování knihovny na Tento počítač | sekce Knihovna (formulář je tam, dokud knihovna neexistuje) |
| nálezy knihovny (Factory i Tento počítač) | jen v sekci Knihovna |
| nálezy počítače nezávislé na repu na Factory | jen na Tento počítač. Factory místo nich ukáže jeden řádek „Další nálezy tohoto počítače a knihovny: N · Otevřít Tento počítač“ |
| nálezy počítače, které plynou z repa (harness z rosteru, node pro pi, login k hostingu repa, `trace_db_shared`) | dál na Factory ve skupině **Tento počítač: potřebné pro toto repo** |
| položka **Knihovna** v menu přepínače rep | chip knihovny v horní liště a sekce Knihovna |

Factory skryje nález počítače, který má machine check (`GET /api/machine/check`) se stejným `code` a `message`. Když se machine check nenačte, Factory neskryje nic. Verdikt a počty na Factory se počítají z viditelných nálezů.

## Přesměrování

- `#/r/<id>/settings[/…]` vede na `#/r/<id>/factory/settings`. Factory pak sjede na sekci Nastavení repozitáře.
- `#/library` vede na `#/setup/library`. Tento počítač sjede na sekci Knihovna.
- Odkazy jsou v `lib/router.ts` (`SETUP_HREF`, `LIBRARY_HREF`, `repoSettingsHref`). Chip knihovny vede v obou stavech na `#/setup/library`. Krok „Knihovna“ prvního spuštění vede tamtéž. Problémy repa na Přehledu (`not_installed`, `invalid`, `uncommitted`) vedou na Factory, `uncommitted` rovnou na náhled commitu (`#/r/<id>/factory/config_commit`).

## Výslovně odstraněno

- **Začínáme** na Tento počítač (komponenta `GettingStarted.vue`). Hotové kroky jsou informace bez akce. Nehotové kroky dál ukazuje readiness chip a stránka **Problémy a řešení** se stejnými akcemi (`lib/gettingStarted.ts` zůstává).
- Text „HAIFA je spuštěná na tomto počítači.“ a prázdné skupiny „Bez nálezů“ (na Tento počítač i na Factory). Prázdná skupina se nevykresluje.
- Seznam harnessů s počty rep (`harness-counts`). Počty dál počítá server, aby věděl, který chybějící harness je potřeba. Harnessy se nastavují v dialogu z horní lišty.
- Patička „Další krok: Přidat repozitář · Přehled“ na Tento počítač. Je to jen navigace, kterou nabízí přepínač rep a readiness.
- Náhradní text „Zkontroluj nastavení prostředí podle nálezu.“ u nálezu bez opravy. Takové nálezy server dashboardu neposílá.
- Štítek „knihovna“ u nálezu na Factory. Nálezy knihovny tam nejsou.

## Jen akční nálezy

Dashboard filtruje nálezy na serveru, ve vrstvě webu (`web/factory.py`: `is_actionable`, `actionable_findings`, `DASHBOARD_HIDDEN`). `factory check` v CLI se nemění.

- Nález bez `fix` a bez `action` se nezobrazí. Kontrola všech `Finding(` v `check/*_rules.py` a `web/` ukázala jediný takový nález, `repo_installed` („factory is installed in … come from library …“).
- `hosting_skipped` se nezobrazí. Dashboard nemá přepínač offline a rada „run without --offline“ platí jen pro CLI.
- Info `harness_missing` mimo repo (machine check) se nezobrazí pro harness, který nepoužívá žádné registrované repo. Pro harness, který repo používá, zůstane. Seznam všech chybějících harnessů vrací API v `missing_harnesses`. Podle něj roster editor a krok „Harnessy“ dál poznají, které harnessy počítač nemá.
- Chyba (`error`) se nikdy neodfiltruje, takže `ok` zůstává beze změny. `counts` se přepočítá podle vrácených nálezů.

Na dalších místech dashboardu (Přehled, karta repa, readiness, Problémy) jiné neakční nálezy nejsou. Readiness bere jen `error` a `warning`. Stavové údaje (base, verze, napřed/pozadu) nejsou nálezy, a proto zůstávají.

## Dokumentace a rozhodnutí

Kapitoly příručky 03, 04, 08, 10, 12 a 15 popisují nové uspořádání. `docs/decisions.md` je mimo povolené cesty tasku, proto se nemění. Rozdělení těchto stránek ani `repo_installed` v něm nejsou, takže úprava není potřeba.
