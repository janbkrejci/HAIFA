# Evidence běžících operací před claimem

Dashboard a paralelní auto-continue zveřejní spuštěný proces v trace DB ještě před vznikem `task_runs`. Evidence obsahuje samostatné ID operace, task, akci, PID a čas spuštění. Zahrnuje run, retry, return, resolve, approve a publish; přímé `publish_task` eviduje také samotnou publikaci.

Živá operace překryje předchozí neúspěšný běh či uložený `pr_error` při sdíleném odvození kanbanu a přehledu. Chyba publikace zůstává zachována do výsledku nového pokusu. Po claimu má přednost skutečný běh s fází a pauzou. Operace se neukládá jako nový běh.

Ukončený proces se v pohledu ignoruje. Launcher odstraní operaci při dokončení, ProcessRunner při claimu, selhání či timeoutu. Store odstraňuje mrtvé lokální vlastníky také při čtení živých operací. Read-only přehled záznamy nemění a umí číst starší DB bez nové tabulky.

Výpočty slotů a připravenosti dál používají skutečné živé běhy a otevřené PR. Samotná operace nemění kapacitu ani chování ovládání běhů.

Ověření zahrnuje čekání před claimem, retry stejného run ID, opakovanou publikaci se starou chybou, selhání člena před claimem, mrtvý proces, úklid a shodu obou pohledů. Testy nepoužívají živé modely ani hosting.

Frontend přijímá `run_id: null` se stabilním `operation_id`. Pending položky mají samostatné klíče a odkazují na existující detail tasku, po claimu na detail běhu. Pending operace sama nenabízí ovládání vyžadující skutečný run ID. Regrese pokrývá více souběžných operací, změnu pořadí a přechod na claimnutý běh s původní fází a pauzou.
