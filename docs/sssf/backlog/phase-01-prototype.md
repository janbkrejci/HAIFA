# Fáze 01: Prototyp

Prototyp ověří rizika R1 až R5 a R10 z [briefu](../docs/product-brief.md) dřív, než začne vývoj produktu. Je úzký a zahoditelný. Končí bránou G1: engineer schválí zprávu z úkolu 1.10.

Stav úkolů je v [BACKLOG.md](../BACKLOG.md). Prompt každého úkolu je v `backlog/phase-01/task-1.N.md` a jde spustit bez dalšího kontextu.

## Pravidla pro všechny úkoly

- Kód prototypu žije jen v `prototype/` (uv projekt, balíček `haifa_proto`, CLI `haifa-proto`).
- Engine je `vendor/sssf/templates/adws/adw_modules/`, importovaný přes `sys.path`. `vendor/` je jen ke čtení, rozšíření patří do `prototype/`.
- Testy nevolají žádný model. Agenty nahrazuje falešný harness registrovaný v `agents.INTERFACES`.
- Specifikace je brief. Když se úkol a brief rozcházejí, platí úkol a rozdíl se zapíše do zprávy 1.10.
- Jeden chain najednou. sssf commituje v hlavním checkoutu, takže paralelní běhy by si přepisovaly strom.

## Spuštění

```bash
uv run adws/adw_simple_sdlc.py backlog/phase-01/task-1.2.md
just phases <adw_id>        # sledování, dále just tail / just obs
```

## Úkoly a chainy

| # | Prompt | Chain | Závisí na | Proč tento chain |
|---|---|---|---|---|
| 1.1 | [task-1.1.md](phase-01/task-1.1.md) | `adw_plan_build_test` | — | kostra a nástroje, akceptace je zelený `just test` |
| 1.2 | [task-1.2.md](phase-01/task-1.2.md) | `adw_simple_sdlc` | 1.1 | formát backlogu nese celý produkt, stojí za review |
| 1.3 | [task-1.3.md](phase-01/task-1.3.md) | `adw_simple_sdlc` | 1.1 | nový harness, rozhraní musí sedět s Claude Code a pi |
| 1.4 | [task-1.4.md](phase-01/task-1.4.md) | `adw_simple_sdlc` | 1.1, 1.3 | ověřuje R1, jádro celého produktu |
| 1.5 | [task-1.5.md](phase-01/task-1.5.md) | `adw_simple_sdlc` | 1.2, 1.4 | worktree a omezení zápisů, chyba tady rozbije repo |
| 1.6 | [task-1.6.md](phase-01/task-1.6.md) | `adw_simple_sdlc` | 1.5 | ověřuje R3, merge do base musí sedět |
| 1.7 | [task-1.7.md](phase-01/task-1.7.md) | `adw_plan_build_test` | 1.6 | pravidla řetězení nad hotovým během, akceptace jsou testy |
| 1.8 | [task-1.8.md](phase-01/task-1.8.md) | `adw_plan_build_test` | 1.6 | jedna stránka nad existujícími funkcemi |
| 1.9 | [task-1.9.md](phase-01/task-1.9.md) | `adw_plan_build_test` | 1.7, 1.8 | skript scénářů, akceptace je jeho běh na lokálním remote |
| 1.10 | [task-1.10.md](phase-01/task-1.10.md) | `adw_build_review` | 1.9 | píše se zpráva, review potvrdí, že odpovídá na R1–R5 a R10 |
| 1.11 | [task-1.11.md](phase-01/task-1.11.md) | `adw_plan_build_test` | 1.8 | sada běží 7:42 a builder ji nestihne ověřit, akceptace je čas běhu testů |
| 1.12 | [task-1.12.md](phase-01/task-1.12.md) | `adw_simple_sdlc` | 1.7 | souběh v paralelních bězích z 1.7, oprava bezpečnosti běhů stojí za review |
| 1.13 | [task-1.13.md](phase-01/task-1.13.md) | `adw_plan_build_test` | 1.9 | codex bez kreditu, validace proti GitHubu potřebuje jiný roster, akceptace jsou testy |

Pořadí: 1.1, potom 1.2 a 1.3 v libovolném pořadí, 1.4, 1.5, 1.6, potom 1.7 a 1.8, 1.12, 1.11, 1.9, 1.13, 1.10.

## Co musí engineer udělat sám

- **Před 1.9:** hotovo 2026-09-26. Testovací repo `https://github.com/janbkrejci/haifa-sandbox` (soukromé, `main` s README) je v `.env` jako `HAIFA_SANDBOX_REPO`.
- **Před 1.10:** spustit `just proto-validate` z úkolu 1.9 proti sandboxu a nechat výsledky v `prototype/validation/`.

## Brána G1

G1 je schválená, když zpráva `docs/prototype-report.md` pro každé riziko R1–R5 a R10 uvádí výsledek, důkaz (test, trace, měření) a dopad na rozhodnutí D1–D13.
