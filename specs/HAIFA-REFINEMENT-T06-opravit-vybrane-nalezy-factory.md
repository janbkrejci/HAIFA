# HAIFA-REFINEMENT-T06: Vybrané nálezy Factory

## Rozsah

Ověřit nálezy `repo_onboarded` (akce `adopt`) a `item_local` pro workflow
`manual-test-duration` (akce `export`), provést operace v oprávnění běhu,
poté spustit `factory check` a popsat výsledek každého nálezu.

Povolené změny jsou v `aifactory/`, `justfile` a ve dvou dokumentech tohoto
úkolu. `.factory/` je chráněná konfigurací repozitáře i `CLAUDE.md`.
Hlavní checkout a knihovna `/Users/jbk/.config/haifa/library` jsou mimo
pracovní adresář běhu. Nelze do nich zapisovat ani provádět commity.

## Postup a podmínky dokončení

1. Spustit `just factory check --json` a zaznamenat kontrolovaný base commit.
2. Ověřit `just factory adopt --dry-run --json`. Pokud všechny položky jsou
   `present` a plán neobsahuje import, lze provést skutečný `adopt` bez zápisů.
   Případný import do knihovny mimo worktree musí provést operátor.
3. Ověřit `just factory config export workflow manual-test-duration --dry-run
   --json`. Zapsat cílové soubory a verzi; export se zápisem do chráněného
   manifestu a externí knihovny v tomto běhu neprovádět.
4. Po ověření operací zopakovat `just factory check --json`. U každého nálezu
   uvést skutečný stav a při omezení konkrétní postup pro operátora.

`repo_onboarded` je trvalý informační nález o úspěšném onboardingu.
Opětovný onboarding ani potlačení nálezu nejsou součástí opravy.
`adopt` doplňuje pouze položky uvedené v manifestu; lokální workflow bez
záznamu v manifestu se musí exportovat. Samotný exit code 0 kontroly
neznamená, že informační nález `item_local` zmizel.

## Výstup

Výsledky, omezení a příkazy pro operátora jsou v
[dokumentaci úkolu](../app_docs/HAIFA-REFINEMENT-T06-opravit-vybrane-nalezy-factory.md).
Produktový kód ani konfigurace se pro tento výstup nemění.
