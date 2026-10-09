---
id: HAIFA-S05-T03
title: "Knihovna v domově: založení ze semínka, výpis, detail a import"
status: done
depends_on: [HAIFA-S05-T01, HAIFA-S01-T09, HAIFA-S01-T11]
---

## Zadání
Přidej knihovnu HAIFA v domovském adresáři: git repozitář s položkami z L1, který se založí ze semínka, umí vypsat položky a jejich historii a importovat položku ze složky nebo souboru pod domovem. Každý zápis jde přes plán s digestem a commit bez checkoutu (primitiva z M7), takže ruční práci v knihovně nic nepřepíše.

Where: `aifactory/src/aifactory/library/` (z L1), modul domovského adresáře z M2, zveřejnění commitu z M7 (`aifactory/src/aifactory/providers/git.py`), `aifactory/src/aifactory/cli.py`, `aifactory/src/aifactory/skill/` (`skill.md`, `codes.py`), testy v `aifactory/tests/library/`.

Done means:
- Knihovna je `$HAIFA_HOME/library` (cestu přebije `HAIFA_LIBRARY`). `library.yaml` má `format: 1`, `id` (uuid4), `name`, `min_factory_version` (null) a `seed` (mapa `typ/jméno` na verzi semínka, ze které položka vznikla).
- `factory library init [--name N] --json` založí knihovnu ze semínka jedním commitem. Existující knihovnu odmítne (`library_exists`), bez `user.name` a `user.email` v gitu vrátí `git_identity_missing`.
- `factory library list [--type T] --json` vrátí položky s verzí, krátkou verzí (8 znaků), datem a autorem poslední změny. `factory library show TYP JMÉNO [--version V] --json` vrátí soubory a historii verzí (verze, commit, datum, autor). Čte se strom HEAD, ne pracovní strom.
- Verzi v historii najde `git log -- <cesta položky>` a hash položky v každém commitu. Výsledek se drží v `$HAIFA_HOME/cache/` a smazaná cache se dopočítá.
- `factory library import CESTA --type agent|workflow|skill|extension [--name N] [--dry-run] --json` vezme složku nebo soubor jen pod domovem uživatele (jinak `outside_home`), symlink mimo domov odmítne, ověří položku (L1) a vrátí plán s digestem a diffem. Stejný obsah je no-op, jiný obsah pod existujícím jménem je nová verze položky.
- Zápis drží flock `$HAIFA_HOME/library.lock`, odmítne knihovnu s necommitnutými změnami (`library_dirty`), postaví commit bez checkoutu nad HEAD a posune větev i pracovní strom fast-forwardem. Zpráva commitu jmenuje položky a zdroj.
- `factory --skill` popisuje příkazy. Nové kódy jsou v `skill/codes.py`.
- Testy (pytest) pod dočasným `HAIFA_HOME`: init a druhý init, list, show s historií dvou verzí, import skillu se spustitelným skriptem (spustitelnost zůstane), import mimo domov a symlink ven z domova, `library_dirty`, dva souběžné zápisy se serializují, smazaná cache.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: remote, clone, pull a push (L3), manifest repa, mazání a přejmenování položek, dashboard.

Pevná omezení:
- Knihovna se mění jen přes plán, nikdy force a nikdy přepis historie.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť a nesahají na skutečný domov.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-04 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/49 · náklady $3.92
