Založ kostru balíčku `aifactory`: uv projekt v `aifactory/` s balíčkem `aifactory` a CLI `factory` a přepni recepty `just test`, `just typecheck` a `just lint` na nový balíček. Prototyp dostane vlastní recepty.

Where: `aifactory/pyproject.toml`, `aifactory/src/aifactory/`, `aifactory/tests/`, `justfile` (kořen repa).

Done means:
- `uv run --project aifactory factory --help` vypíše nápovědu s podpříkazy, které zatím nic nedělají: `task`, `backlog`, `workflow`, `config`, `harness`.
- `just test`, `just typecheck` (mypy) a `just lint` (ruff) běží nad `aifactory/` a projdou. Jeden smoke test ověří, že jde importovat `aifactory` a spustit `factory --help`.
- Stávající recepty prototypu se přejmenují na `proto-test`, `proto-typecheck` a `proto-lint` a dál procházejí. `proto` a `proto-validate` zůstávají.
- `just factory *ARGS` volá `factory` s argumenty.

Out of scope: jakákoli logika enginu, backlogu, workflow nebo běhů.

Pevná omezení:
- `prototype/` a `vendor/` se nemění, kromě cest v receptech `justfile`.
- Závislosti pokrývají i to, co potřebuje engine: pydantic, python-dotenv, pyyaml, rich.
- Ostatní recepty v `justfile` zůstávají beze změny.
