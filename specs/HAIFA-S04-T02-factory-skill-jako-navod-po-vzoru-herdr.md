# HAIFA-S04-T02: factory --skill jako návod pro agenty

Výstup `factory --skill` je uložitelný Markdown skill s YAML front matter
`name: factory`, popisem použití a verzí. Po změně `factory --version` se obnovuje.
JSON varianta zachovává dosavadní envelope i generované příkazy a chybové kódy.

Návod začíná kontrolou `factory check --json` a volí init, onboard, adopt nebo
commit konfigurace podle stavu a akce. Instalace do stávajícího repa používá
náhled s výběrem agentů a vazeb, kontrolu souborů a digestu uživatelem, potvrzení
s `--expect` a stejné volby jako náhled. PR po `push_failed` vyžaduje souhlas.
Po instalaci následuje kontrola factory i backlogu.

Reference konfigurace čerpá popisy a výchozí hodnoty z Pydantic modelů včetně
vnořených azure a generated. Chybějící popis zastaví generování. Návod vysvětluje
sloty, vazby, oba povinné prompty, proměnné, testovací krok, manifest a export
upravených promptů. Projekty a stepy vznikají přes backlog add, nastavení přes
backlog edit, hierarchie je project → step → task.

Regresní testy běží bez modelů a sítě. Implementace nemění CLI pro ukládání skillu,
chráněné snapshoty ani produktový brief.
