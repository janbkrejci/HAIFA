---
id: HAIFA-S06-T03
title: "Jednorázový onboarding (`factory onboard`) a `.factory/` z doby před knihovnou"
status: done
workflow: simple-sdlc
depends_on: [HAIFA-S06-T02, HAIFA-S05-T08, HAIFA-S01-T12]
---

## Zadání
Přidej `factory onboard`, který jednou vytěží konfiguraci repa do knihovny a do commitnuté `.factory/` s manifestem a značkou onboardingu (rozhodnutí 8). Tento úkol řeší repo s `.factory/` z doby před knihovnou (HAIFA, haifa-sandbox) a rámec, na který O4 přidá převod sssf. Vytěžení proběhne jen na prvním stroji: plán ověří remote base a pevnou větev PR a knihovna se pushne dřív než repo.

Where: `aifactory/src/aifactory/onboard/` (z O1), `aifactory/src/aifactory/library/` (z L1 až L4, L7 a L8), plán, digest a zveřejnění commitu z M7 a M8, `aifactory/src/aifactory/providers/` (`git.py`, `base.py`), `aifactory/src/aifactory/backlog/`, `aifactory/src/aifactory/cli.py`, `aifactory/src/aifactory/skill/` (`skill.md`, `codes.py`), testy v `aifactory/tests/onboard/`.

Done means:
- `factory onboard [--repo] [--dry-run | --commit [--pr] [--expect DIGEST] [-m TEXT]] [--keep-local TYP/JMÉNO]… [--name TYP/JMÉNO=NOVÉ]… --json`. Bez `--commit` vrátí jen plán a pracovní strom se nemění.
- Blokátory: stav není `pre_library` (`already_onboarded`, `not_installed`, `config_not_committed`, `sssf_not_supported` do O4), zdrojová konfigurace má necommitnuté změny (`source_not_committed`), blokátory M7, `library_missing`, `library_dirty`, `library_behind` a `library_diverged`.
- Kontrola remote je jediný síťový krok: `git fetch <remote> <base>` a `git ls-remote --heads <remote> factory-config/onboarding`. Manifest v remote base dá `onboarded_in_remote` (oprava `factory config pull`, pak `factory adopt`), existující větev `onboarding_pending` a nedostupný remote `remote_unchecked`. Repo bez remote dostane varování `no_remote`.
- Agenti (purpose a prompty) a workflow v `.factory/` se zahashují. Obsah, který knihovna má (verze v historii položky stejného jména nebo hlava jiné položky), se napojí. Jiný obsah dostane novou položku `<jméno>`, když je volné, jinak `<jméno>-<slug kořenové složky repa>` (D30). `--keep-local` napojí slot na položku stejného jména a rozdíl nechá v repu, `--name` určí jméno nové položky. Workflow, která jmenuje backlog v base a v repu chybí, se přidají z knihovny.
- Existující soubory `.factory/` zůstanou bajtově stejné. Plán přidá manifest s blokem `onboarding` (`source: pre_library`, `source_commit`, `at`, `by` z `git config user.name`, `factory`, `library_commit`), chybějící workflow a řádky `.gitignore`.
- Plán projde `load_config` a preflight každého workflow v repu. Digest pokrývá část knihovny (obsahy a sha hlavy) i část repa. Zpráva po kódech (`linked`, `converted`, `carried_over`, `changed_meaning`, `not_converted`, `manual`, `left_in_place`) je v `--json`, ve zprávě commitu i v popisu PR.
- `--commit`: plán se přepočítá (`plan_changed`), knihovna dostane commit a push (L3) a odmítnutí zastaví vše před zápisem do repa. Repo dostane commit bez checkoutu (M7) přímo do base, nebo s `--pr` PR z větve `factory-config/onboarding`.
- `factory --skill` popisuje postup: `--dry-run`, ukázat zprávu, soubory a digest uživateli, pak `--commit --expect`. Nové kódy jsou v `skill/codes.py`.
- Testy (pytest) s holými remote: kopie `.factory/` HAIFA (agenti se rovnají semínku, knihovna beze změny, přibude manifest a workflow backlogu), kopie haifa-sandbox (upravení agenti jako nové položky, s `--keep-local` napojení), `already_onboarded`, `onboarded_in_remote` z druhého klonu, `onboarding_pending`, `remote_unchecked`, odmítnutý push knihovny nechá repo beze změny, odmítnutý push repa po push knihovny a opakování, bajty zdroje beze změny, druhý `onboard` po úspěchu.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: převod sssf (O4), dashboard, smazání `adws/`, převod backlogu (F6).

Pevná omezení:
- Onboarding commituje jen přidané soubory pod `.factory/` a řádky `.gitignore`.
- Knihovna se pushuje dřív než repo a nikdy force.
- `.factory/` repa HAIFA se nemění (HAIFA onboarduje engineer).
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-06 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/75 · náklady $7.07
