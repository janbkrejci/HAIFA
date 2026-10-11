---
id: HAIFA-S01-T10
title: "factory check: kontrola factory v repu a na stroji"
status: done
depends_on: [HAIFA-S03-T01]
---

## Zadání
Přidej příkaz `factory check`, který jen čte a řekne, jestli factory v repu poběží a co opravit. Nálezy dělí na repo (opravit a commitnout) a stroj (opravit lokálně). Dashboard ho spustí po přidání repa a na záložce Factory. Stavy onboardingu doplní O1 a kontrolu přihlášení a knihovny P2, proto jsou pravidla kontroly seznam, do kterého jde přidat skupinu bez změny CLI.

Where: `aifactory/src/aifactory/cli.py`, `aifactory/src/aifactory/config/` (`source.py`, `status.py`, `loader.py`, `run.py`), `aifactory/src/aifactory/harness/check.py`, `aifactory/src/aifactory/workflow/`, `aifactory/src/aifactory/backlog/`, `aifactory/src/aifactory/run/task.py` (`named_workflow`, `prepare_cfg`, `resolve_test_command`), `aifactory/src/aifactory/skill/` (`skill.md`, `codes.py`), testy v `aifactory/tests/`. Nový modul kontroly v `aifactory/src/aifactory/`.

Done means:
- `factory check [--repo CESTA] [--offline] --json` vrátí stav instalace (`none`, `working_tree` nebo `base`) a nálezy `{code, scope, severity, message, fix, action}` se `scope` `repo` nebo `machine` a `severity` `error`, `warning` nebo `info`. `action` pojmenuje opravný příkaz (`init`, `update`, `config_commit`, `config_pull`), nebo je null.
- Repo: hlavní checkout na base, base je commit, náskok a zpoždění proti `refs/remotes/<remote>/<base>` jen z lokálních refů, `load_config` z pracovního stromu i z base, necommitovaná konfigurace (D4), souhrn `factory backlog check` po kódech, workflow použitá backlogem v base (načtení a `preflight`), spustitelnost testovacího příkazu podle `test_command` a výchozího `just test` (HAIFA-S03-T01, u `just` recept v justfile z base) a řádky `.gitignore` pro runtime factory.
- Stroj: harnessy agentů z rosteru v base, `just`, přihlášení `gh` nebo `az` podle `git_provider`. `--offline` vynechá volání hostingu.
- Návratový kód je 0 bez chyb, 1 s chybou (`checks_failed`, zpráva v `data`) a 2, když kontrola nejde spustit (složka není git repo).
- Čtecí git volání konfigurace běží s `GIT_OPTIONAL_LOCKS=0`, takže kontrola ani varování D4 neberou `index.lock` během běžících tasků.
- `factory --skill` popisuje příkaz. Nové kódy jsou v `skill/codes.py`.
- Testy (pytest) nad dočasnými repy: repo bez factory, konfigurace jen v pracovním stromu, neplatná konfigurace v base, chybějící prompt, backlog s problémy, chybějící recept `test`, `test_command` s chybějícím programem, chybějící harness, zpoždění za remote, `--offline` a návratové kódy. Test ověří, že kontrola nezmění `git status`, index ani refy repa.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: opravy (instalace, aktualizace, commit), stavy onboardingu (O1), přihlášení harnessů a knihovna (P2), postup instalace ve skillu (HAIFA-S04-T02), dashboard, sdílená trace DB mezi repy (hlásí dashboard), `git fetch`.

Pevná omezení:
- Kontrola nic nezapisuje do repa, trace DB ani domovského adresáře.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-03 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/11 · náklady $5.58
