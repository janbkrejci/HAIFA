---
id: HAIFA-S06-T04
title: Převod instalace sssf při onboardingu
status: done
workflow: simple-sdlc
depends_on: [HAIFA-S06-T03, HAIFA-S06-T01, HAIFA-S05-T05]
---

## Zadání
Rozšiř `factory onboard` o repa s instalací sssf (`adws/`). Roster, prompty, rozšíření pi, chainy a nastavení testu se jednou převedou do knihovny a do `.factory/` repa podle tabulky převodu. Zpráva řekne, co se převedlo, co mění význam a co zůstalo. `adws/` zůstane beze změny.

Where: `aifactory/src/aifactory/onboard/` (z O1 a O2), nová data `aifactory/src/aifactory/onboard/sssf_stock/`, `aifactory/src/aifactory/library/` (z L1, L2 a L8), detekce z M8, `aifactory/src/aifactory/config/settings.py`, zdroje stock dat `vendor/sssf/templates/prompt_engineering/`, `vendor/sssf/templates/adws/` a `vendor/sssf/templates/harness_engineering/`, `aifactory/src/aifactory/skill/` (`skill.md`, `codes.py`), testy v `aifactory/tests/onboard/`.

Done means:
- Převodník čte jen strom base (`ls-tree` a `cat-file`) a z rosterů jen `adws/adw_sssf_config/sssf.config.yaml`. Další rostery hlásí `alternate_rosters`.
- Agenti: `coding_agent` na `harness` (`claude_code` na `claude`), `model`, `tools`, `color` a `writes` jako vazby, `thinking: auto` na `medium` (`changed_meaning`), `purpose` do položky. `writes` `**/*.md` se ve zprávě označí. `data_dir` a `observability` se vynechají (`not_converted`). `defaults.protected_files` přejde do `config.yaml` spolu s `.factory/`. Vygenerovaný `agents.yaml` má v hlavičce odkaz na zdrojový roster.
- Prompty: balíček nese stock texty z `vendor/sssf/templates/prompt_engineering/` a jejich blob id. Stock `system.md` se nahradí promptem položky z knihovny (`linked`). Upravený `system.md` projde `git merge-file -p` (base stock, ours repo, theirs knihovna). Konflikt jen ze vložení vyřeší `--union` (`carried_over`), jiný konflikt nechá text knihovny a zpráva ocituje změnu (`manual`). `user.md` je vždy text knihovny a úprava je `manual`. Agent bez stock předlohy převezme prompty beze změny jako `manual`. Agent s výsledkem shodným s knihovnou se napojí, jinak dostane novou položku podle O2.
- `harness_engineering`: každý soubor `.ts` se svými relativními importy (`subagents.ts` táhne `themeMap.ts`) je položka rozšíření se jménem podle souboru a agent dostane vazbu `extensions`.
- Chainy podle blob id: stock `adw_plan`, `adw_plan_build`, `adw_plan_build_test`, `adw_simple_sdlc` (blob `a6a5c4c1c4be7fb2bf3de4c80cdb798c8df23ffc` i `3f5d48378a8daefb7e9dfa79af8279454db42d34`), `adw_document` a `adw_scout` mají workflow stejného jména v knihovně. Do repa jde `simple-sdlc` a s `--workflows` další. Upravené a ostatní chainy a recepty jsou `not_converted` nebo `manual`.
- `adws/adw_modules/quality.py`: argv a `timeout_seconds` testovacího bloku z literálů `QualityCheckSpec` přes `ast` (nic se nespouští) dají `test_command` a `test_timeout` (O3). `_placeholder` nic nenastaví. Lint, typecheck a build jsou `not_converted`. Jiné změny `adw_modules/` proti stock jsou `manual`.
- `.claude/skills/sssf`, justfile, `.env` a skripty jsou `left_in_place`. `config.yaml` dostane base, remote, provider a adresáře zjištěné jako v M8.
- Blokátor `sssf_not_supported` z O2 zmizí.
- `factory --skill` popisuje vytěžení sssf a zprávu. Nové kódy jsou v `skill/codes.py`.
- Testy (pytest) nad fixturami z `vendor/sssf/templates/` se záplatami: Omnibus (claude, `quality.py` s 1800 s a `just lint`), JSST (pi, rozšíření, builder a reviewer s vloženými pravidly, union), amber (čistý merge) a upravený chain. Zlaté zprávy, převedená konfigurace projde `load_config` a preflight `simple-sdlc`, bajty `adws/` beze změny, druhé spuštění vrátí `already_onboarded`.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: převod backlogu (F6 a `factory --skill`), workflow typu `script`, převod receptů, smazání `adws/`, dashboard.

Pevná omezení:
- Onboarding sssf zdroj jen čte a do repa jen přidává.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-07 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/76 · náklady $10.86
