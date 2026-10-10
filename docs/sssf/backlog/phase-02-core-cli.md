# Fáze 02: Core a CLI

Balíček `aifactory` s CLI `factory`: engine přenesený ze sssf s testy, konfigurace `.factory/`, backlog, interpret workflow, běh ve worktree až po PR a `GitProvider`. Rozsah je F2 v sekci Plán v [briefu](../docs/product-brief.md), upravený rozhodnutími po zprávě z prototypu (sekce „Rozhodnutí po zprávě z prototypu“ v [BACKLOG.md](../BACKLOG.md)).

Hotovo, když na ukázkovém repu projde z CLI 5 úkolů, z toho 2 paralelně, od `factory task run` po mergnutý PR a stav `done` (úkol 2.18).

## Pravidla pro všechny úkoly

- Kód žije v `aifactory/` (uv projekt, balíček `aifactory`, CLI `factory`). `prototype/` je reference: kód se z něj přenáší, prototyp se nemění.
- Engine je v balíčku (`aifactory/src/aifactory/engine/`), ne ve `vendor/`. `vendor/` je jen ke čtení.
- Testy nevolají žádný model. Agenty nahrazuje falešný harness.
- Specifikace je brief plus rozhodnutí v `BACKLOG.md`. Když se úkol a brief rozcházejí, platí úkol.
- Jeden chain najednou. sssf commituje v hlavním checkoutu.

## Rozhodnutí z G1, která F2 zapracuje

| Rozhodnutí | Úkol |
|---|---|
| Konfigurace běhu se čte celá z commitu v `base`, necommitnutá konfigurace dává varování (O16, D4) | 2.4 |
| `until` v `repeat` se vyhodnocuje po každém kroku těla, smyčka končí hned (O18, D7) | 2.7 |
| Zápis mimo worktree a mimo povolené cesty se hlídá kódem a vrací, prázdný commit běh neshodí (B1) | 2.3, 2.9 |
| Výstupy (specs, docs) se jmenují podle tasku, čitelně pro člověka (N6) | 2.9 |
| Schválení zatím bez approve review, rovnou merge. K dodělání (N2, D11) | 2.12 |
| `backlog sync` zapisuje `done` přes PR (N4, D6) | 2.13 |
| Workflow `resolve` je povinný (N5) | 2.14 |
| Azure DevOps se implementuje, ověří se proti falešnému `az`, živě až bude k dispozici (N5, D8) | 2.11 |
| Opravná kola se ve validaci vynutí (B2) | 2.17 |

## Spuštění

```bash
uv run adws/adw_simple_sdlc.py backlog/phase-02/task-2.2.md
just phases <adw_id>
```

## Úkoly a chainy

