---
id: HAIFA-S07-T05
title: "Bundle HAIFA pro distribuci (`just bundle`)"
status: done
depends_on: [HAIFA-S07-T01]
---

## Zadání
Přidej sestavení distribučního bundlu HAIFA: recept `just bundle` vytvoří `aifactory/dist/haifa-<verze>.zip`, který kolega rozbalí a nainstaluje bez přístupu k repu HAIFA (rozhodnutí Distribuce bundlem v `docs/decisions.md`).

Where: `justfile` (recept `bundle`), nový modul nebo skript pod `aifactory/` pro sestavení, šablony `install.sh` a `INSTALL.md` pod `aifactory/`, `aifactory/.gitignore`, testy v `aifactory/tests/`.

Done means:
- `just bundle` postaví frontend (`just web-build`), wheel `aifactory` a zip `aifactory/dist/haifa-<verze>.zip`. Zip obsahuje jen: wheel, `constraints.txt` (připnuté verze běhových závislostí podle `aifactory/uv.lock`), `install.sh`, `INSTALL.md`, `THIRD_PARTY_NOTICES` a `SHA256SUMS` se součty všech ostatních souborů. Žádné `.env`, trace, `__pycache__` ani jiné soubory.
- Verze v názvu zipu se rovná `aifactory.__version__`.
- `install.sh` (bash, bez přepínačů dostupných jen v GNU, macOS i Linux) zkontroluje, že je `uv` na PATH (jinak vypíše, jak ho nainstalovat, a skončí nenulovým kódem), ověří `SHA256SUMS` a spustí `uv tool install --force <wheel> --constraints constraints.txt`. Na konci poradí `factory check`.
- `INSTALL.md` česky popíše předpoklady, instalaci (`./install.sh`), ověření (`factory check`), přidání prvního repa a aktualizaci (`factory upgrade <bundle>`).
- `aifactory/dist/` je v `aifactory/.gitignore`.
- Testy (pytest) bez sítě: sestavení bundlu do dočasné složky z existujícího buildu frontendu, obsah zipu, součty, verze v názvu, `bash -n install.sh` a běh `install.sh` s falešným `uv` na PATH, který zaznamená volaný příkaz.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: rozesílání a hostování bundlu, podpis bundlu, Windows bez WSL, `factory upgrade`.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-04 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/50 · náklady $1.09
