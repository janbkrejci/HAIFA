# HAIFA-S11-T02: živé Auto continue

Automatické pokračování používá lokální `RepositorySettings` z T01. Chybějící
nastavení znamená off. Přepínač patří společnému Git adresáři repozitáře, platí
pro všechny jeho projekty a instance workeru a přežije restart. Výběr řetězu
zůstává uvnitř původního projektu; pořadí fronty, závislosti, vyloučení a kolize
zápisů nadále platí. Staré hodnoty v tasku, kroku nebo projektu výběr nefiltrují.

## Přijetí automatického běhu

`run.policy.acceptance` drží stejný procesový zámek jako aktualizace nastavení
pouze přes `claim`, `reclaim` nebo `Popen`. Potvrzené off proto předchází každému
dalšímu přijetí. Zámek se nedrží při workflow, čekání na claim child procesu ani
při CI. Child znovu ověří politiku při vlastním claimu: spawn před off neopravňuje
opožděný claim po off. Původ `auto-continue` předává i webový launcher.

Sekvenční i paralelní fronta čte politiku za běhu a před každým opakováním startu
po zamčené trace DB. Off zastaví refill, nové pokusy automatického healu a quota
fallbacku i pokračování po publish/approve. Přijaté běhy se nezabíjejí a jejich
vnitřní fáze, CI opravy, resolve a dokončení merge pokračují. Ruční run a retry
jednoho tasku zůstávají dostupné. Zapnutí samotné žádnou práci nespouští.

`--auto` je kompatibilní deprecated volba bez vlivu na politiku; CLI to výslovně
vypisuje. Nastavení se mění příkazem
`factory config local set --auto-continue on|off --repo PATH --json`.
Pokud off vyhraje závod před uzavřením `nothing_to_do` healu, uzavření se neprovede
a fronta dokončí čekání na přijaté členy se stavem `disabled`, bez výjimky a abortu.
Odmítnutý start nese registrovaný JSON kód `auto_continue_disabled` a české vysvětlení. Ukončený řetěz
má `stop: disabled` a `stop_detail` s vysvětlením lokálního vypnutí.
Neplatné či nečitelné nastavení se hlásí jako chyba a nepoužívá dřívější on.

## Regrese a ověření

`tests/run/test_live_auto_continue.py` pokrývá změnu během přijatého workflow,
mezi select a startem, před claim/reclaim child procesu, během CI a lock retry,
doběhnutí paralelních členů, heal, publish, kompatibilní CLI a původ webového startu.
Procesové testy ověřují perzistenci a oddělení dvou repozitářů. Existující
`tests/test_repo_settings.py` ověřuje serializaci aktualizace s přijatým startem
mezi procesy. Testy approve ověřují off i u řetězu původně spuštěného s `--auto`.

Validační scénáře F2 a Azure E2E zapínají lokální pokračování pouze pro svůj
řetěz a v bloku `finally` jej opět vypínají, včetně selhání spuštění.

Diagnostické zkoušky ověřily claim bariéru s ručním startem a členskou CLI cestu
s lokálním on i off včetně platné JSON obálky odmítnutého startu.
Úplnou cílenou verifikaci změn provádí samostatný testovací krok workflow.
