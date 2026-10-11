---
id: HAIFA-S01-T14
title: factory update z knihovny s migracemi
status: done
workflow: simple-sdlc
depends_on: [HAIFA-S05-T07, HAIFA-S01-T12]
---

## Zadání
Přidej příkaz `factory update`, který přenese do repa nové verze položek z knihovny (bez knihovny ze semínka) a bez výslovné volby nikdy nepřepíše soubor, který repo upravilo (D20). Porovnává po souborech tři verze: verzi z manifestu, kopii v repu a hlavu knihovny. Doplní chybějící soubory, řádky `.gitignore` a manifest a nabídne migrace (D26).

Where: `aifactory/src/aifactory/cli.py`, položky, knihovna, manifest a stavy z L1, L2 a L4 a plán položek z L7 v `aifactory/src/aifactory/library/`, plán a zveřejnění commitu z M7 a M8, kontrola z M6, `aifactory/src/aifactory/config/`, `aifactory/src/aifactory/skill/` (`skill.md`, `codes.py`), testy v `aifactory/tests/`.

Done means:
- Jednotka je soubor: u agenta purpose, `system.md` a `user.md`, u workflow soubor, u skillu a rozšíření každý soubor včetně přidaných a smazaných. Base je obsah verze z manifestu (z historie knihovny), ours kopie v repu, theirs hlava knihovny.
- Pravidlo: ours = base vezme theirs, theirs = base nechá ours, ours = theirs je beze změny, jinak konflikt: ours zůstane a plán ukáže oba diffy. `--take TYP/JMÉNO[:SOUBOR]` vezme theirs. `--merge TYP/JMÉNO` vezme výsledek `git merge-file`, jen když je bez konfliktu a projde validací, jinak vrátí `merge_conflict`.
- Položka `unknown` (verze z manifestu není v historii) nemá base: plán ukáže diff ours proti theirs, výchozí je ponechat a `--take` převezme.
- Po aktualizaci ukazuje manifest na hlavu a `written_by` na nainstalovanou verzi. Chybějící prompty deklarovaných agentů, soubory položek `missing` a řádky `.gitignore` se doplní.
- Migrace: plán vypíše zjištěné migrace s diffem a provede je jen `--migrate ID`. První migrace `m001` změní `levels: [module, step, task]` na `[project, step, task]` round tripem ruamel.yaml se zachovanými komentáři. Detektor dělá migraci idempotentní.
- Režimy jako `init`: `--dry-run` (plán s digestem), bez volby zápis do pracovního stromu (blokuje `run_in_progress`), `--commit [--pr] [--expect DIGEST] [-m TEXT]` jedním commitem cestou z M7.
- Odmítne repo bez manifestu (`not_onboarded`, poradí `factory onboard` nebo `factory init`), konfiguraci jen v pracovním stromu (`config_not_committed`) a formát, který HAIFA nezná (`format_unsupported`).
- `factory check` hlásí `update_available`.
- `factory --skill` popisuje postup aktualizace. Nové kódy jsou v `skill/codes.py`.
- Testy (pytest): nahrazení, ponechání, konflikt s `--take` i `--merge`, `merge_conflict`, `unknown`, chybějící prompt, skill s přidaným a smazaným souborem, `m001` se zachovanými komentáři a druhý běh bez migrace, druhý update beze změn, commit s holým remote, repo bez manifestu.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: aktualizace více rep (L9), semínko do knihovny (L10), dashboard.

Pevná omezení:
- Kopie upravená v repu se bez `--take` nebo `--merge` nepřepíše a text se nikdy nesloučí sám.
- `.factory/` repa HAIFA se nemění.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-07 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/74 · náklady $7.00
