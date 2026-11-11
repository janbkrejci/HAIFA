# Testování podle rozsahu změny

Interpreter odkládá plán s `coverage: full` v implementačních a resolve workflow až za běžné opravy a review. Nejprve si vyžádá scoped plán. Po opravě nebo revizi vyžaduje scoped pokrytí: neúspěšné a nespuštěné kontroly, kontroly posledních úprav a přímých volajících. Zelené kontroly nedotčeného chování není nutné opakovat ani pokaždé zdůvodňovat v `dropped`.

Před konečným commitem nebo akceptací proběhne jedno potvrzení celé sady, pokud ji první plán požadoval. Selhání vrátí běh do nejvýše tří cílených opravných kol; opravy znovu posoudí reviewer, jestliže už v běhu review proběhlo. Neúspěšná celá sada se rozdělí na cílené regrese pod stejným názvem kontroly, neopakuje se. Běžnou neúspěšnou kontrolu nelze zahodit ani důvodem v `dropped`; oprava neplatného příkazu vyžaduje pojmenovanou náhradu a důvod. Samostatné read-only workflow `quality` spouští vyžádanou celou sadu přímo, jednou. `heal` používá scoped opravy a stejné jednorázové konečné potvrzení.

Tester dostává kromě skutečného diffu také `testing_scope`: seznam souborů, sdílené cesty a doporučené pokrytí. Dokumentace a backlog vyžadují jen kontroly, které soubory čtou; žádný build ani testy kódu. Kód vyžaduje dotčené projekty a přímé volající. Celá sada patří změně sdílené infrastruktury nebo závislostem, které nelze dohledat ani po hledání volajících. Profil může uvést repozitářové sdílené cesty řádkem `shared_paths: glob, path/prefix`. Doporučení nenahrazuje posouzení skutečného diffu testerem a reviewerem.

Resolve připíná testovací baseline na HEAD PR před rebase a ukládá ji do journalu. Tester tak vidí i automaticky sloučený kód, nikoli jen seznam konfliktů. Markdownový konflikt sám nevyžaduje build; změněný `.cs` vyžaduje build a testy dotčeného projektu.

Počet a důvody celých sad obsahuje výsledek `full_suite`, souhrn výsledku testu a log fáze (`full_suite_runs`, `full_suite_reasons`). Souhrn se přenáší do PR a důkazy fáze jsou dostupné v dashboardu. Journal zachovává výsledky při retry, takže dokončené potvrzení není znovu spuštěno.

Regrese pokrývají scoped opravu a revizi před jediným konečným potvrzením, selhání potvrzení, zákaz druhého spuštění, ochranu neúspěšné kontroly, replay, kategorie diffu a resolve s automaticky sloučeným kódem. Builder diagnosticky ověřil jeden scénář opravy a revize; kompletní cílené ověření provádí testovací krok workflow. Provozní hodnoty NEO_HEF po nasazení nejsou součástí tohoto lokálního ověření.
