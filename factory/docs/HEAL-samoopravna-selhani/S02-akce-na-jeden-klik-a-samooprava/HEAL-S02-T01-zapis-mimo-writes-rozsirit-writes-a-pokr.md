# HEAL-S02-T01: Zápis mimo writes: rozšířit writes a pokračovat

## Co se změnilo

Když běh selže na `writes_violation`, karta selhání v detailu běhu nabídne
**Povolit tyto cesty a pokračovat**. V CLI dělá totéž `factory task retry ID --allow-writes`.

Akce:

1. vezme cesty, které agent zapsal ve worktree mimo writes (`failure_detail.paths`),
2. přidá je do vlastních `writes` tasku (dosavadní efektivní writes + nové cesty) přes
   `backlog/edit`,
3. commitne backlog do base podle `base_changes` (`commit_backlog`),
4. spustí `factory task retry` téhož běhu. Agent fázi zopakuje a cesty už smí zapsat.

Cesty, které akce nepřidá, karta vypíše pod „Tyto cesty akce nepovolí“ i s důvodem:

| Důvod (`reason`) | Kdy |
| --- | --- |
| `protected` | cesta v `protected_files` (`config.yaml` nebo `agents.yaml`) |
| `backlog` | cesta v backlogu; backlog zapisuje jen factory |
| `main_checkout` | zápis do hlavního checkoutu mimo worktree běhu |
| `already_allowed` | writes tasku ji už povolují; zápis zakázaly writes agenta v `agents.yaml` |

Když akce nemá co přidat, tlačítko se neukáže a CLI skončí chybou `nothing_to_allow`.
Při `base_changes: pr` bez okamžitého merge čeká změna v PR backlogu. Běh se pak
nespustí (`writes_in_pr`), retry spusť až po merge.

## Data

- Guard běhu (`run/guard.py`) teď do `failure_detail` zapisuje i `paths` (vrácené cesty
  ve worktree) a `main_paths` (cesty v hlavním checkoutu). U staršího běhu se cesty
  worktree čtou z `problems`.
- Logika je v `run/allow_writes.py` (`plan_allow_writes`, `allow_writes`).
- API: `GET /api/runs/{id}/allow-writes` vrací plán (`allow`, `refused`, `writes`).
  `POST /api/runs/{id}/allow-writes` rozšíří writes a spustí retry (HTTP 202,
  `{allow_writes, task_id, action, run, pending}`).
- CLI `--json` vrací plán a commit v `data.allow_writes`. Nové chybové kódy:
  `not_writes_violation`, `nothing_to_allow`, `writes_in_pr`.

## Testy

- `tests/run/test_allow_writes.py`: běh selže na zápisu mimo writes,
  `task retry --allow-writes` rozšíří writes v base a retry doběhne. Chráněné cesty,
  backlog a hlavní checkout se odmítnou. Jiný druh selhání se odmítne. Cesty staršího
  běhu se čtou z `problems`. Při `base_changes: pr` s nemergnutým PR backlogu skončí
  `writes_in_pr`, base se nepohne a retry se nespustí. Plán a akce jdou i přes API.
- `web/src/components/runs/FailureCard.test.ts`: tlačítko, potvrzení, POST a výpis
  odmítnutých cest.
