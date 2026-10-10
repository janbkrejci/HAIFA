Implementuj příkazy `factory task add`, `task edit`, `task show`, `task list` a `task link` nad knihovnou backlogu z 2.5.

Where: CLI v `aifactory/src/aifactory/`, `aifactory/tests/`.

Done means:
- `task add` založí soubor tasku ve správném adresáři stepu s hlavičkou podle briefu. `task edit` mění pole hlavičky (`title`, `status` jen `todo|cancelled`, `workflow`, `writes`). `task link` přidá nebo odebere `depends_on` a `related`.
- Každý příkaz zapisuje jen soubory backlogu a po zápisu spustí validaci z 2.5. Zápis, který by backlog rozbil (cyklus, neexistující odkaz), se neprovede a vrátí chybu.
- `task show` a `task list` vypíšou task a jeho odvozený stav.
- Všechny příkazy umí `--json` se stabilními kódy chyb.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: `task run` (2.9), dashboard.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
