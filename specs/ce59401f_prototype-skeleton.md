# Plán: kostra prototypu HAIFA (`prototype/`, `haifa_proto`, `haifa-proto`, recepty v `justfile`)

## Cíl

Založit uv projekt `prototype/` s balíčkem `haifa_proto`, CLI `haifa-proto` (podpříkazy `backlog`, `task`, `serve` bez logiky), jedním místem pro import enginu z `vendor/sssf/templates/adws/adw_modules`, smoke testem a recepty `test`, `typecheck`, `lint`, `proto` v kořenovém `justfile`.

Mimo rozsah: jakákoli logika backlogu, workflow, běhů nebo webu.

## Zjištěný stav (recon)

- `prototype/` ani `specs/` zatím neexistují.
- `justfile` má `set dotenv-load` a `set positional-arguments` → v receptech s `*ARGS` používej `"$@"` (stejně jako stávající recepty).
- Nástroje v PATH: `uv`, `just`. `ruff`, `mypy`, `pyright` globálně NEJSOU → musí přijít jako dev závislosti projektu a volat se přes `uv run`.
- Python: dostupné 3.11, 3.13, 3.14. Použij `requires-python = ">=3.11"`.
- `adw_modules` importují třetí strany: `pydantic`, `python-dotenv` (`dotenv`), `pyyaml` (`yaml`), `rich`. Zbytek je stdlib. `adw_modules/utils.py` volá při importu `load_dotenv()` – neškodné.
- POZOR: v repu existuje i `adws/adw_modules/` (kopie pro ADW). Helper musí vkládat cestu k `vendor/...` na začátek `sys.path` (index 0), a test ověří, že načtený modul skutečně pochází z `vendor/sssf/templates/adws/adw_modules`.
- `vendor/` se NEUPRAVUJE. Stávající recepty v `justfile` se NEMĚNÍ, jen se přidávají nové na konec.

## Soubory k vytvoření / úpravě

### 1. `prototype/pyproject.toml` (nový)

```toml
[project]
name = "haifa-proto"
version = "0.1.0"
description = "HAIFA prototype: local control panel and CLI over the sssf engine"
requires-python = ">=3.11"
dependencies = [
    "pydantic",
    "python-dotenv",
    "pyyaml",
    "rich",
]

[project.scripts]
haifa-proto = "haifa_proto.cli:main"

[dependency-groups]
dev = [
    "pytest",
    "ruff",
    "mypy",
    "types-PyYAML",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/haifa_proto"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py311"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.mypy]
python_version = "3.11"
strict = true
files = ["src", "tests"]

[[tool.mypy.overrides]]
module = ["adw_modules", "adw_modules.*"]
ignore_missing_imports = true
follow_imports = "skip"
```

Poznámky:
- `uv run` instaluje projekt editable a dev skupinu defaultně → `__file__` balíčku ukazuje do `prototype/src/`, na čemž stojí výpočet cesty k vendoru.
- Po vytvoření spusť `uv lock --project prototype` (vznikne `prototype/uv.lock`, commitnout ho).
- Typecheck: zvolen **mypy** (čistě pip balíček, nepotřebuje node jako pyright).

### 2. `prototype/src/haifa_proto/__init__.py` (nový)

```python
"""HAIFA prototype."""

__version__ = "0.1.0"
```

### 3. `prototype/src/haifa_proto/engine.py` (nový) – JEDINÉ místo, které sahá na `sys.path`

Obsah (tvar závazný, detaily volné):

```python
"""Single entry point to the sssf engine vendored in vendor/sssf/templates/adws."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

# prototype/src/haifa_proto/engine.py -> parents[3] == repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
ENGINE_DIR = REPO_ROOT / "vendor" / "sssf" / "templates" / "adws"


def ensure_engine_on_path() -> Path:
    """Put the vendored adws dir first on sys.path (idempotent) and return it."""
    if not (ENGINE_DIR / "adw_modules" / "__init__.py").is_file():
        raise RuntimeError(f"sssf engine not found at {ENGINE_DIR}")
    entry = str(ENGINE_DIR)
    if entry in sys.path:
        sys.path.remove(entry)
    sys.path.insert(0, entry)
    return ENGINE_DIR


def load_engine_module(name: str) -> ModuleType:
    """Import `adw_modules.<name>` (or `adw_modules` for name == "") from the vendored engine."""
    ensure_engine_on_path()
    full = "adw_modules" if not name else f"adw_modules.{name}"
    return importlib.import_module(full)
```

