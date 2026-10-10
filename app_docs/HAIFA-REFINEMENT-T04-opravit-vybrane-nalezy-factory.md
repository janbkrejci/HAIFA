# HAIFA-REFINEMENT-T04: Výsledky kontroly Factory

## Výsledky vybraných nálezů

Ověřeno dne 2026-10-08 příkazem `just factory check --json` z worktree
`c5dccfe7`. Factory kontroluje hlavní checkout `/Users/jbk/Documents/HAIFA`
a konfiguraci z main `f269d53569ad2ec945f8b12f52918b370fb1e167`, nikoli pouze
lokální soubory tohoto worktree. Commit `592eabb` ze zadání už není aktuální.

| Nález | Výsledek | Konkrétní překážka |
| --- | --- | --- |
| `workflow_not_in_repo` (repo, error) | Přetrvává: task `HAIFA-S90-T06` v main používá `manual-test-duration`, ale workflow není v main. | `.factory/` je chráněná a mimo povolené cesty; změna backlogu je také mimo rozsah. Doporučený `config add` navíc vrací `unknown_item`, protože workflow není v knihovně. |
| `config_uncommitted` (repo, warning, akce `config_commit`) | Přetrvává: workflow je untracked v hlavním checkoutu. | Commit do main je mimo oprávnění builderu; plán `config commit` navíc hlásí `run_in_progress` pro běh `c5dccfe7` úkolu `HAIFA-REFINEMENT-T04`. |

`factory check` skončil kódem **1**, `ok: false`, `checks_failed`:
1 error, 3 warning a 1 info. Jediná chyba je vybraný `workflow_not_in_repo`.
Další upozornění jsou `workflow_unset` pro čtyři úkoly a
`codex_not_isolated` na tomto počítači; jsou mimo vybraný rozsah a nebyla měněna.
Výstup neobsahoval nález knihovny. Konfigurace nebyla opravena ani commitnuta.

## Postup pro operátora po skončení běhu

1. V hlavním checkoutu zkontrolovat obsah existujícího
   `.factory/workflows/manual-test-duration.yaml`. Jeho commit řeší oba
   nálezy současně; samotné odstranění lokálního souboru ponechá chybějící
   workflow úkolu `HAIFA-S90-T06`.
2. Po skončení aktivních běhů obnovit plán:

   ```bash
   cd /Users/jbk/Documents/HAIFA
   just factory config commit --dry-run --json
   ```

   Při ověření měl plán jedinou změnu: vytvoření výše uvedeného workflow.
   Dry-run skončil kódem 0 a `committed: false`, ale seznam `blockers`
   obsahoval `run_in_progress`. Kód 0 dry-runu tedy neznamená, že lze commit
   provést. Před pokračováním musí být `blockers` prázdné a všechny změny
   v plánu zkontrolované.
3. Použít čerstvý `digest` z ověřeného plánu:

   ```bash
   just factory config commit --expect <DIGEST_Z_NOVEHO_PLANU> -m "HAIFA-REFINEMENT-T04: Commit manual-test-duration workflow"
   just factory check --json
   ```

   `config commit` může pushovat do vzdáleného repozitáře; tento krok provádí
   operátor. Pokud se plán změnil nebo je stále blokovaný, znovu jej prověřit
   a nejprve vyřešit uvedené překážky.
4. Ve výstupu kontroly ověřit nepřítomnost `workflow_not_in_repo` pro toto
   workflow a `config_uncommitted` pro tento soubor. Případné jiné nálezy
   posoudit samostatně; celkový exit status závisí na všech chybách.

Pokud operátor workflow nechce zachovat, musí mimo tento běh upravit task
schválenými backlog příkazy na vhodné existující workflow a teprve poté
vyřešit lokální soubor. Příkaz `config add` není nyní použitelný, dokud položka
nevznikne v knihovně; knihovna nebyla v tomto běhu měněna.

## Validace tohoto výstupu

Změna obsahuje pouze dva dokumenty tohoto úkolu. Žádný produktový kód nebyl
změněn; regresní testy nejsou pro tento dokumentační výstup potřeba.
Diagnostika výše je skutečný výsledek kontroly, nikoli tvrzení, že Factory
je po tomto běhu bez nálezů.

Po zápisu dokumentů opakovaný `just factory check --json` vrátil stejné
nálezy a exit code 1. `just typecheck` a `just lint` prošly s exit code 0;
`git diff --check` také skončil kódem 0.
