# HAIFA-S01-T10: `factory check`

Čtecí kontrola, jestli factory v repu a na stroji poběží a co opravit.

```
factory check [--repo CESTA] [--offline] [--json]
```

- Jen čte: nic nezapisuje do repa, trace DB ani domovského adresáře a nevolá `git fetch`.
  Dočasné soubory (prompty pro `preflight`, backlog rozbalený z base) jdou do `tempfile`.
- Čtecí git volání konfigurace (`aifactory.config.source.git`) běží s
  `GIT_OPTIONAL_LOCKS=0`. `config_changes` (D4) používá plumbing `git diff-index --raw` a
  `git hash-object`, protože porcelain `git diff <sha>` index obnovuje a bere `index.lock`
  i s touto proměnnou.
- `--repo` může mířit i do linked worktree. Kontroluje se vždy hlavní checkout.

## Výstup (`--json`)

`data`: `repo`, `install` (`none` | `working_tree` | `base`), `base`, `commit`, `remote`,
`ahead`, `behind` (jen z lokálního `refs/remotes/<remote>/<base>`), `offline`, `ok`, `counts`
(`error`/`warning`/`info`), `groups`, `backlog` (počty kódů `backlog check`) a `findings`.

Nález: `{code, scope, severity, message, fix, action}`.

- `scope`: `repo` (opravit a commitnout do base) nebo `machine` (opravit lokálně).
- `severity`: `error`, `warning` nebo `info`.
- `action`: `init`, `update`, `config_commit`, `config_pull` nebo `null`. Je to jen jméno
  opravy pro dashboard, opravné příkazy tento task neimplementuje.

Návratové kódy: 0 bez chyb, 1 s chybou (`checks_failed`, report v `data`), 2 když složka
není git repo (`not_a_repository`).

## Kódy (`ISSUE_CODES["check"]` v `skill/codes.py`)

Repo: `factory_missing` (init), `config_not_committed` (config_commit), `base_missing`,
`checkout_not_on_base`, `remote_missing`, `remote_base_missing`, `base_behind_remote`
(config_pull), `base_ahead_of_remote`, `base_config_invalid`, `worktree_config_invalid`,
`config_uncommitted` (config_commit), `base_setting_mismatch`, `backlog_missing`,
`backlog_invalid`, `workflow_unset`, `workflow_unknown`, `workflow_invalid`,
`justfile_missing`, `test_recipe_missing`, `test_script_missing`, `gitignore_missing`
(update).

Stroj: `harness_missing`, `just_missing`, `test_program_missing`, `local_config_invalid`,
`gh_missing`, `gh_not_logged_in`, `az_missing`, `az_devops_missing`, `az_not_logged_in`,
`hosting_skipped`.

`check_failed` (warning) vznikne, když pravidlo skončí očekávanou chybou (git, konfigurace,
I/O). Kontrola pak pokračuje dalšími pravidly.

## Struktura (`aifactory/src/aifactory/check/`)

- `model.py`: `Finding`, `Rule`, `RuleGroup`, `CheckReport`.
- `context.py`: `CheckContext`, líně počítaný kontext (base, commit, stav instalace,
  konfigurace z base i pracovního stromu, settings, roster, testovací příkaz, remote,
  backlog z base) a `NotARepositoryError`.
- `machine.py`: protokol `Machine` (`which`, `run`, `env`, `harness`) a `SystemMachine`.
  Testy podstrčí `FakeMachine`.
- `repo_rules.py` (`REPO_GROUP`), `machine_rules.py` (`MACHINE_GROUP`).
- `__init__.py`: `RULE_GROUPS`, `run_check`, `default_machine`.

## Jak přidat skupinu pravidel (O1, P2)

```python
from aifactory.check import RULE_GROUPS, Finding, Rule, RuleGroup

def login(ctx):
    if ...:
        yield Finding("my_code", "machine", "error", "zpráva", "jak opravit")

RULE_GROUPS.append(RuleGroup("logins", (Rule("login", login),), scope="machine"))
```

`run_check` čte `RULE_GROUPS` až při volání, CLI se nemění. Nový kód přidej do
`ISSUE_CODES["check"]`. Test `test_check_codes_complete` porovnává literály prvního
argumentu `Finding(...)` v `check/*.py` s tímto seznamem. Pravidlo s `needs_install=False`
běží i v repu bez factory.

## Další změněné soubory

- `aifactory/src/aifactory/cli.py`: subcommand `check` (`_add_check_command`, `_check`).
  Bez `--json` tiskne stav instalace, remote (ahead/behind), nálezy s `fix` a `[action]`
  a souhrn počtů.
- `aifactory/src/aifactory/config/source.py`: `READ_ENV` (`GIT_OPTIONAL_LOCKS=0`) pro
  všechna volání `git()` a nový helper `git_try` (stdout, nebo `None` při chybě).
- `aifactory/src/aifactory/config/status.py`: `config_changes` přepsané na
  `git diff-index --raw -z` + `git hash-object` pro záznamy se zastaralými stat daty.
- `aifactory/src/aifactory/skill/codes.py`: chybové kódy `checks_failed` (1) a
  `not_a_repository` (2) a `ISSUE_CODES["check"]`.
- `aifactory/src/aifactory/skill/skill.md`: doporučení začít `factory check --json`,
  postup „Check“ v Procedures a návod pro `checks_failed`.

## Testy

`aifactory/tests/check/`: `test_factory_check.py` (dočasná repa, `FakeMachine`, ověření, že
kontrola nemění index, refy ani soubory), `test_factory_check_cli.py` (envelope a návratové
kódy) a `test_justfile_recipes.py`.
`aifactory/tests/test_skill.py` přidává `test_check_codes_complete` a
`test_skill_describes_check`, `aifactory/tests/test_smoke.py` vyřazuje `check` ze seznamu
neimplementovaných příkazů.

## Ověření

```
factory check --json                 # v aktuálním repu
factory check --repo CESTA --offline # bez gh/az
just test && just typecheck && just lint
```

`test_check_changes_nothing` ověřuje, že kontrola nezmění `git status`, index ani refy;
`test_config_git_reads_without_optional_locks` ověřuje `GIT_OPTIONAL_LOCKS=0`.
