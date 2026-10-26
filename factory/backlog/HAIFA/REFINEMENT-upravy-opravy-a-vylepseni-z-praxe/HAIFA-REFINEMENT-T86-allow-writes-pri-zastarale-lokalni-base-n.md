---
id: HAIFA-REFINEMENT-T86
title: "retry --allow-writes při zastaralé lokální base nechá necommitnutou změnu v hlavním checkoutu"
status: todo
depends_on: []
related: [HAIFA-REFINEMENT-T63, HEAL-S02-T08]
writes: [aifactory/src/aifactory/run/allow_writes.py, aifactory/src/aifactory/run/retry.py, aifactory/tests/]
---

## Zadání
`factory task retry <ID> --allow-writes` upraví `writes` úlohy v hlavním checkoutu a potřebuje, aby změna byla v base commitnutá. Když je lokální base větev pozadu za `origin`, příkaz skončí `writes_not_committed` a upravený soubor úlohy zůstane v hlavním checkoutu jako necommitnutá změna. Další `git pull --ff-only` pak může selhat a operátor musí změnu ručně zahodit.

## Současný stav (naměřeno v NEO_HEF 2026-10-22, factory 0.1.482)

- `ROB-TODO-T39` skončila `writes_needed` (soubor `src/modules/ROB/Fenix.ROB.Application/Progress/RobProgress.cs`).
- `retry ROB-TODO-T39 --allow-writes --auto` selhal `writes_not_committed`. Lokální `develop` byl pozadu a `origin/develop` už měl soubor ve `writes` z jiného PR.
- V hlavním checkoutu zůstal změněný soubor úlohy. Ruční oprava: zahodit změnu, `git pull --ff-only`, znovu `retry`.
- Stejný postup (pull, pak `--allow-writes`) prošel u `ROB-TODO-T41`.

## Co udělat

1. Před úpravou `writes` porovnat lokální base s `origin/<base>` (fetch). Když je pozadu a lze fast-forward bez konfliktu s rozpracovanými soubory, posunout ji, jinak skončit jasnou chybou ještě před zápisem.
2. Když už `writes` v `origin/<base>` požadované cesty obsahují, nic nezapisovat a rovnou spustit retry.
3. Při selhání vrátit hlavní checkout do původního stavu (žádná necommitnutá změna po neúspěšném příkazu).

## Hotovo znamená

- `retry --allow-writes` při zastaralé lokální base buď projde, nebo skončí bez změny v hlavním checkoutu.
- Testy pokrývají base pozadu, base aktuální a cesty už obsažené v origin.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
