---
id: HAIFA-S07-T01
title: "Verze, meze závislostí, obsah balíčku a prostředí"
status: done
depends_on: [HAIFA-S01-T09]
---

## Zadání
Připrav balíček `aifactory` na instalaci u kolegů z bundlu `haifa-<verze>.zip` přes `uv tool install` (D2, rozhodnutí Distribuce bundlem v `docs/decisions.md`): verze z jednoho místa, horní meze závislostí, test obsahu wheelu a proměnné prostředí z `$HAIFA_HOME/env` místo `.env` hledaného od umístění balíčku. Dnes je verze 0.1.0 ve dvou souborech, `load_dotenv()` v `engine/utils.py` čte `.env` z nadřazených složek balíčku (u vývojové instalace HAIFA/.env pro každé repo) a obsah wheelu nikdo neověřil.

Where: `aifactory/pyproject.toml`, `aifactory/uv.lock`, `aifactory/src/aifactory/__init__.py`, `aifactory/src/aifactory/engine/utils.py`, `aifactory/src/aifactory/cli.py`, modul domovského adresáře z M2, `aifactory/src/aifactory/skill/codes.py`, testy v `aifactory/tests/`.

Done means:
- Verze je jen v `aifactory/src/aifactory/__init__.py`. `pyproject.toml` ji čte přes `dynamic = ["version"]` a `[tool.hatch.version]`.
- Běhové závislosti mají dolní i horní mez (další major verze, u verzí 0.x další minor) a `uv.lock` odpovídá.
- `hatchling` je ve skupině dev. Test postaví wheel přes `hatchling.build.build_wheel` do dočasné složky bez sítě a ověří, že obsahuje každý soubor pod `src/aifactory/` kromě `__pycache__` (mimo jiné `web/static/index.html`, `defaults/workflows/*.yaml`, `engine/defaults/roles.yaml`, `skill/skill.md` a `seed/agents/*/agent.yaml`) a že verze v metadatech wheelu se rovná `__version__`.
- `aifactory/THIRD_PARTY_NOTICES` je kopie souboru `THIRD_PARTY_NOTICES` z kořene repa, `pyproject.toml` ho uvádí v `license-files` a test ověří, že je ve wheelu a shoduje se s kořenovým souborem.
- `engine/utils.py` už při importu nenačítá `.env` (změna se značkou `# aifactory`). `factory` při startu načte `$HAIFA_HOME/env` (KEY=VALUE), pokud existuje, a nepřepíše proměnné, které prostředí už má. Soubor s jinými právy než 0600 načte a vypíše na stderr varování `env_file_mode`.
- `just factory` dál načítá `.env` repa HAIFA přes `set dotenv-load` (justfile se nemění).
- Testy: wheel, verze, načtení `env` bez přepsání, import `engine.utils` nevolá `load_dotenv`, práva souboru.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: sestavení bundlu (`just bundle`), `factory upgrade`, kontrola stroje, hatch-vcs.

Pevná omezení:
- Každá změna logiky v `aifactory/src/aifactory/engine/` má značku `# aifactory`.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-04 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/46 · náklady $0.81
