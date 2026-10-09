---
id: HAIFA-S05-T08
title: "`factory config export`, `revert` a `diff`"
status: done
depends_on: [HAIFA-S05-T07, HAIFA-S05-T06]
---

## Zadání
Přidej přenos z repa do knihovny a zpět: export upravené nebo nové položky do knihovny, návrat kopie v repu na verzi z manifestu nebo z knihovny a diff tří verzí. Export zapíše knihovnu dřív než repo. Na exportu stojí přenos dobrého agenta do jiného repa (rozhodnutí 4).

Where: `aifactory/src/aifactory/cli.py`, `aifactory/src/aifactory/library/` (z L1 až L4 a L7), zveřejnění commitu z M7, `aifactory/src/aifactory/skill/` (`skill.md`, `codes.py`), testy v `aifactory/tests/library/`.

Done means:
- `factory config export TYP JMÉNO [--as NOVÉ] --json` zapíše kopii z repa do knihovny jako další verzi napojené položky, nebo s `--as` jako novou položku, a pak obnoví manifest v repu (napojení a verze). Položka `local` (bez záznamu v manifestu) se exportuje jako nová položka.
- Když se hlava knihovny od verze v manifestu změnila a kopie v repu se jí nerovná, export odmítne `library_changed_since` s opravou `factory update` nebo `--as`.
- Pořadí: zápis knihovny s push (L3), pak repo (pracovní strom nebo `--commit`). Odmítnutý push knihovny zastaví vše dřív, než se sáhne na repo. Selhání repa po push knihovny nechá v knihovně jen nepoužitou verzi a opakovaný export ji napojí.
- `factory config revert TYP JMÉNO [--to manifest|head] --json` vrátí kopii v repu na verzi z manifestu (z historie knihovny, jinak `unknown`) nebo na hlavu knihovny.
- `factory config diff TYP JMÉNO --json` jen čte a vrátí diff po souborech: repo proti verzi z manifestu a repo proti hlavě.
- `factory --skill` popisuje export a přenos agenta do jiného repa (export, pak `config add` v cílovém repu). Nové kódy jsou v `skill/codes.py`.
- Testy (pytest) s holým remote knihovny i repa: export upraveného promptu a add do druhého repa, `--as`, položka `local`, `library_changed_since`, odmítnutý push knihovny nechá repo beze změny, odmítnutý push repa po push knihovny a opakovaný export, revert na obě verze, diff.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: aktualizace z knihovny (M9), slučování textu, dashboard.

Pevná omezení:
- Knihovna se pushuje dřív než repo a nikdy force.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-06 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/72 · náklady $3.61
