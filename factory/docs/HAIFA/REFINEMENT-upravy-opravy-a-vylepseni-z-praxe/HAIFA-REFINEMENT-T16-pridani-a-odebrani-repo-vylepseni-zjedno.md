# HAIFA-REFINEMENT-T16: přidání a odebrání repa

## Přidání repa, které už factory má

Má-li base repa `.factory/config.yaml`, přidání v dashboardu (`POST /api/repos`, `web.repos.add_repo`)
repo jen zaregistruje: nic necommitne ani nepushne. Řádky runtime dat factory (`.factory/data/`,
`.factory/worktrees/`, `.factory/local.yaml`, `.factory/trace.db*`), které v `.gitignore` chybí, zapíše
do `info/exclude` tohoto klonu. Odpověď má `install.committed: false` a prázdné `files`.

Karta repa na stránce Přidat repozitář u nainstalovaného repa napíše, že přidání repo jen připojí, a
nenabízí volbu pull requestu ani tlačítko Synchronizovat s knihovnou. Repo bez factory (nebo s
necommitnutou konfigurací) se instaluje commitem jako dřív.

## Odebrání repa

Odebrání z dashboardu (`DELETE /api/repos/{id}`) repo jen odpojí: smaže záznam v registru a zavře jeho
živý hub. Složka `.factory/`, backlog, specifikace, dokumentace ani historie repa se nemění. Dialog už
nečte plán odinstalace (`GET /api/repos/{id}/removal`) a posílá `{uninstall: false}`. Výchozí hodnota
`uninstall` v API je `false`; `{uninstall: true}` dál commitne smazání `.factory/` (pro skripty).

## Ověření

- `cd aifactory && uv run pytest tests/web/test_web_repos.py -n0`
- `cd aifactory/web && bun x vitest run src/views/OverviewView.test.ts src/views/ReposAddView.test.ts src/App.test.ts`
- prohlížeč: `tests/e2e/test_f3_browser.py`, `tests/e2e/test_multi_repo_browser.py`
