# Řešení problémů

Problémy počítače, knihovny a repa hledá `factory check`. V dashboardu je výsledek na stránce **Tento počítač** (počítač a knihovna), v záložce **Factory** repa (repo a nálezy počítače, které plynou z repa) a souhrnně pod chipem **Nalezeny problémy** v horní liště, který otevře stránku **Problémy a řešení** s návody a tlačítky k opravě.

```bash
factory check            # počítač a knihovna, v repu i repo
factory check --offline  # bez dotazů na hosting a přihlášení harnessů
factory check --json     # strojově čitelný výstup
```

Každé zjištění má kód, závažnost a radu. `error` blokuje práci (tasky nespouštěj), `warning` upozorňuje na něco, co pravděpodobně chceš opravit, `info` jen informuje.

## Počítač

| Kód | Co znamená a jak to opravit |
| --- | --- |
| `unsupported_platform` | Kontrola zná macOS, Linux, WSL a Windows. Na jiném systému HAIFA nepodporuje. |
| `git_missing` | Nainstaluj git. |
| `git_identity_missing` | `git config --global user.name "…"` a `git config --global user.email …`. |
| `uv_missing` | Nainstaluj uv (`curl -LsSf https://astral.sh/uv/install.sh \| sh` nebo `brew install uv`). Bez něj nejde aktualizovat. |
| `node_missing` | Některý agent používá harness pi, který potřebuje Node.js; nainstaluj ho. |
| `harness_missing` | CLI harnessu (`claude`, `codex`, `pi`) není na PATH. Nainstaluj ho, nastav cestu v proměnné, kterou uvádí rada, nebo přepni agenty na jiný harness (`factory config roster set …`). Mimo repo je to jen informace; dashboard ji ukáže, jen když harness používá některé registrované repo. |
| `harness_login` | Přihlas se: `claude auth login`, `codex login` nebo `pi auth login`. |
| `pi_model_unknown` | Model není v `pi --list-models` nebo je nejednoznačný; zaregistruj ho v pi, nebo oprav `model` v `.factory/agents.yaml`. |
| `codex_not_isolated` | Codex by načetl tvoje globální soubory (`~/.codex/AGENTS.md`, `~/.codex/skills`, `~/.agents/skills`). Přesuň je jinam, nebo nastav `CODEX_SAFE_MODE=1`. |
| `pi_not_isolated` | pi by načetlo globální soubory v `~/.pi/agent`. Přesuň je jinam, nebo nastav `PI_SAFE_MODE=1`. |
| `gh_missing` | Repo používá GitHub; nainstaluj GitHub CLI `gh`. |
| `gh_login` | `gh auth login` (a `gh auth setup-git`). |
| `az_missing` | Repo používá Azure DevOps; nainstaluj Azure CLI `az`. |
| `az_devops_missing` | `az extension add --name azure-devops`. |
| `az_login` | `az login`, nebo nastav `AZURE_DEVOPS_EXT_PAT`. |
| `hosting_skipped` | Kontrola běžela s `--offline`; hosting zkontroluje běh bez něj. Dashboard ji nezobrazuje. |
| `local_config_invalid` | Oprav `.factory/local.yaml` (`trace_db`) podle zprávy kontroly. |
| `local_port_ignored` | Smaž řádek `port` z `.factory/local.yaml`; port dashboardu nastavíš na stránce Tento počítač nebo přes `factory obs --port N`. |
| `env_file_mode` | Soubor s tajemstvími `$HAIFA_HOME/env` je čitelný i pro ostatní: `chmod 600 $HAIFA_HOME/env`. |
| `env_override` | Proměnná prostředí (`CLAUDE_SAFE_MODE`, `CODEX_SANDBOX`, …) mění chování harnessu. Zruš ji v shellu nebo v `$HAIFA_HOME/env`, pokud ji nechceš. |

## Knihovna

| Kód | Co znamená a jak to opravit |
| --- | --- |
| `library_missing` | Knihovna neexistuje: `factory library clone <URL>` (týmová), nebo `factory library init`. |
| `library_dirty` | Knihovna má necommitnuté změny; commitni je nebo zahoď přímo v adresáři knihovny. |
| `library_behind` | Tým poslal do knihovny novější commity: `factory library pull`. |
| `library_unpushed` | Máš v knihovně commity, které ostatní nemají: `factory library push`. |
| `seed_update_available` | Nová verze HAIFA přinesla novější agenty nebo workflow: `factory library seed --dry-run`, pak `factory library seed`. |
| `factory_outdated` | Knihovna vyžaduje novější HAIFA (`min_factory_version`): `factory upgrade haifa-<verze>.zip`. |