- Nic jiného v `haifa_proto` ani v testech `sys.path` neupravuje.
- Import `adw_modules` NEprovádět při importu `haifa_proto` ani `haifa_proto.cli` (CLI `--help` musí jít i bez načítání enginu).

### 4. `prototype/src/haifa_proto/cli.py` (nový)

argparse (žádná nová závislost):

```python
"""haifa-proto command line."""

from __future__ import annotations

import argparse
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="haifa-proto",
        description="HAIFA prototype: control panel and CLI over the sssf engine.",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.add_parser("backlog", help="work with the backlog (not implemented yet)")
    sub.add_parser("task", help="run and inspect tasks (not implemented yet)")
    sub.add_parser("serve", help="start the local web panel (not implemented yet)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    print(f"haifa-proto {args.command}: not implemented yet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`[project.scripts]` volá `main()`; návratová hodnota int se použije jako exit code (setuptools/hatch entry-point wrapper dělá `sys.exit(main())`).

### 5. `prototype/tests/test_engine_import.py` (nový) – smoke test

```python
from pathlib import Path

from haifa_proto import engine


def test_engine_modules_load_from_vendor() -> None:
    runner = engine.load_engine_module("runner")
    agents = engine.load_engine_module("agents")
    assert hasattr(runner, "Run")
    assert hasattr(agents, "INTERFACES")
    vendor_pkg = engine.ENGINE_DIR / "adw_modules"
    for mod in (runner, agents):
        assert mod.__file__ is not None
        assert Path(mod.__file__).resolve().parent == vendor_pkg.resolve()
```

### 6. `prototype/tests/test_cli.py` (nový)

```python
import pytest

from haifa_proto.cli import main


def test_help_lists_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    for name in ("backlog", "task", "serve"):
        assert name in out


@pytest.mark.parametrize("name", ["backlog", "task", "serve"])
def test_subcommands_are_noops(name: str) -> None:
    assert main([name]) == 0
```

Žádné `__init__.py` v `tests/` není potřeba (pytest rootdir `prototype/`, balíček je nainstalovaný).

### 7. `justfile` (kořen) – PŘIDAT na konec, nic stávajícího neměnit

```just
# ── prototype ───────────────────────────────────────────────────────────────

# run the prototype test suite: just test  (args go to pytest)
test *ARGS:
    cd prototype && uv run pytest "$@"

# type-check the prototype with mypy
typecheck:
    cd prototype && uv run mypy

# lint the prototype with ruff
lint:
    cd prototype && uv run ruff check . && uv run ruff format --check .

# run the prototype CLI: just proto --help
proto *ARGS:
    uv run --project prototype haifa-proto "$@"
```

- Odsazení 4 mezerami jako ve zbytku souboru.
- `cd` a příkaz musí být na jednom řádku (každý řádek receptu = vlastní shell).
- Pokud `ruff format --check` narazí na neformátovaný kód, zformátuj ho `uv run ruff format .` v `prototype/` (jen vlastní soubory, nikdy vendor).

### 8. Ostatní

- `.gitignore`: přidat `prototype/.venv/` a `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/` (pokud tam nejsou).
- Neupravovat `vendor/`, `adws/adw_modules/`, `adws/adw_sssf_config/`, `adws/adw_*.py`, `docs/product-brief.md`.

## Ověření (všechny musí skončit exit kódem 0)

```bash
uv lock --project prototype
just test
just typecheck
just lint
uv run --project prototype haifa-proto --help     # výpis obsahuje backlog, task, serve
just proto --help
just proto backlog                                 # vypíše "not implemented yet", exit 0
just --list                                        # stávající recepty beze změny + test/typecheck/lint/proto
git diff --stat -- vendor/ adws/adw_modules/       # prázdné
git diff justfile                                  # jen přidané řádky (+), žádné (-)
```

Úspěch posuzuj podle exit kódu, ne podle slov ve výstupu.

## Rizika

- Pokud mypy strict zlobí u `importlib`/`ModuleType`, je v pořádku zúžit (`hasattr` testy už typově projdou); nevypínat strict globálně, spíš lokální override jen pro `tests.*`, kdyby bylo nutné.
- Kdyby se `adw_modules` načetlo z `adws/` místo z vendoru, smoke test to chytí (kontrola `__file__`).
