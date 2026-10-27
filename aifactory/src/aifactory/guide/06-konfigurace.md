# Konfigurace repa, agenti a workflow

Konfigurace je v `.factory/` repa: `config.yaml`, `agents.yaml` (roster agentů), volitelně `roles.yaml`, `workflows/` a `prompts/<agent>/`. Mimo git zůstávají `local.yaml` (trace DB, `database_url`), `trace.db` a `worktrees/`. Co repo nemá, dědí z knihovny.

**Běhy čtou sdílenou konfiguraci z commitu v base.** Změnu commitni ikonou s tooltipem **Necommitnutá konfigurace** nebo `factory config commit` (na chráněnou base `--pr`). `factory config show` ukáže konfiguraci běhu.

## config.yaml

| Klíč | Výchozí | Význam |
| --- | --- | --- |
| `base`, `remote` | `main`, `origin` | Cílová větev a remote. |
| `git_provider` | `local` | `local`, `github` (`gh`), `azure` (`az`, sekce `azure`). |
| `merge_strategy` | `squash` | `squash` nebo `merge`. |
| `github_approver` | — | Jiný účet v `gh`, který při schválení pošle approve review. |
| `base_changes` | `direct` | `pr`: každou změnu base pošle factory pull requestem. |
| `base_pr_merge` | `manual` | `auto`: tyto PR factory hned schválí a mergne. |
| `docs_root` | `factory` | Kořen `backlog/`, `specs/`, `docs/`. |
| `protected_files` | `[".factory/"]` | Cesty, které agenti nemění. |
| `max_parallel_runs` | `1` | Sloty pro souběžné tasky. |
| `stacked_prs` | `false` | Navazující PR na PR závislostí. |
| `test_timeout`, `test_slots` | 600, `1` | Limit testů a souběžné testy na počítači. |

Další klíče: `levels`, `workdir`, `worktrees_dir`, `generated`.

## Záložka Factory

- **Stav repa**, **Nainstalovat factory**, **Stáhnout konfiguraci z base** a po instalaci **Co dál**.
- **Souhrn kontroly** a nálezy repa; vybrané opraví agent (**Vyřešit vybrané nálezy**).
- **Nastavení repozitáře:** **Sdílené nastavení repozitáře** (mimo jiné **Změny base**, **Merge pull requestů factory**, **Stacked pull requesty**) a **Lokální necommitované nastavení** (trace DB). **Uložit** zapisuje do pracovního stromu.
- **Nastavení agentů:** harness, model a přemýšlení agentů, **zděděno**, nebo **přepsáno**; **Upravit** a **Vrátit na zděděné**.

## Agenti a harness

Výchozí agenti: planner, scout, builder, tester, test-reviewer, reviewer, documenter. Agent má `harness` (vždy explicitně), `model`, `thinking` a `writes`. Celý roster přepneš `factory config roster set claude` (nebo `codex`).

Harness a model od nejslabšího po nejsilnější: roster repa, výchozí volby počítače (dialog **Harnessy tohoto počítače**), task (nebo jeho step a projekt), volba pro jeden běh, přepis na kroku workflow.

## Workflow

| Workflow | Co dělá |
| --- | --- |
| `build`, `build-test` | Implementace; bez testů, nebo do zelených testů. |
| `build-review` | Implementace a review (dokumentace). |
| `build-test-review` | Implementace, testy, review; přesné zadání. |
| `plan`, `plan-build`, `plan-build-test` | Plán, případně implementace a testy. |
| `plan-build-test-quality` | Navíc lint, typy a testy celého repa. |
| `simple-sdlc` | Plán až dokumentace; velké nebo vágní tasky. |
| `scout`, `quality`, `document`, `heal` | Průzkum, kontrola repa, dokumentace, oprava sady. |
| `resolve`, `resolve-reviewed` | Konflikt PR s base. |
| `ci-fix` | Oprava červené CI v témže PR. |

Malá přesná změna: `build-test-review`; velká: `simple-sdlc` nebo nejdřív `plan`. Pomůže **Navrhnout workflow**. Vlastní workflow: [Příloha pro autory workflow](#/guide/autori-workflow).
