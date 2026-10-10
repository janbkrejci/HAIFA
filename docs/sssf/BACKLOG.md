# HAIFA — Master Backlog

Zadání úkolů jsou v souborech fází vedle tohoto. Řádek je odkaz, ne specifikace: před spuštěním si přečti soubor fáze a prompt úkolu. Specifikace produktu je [docs/product-brief.md](docs/product-brief.md).

Legenda: 🔲 TODO · 🔄 IN PROGRESS · ✅ DONE · ❌ FAILED

## Fáze 00: Příprava repa

| # | Úkol | Chain | Závisí na | Status | adw_id | Commit | Docs |
|---|---|---|---|---|---|---|---|
| 0.1 | Git repo, `vendor/sssf` (snapshot sssf `aa8b55c`), instalace sssf, roster z Omnibusu, backlog fáze 01 | ručně | — | ✅ | — | první commit | — |

## Fáze 01: Prototyp

Soubor fáze: [backlog/phase-01-prototype.md](backlog/phase-01-prototype.md). Prompty: `backlog/phase-01/task-1.N.md`.

| # | Úkol | Chain | Závisí na | Status | adw_id | Commit | Docs |
|---|---|---|---|---|---|---|---|
| 1.1 | Kostra prototypu: uv projekt, CLI `haifa-proto`, recepty test/typecheck/lint | `adw_plan_build_test` | — | ✅ | `ce59401f` | `a43e84b` | — |
| 1.2 | Backlog: strom modul → step → task, validace, odvozený stav, `backlog check/list` | `adw_simple_sdlc` | 1.1 | ✅ | `f2a0270a` | `194ae0f` | — |
| 1.3 | Harness Codex a registr harnessů claude/codex/pi, kontraktové testy | `adw_simple_sdlc` | 1.1 | ✅ | `bdd44bbe` | `9edba75` | — |
| 1.4 | Interpret YAML workflow s volbou harnessu po krocích, `simple-sdlc.yaml` | `adw_simple_sdlc` | 1.1, 1.3 | ✅ | `68b41af8` | `b426aed` | — |
| 1.5 | Běh tasku ve worktree, omezení zápisů na task, `task_runs` | `adw_simple_sdlc` | 1.2, 1.4 | ✅ | `4a10f3b6` | `6dd36f0` | — |
| 1.6 | PR: `GitProvider` local a github, approve s commitem done, return, `backlog sync` | `adw_simple_sdlc` | 1.5 | ✅ | `1ecab8c6` | `b69889d` | — |
| 1.7 | Auto-continue a bezpečné paralelní běhy | `adw_plan_build_test` | 1.6 | ✅ | `5eedb417` | `2091245` | — |
| 1.8 | Review stránka (Starlette): seznam PR, Schválit, Vrátit | `adw_plan_build_test` | 1.6 | ✅ | `e273bee4` | `750862c` | — |
| 1.9 | Validační scénáře R1–R5 a R10, `just proto-validate` | `adw_plan_build_test` | 1.7, 1.8 | ✅ | `1c2e5607` | `97fc864` | — |
| 1.10 | Zpráva z prototypu `docs/prototype-report.md` (podklad pro G1) | `adw_build_review` | 1.9 | ✅ | `37c2fd7e` | `0a1a3a4` | — |
| 1.11 | Zrychlení testové sady: `just test` do 2 minut | `adw_plan_build_test` | 1.8 | ✅ | `e1f8b8ce` | `120de76` | — |
| 1.12 | Oprava souběhu SQLite při prvních paralelních bězích | `adw_simple_sdlc` | 1.7 | ✅ | `f09e5c20` | `d5d67cf` | — |
| 1.13 | Validace: volba `--roster`, R1 a R10 `inconclusive` bez codexu | `adw_plan_build_test` | 1.9 | ✅ | `cf0aef06` | `2e58dc7` | — |

