---
id: HAIFA-S01-T11
title: "Commit konfigurace do base: factory config commit a pull"
status: done
depends_on: [HAIFA-S01-T10]
---

## Zadání
Přidej zveřejnění commitu do base, které posune hlavní checkout až poté, co je commit na remote, a postav na něm `factory config commit` (necommitovaná sdílená konfigurace jedním commitem do base podle D4) a `factory config pull` (dorovnání lokální base s remote). Stejnou cestou půjdou instalace a aktualizace factory. Dnešní `backlog commit` commituje v hlavním checkoutu a při odmítnutém push nechá na lokální base nepushnutý commit, který pak skončí v každém PR tasku.

Where: `aifactory/src/aifactory/cli.py`, `aifactory/src/aifactory/config/` (`status.py`, `source.py`, `loader.py`, `run.py`), `aifactory/src/aifactory/providers/` (`git.py`, `base.py`, `local.py`, `github.py`, `azure.py`), `aifactory/src/aifactory/run/store.py`, `aifactory/src/aifactory/review/flow.py` (`_catch_up_base` jako vzor), `aifactory/src/aifactory/backlog/commit.py` (vzor), `aifactory/src/aifactory/skill/` (`skill.md`, `codes.py`), testy v `aifactory/tests/config/` a `aifactory/tests/providers/`.

Done means:
- Plán vrátí soubory (cesta, akce, diff proti base, obsah), blokátory a `digest`: sha256 přes base, sha base, původní blob a nový obsah každé cesty. Cíl (přímo nebo PR) a zpráva commitu do digestu nepatří.
- Commit vznikne bez checkoutu nad sha base (dočasný index, `commit-tree`) a obsahuje přesně plánované cesty a bajty. Jiná staged i unstaged práce v hlavním checkoutu zůstane.
- Přímý cíl s remote: nejdřív `git fetch` base. Posunutý remote dá blokátor `base_behind`, rozejitý `base_diverged`. Pak push bez force. Odmítnutý push vrátí `push_failed` a v repu se nic nezmění.
- Cíl PR (`github`, `azure`): větev `factory-config/<n>` z commitu, push a PR přes `GitProvider`. Base ani hlavní checkout se nemění.
- Bez remote vznikne jen commit. Lokální base se posune až po úspěšném push, pod zápisovým zámkem trace DB a jen když v repu neběží běh s živým procesem (jinak `run_in_progress`). Cesty, které už v pracovním stromu mají plánovaný obsah, se před posunem stagnou. Když posun po úspěšném push selže, výsledek varuje a nic nevrací zpět.
- `factory config commit [--repo] [--dry-run] [--pr] [--expect DIGEST] [-m TEXT] --json` vezme sdílené cesty z `config_changes`. Pracovní strom musí projít `load_config` a u přímého cíle musí být hlavní checkout na base (`not_on_base`). Jiný digest než `--expect` vrátí `plan_changed`. Bez změn vrátí `committed: false`.
- `factory config pull [--repo] --json` dorovná lokální base na remote fast-forwardem, když v repu nic neběží. Rozejitou base a špinavý checkout odmítne a nic nezmění.
- `factory --skill` popisuje oba příkazy. Nové kódy jsou v `skill/codes.py`.
- Testy (pytest) s holým remote: commit a push, odmítnutý push přes `pre-receive` hook (refy, index a soubory zůstanou bajtově stejné), PR přes `tests/providers/gh_fake.py`, `plan_changed` po novém commitu v base, běh s živým pid blokuje a s mrtvým ne, cizí staged práce přežije, repo bez remote, `config pull` při zpoždění i rozejití.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: instalace a aktualizace factory, API a dashboard, změna `factory backlog commit`.

Pevná omezení:
- Žádný force push a žádný jiný posun base než fast-forward.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-03 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/13 · náklady $4.89
