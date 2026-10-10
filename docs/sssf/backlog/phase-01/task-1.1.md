Založ kostru prototypu HAIFA: uv projekt v `prototype/` s balíčkem `haifa_proto`, CLI `haifa-proto` a recepty v `justfile`, které spouští jeho testy.

Where: `prototype/pyproject.toml`, `prototype/src/haifa_proto/`, `prototype/tests/`, `justfile` (kořen repa).

Done means:
- `just test` spustí pytest v `prototype/` a projde.
- Jeden smoke test importuje `adw_modules` z `vendor/sssf/templates/adws` přes pomocnou funkci v `haifa_proto` (jedno místo, které přidává cestu do `sys.path`) a ověří, že jde načíst `adw_modules.runner` a `adw_modules.agents`.
- `uv run --project prototype haifa-proto --help` vypíše nápovědu s podpříkazy, které zatím nic nedělají: `backlog`, `task`, `serve`.
- `just proto *ARGS` volá `haifa-proto` s argumenty.
- Recepty `just typecheck` a `just lint` existují a projdou (pyright nebo mypy, ruff).

Out of scope: jakákoli logika backlogu, workflow, běhů nebo webu.

Pevná omezení:
- `vendor/` se neupravuje. Engine se importuje, nekopíruje.
- Závislosti prototypu pokrývají i to, co potřebuje `adw_modules`: pydantic, python-dotenv, pyyaml, rich.
- Stávající recepty v `justfile` zůstávají beze změny, nové se jen přidávají.
