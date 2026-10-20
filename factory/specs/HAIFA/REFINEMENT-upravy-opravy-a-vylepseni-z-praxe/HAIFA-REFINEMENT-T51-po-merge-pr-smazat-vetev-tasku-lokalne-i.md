# Úklid větví sloučených task PR

Po úspěšném schválení i automatickém merge se nejprve dokončí restack závislých PR.
Společná review flow pak odstraní lokální větev přes `git branch -D` a existující
remote větev přes `git push <remote> --delete`. Použije nakonfigurovaný remote
(výchozí `origin`). Merge strategie ani jednotlivé provider merge operace se nemění.

Větev se ponechá, pokud na ní stále stojí otevřený stacked PR bez úspěšného restacku, má běžící běh nebo je
checkoutnutá v některém worktree včetně hlavního checkoutu. Base větev se nemaže.
Úklid worktree nesmí odstranit cestu používanou běžícím během, ani když ji sdílí
starší dokončený běh. Chyba mazání lokální či remote větve pouze přidá warning;
neexistující větev není chyba. Lokální a remote mazání se zkouší nezávisle.

`factory task clean` zachovává úklid worktree a navíc prochází všechny evidované
sloučené PR, i bez zbývajícího worktree. Používá stejné ochrany a umožňuje znovu
zkusit neúspěšné mazání. Větve otevřených a zavřených PR a opuštěných běhů zůstávají.

Výsledky approve i clean přidávají `deleted_branches`: názvy skutečně smazaných
lokálních větví a remote větví s prefixem remote (např. `origin/factory/T01-1`).
CLI je vypíše také v textovém režimu; JSON chyby úklidu předává v `warnings`.

Offline testy používají skutečné git repozitáře a bare remote, fake gh a fake harness.
Ověřují operator i auto-merge, pořadí restack → mazání, pokračování stacked PR,
bezpečnost checkoutů a běžících běhů, historický úklid a opakování po chybě remote.