Testovací repo pro 1.9 je [janbkrejci/haifa-sandbox](https://github.com/janbkrejci/haifa-sandbox) (soukromé), zapsané v `.env` jako `HAIFA_SANDBOX_REPO`. Před 1.10 spustí engineer `just proto-validate --remote github`.

## Rozhodnutí po zprávě z prototypu (vstup pro F2)

Podklad: [docs/prototype-report.md](docs/prototype-report.md), 2026-09-27.

- **G1:** pokračuje se do F2. R10 (Codex) a Codex v R1 se ověří, až bude kredit na codex.
- **Oprava zápisů mimo worktree (Z1):** povinná v F2.
- **Opravná kola (fix, revise):** vynutit ve validaci, aby smyčky `repeat` a `when` proběhly.
- **K dodělání, schválení vlastního PR (D11):** zatím HAIFA approve review přeskočí a rovnou merguje. Approve review jménem uživatele nebo přes bota se dodělá později.
- **`backlog sync` (D6):** `done` se zapisuje přes PR, ne přímo do base.
- **Konflikty PR (D8):** workflow `resolve` je povinný. Azure DevOps se bude používat, teď ale není k dispozici k ověření.
- **Pojmenování výstupů:** specs a app_docs se jmenují podle tasku (čitelně pro člověka), ne podle `adw_id`.
- **Konfigurace běhu (D4):** běh čte veškerou konfiguraci z commitu v `base`. Necommitnutá konfigurace dává varování v CLI i dashboardu.
- **Smyčky (D7):** `until` se vyhodnocuje po každém kroku těla `repeat` a smyčka končí hned. Po posledním zamítnutí review se `revise` nespouští.
- **Prázdný commit (B1):** krok commit bez změn běh neshodí. Zápisy mimo worktree a povolené cesty se hlídají kódem.
- **Vlastník modulu (2026-10-01):** institut vlastníka se ruší. Pole `owner` v `index.md` se ignoruje a dashboard podle něj nefiltruje (úkol 3.9). Brief ho zatím zmiňuje v sekci Cíl a rozsah, v tabulce Dashboard a v D11.

## Fáze 02: Core a CLI

Soubor fáze: [backlog/phase-02-core-cli.md](backlog/phase-02-core-cli.md). Prompty: `backlog/phase-02/task-2.N.md`.

| # | Úkol | Chain | Závisí na | Status | adw_id | Commit | Docs |
|---|---|---|---|---|---|---|---|
| 2.1 | Kostra `aifactory`: uv projekt, CLI `factory`, recepty test/typecheck/lint | `adw_plan_build_test` | — | ✅ | `0c31615d` | `5da5ab2` | — |
| 2.2 | Engine sssf přenesený do balíčku, testy chování (R6) | `adw_simple_sdlc` | 2.1 | ✅ | `6a19967f` | `38e2f71` | — |
| 2.3 | Harnessy claude/codex/pi, registr, kontraktové testy | `adw_simple_sdlc` | 2.2 | ✅ | `751a0ea3` | `19abb2e` | — |
| 2.4 | Konfigurace `.factory/` z commitu v base, varování na necommitnuté změny | `adw_simple_sdlc` | 2.1 | ✅ | `6cf89842` | `9b3ed57` | — |
| 2.5 | Backlog knihovna, `backlog check/list` | `adw_simple_sdlc` | 2.4 | ✅ | `4c2110c9` | `961fe1b` | — |
| 2.6 | `task add/edit/show/list/link` | `adw_plan_build_test` | 2.5 | ✅ | `faa6efc2` | `cd5234f` | — |
| 2.7 | Interpret workflow, `until` po každém kroku, krok `command` | `adw_simple_sdlc` | 2.2, 2.4 | ✅ | `6c1e6fb5` | `698f92e` | — |
| 2.8 | YAML verze stávajících ADW | `adw_plan_build_test` | 2.7 | ✅ | `d9597475` | `6a10bcd` | — |
| 2.9 | `task run` ve worktree, hlídání zápisů mimo worktree, výstupy podle tasku | `adw_simple_sdlc` | 2.3, 2.5, 2.7 | ✅ | `98991696` | `f8d7db9` | — |
| 2.10 | `GitProvider` github a local, mergeability | `adw_simple_sdlc` | 2.1 | ✅ | `02f264c1` | `c5da828` | — |
| 2.11 | Provider Azure DevOps proti falešnému `az` | `adw_plan_build_test` | 2.10 | ✅ | `a1328d04` | `04a1605` | — |
| 2.12 | PR tok: approve (zatím bez approve review), return, closed, úklid | `adw_simple_sdlc` | 2.9, 2.10 | ✅ | `7c3b89ff` | `4b4bd60` | — |
| 2.13 | `backlog sync` přes PR | `adw_simple_sdlc` | 2.12 | ✅ | `077275cc` | `1e1230b` | — |
| 2.14 | Workflow `resolve` a `task resolve` | `adw_simple_sdlc` | 2.8, 2.12 | ✅ | `89c73e8f` | `f52fda7` | — |
| 2.15 | Auto-continue a paralelní běhy | `adw_plan_build_test` | 2.12 | ✅ | `3ff1e5a8` | `4f730f0` | — |
| 2.16 | `factory --skill` a jednotné `--json` | `adw_simple_sdlc` | 2.6, 2.13, 2.14, 2.15 | ✅ | `82d061a3` | `4c14dcf` | — |
| 2.17 | Validace v `aifactory` s vynucenými opravnými koly | `adw_plan_build_test` | 2.16 | ✅ | `ff253d91` | `2bbab04` | — |
| 2.18 | Akceptační scénář F2: 5 úkolů, 2 paralelně | `adw_plan_build_test` | 2.17 | ✅ | `0190342e` | `e2cb085` | — |
| 2.19 | Názvy výstupů v promptech podle tasku, falešný harness čte prompt | `adw_simple_sdlc` | 2.18 | ✅ | `cdb67cc3` | `30cb005` | — |
| 2.20 | Zrychlení testové sady `aifactory`: paralelní běh | `adw_plan_build_test` | 2.19 | ✅ | `1a545cb0` | `0b0603c` | — |
| 2.21 | Validace: skrytý test R10 se spustí, `resolve` se smyčkou test → fix | `adw_plan_build_test` | 2.20 | ✅ | `80f76a2b` | `d1a7949` | — |
| 2.22 | Agenti necommitují (prompty), unikátní větev `backlog sync` | `adw_plan_build_test` | 2.21 | ✅ | `76f87ca9` | `545fedd` | — |
| 2.23 | Hlídač obnoví necommitnutou práci v hlavním checkoutu, `context_handoff_dir` v promptech, R10 nehlásí selhání jako inconclusive | `adw_simple_sdlc` | 2.22 | ✅ | `15965f89` | `79d30cc` | — |

## Otevřené body

Věci, které zůstaly po fázi 02 neověřené nebo dočasné. Každá fáze je při plánování projde a zařadí, co jde.

| # | Bod | Proč je otevřený | Co ho uzavře |
|---|---|---|---|
| OB1 | R1 se třemi harnessy (claude, codex, pi) v jednom workflow | codex bez kreditu, pi s modelem space bunny nevracel platný JSON (validace `github-160918`) | `just validate --remote github` s rosterem, který má codex i pi, R1 `passed` |
| OB2 | R10: opravné kolo v Codex threadu (`codex exec resume`) | codex bez kreditu | tatáž validace, R10 `passed` |
| OB3 | Approve review jménem uživatele při schválení (D11) | GitHub nedovolí schválit vlastní PR, factory zatím rovnou merguje | approve review přes jiný účet nebo bota, ověřené proti GitHubu |
| OB4 | Provider Azure DevOps proti skutečnému repu (D8) | Azure DevOps teď není k dispozici, provider je ověřený jen proti falešnému `az` | validace s `--remote` na Azure DevOps |
| OB5 | Spolehlivý model na pi | space bunny nevracel platný JSON envelope | výběr modelu pro pi a roster s ním bez `failed` |
| OB6 | Doba testové sady `aifactory` | časové cíle se v 2.20 neověřily kvůli přetíženému stroji | změřit `just test` na klidném stroji, případně úkol na zrychlení |
| OB7 | Náklad worktree na velkém projektu (.NET, `node_modules`) (R5) | sandbox je malý Python projekt | měření na skutečném projektu migrace |

Brána F2 je splněná během `aifactory/validation/results/2026-09-29/github-075535` (F2 a R2–R5 `passed`, R1 a R10 `inconclusive` kvůli OB1 a OB2).

## Fáze 03: Dashboard základ

Soubor fáze: [backlog/phase-03-dashboard.md](backlog/phase-03-dashboard.md). Prompty: `backlog/phase-03/task-3.N.md`.

| # | Úkol | Chain | Závisí na | Status | adw_id | Commit | Docs |
|---|---|---|---|---|---|---|---|
| 3.1 | Kostra dashboardu: Starlette backend, Vue frontend z visualizeru, `factory obs` | `adw_simple_sdlc` | — | ✅ | `772ae67d` | `2669429` | — |
| 3.2 | Obrazovka Běhy: běhy, fáze, trace, náklady, zastavení | `adw_simple_sdlc` | 3.1 | ✅ | `bacc11a0` | `f2d24a4` | — |
| 3.3 | Obrazovka Backlog: strom, kanban, detail, založení, editace, vazby | `adw_simple_sdlc` | 3.1 | ✅ | `8c8992eb` | `22467a8` | — |
| 3.4 | Backlog: graf závislostí, spuštění tasku, auto-continue | `adw_simple_sdlc` | 3.3 | ✅ | `70e41add` | `c5fccad` | — |
| 3.5 | Obrazovka Review: PR, diff, schválit, vrátit, vyřešit konflikt | `adw_simple_sdlc` | 3.1 | ✅ | `4b27b2b8` | `7010a1d` | — |
| 3.6 | Obrazovka Nastavení a varování na necommitnutou konfiguraci | `adw_simple_sdlc` | 3.1 | ✅ | `ce6aa09c` | `0f38d1b` | — |
| 3.7 | Živé aktualizace: sledování souborů, SSE, trace s kurzorem | `adw_plan_build_test` | 3.2, 3.3, 3.5 | ✅ | `ad4ac9b6` | `90af12f` | — |
| 3.8 | Akceptační test F3 v prohlížeči | `adw_plan_build_test` | 3.4, 3.5, 3.6, 3.7 | ✅ | `64ca0060` | `3adcfff` | — |
| 3.9 | Odstranění vlastníka modulu z backlogu, API a dashboardu | `adw_simple_sdlc` | 3.8 | ✅ | `b2259a94` | `e403928` | — |

Brána F3 je schválená 2026-09-30 ručním průchodem v dashboardu na `~/Documents/haifa-f3-walkthrough/repo` (base `haifa-validate/20260930-071816`, roster `claude-haiku`): založení, vazba, spuštění, sledování, schválení a merge bez terminálu. Tasky M01-S01-T04 (běh `d84de36d`, $0.28, PR [#38](https://github.com/janbkrejci/haifa-sandbox/pull/38)) a M01-S01-T05 (běh `9aa6e3b9`, $0.19, PR [#39](https://github.com/janbkrejci/haifa-sandbox/pull/39)), oba `done` v base. Příprava repa: `aifactory/validation/results/2026-09-30/github-071816`.

## Fáze 04 až 06

Rozpracují se po F3: F4 Editory, F5 Dokumenty, F6 Přechod. Obsah a kritéria hotovo jsou v sekci Plán v briefu.

---

## Current Position

**Aktivní úkol:** —
**Hotovo:** 9 / 9 (fáze 03)
**Na řadě:** —
