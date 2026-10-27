# System info a úklid stroje

Globální dashboard poskytuje `GET /api/machine/system` a `POST /api/machine/cleanup`.
Oba endpointy používají standardní API envelope a blokující práci provádějí ve vlákně.

System info obsahuje `volumes`, `memory` a souhrnný `status` (`ok` nebo `warning`).
Svazek má `id`, `paths`, `free`, `total` a `status`; paměť má `free`, `total` a `status`.
Velikosti jsou v bajtech, nezjistitelné hodnoty jsou `null`. Svazky domova HAIFA,
systémového tempu a registrovaných rep se slučují podle zařízení, případně kořene disku.
Neexistující cesta se měří přes nejbližšího existujícího předka.

Warning nastává při volném disku pod 10 GiB nebo pod 10 % a při dostupné fyzické
paměti pod 1 GiB nebo pod 10 %. Rovnost s prahem je `ok`; neznámá hodnota sama
warning nevyvolává. Linux používá MemAvailable, Windows GlobalMemoryStatusEx,
macOS hw.memsize a součet volných, neaktivních a spekulativních stránek vm_stat.

Úklid přijímá JSON objekt `{}` a volá pouze existující `cleanup_orphans` nad systémovým
tempem a `clean_worktrees` pro každé registrované repo. Vrací `advice_directories`,
`repos` s výsledky CLI úklidu, `freed_bytes` a `warnings`. Chyba jednoho kroku nezastaví
ostatní repa. Souběžný požadavek na úklid vrací 409 s kódem `busy`.
Zápisy procházejí stávající ochranou Origin, Sec-Fetch-Site a Content-Type.
Úklid navíc vyžaduje přítomný platný Origin shodný s adresou serveru i při volání
z CLI; chybějící Origin vrací HTTP 403 `cross_origin` bez spuštění úklidu.

Ověření: `tests/web/test_web_system.py`, `tests/web/test_web_write_guard.py`,
`tests/web/test_web_machine.py` a `tests/web/test_web_cleanup.py`; lint a mypy
nad změněnými Python soubory. UI ani mazání archivovaných běhů, logů a trace DB
nejsou součástí změny.