## Repo

| Kód | Co znamená a jak to opravit |
| --- | --- |
| `factory_missing` | Repo nemá `.factory/`. Přidej ho v dashboardu (Přidat repozitář) nebo `factory init`. |
| `repo_unsupported` | Repo nejde použít (například bez gitu); postupuj podle rady kontroly. |
| `repo_installed` | Informace: repo má HAIFA nainstalovanou. Jen v `factory check`; dashboard ji nezobrazuje, protože nevyžaduje akci. |
| `config_not_committed` | `.factory/` není v base. Běhy čtou konfiguraci z commitu v base: `factory config commit`. |
| `config_uncommitted` | V pracovním stromu je změna `.factory/`, kterou běhy nevidí: `factory config commit`, nebo ji zahoď. |
| `worktree_config_invalid` | Necommitnutá konfigurace je chybná; oprav ji, než ji commitneš. |
| `base_config_invalid` | Konfigurace v base je chybná; oprav `.factory/` a commitni ji do base. |
| `base_missing` | Větev `base` neexistuje: vytvoř ji s prvním commitem, nebo oprav `base` v `.factory/config.yaml`. |
| `base_setting_mismatch` | `base` v pracovním stromu a v base se liší; sjednoť je. |
| `checkout_not_on_base` | Hlavní checkout repa není na větvi base: `git switch <base>`. Commity backlogu a dashboard s tím počítají. |
| `remote_missing` | Repo nemá remote: `git remote add origin URL`, nebo nastav `remote` v `.factory/config.yaml`. |
| `remote_base_missing` | Remote nezná base: `git fetch origin`. |
| `base_behind_remote` | Base je za remote: `git pull origin <base>`. |
| `base_ahead_of_remote` | Base má neodeslané commity: `git push origin <base>`. |
| `backlog_missing` | Backlog neexistuje; vytvoř projekt a commitni ho (`factory backlog commit`). |
| `backlog_invalid` | `factory backlog check`, oprav soubory, pak `factory backlog commit`. |
| `workflow_unset` | Tasky nemají workflow; nastav `workflow` na tasku, nebo v `index.md` projektu či stepu. |
| `workflow_unknown` | Workflow neexistuje v repu ani v knihovně; přidej ho, nebo změň tasky. |
| `workflow_invalid` | Workflow nebo `.factory/agents.yaml` je chybné; oprav (`factory workflow check`) a commitni. |
| `unknown_thinking` | Neznámá úroveň `thinking` v `.factory/agents.yaml`; použij jednu z povolených. |
| `disallowed_commands_unenforced` | Zakázané příkazy agenta umí vynutit jen harness claude; přepni agenta, nebo `disallowed_commands` odeber. |
| `roles_full_copy` | `.factory/roles.yaml` je úplná kopie; nech v něm jen role, které měníš. |
| `gitignore_missing` | Do `.gitignore` chybí položka, kterou uvádí rada; přidej ji a commitni. |
| `skill_mirror_missing`, `skill_mirror_differs`, `skill_mirror_extra` | Kopie skillů v `.agents/skills/` (pro codex a pi) neodpovídá zdroji v `.claude/skills/`: `factory skills sync`. |

## Časté situace

**Dashboard hlásí, že kód HAIFA se změnil.** Po aktualizaci nebo merge do HAIFA samotné běží server se starým kódem. Klikni v pruhu na restart, nebo ukonči `factory obs` a spusť ho znovu.

**Běh se nespustí, protože task nemá workflow.** Nastav workflow v detailu tasku, nebo jako výchozí v projektu či stepu.

**Změna v `.factory/` se v běhu neprojevila.** Běhy čtou sdílenou konfiguraci z commitu v base. Commitni ji (`factory config commit`, v dashboardu tlačítko commitu konfigurace).

**Necommitnutý backlog.** Úpravy backlogu z dashboardu se ukládají do souborů; pruh dole na stránce repa je commitne do base jedním kliknutím, z CLI `factory backlog commit`.

**Harness narazil na limit předplatného.** Lišta limitů v horní liště ukazuje poslední hodnoty, které harness vrátil. Počkej na obnovení, nebo přepni agenty na jiný harness.

**Agent vypadá zaseknutý.** V detailu běhu sleduj živý výstup fáze. Běh můžeš pozastavit, pokračovat v něm nebo ho zastavit; zastavený běh se dá spustit znovu.

Když nic z toho nepomůže, spusť `factory check --json` a výstup přilož k hlášení problému spolu s verzí (`factory --version`).