| # | Prompt | Chain | Závisí na | Proč tento chain |
|---|---|---|---|---|
| 2.1 | [task-2.1.md](phase-02/task-2.1.md) | `adw_plan_build_test` | — | kostra a nástroje, akceptace je zelený `just test` |
| 2.2 | [task-2.2.md](phase-02/task-2.2.md) | `adw_simple_sdlc` | 2.1 | přenos enginu, regrese jsou riziko R6 |
| 2.3 | [task-2.3.md](phase-02/task-2.3.md) | `adw_simple_sdlc` | 2.2 | tři harnessy se stejným rozhraním, kontrakt musí sedět |
| 2.4 | [task-2.4.md](phase-02/task-2.4.md) | `adw_simple_sdlc` | 2.1 | konfigurace z base mění, co běh vidí (R4) |
| 2.5 | [task-2.5.md](phase-02/task-2.5.md) | `adw_simple_sdlc` | 2.4 | formát backlogu nese celý produkt |
| 2.6 | [task-2.6.md](phase-02/task-2.6.md) | `adw_plan_build_test` | 2.5 | příkazy nad hotovou knihovnou, akceptace jsou testy |
| 2.7 | [task-2.7.md](phase-02/task-2.7.md) | `adw_simple_sdlc` | 2.2, 2.4 | jádro workflow, nová sémantika smyček |
| 2.8 | [task-2.8.md](phase-02/task-2.8.md) | `adw_plan_build_test` | 2.7 | přenos YAML souborů, akceptace jsou testy |
| 2.9 | [task-2.9.md](phase-02/task-2.9.md) | `adw_simple_sdlc` | 2.3, 2.5, 2.7 | izolace běhu, chyba tady rozbije repo (Z1) |
| 2.10 | [task-2.10.md](phase-02/task-2.10.md) | `adw_simple_sdlc` | 2.1 | rozhraní providera nese GitHub i Azure DevOps |
| 2.11 | [task-2.11.md](phase-02/task-2.11.md) | `adw_plan_build_test` | 2.10 | implementace hotového rozhraní, akceptace jsou testy |
| 2.12 | [task-2.12.md](phase-02/task-2.12.md) | `adw_simple_sdlc` | 2.9, 2.10 | tok PR a stav done (R3) |
| 2.13 | [task-2.13.md](phase-02/task-2.13.md) | `adw_simple_sdlc` | 2.12 | stav v base se mění přes PR |
| 2.14 | [task-2.14.md](phase-02/task-2.14.md) | `adw_simple_sdlc` | 2.8, 2.12 | řešení konfliktů agentem, riziko R2 |
| 2.15 | [task-2.15.md](phase-02/task-2.15.md) | `adw_plan_build_test` | 2.12 | přenos auto-continue, akceptace jsou testy |
| 2.16 | [task-2.16.md](phase-02/task-2.16.md) | `adw_simple_sdlc` | 2.6, 2.13, 2.14, 2.15 | skill čtou agenti, stojí za review |
| 2.17 | [task-2.17.md](phase-02/task-2.17.md) | `adw_plan_build_test` | 2.16 | validační scénáře, akceptace je jejich běh v local režimu |
| 2.18 | [task-2.18.md](phase-02/task-2.18.md) | `adw_plan_build_test` | 2.17 | akceptační scénář F2 |
| 2.19 | [task-2.19.md](phase-02/task-2.19.md) | `adw_simple_sdlc` | 2.18 | validace proti GitHubu odhalila nesoulad promptů s pojmenováním z 2.9 |
| 2.20 | [task-2.20.md](phase-02/task-2.20.md) | `adw_plan_build_test` | 2.19 | sada běží přes 10 min a fáze test naráží na limit, akceptace je čas běhu |
| 2.21 | [task-2.21.md](phase-02/task-2.21.md) | `adw_plan_build_test` | 2.20 | validace proti GitHubu: R10 bez skrytého testu, resolve bez opravy testů, akceptace jsou testy |
| 2.22 | [task-2.22.md](phase-02/task-2.22.md) | `adw_plan_build_test` | 2.21 | validace s claude haiku: agent commituje sám, sync větev koliduje s remote, akceptace jsou testy |
| 2.23 | [task-2.23.md](phase-02/task-2.23.md) | `adw_simple_sdlc` | 2.22 | ochrana necommitnuté práce engineera, stojí za review |

Pořadí: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12, 2.13, 2.14, 2.15, 2.16, 2.17, 2.18, 2.19, 2.20, 2.21, 2.22, 2.23.

## Co musí engineer udělat sám

- **Po 2.18:** spustit `just validate --remote github --roster <roster>` proti sandboxu a nechat výsledky v `aifactory/validation/results/`.
- **Až bude kredit na codex:** spustit validaci s rosterem, který codex obsahuje (R1 se třemi harnessy, R10).
- **Až bude Azure DevOps:** ověřit provider proti skutečnému repu.

## Brána F2

F2 je hotová, když `just validate --remote github` projde akceptačním scénářem 2.18 (5 úkolů, 2 paralelně, mergnuté PR, `status: done` v base) a scénáři R1–R5 bez `failed`.
