# Přehled po projektech

Přepínač „Po projektech“ v hlavičce Přehledu je ve výchozím stavu zapnutý. Zobrazí se, pokud alespoň jedno registrované repo obsahuje více projektů. Volba se ukládá v prohlížeči pod klíčem `haifa.overview.byProject`; při nedostupném úložišti funguje pro aktuální zobrazení.

Víceprojektové repo zobrazuje sekce s názvem projektu, jeho id v tooltipu, barevnými chipy počtů tasků a příslušnými běhy, review, automerge PR a selháními. Běh s ukončeným procesem zůstává mezi selháními svého projektu. Položky bez přiřazeného projektu (včetně položek ze staršího serveru a neznámých id) patří do sekce „Bez projektu“, která vzniká pouze při jejich výskytu.

Stejné členění mají klidná repa. Ovládání továrny, sloty, konfigurace, automatické zásahy, PR sloučené mimo factory a poslední aktivita zůstávají společné pro repo. Vypnutý přepínač a repa s nejvýše jedním projektem zachovávají souhrnné zobrazení. Řazení, součty a filtr používají nadále celé repo. Starší odpověď API bez `projects` se normalizuje na prázdný seznam.

Ověření pokrývají unit testy pomocných funkcí, komponenty karty a obrazovky Přehledu: rozdělení práce včetně nepřiřazených položek, chipy, přepnutí na souhrn, jediný projekt, klidná repa, skrytý přepínač a zapamatování volby. Statický frontend se obnovuje receptem `just web-build`.
