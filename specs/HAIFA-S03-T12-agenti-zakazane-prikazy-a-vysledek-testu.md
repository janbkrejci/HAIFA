# Spec HAIFA-S03-T12: Agenti: zakázané příkazy a výsledek testu pro review

## Cíl
Agenti nemají pouštět celou testovací sadu. Fáze test ji pouští sama a reviewer dostane její výsledek.

## Požadavky
1. Agent v `.factory/agents.yaml` má volitelný seznam `disallowed_commands`, který se dědí z `defaults`. Položka je vzor Bash příkazu (`just test`, `just test *`, `pytest`).
2. Adaptér claude předá seznam jako `--disallowedTools "Bash(<vzor>)" …`. Codex a pi zákaz neumí (`SUPPORTS_DISALLOWED_COMMANDS = False`).
3. Agenta se zákazem na harnessu bez podpory nahlásí `factory check` (varování `disallowed_commands_unenforced`) i začátek běhu (log fáze `request`, `WorkflowRun.warnings`). Začátek běhu počítá i s override harnessu v kroku.
4. Role krok workflow dostane `{{test_result}}`, tedy poslední výsledek kroku `test`: `passed`, `command`, `log`, `failures` a `code_changed_since`. `input:` může být mapa `{proměnná: kroky}`. V ní `previous_envelope` zachovává původní význam a ostatní názvy jsou samostatné proměnné šablony.
5. Seed prompt revieweru uvádí `test_result` a zakazuje sadu znovu spouštět.
6. Testy bez modelu a sítě: zákaz v příkazu claude, nahlášení harnessu bez podpory a review s obálkou builderu i výsledkem testu.

## Mimo rozsah
Sandbox na úrovni systému, omezení sítě a změny v `.factory/` (chráněné, upravuje je operátor).
