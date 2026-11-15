# T05 — příprava migrace repozitáře

[Provozní postup T06](../../../../docs/rebranding/repository-migration.md)
obsahuje read-only inventuru hostingu z 2026-11-15, přesný zdroj/cíl, devět
vzdálených větví a přenos všech heads/tags se zachováním SHA. Otevřené PR/issues
nebyly nalezeny; staré objekty a releasy zůstanou v HAIFA. Knihovna zůstává
HAIFA-LIBRARY podle kompatibilní výjimky T01.

Poslední HAIFA se sestaví výhradně z T04 commitu
`4dd3ddf1ea18f672674123df94dc4643a4868f52`, po ověření prvního GIRO z nového
repo. Postup rozlišuje dosud neexistující výsledný T06 SHA/verze od doložených
zdrojů, určuje jednorázový H gate a ukončení Actions v HAIFA. Zahrnuje rollback,
konkrétní mapu aktivních URL a popisků i odstávku při volitelném přesunu checkoutu.

Regresní test `docs/rebranding/verify_repository_migration.py` provádí přímo
Git blok dokumentace v izolovaných lokálních repozitářích. Pokrývá historii,
dvě větve, oba typy tagů, nedotčený zdroj a odmítnutí neprázdného cíle,
shodného zdroje/cíle a existujícího staging adresáře. Je určen pro samostatný
test krok: `python3 docs/rebranding/verify_repository_migration.py`.
Builder testovací gate nespouštěl. Hostingové důkazy pocházejí z GitHub connectoru,
read-only gh API a aktuálních oficiálních GitHub dokumentů, odkázaných v postupu.
Žádný remote, hosting, hlavní checkout ani knihovna nebyly změněny.
