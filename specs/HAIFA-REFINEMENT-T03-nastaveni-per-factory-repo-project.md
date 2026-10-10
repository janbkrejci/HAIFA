# HAIFA-REFINEMENT-T03 — Nastavení per factory/repo/project

Nastavení rozlišuje lokální `.factory/local.yaml`, sdílené výchozí hodnoty
repozitáře v `.factory/config.yaml` a sdílená přetížení nejvyšších kontejnerů
backlogu v jejich `index.md`. Projektový panel nabízí pouze `specs_dir`,
`docs_dir` a `workdir`, výběr projektu a obnovení dědění odstraněním klíče.
Zobrazuje účinnou hodnotu a původ. Repo může mít libovolný počet projektů.

Pro výstupy zůstává pořadí task → step → projekt → konfigurace repozitáře.
Pracovní adresář se bere pouze z projektu, jinak z konfigurace repozitáře
(výchozí `.`). Null i chybějící klíč dědí. Přetížení workdir na nižších
úrovních se odmítne; žádné další projektové parametry se nezavádějí.

Běh čte konfiguraci a backlog z base commitu. Před vytvořením běhu ověří
relativní cesty, existenci pracovního adresáře a adresářové komponenty
v použitém Git stromu. Symlinky a soubory místo adresářů odmítne.
Projektový cwd se předá adaptérům agentů. Kořen workflow, Git operace,
testovací příkazy, ochrana writes i interpretace artefaktů zůstávají v kořeni
izolovaného worktree. Prompt obsahuje oba adresáře a vysvětluje jejich význam.

Před uložením API odmítá prázdné, absolutní či unikající cesty (včetně
Windows drive/backslash syntaxe) a existující symlinky vedoucí ven z repozitáře.
Lokální soubor zůstává ignorovaný; sdílené úpravy se automaticky necommitují.

Regresní ověření: dědění a jeho obnovení, izolace dvou projektů, jejich
skutečný agent cwd a výstupy, čtení commitu namísto necommitovaných změn,
odmítnutí neplatných adresářů, zachování writes a tři úrovně nastavení v UI.
Frontendové assets se generují pomocí `just web-build`.
