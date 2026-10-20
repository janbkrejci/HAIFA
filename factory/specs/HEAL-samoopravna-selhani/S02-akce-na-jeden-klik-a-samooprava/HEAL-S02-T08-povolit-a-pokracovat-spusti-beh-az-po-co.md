# HEAL-S02-T08: Pokračování až po commitu writes do base

Akce „Povolit tyto cesty a pokračovat“ a `factory task retry --allow-writes`
smějí pokračovat pouze tehdy, když backlog v commitu lokální větve base
povoluje všechny nově schválené cesty v efektivních writes tasku.

Po existujících `edit_task` a `commit_backlog` se backlog načte z
`refs/heads/<base>` přes `gitops.extract_backlog`. Kontrola používá stejné
párování cest a dědění writes jako běh. Platí i pro výsledek `committed=False`
a pro sloučený backlog PR. Nezávisí na obsahu pracovního stromu.

Chybějící cesty znamenají `writes_not_committed` (CLI exit 2, HTTP 409).
Zpráva vypíše chybějící cesty a pokyn commitnout backlog a potom spustit
`factory task retry <task>`. Retry ani launcher se při chybě nezavolají;
stav a attempt původního běhu zůstávají zachovány. Nesloučený PR nadále
vrací `writes_in_pr`. Ochrana nepovolených cest zůstává zachována.
