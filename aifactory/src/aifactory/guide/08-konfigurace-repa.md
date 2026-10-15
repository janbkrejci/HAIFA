# Konfigurace repa

Konfigurace HAIFA v repu je adresář `.factory/`:

| Soubor | Obsah | V gitu |
| --- | --- | --- |
| `config.yaml` | Nastavení repa: base, hosting, cesty, souběh. | ano |
| `agents.yaml` | Roster: agenti repa a jejich harness, model, thinking. | ano |
| `roles.yaml` | Volitelně: přepis rolí kroků workflow. | ano |
| `workflows/<jméno>.yaml` | Vlastní workflow repa. | ano |
| `prompts/<agent>/` | Vlastní prompty agentů (`system.md`, `user.md`). | ano |
| `extensions/<jméno>/` | Rozšíření pi. | ano |
| `local.yaml` | Nastavení jen tohoto počítače (trace DB, sdílená databáze). | ne |
| `trace.db`, `data/`, `worktrees/` | Trace běhů, data sessions, worktree běhů. | ne |

Agenti, workflow, skilly a rozšíření, které repo nemá, se dědí z knihovny (kapitola [Knihovna](#/guide/knihovna)). Skilly repa jsou v `.claude/skills/` s kopií v `.agents/skills/` pro codex a pi (`factory skills sync`).

## Konfigurace z base

**Běhy čtou sdílenou konfiguraci (vše kromě `local.yaml`) z commitu ve větvi base, ne z pracovního stromu.** Změna `.factory/` se v běhu projeví až po commitu:

```bash
factory config status
factory config commit
```

`factory config commit` commitne sdílenou konfiguraci do base a odešle ji (nejdřív push, pak posun base). Na chráněnou base použij `factory config commit --pr`, nebo nastav repu `base_changes: pr` (sekce Chráněná base). V dashboardu je na to červený čip **Necommitnutá konfigurace** v horní liště, který otevře náhled commitu na záložce Factory. `factory config show` ukáže konfiguraci, kterou by použil běh; `factory config pull` posune lokální base na remote.

## Chráněná base

Když base přijímá změny jen přes pull request, nastav repu `base_changes: pr`. Nejlépe hned při přidání repa v dashboardu (**Změny base přes pull request**), později v sekci **Nastavení repozitáře** záložky Factory nebo `factory init --base-changes pr`. Factory pak každou svou změnu base pošle pull requestem: instalaci, commit konfigurace, nastavení a přesun položek knihovny, commit backlogu i odebrání repa.

- **`base_pr_merge: manual`:** PR schválí a mergne člověk. Změny backlogu do té doby zůstanou v pracovním stromu a panel čipu **Necommitnutý backlog** v horní liště odkáže na PR. Po mergi použij **Stáhnout konfiguraci z base** (`factory config pull`). Stažení vezme i necommitnuté soubory, které merge přináší beze změny.
- **`base_pr_merge: auto`:** factory PR hned mergne a posune lokální base. Na Azure DevOps ho nejdřív sama schválí, což repo musí povolit (autor smí schvalovat vlastní změny). Na GitHubu autor vlastní PR schválit nemůže, proto factory merguje s `gh pr merge --admin`, což vyžaduje administrátorská práva k repu. Když merge selže, PR zůstane otevřený a výsledek nese varování.

## config.yaml

| Klíč | Výchozí | Význam |
| --- | --- | --- |
| `base` | `main` | Větev, do které míří PR a ze které běhy čtou konfiguraci a backlog. |
| `remote` | `origin` | Git remote pro publikaci. |
| `git_provider` | `local` | `local`, `github` nebo `azure`. |
| `azure` | — | `organization`, `project`, `repository` pro Azure DevOps. |
| `merge_strategy` | `squash` | `squash` nebo `merge`. |
| `github_approver` | — | GitHub login, kterým factory při schválení PR úkolu pošle approve review. Musí to být jiný účet než autor PR, přihlášený v `gh` na tomto počítači (`gh auth login`). Bez něj se review neposílá a PR se rovnou merguje. |
| `base_changes` | `direct` | Jak factory mění base: `direct` commit a push, `pr` pull request pro každou změnu (instalace, konfigurace, knihovna, backlog, odebrání). |
| `base_pr_merge` | `manual` | Pull requesty factory s `base_changes: pr`: `manual` je mergne člověk, `auto` je factory hned schválí (Azure DevOps), mergne (GitHub přes `--admin`) a posune base. |
| `docs_root` | `factory` | Kořen `backlog/`, `specs/` a `docs/`. |
| `levels` | `[project, step, task]` | Názvy úrovní backlogu (nejméně dvě). |
| `workdir` | `.` | Pracovní adresář agentů v repu. |
| `worktrees_dir` | `.factory/worktrees` | Kam se zakládají worktree běhů. |
| `protected_files` | `[".factory/"]` | Cesty, které agenti nesmějí měnit. |
| `max_parallel_runs` | `1` | Souběžné běhy jednoho řetězu auto-continue. |
| `test_timeout` | 600 s | Časový limit kroku testů (task ho může přepsat). |
| `test_slots` | `1` | Kolik kroků testů smí běžet zároveň na počítači. |
| `generated` | — | Generované soubory `{path, command, timeout}`, které se při řešení konfliktu přegenerují. |

Neznámé klíče konfigurace odmítne. Port dashboardu ani cesta k trace DB do `config.yaml` nepatří.

Příklad pro GitHub:

```yaml
base: main
git_provider: github
docs_root: factory
max_parallel_runs: 2
protected_files:
  - .factory/
  - .github/
```

Pro Azure DevOps:

```yaml
base: main
remote: origin
git_provider: azure
azure:
  organization: https://dev.azure.com/firma
  project: Projekt
  repository: repo
```

## local.yaml

Lokální, necommitované nastavení tohoto počítače:

- `trace_db`: cesta k trace databázi běhů (výchozí `.factory/trace.db`),
- `database_url`: adresa sdíleného databázového serveru (kapitola [Počítač a harnessy](#/guide/pocitac/sdilena-databaze)).

## Nastavení repozitáře

Sekce **Nastavení repozitáře** je na záložce **Factory** (adresa `#/r/<repo>/factory/settings`), když je factory v repu nainstalovaná. Formulář **Sdílené nastavení repozitáře** upravuje `config.yaml`: pracovní adresář agentů, kořen dokumentů, adresář worktree, base větev, git provider, merge strategii, souběžné běhy auto-continue a chráněné soubory. **Lokální necommitované nastavení** upravuje cestu k trace DB v `local.yaml`. **Uložit** zapisuje do pracovního stromu a kontrolu factory zopakuje; sdílené nastavení pak commitni čipem **Necommitnutá konfigurace** v horní liště. Ostatní klíče (`azure`, `levels`, `test_timeout`, `test_slots`, `generated`, `remote`) uprav v souboru.

## Záložka Factory

- **Stav repa:** verdikt kontroly, verze, base a její náskok nebo zpoždění proti remote.
- **Akce:** **Nainstalovat factory** (formulář: base, git hosting, kořen dokumentů) a **Stáhnout konfiguraci z base**. Commit konfigurace otevírá červený čip **Necommitnutá konfigurace** v horní liště. Každá akce ukáže náhled plánu a zapíše ho do base, nebo jako PR (**Otevřít jako PR**, když base nepřijme přímý push).
- **Nálezy** ve skupinách **Repozitář: opravit a commitnout** a **Počítač: potřebné pro toto repo** (jen skupiny s nálezy). Nálezy knihovny a nálezy počítače, které ukazuje i stránka **Knihovna**, jsou jen tam; Factory na ně odkáže řádkem **Další nálezy tohoto počítače a knihovny**. Dashboard ukazuje jen nálezy, se kterými jde něco udělat. Vybrané nálezy repa vyřeší agent: **Vyřešit vybrané nálezy** založí a spustí task „Opravit vybrané nálezy Factory“; jeho panel se otevře hned pod tlačítkem, u nálezů. Necommitnuté soubory konfigurace jsou jeden souhrnný nález `config_uncommitted` se seznamem souborů.
- **Nastavení repozitáře:** viz předchozí oddíl.
- **Vybavení továrny:** úvodní věta uvádí knihovnu, ze které se položky bez vlastní kopie dědí, názvem a zkráceným commitem. **Agenti** jsou v tabulce každý jednou, s harnessem, modelem a přemýšlením a štítkem **zděděno** (z knihovny a výchozích hodnot projektu), nebo **přepsáno** (popisek ukáže zděděnou hodnotu). **Upravit** zapíše přepis do `.factory/agents.yaml`, **Vrátit na zděděné** přepis odstraní; obojí nejdřív ukáže náhled změny pod agentem a uloží se do pracovního stromu, běhy ji použijí po commitu konfigurace. Pod agenty jsou přepisy na krocích workflow. **Workflow**, **Skilly** a **Rozšíření pi** jsou karty s původem vlastní kopie, nebo z knihovny. Vlastní kopii můžeš **Přesunout do knihovny**.

## Instalace a odebrání

`factory init` (nebo **Přidat repozitář** v dashboardu) zapíše `.factory/config.yaml`, adresář backlogu a do `.gitignore` řádky `.factory/data/`, `.factory/worktrees/`, `.factory/local.yaml` a `.factory/trace.db*`. Agenty ani workflow nekopíruje. Odebrání repa z dashboardu `.factory/` z repa smaže a commitne to (kapitola [Dashboard](#/guide/dashboard)).
