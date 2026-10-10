# Plán: kostra balíčku `aifactory` a přepnutí receptů v `justfile`

## Cíl
Založit uv projekt `aifactory/` (balíček `aifactory`, CLI `factory`) s prázdnými podpříkazy
`task`, `backlog`, `workflow`, `config`, `harness`. Recepty `just test|typecheck|lint` přepnout
na `aifactory/`, recepty prototypu přejmenovat na `proto-test|proto-typecheck|proto-lint`,
přidat `just factory *ARGS`.

Mimo rozsah: jakákoli logika enginu, backlogu, workflow či běhů.
Neměnit `prototype/` ani `vendor/` (kromě cest v receptech justfile – ty se ale ani měnit nemusí,
jen se přejmenují recepty). Ostatní recepty v `justfile` zůstávají beze změny.

Poznámka: quality gate sssf (`adws/adw_modules/quality.py`) volá `just test` / `just typecheck`,
takže po změně gate testuje nový balíček. To je záměr.

## Soubory k vytvoření

### 1. `aifactory/pyproject.toml`
Vzor je `prototype/pyproject.toml` (stejný styl, hatchling, src layout).

```toml
[project]
name = "aifactory"
version = "0.1.0"
description = "HAIFA (Helios AI Factory): local control panel and CLI"
requires-python = ">=3.11"
dependencies = [
    "pydantic",
    "python-dotenv",
    "pyyaml",
    "rich",
]

[project.scripts]
factory = "aifactory.cli:main"

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
packages = ["src/aifactory"]

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
```

Po vytvoření spustit `cd aifactory && uv lock` (vznikne `aifactory/uv.lock`, commitnout ho;
`aifactory/.venv/` necommitovat – přidat `.venv/` do kořenového `.gitignore`, pokud tam ještě
není; zkontrolovat `git status`, že `.venv` nevyskočí jako untracked).

### 2. `aifactory/src/aifactory/__init__.py`
```python
"""HAIFA – Helios AI Factory."""

__version__ = "0.1.0"
```

### 3. `aifactory/src/aifactory/py.typed`
Prázdný soubor (PEP 561 marker).

### 4. `aifactory/src/aifactory/cli.py`
argparse, bez logiky. Požadavky:
- `build_parser() -> argparse.ArgumentParser` s `prog="factory"`, popisem
  a `--version` (`action="version"`, `version=f"%(prog)s {__version__}"`).
- `sub = parser.add_subparsers(dest="command", metavar="<command>")` a pět podpříkazů
  v tomto pořadí s krátkým `help`:
  - `task` – "run and inspect backlog tasks"
  - `backlog` – "load and validate the backlog"
  - `workflow` – "validate and inspect workflows"
  - `config` – "show and validate factory configuration"
  - `harness` – "inspect the coding-agent harnesses"
- `main(argv: Sequence[str] | None = None) -> int`:
  - rozparsuje argumenty;
  - bez příkazu: vytiskne `parser.print_help()` a vrátí 0;
  - s podpříkazem: vypíše na stderr `factory <cmd>: not implemented yet` a vrátí 2
    (podpříkazy "zatím nic nedělají"; nevyhazovat výjimku).
- na konci `if __name__ == "__main__": raise SystemExit(main())`.
- Plné typové anotace (mypy strict).

### 5. `aifactory/src/aifactory/__main__.py`
```python
from aifactory.cli import main

raise SystemExit(main())
```
(umožní `python -m aifactory`; smoke test ho využije).

### 6. `aifactory/tests/test_smoke.py`
Jeden smoke test (může být rozdělen do 2–3 funkcí v jednom souboru):
- `import aifactory` a `aifactory.__version__` je řetězec.
- `subprocess.run([sys.executable, "-m", "aifactory", "--help"], capture_output=True, text=True, check=False)`
  → `returncode == 0`, stdout obsahuje `factory` a všech pět názvů podpříkazů.
- Volitelně: `main(["--help"])` přes `pytest.raises(SystemExit)` s kódem 0 a `capsys`.
Anotace `-> None` a typy parametrů (`capsys: pytest.CaptureFixture[str]`) kvůli mypy strict.
Nepřidávat `tests/__init__.py` (není potřeba; pokud by mypy hlásil duplicitní moduly, přidat ho).

## Úprava `justfile` (kořen repa)
Nahradit sekci `# ── prototype ──` takto (ostatní recepty beze změny):

```just
# ── aifactory ───────────────────────────────────────────────────────────────

# run the aifactory test suite: just test  (args go to pytest)
test *ARGS:
    cd aifactory && uv run pytest "$@"

# type-check aifactory with mypy
typecheck:
    cd aifactory && uv run mypy

# lint aifactory with ruff
lint:
    cd aifactory && uv run ruff check . && uv run ruff format --check .

# run the factory CLI: just factory --help
factory *ARGS:
    uv run --project aifactory factory "$@"

# ── prototype ───────────────────────────────────────────────────────────────

# run the prototype test suite: just proto-test  (args go to pytest)
proto-test *ARGS:
    cd prototype && uv run pytest "$@"

# type-check the prototype with mypy
proto-typecheck:
    cd prototype && uv run mypy

# lint the prototype with ruff
proto-lint:
    cd prototype && uv run ruff check . && uv run ruff format --check .

# run the prototype CLI: just proto --help
proto *ARGS:
    uv run --project prototype haifa-proto "$@"

# validation scenarios R1–R5, R10: just proto-validate --remote local|github [--roster DIR]
proto-validate *ARGS:
    cd prototype && uv run python -m validation "$@"
```
Těla `proto` a `proto-validate` zůstávají doslova stejná.

## Volitelně (dokumentace)
V `CLAUDE.md` je věta o `just test` atd. u prototypu – builder ji nemusí měnit; případně to
udělá documenter. Nesahat na `docs/product-brief.md`, `vendor/`, `adws/`.

## Ověření (vše musí skončit exit kódem 0, posuzovat podle exit statusu)
1. `uv run --project aifactory factory --help` – nápověda obsahuje `task`, `backlog`,
   `workflow`, `config`, `harness`.
2. `just factory --help` – totéž.
3. `just test`, `just typecheck`, `just lint` – projdou nad `aifactory/`
   (pokud `ruff format --check` selže, spustit `cd aifactory && uv run ruff format .`).
4. `just proto-test`, `just proto-typecheck`, `just proto-lint` – projdou jako dřív.
5. `just --list` ukazuje `proto`, `proto-validate`, `factory` a nové názvy.
6. `git status` – změny jen v `aifactory/`, `justfile`, případně `.gitignore`; žádná změna
   v `prototype/` ani `vendor/`.
