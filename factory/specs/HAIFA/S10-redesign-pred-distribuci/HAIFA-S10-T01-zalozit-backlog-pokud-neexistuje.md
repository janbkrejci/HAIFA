# HAIFA-S10-T01 — Založit backlog, pokud neexistuje

## Cíl
Kde se dnes hlásí chyba `missing_backlog_dir` („backlog directory '…' does not exist“),
se má složka backlogu tiše vytvořit.

## Řešení
- `aifactory/src/aifactory/backlog/loader.py`: `load_backlog(..., create_missing=True)`;
  chybějící kořen backlogu bez wildcardu (`backlog_dir`, položka `backlog_dirs`) se vytvoří
  (`mkdir(parents=True)`), pokud existuje kořen repozitáře. Selže-li `mkdir`, hlásí se
  `missing_backlog_dir` jako dřív. Wildcardový vzor bez shody se dál hlásí (není co vytvořit).
- `aifactory/src/aifactory/check/context.py`: `factory check` čte backlog z base commitu
  s `create_missing=False`, aby varování `backlog_missing` (backlog není commitnutý) zůstalo.
- `skill/codes.py`: popis kódu `missing_backlog_dir` odpovídá novému chování.
- Testy upraveny (backlog CLI, check, roots, task edit, e2e multi-repo).
