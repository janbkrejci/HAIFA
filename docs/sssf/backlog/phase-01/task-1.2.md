Implementuj načtení a validaci backlogu HAIFA podle sekce „Backlog v markdownu“ v `docs/product-brief.md`: strom adresářů modul → step → task, task jako markdown soubor s YAML hlavičkou, odvozený stav a příkazy `haifa-proto backlog check` a `haifa-proto backlog list`.

Where: `prototype/src/haifa_proto/backlog.py`, `prototype/src/haifa_proto/config.py`, CLI v `prototype/src/haifa_proto/`, testy v `prototype/tests/`, vzorová data v `prototype/tests/fixtures/backlog/`.

Done means:
- Konfigurace se čte z `.factory/config.yaml` v cílovém repu: `levels` (výchozí `[module, step, task]`) a `backlog_dir` (výchozí `backlog`).
- Každý adresář modulu a stepu má `index.md` s YAML hlavičkou (`id`, `title`, volitelně `owner`, `source`, `target`, `test`, `workflow`, `auto_continue`). Task tyto hodnoty dědí, vlastní hodnota má přednost.
- Hlavička tasku: `id`, `title`, `status` (`todo` | `done` | `cancelled`), `workflow`, `depends_on`, `related`, `writes`.
- `depends_on` smí mířit na task i na step. Step je hotový, když jsou hotové všechny jeho tasky.
- Odvozené stavy: `ready` (todo a všechny závislosti hotové), `blocked` (todo a něco chybí, s výpisem čeho). „Blokuje“ se dopočítá jako opačný směr `depends_on`.
- `backlog check` hlásí: duplicitní id, neznámý odkaz v `depends_on` nebo `related`, cyklus (s cestou cyklu), neplatný `status`, adresář bez `index.md`, id tasku nezačínající id jeho stepu a modulu. Návratový kód 0 bez chyb, 1 s chybami.
- `backlog list` vypíše strom se stavy. `--json` u obou příkazů vrací strojově čitelný výstup.
- Vzorový backlog: 2 moduly, 3 stepy, 6 tasků, aspoň jedna závislost na step a jedna mezi moduly. Každá validace má test s rozbitou kopií vzorových dat.

Out of scope: spouštění tasků, trace, zápis stavu `done`, web.

Pevná omezení:
- V souborech se ukládá jen `depends_on`. „Blokuje“ se nikdy neukládá.
- Stavy `running`, `failed` a `in review` do souborů nepatří, tady se neřeší vůbec.
- `vendor/` se neupravuje.
