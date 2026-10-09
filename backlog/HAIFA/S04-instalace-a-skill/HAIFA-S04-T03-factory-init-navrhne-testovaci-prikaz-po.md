---
id: HAIFA-S04-T03
title: "`factory init` navrhne testovací příkaz podle technologie"
status: done
depends_on: [HAIFA-S04-T01]
---

## Zadání
Doplň do `factory init` návrh testovacího příkazu podle technologie repa. Dnes ho engineer nastavuje ručně (rozhodnutí Testovací příkaz podle technologie v `docs/decisions.md`).

Where: nový modul pro rozpoznání technologie v `aifactory/src/aifactory/`, `aifactory/src/aifactory/cli.py` (`factory init`), `aifactory/src/aifactory/skill/` (`skill.md`, `codes.py`), testy v `aifactory/tests/`.

Done means:
- Funkce rozpozná technologii podle souborů v kořeni repa a navrhne `test_command`: `justfile` s receptem `test` → `just test`, `pyproject.toml` nebo `pytest.ini` → `uv run pytest` (bez uv `pytest`), `package.json` se skriptem `test` → podle lockfilu `npm test`, `pnpm test`, `yarn test` nebo `bun test`, `*.sln` nebo `*.csproj` → `dotnet test`, `Cargo.toml` → `cargo test`, `go.mod` → `go test ./...`, `Makefile` s cílem `test` → `make test`. Při více shodách vrátí všechny kandidáty seřazené (justfile první).
- `factory init` zapíše první kandidát jako `test_command` do `.factory/config.yaml` a vypíše ostatní. `--test-command "..."` návrh přebije, bez kandidátů zůstane výchozí `just test` s varováním.
- Funkci jde použít i při onboardingu.
- `factory --skill` popisuje rozpoznání a volbu.
- Testy (pytest) nad dočasnými repy pro každou technologii, více shod, žádná shoda a `--test-command`.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: spouštění rozpoznaného příkazu při initu, monorepa s víc technologiemi v podadresářích (jen kořen repa), dashboard.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-04 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/57 · náklady $1.43
