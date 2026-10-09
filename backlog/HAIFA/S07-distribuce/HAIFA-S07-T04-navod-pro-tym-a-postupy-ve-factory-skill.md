---
id: HAIFA-S07-T04
title: "Návod pro tým a postupy ve `factory --skill`"
status: todo
depends_on: [HAIFA-S07-T02, HAIFA-S07-T03, HAIFA-S06-T02, HAIFA-S06-T04, HAIFA-S05-T09, HAIFA-S05-T10, HAIFA-S04-T02, HAIFA-S07-T05]
---

## Zadání
Napiš česky návod, podle kterého si kolega HAIFA stáhne, zprovozní a přidá svoje repa, a doplň stejné postupy do `factory --skill`. Úkoly HAIFA smí zapisovat jen pod `aifactory/`, proto je návod v `aifactory/README.md`.

Where: nový soubor `aifactory/README.md`, `aifactory/pyproject.toml` (`readme`), `aifactory/src/aifactory/skill/` (`skill.md`, `render.py`, `codes.py`), `aifactory/tests/test_skill.py`.

Done means:
- `aifactory/README.md` má sekce Předpoklady (macOS, Linux nebo WSL, git s identitou, uv, gh (pro provider github) nebo az, CLI harnessů a jejich přihlášení, node pro pi, just pro výchozí testovací příkaz), Instalace z bundlu (rozbalit `haifa-<verze>.zip`, spustit `./install.sh`, bez přístupu k repu HAIFA), Kontrola (`factory check`), Knihovna (clone týmové knihovny nebo init ze semínka), Přidání repa (`factory init` pro repo bez factory, `factory adopt` pro onboardované, dashboard `factory obs`), Onboarding (jednou na repo: `factory onboard --dry-run`, pak `--commit`), Aktualizace HAIFA (`factory upgrade <bundle>`, `factory library seed`, `factory update`), Vydání (pro engineera: verze v `__init__.py`, `just check`, `just bundle`, rozeslání zipu, `min_factory_version` v knihovně) a Řešení problémů (tabulka kód kontroly a oprava).
- `pyproject.toml` uvádí README jako `readme`.
- `factory --skill` má postupy Nastavení stroje (check, library clone), Přidání repa (init, adopt), Onboarding (jednou: dry-run, zpráva, commit s `--expect`), Správa položek (add, set, export, update, where, operace ve více repech) a Upgrade.
- Testy (pytest): README obsahuje každý kód kontroly stroje a knihovny ze `skill/codes.py`, příkazy z README i ze skillu existují v parseru CLI, skill obsahuje nové postupy.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: soubory v `docs/` mimo `aifactory/`, změna `docs/product-brief.md`, nové příkazy.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
