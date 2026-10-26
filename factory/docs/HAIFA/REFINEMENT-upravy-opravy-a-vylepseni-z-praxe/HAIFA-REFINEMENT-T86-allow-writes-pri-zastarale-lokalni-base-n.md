# Retry s povolením dalších cest při zastaralé base

`factory task retry <ID> --allow-writes` před změnou úlohy načte vzdálenou base a bezpečně posune lokální větev pomocí postupu pro retry. Nekonfliktní staged i unstaged změny zachová Git při fast-forwardu bez stashe nebo pomocného commitu. Divergence, konfliktní rozpracované změny nebo chyba fetch zastaví operaci před zápisem do úlohy.

Po aktualizaci se znovu vyhodnotí aktuální `writes`. Pokud požadované cesty přinesl vzdálený commit nebo již byly commitnuté ve shodné lokální a vzdálené base, pokračuje retry bez zápisu a dalšího backlog commitu.

Při chybě během úpravy, commitu nebo ověření oprávnění se vrátí původní obsah souboru úlohy a indexu. Pokud již vznikl commit, zůstává zachován a soubor odpovídá jeho obsahu; nevytváří se necommitnutá opačná změna. Při čekání na ručně schvalované backlog PR se rovněž odstraní místní necommitnutá úprava; změna zůstává v PR.

Regresní testy používají lokální Git remote a falešné agenty. Pokrývají aktuální base, zastaralou base, oprávnění již přidaná vzdáleným commitem, zachování nekonfliktních staged i unstaged změn, odmítnutí konfliktní rozpracované změny a obnovení původních staged i unstaged úprav při chybě.
