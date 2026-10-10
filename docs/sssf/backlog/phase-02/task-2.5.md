Přenes knihovnu backlogu do `aifactory` podle sekce „Backlog v markdownu“ v `docs/product-brief.md` a implementuj `factory backlog check [--json]` a `factory backlog list [--json]`.

Where: `aifactory/src/aifactory/backlog/`, CLI, `aifactory/tests/`. Zdroj: `prototype/src/haifa_proto/backlog.py`, `taskfile.py`.

Done means:
- Strom modul → step → task s počtem a názvy úrovní z `levels` v `.factory/config.yaml`, soubor na task s YAML hlavičkou, `index.md` na modul a step s výchozími hodnotami (vlastník, `source`, `target`, testovací příkaz, workflow, `writes`), které tasky dědí.
- Validace: duplicitní id, odkaz na neexistující task nebo step, cyklus v `depends_on`, neznámý stav, chybějící povinné pole. `backlog check` vrací nenulový kód a seznam chyb s cestou k souboru.
- Odvozený stav `ready` a `blocked` z `depends_on`. Step je hotový, když jsou hotové všechny jeho tasky.
- `backlog list` vypíše strom se stavem, filtr `--status` a `--module`.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: příkazy `task add|edit|show|list|link` (2.6), zápis `done` (2.12).

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
