---
id: HAIFA-S05-T06
title: Sdílení knihovny přes git remote
status: done
depends_on: [HAIFA-S05-T03]
---

## Zadání
Umožni týmu sdílet knihovnu přes git remote: založit ji s remote, naklonovat, zjistit stav, stáhnout a odeslat změny. Každý zápis do knihovny s remote nejdřív stáhne remote a pushne dřív, než posune lokální větev, takže odmítnutý push nic nezmění.

Where: `aifactory/src/aifactory/library/` (z L1 a L2), `aifactory/src/aifactory/cli.py`, `aifactory/src/aifactory/providers/git.py`, `aifactory/src/aifactory/skill/` (`skill.md`, `codes.py`), testy v `aifactory/tests/library/`.

Done means:
- `factory library init --remote URL` pushne novou knihovnu do prázdného remote. Neprázdný remote odmítne (`remote_not_empty`) a nic nezaloží.
- `factory library clone URL [--branch B] --json` naklonuje knihovnu, existující knihovnu odmítne (`library_exists`) a ověří `library.yaml` (`invalid_library`).
- `factory library status [--fetch] --json` vrátí cestu, `id`, `name`, remote bez přihlašovacích údajů, větev, náskok a zpoždění (bez `--fetch` z posledních refů), čas posledního fetch, necommitnuté změny a `min_factory_version` proti nainstalované verzi.
- `factory library pull` posune jen fast-forwardem a rozejitou nebo špinavou knihovnu odmítne (`library_diverged`, `library_dirty`). `factory library push` nikdy nepoužije force a rozejitou knihovnu odmítne.
- Zápis s remote: fetch, zpoždění dá `library_behind` s opravou `factory library pull`, rozejití `library_diverged`. Commit vznikne bez checkoutu nad HEAD a push jde bez force. Odmítnutý push vrátí `push_failed` a lokální refy, index i soubory zůstanou bajtově stejné. Po úspěchu se lokální větev posune fast-forwardem.
- Remote se vypisuje a ukládá bez uživatele a hesla z URL.
- `factory --skill` popisuje sdílení. Nové kódy jsou v `skill/codes.py`.
- Testy (pytest) s holým remote a dvěma `HAIFA_HOME`: init s remote, clone, zápis v A, zápis v B dá `library_behind`, pull a druhý zápis projde, odmítnutý push přes `pre-receive` hook, prázdný a neprázdný remote, URL s heslem.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: PR do knihovny, slučování textu, mazání položek, dashboard.

Pevná omezení:
- Žádný force push a žádný přepis historie knihovny.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-04 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/52 · náklady $2.16
