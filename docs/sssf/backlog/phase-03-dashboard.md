# Fáze 03: Dashboard základ

Lokální dashboard nad core `aifactory`: Python backend, Vue frontend z visualizeru sssf, obrazovky Backlog, Běhy, Review a Nastavení (sekce „Dashboard“ v [briefu](../docs/product-brief.md), D3).

Hotovo, když úkol jde založit, provázat, spustit, sledovat, schválit a mergovat bez terminálu (úkol 3.8).

## Pravidla pro všechny úkoly

- Backend je v `aifactory/src/aifactory/web/` (Starlette), frontend v `aifactory/web/` (Vue 3, Vite, TypeScript, stejné závislosti a vzhled jako `vendor/sssf/apps/visualizer`). Build frontendu se přibalí do balíčku a backend ho servíruje.
- Backend nemá vlastní logiku backlogu, běhů ani PR. Volá tytéž funkce core jako CLI a vrací stejnou JSON obálku jako `--json` (úkol 2.16).
- Server poslouchá jen na `127.0.0.1`. Port a cesta k trace DB jsou v `.factory/local.yaml`.
- Dashboard se spouští příkazem `factory obs` (recept `just dash`). `just obs` zůstává visualizer vývojové factory HAIFA.
- `just test` spouští i testy a typecheck frontendu.
- Testy nevolají model. `vendor/` a `prototype/` se nemění.

## Spuštění

```bash
uv run adws/adw_simple_sdlc.py backlog/phase-03/task-3.1.md
just phases <adw_id>
```

## Úkoly a chainy

| # | Prompt | Chain | Závisí na | Proč tento chain |
|---|---|---|---|---|
| 3.1 | [task-3.1.md](phase-03/task-3.1.md) | `adw_simple_sdlc` | — | architektura backendu a frontendu, stojí za review |
| 3.2 | [task-3.2.md](phase-03/task-3.2.md) | `adw_simple_sdlc` | 3.1 | přenos visualizeru nad novou trace |
| 3.3 | [task-3.3.md](phase-03/task-3.3.md) | `adw_simple_sdlc` | 3.1 | editace backlogu z UI, zápisy do souborů |
| 3.4 | [task-3.4.md](phase-03/task-3.4.md) | `adw_simple_sdlc` | 3.3 | spouštění běhů z UI |
| 3.5 | [task-3.5.md](phase-03/task-3.5.md) | `adw_simple_sdlc` | 3.1 | schvalování a merge z UI |
| 3.6 | [task-3.6.md](phase-03/task-3.6.md) | `adw_simple_sdlc` | 3.1 | nastavení projektu a varování D4 |
| 3.7 | [task-3.7.md](phase-03/task-3.7.md) | `adw_plan_build_test` | 3.2, 3.3, 3.5 | živé aktualizace, akceptace jsou testy |
| 3.8 | [task-3.8.md](phase-03/task-3.8.md) | `adw_plan_build_test` | 3.4, 3.5, 3.6, 3.7 | akceptační test F3 v prohlížeči |
| 3.9 | [task-3.9.md](phase-03/task-3.9.md) | `adw_simple_sdlc` | 3.8 | po bráně F3: rozhodnutí zrušit vlastníka modulu, mění backend i frontend |

Pořadí: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9.

## Co musí engineer udělat sám

- **Po 3.8:** otevřít dashboard (`just dash`) a projít tok úkolu na sandboxu ručně: založit, provázat, spustit, sledovat, schválit. Hotovo 2026-09-30, brána F3 schválená (PR #38 a #39 v haifa-sandbox).

## Brána F3

F3 je hotová, když prohlížečový test z 3.8 projde a engineer potvrdí ruční průchod.
