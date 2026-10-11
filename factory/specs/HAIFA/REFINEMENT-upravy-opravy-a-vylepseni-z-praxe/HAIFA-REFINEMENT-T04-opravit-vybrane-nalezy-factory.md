# HAIFA-REFINEMENT-T04: Opravit vybrané nálezy Factory

## Rozsah

Prověřit `workflow_not_in_repo` pro workflow `manual-test-duration` úkolu
`HAIFA-S90-T06` a `config_uncommitted` pro
`.factory/workflows/manual-test-duration.yaml`. Spustit `factory check` a pro každý
nález uvést výsledek, případnou překážku a postup pro operátora.

Povolené změny jsou pouze v `aifactory/`, `justfile` a dokumentech tohoto úkolu
v `specs/` a `app_docs/`. `.factory/` je chráněná podle `.factory/config.yaml`
a `CLAUDE.md`; backlog není mezi povolenými cestami. Hlavní checkout se během
běhu nesmí měnit a builder nesmí vytvářet commity ani pushovat.

## Zjištění a rozhodnutí

Kontrola dne 2026-10-08 nad main `f269d53569ad2ec945f8b12f52918b370fb1e167`
potvrdila oba nálezy. Nejde o chybu produktového kódu: workflow je pouze
necommitovaný soubor hlavního checkoutu a běhy správně čtou konfiguraci z main.
Úprava kontrol by nález pouze skryla.

`factory config add workflow manual-test-duration --dry-run --json` končí
`unknown_item`: workflow není v aktuální knihovně. Plán
`factory config commit --repo /Users/jbk/Documents/HAIFA --dry-run --json`
obsahuje vytvoření jediného souboru
`.factory/workflows/manual-test-duration.yaml`, ale hlásí `run_in_progress`
pro právě tento běh `c5dccfe7`.

Obě opravy proto musí provést operátor po skončení běhu: zkontrolovat lokální
workflow a commitnout jej přes `factory config commit` do main. Změna workflow
ani backlogu není v tomto běhu autorizovaná. Výsledky a ověřovací příkazy
jsou v odpovídajícím dokumentu `app_docs/`.

## Ověření dokončení operátorem

Po commitu do main musí opakovaný `factory check --json` přestat hlásit oba
vybrané kódy. Pokud se plán konfigurace změnil, musí jej operátor znovu
zkontrolovat; tato dokumentace nepotvrzuje opravu konfigurace.
