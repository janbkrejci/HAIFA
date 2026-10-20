# HEAL-S02-T08: Ověření writes před pokračováním

`allow_writes` po úpravě a commitu backlogu ověřuje skutečný obsah commitu
lokální base. Dočasná kopie backlogu se načte přes `gitops.extract_backlog`;
efektivní writes zahrnují děděné hodnoty a mohou cestu pokrývat adresářem
nebo vzorem. Kontrola se provádí i po no-op výsledku a sloučeném PR.

Pokud některá schválená cesta chybí, CLI vrátí `writes_not_committed`
s exit 2 a API HTTP 409. Zpráva uvádí chybějící cesty. Commitněte backlog
příkazem `factory backlog commit --json` a pokračujte pomocí
`factory task retry <task> --json`. Běh zůstává ve stejném stavu a pokusu,
žádný agent se nespustí. Čekající backlog PR nadále vrací `writes_in_pr`.

Regresní testy pokrývají neprovedený commit, neúplný commit, sloučený PR
bez nových writes, úspěšné ověření děděných writes, úspěšné pokračování,
API bez volání launcheru při chybě a popis chyby v generovaném skillu.
