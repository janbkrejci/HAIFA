# Úpravy backlogu během běhu

Zápisy task edit a archivace nadále používají journal továrních zápisů. Guard nyní porovnává jeho původní obsah s bajty po checkout převodu Gitu, včetně CRLF. Čistý soubor s CRLF se tak nepovažuje za předchozí zásah agenta. Obnova čistého souboru používá stejný převod. Zásahy agenta před zápisem továrny i samostatný pohyb HEAD zůstávají porušením.

Dashboard předává varování z backlog commit do výsledku API i jeho envelope. Po commitu s varováním automaticky otevře panel backlogu s důvodem odloženého posunu base a pokynem `factory config pull` po skončení běhu. Totéž platí pro commit z dialogu spuštění úlohy. Varování zmizí po načtení čistého stavu backlogu nebo změně repozitáře.

Regresní pokrytí zahrnuje archivaci CRLF souboru během fáze, souběžný nepovolený pohyb HEAD, obnovu CRLF souboru, přenos varování API a zobrazení ve Vue i skutečném prohlížeči.
