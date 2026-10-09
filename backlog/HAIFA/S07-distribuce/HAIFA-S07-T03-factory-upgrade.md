---
id: HAIFA-S07-T03
title: "`factory upgrade`"
status: done
depends_on: [HAIFA-S07-T01, HAIFA-S05-T06, HAIFA-S07-T05]
---

## Zadání
Přidej `factory upgrade <BUNDLE>`, který nainstaluje novější verzi HAIFA z bundlu `haifa-<verze>.zip` (cesta nebo URL, rozhodnutí Distribuce bundlem v `docs/decisions.md`). Kolega tak po rozeslání nové verze spustí jeden příkaz.

Where: `aifactory/src/aifactory/cli.py`, nový modul v `aifactory/src/aifactory/`, `aifactory/src/aifactory/library/` (`min_factory_version`), `aifactory/src/aifactory/skill/` (`skill.md`, `codes.py`), testy v `aifactory/tests/`.

Done means:
- `factory upgrade <cesta-nebo-URL> [--dry-run] --json` rozbalí bundle do dočasné složky, ověří `SHA256SUMS`, přečte verzi z wheelu a porovná ji s `__version__`. Nižší nebo stejná verze vrátí `up_to_date`, poškozený zip nebo chybějící soubor `bundle_invalid`, chybný součet `checksum_mismatch`.
- Výstup ukáže současnou a cílovou verzi, `min_factory_version` knihovny (cíl pod ním dá varování) a příkaz. Bez `--dry-run` spustí `uv tool install --force <wheel> --constraints constraints.txt` z rozbaleného bundlu a vrátí výsledek. Po úspěchu připomene restart běžícího dashboardu.
- Editovatelnou instalaci (vývoj z repa) odmítne `editable_install` a poradí `git pull`.
- URL stáhne jen přes `https` (nebo `file`) do dočasné složky, jiné schéma odmítne.
- `factory --skill` popisuje upgrade. Nové kódy jsou v `skill/codes.py`.
- Testy (pytest) bez sítě s bundlem postaveným v testu a falešným `uv` na PATH: novější verze, stejná verze, poškozený zip, špatný součet, editovatelná instalace, `--dry-run` nic nespustí, chyba `uv`, URL přes `file://`.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: hostování a rozesílání bundlů, semínko do knihovny, restart dashboardu.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-05 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/58 · náklady $2.29
