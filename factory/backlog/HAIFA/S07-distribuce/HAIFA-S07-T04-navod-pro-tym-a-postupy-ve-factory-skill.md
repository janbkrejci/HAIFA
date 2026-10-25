---
id: HAIFA-S07-T04
title: "Návod pro tým a postupy ve `factory --skill`"
status: done
archived: true
depends_on: [HAIFA-S07-T02, HAIFA-S07-T03, HAIFA-S05-T10, HAIFA-S04-T02, HAIFA-S07-T05, HAIFA-REFINEMENT-T10, HAIFA-S10-T04]
related: [HAIFA-S06-T02, HAIFA-S06-T04, HAIFA-S05-T09, HAIFA-S07-T06]
---

## Zadání
Napiš česky návod, podle kterého si kolega HAIFA stáhne, zprovozní a přidá svoje repa, a doplň stejné postupy do `factory --skill`. Úkoly HAIFA smí zapisovat jen pod `aifactory/`, proto je návod v `aifactory/README.md`.

Návod i skill popisují jen příkazy, které CLI dnes má. Onboarding, `factory adopt`, `factory update`, `factory config export` a `factory library where` byly odstraněny (HAIFA-REFINEMENT-T10, HAIFA-S10-T04). Repa dnes položky z knihovny dědí, takže je návod nezmiňuje.

Where: nový soubor `aifactory/README.md`, `aifactory/pyproject.toml` (`readme`), `aifactory/src/aifactory/skill/` (`skill.md`, `render.py`, `codes.py`), `aifactory/tests/test_skill.py`. Pro soulad s návodem lze sáhnout i do `aifactory/bundle/INSTALL.md`.

Done means:
- `aifactory/README.md` má tyto sekce:
  - Předpoklady: macOS, Linux nebo WSL, git s identitou, uv, gh (pro provider github) nebo az, CLI harnessů a jejich přihlášení, node pro pi, just pro výchozí testovací příkaz.
  - Instalace z bundlu: rozbalit `haifa-<verze>.zip`, spustit `./install.sh`, bez přístupu k repu HAIFA.
  - Kontrola: `factory check`.
  - Knihovna: `factory library clone` týmové knihovny nebo `factory library init` ze semínka.
  - Přidání repa: `factory init` pro repo bez factory, převzetí repa s commitnutou `.factory/` na dalším stroji (clone, knihovna, `factory check`), dashboard `factory obs`.
  - Aktualizace HAIFA: `factory upgrade <bundle>`, pak `factory library seed`. Repa nové verze položek zdědí při dalším běhu.
  - Vydání (pro engineera): verze v `__init__.py`, `just check`, `just bundle`, rozeslání zipu, `min_factory_version` v knihovně.
  - Řešení problémů: tabulka s kódem kontroly a opravou.
- `pyproject.toml` uvádí README jako `readme`.
- `factory --skill` má postupy:
  - Nastavení stroje: `factory check`, `factory library clone` nebo `init`.
  - Přidání repa: `factory init`, převzetí repa s commitnutou `.factory/` na dalším stroji.
  - Správa položek: `factory library import`, `factory config add`, `set`, `remove`, `move`, `factory config commit`, dědění z knihovny.
  - Upgrade: `factory upgrade` a `factory library seed`.
  - Postupy, které skill už má, se doplní nebo propojí, ne zduplikují.
- Testy (pytest):
  - README obsahuje každý kód kontroly stroje a knihovny ze `skill/codes.py`.
  - Každý příkaz `factory …` z README i ze skillu existuje v parseru CLI.
  - Skill obsahuje nové postupy.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: soubory v `docs/` mimo `aifactory/`, změna `docs/product-brief.md`, nové příkazy, obnova odstraněného onboardingu, `adopt`, `update`, `export` a operací ve více repech.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-11 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/10 · náklady $2.07
