# Globální jazyk dashboardu

Volba English/Čeština je dostupná v horní liště na všech stránkách, včetně prázdného dashboardu bez repozitářů. AI průvodce překrývá horní lištu, proto poskytuje stejnou volbu přímo v panelu.

Výchozí jazyk je EN, nezávisle na `navigator.language`. Preference `haifa.dashboard.locale` je společná pro repozitáře v jednom browser origin a přetrvá obnovení stránky. Neplatná nebo nedostupná preference vede k EN podle existujícího kontraktu i18n.

Změna jazyka probíhá reaktivně, bez navigace, obnovení stránky, opakovaného API zápisu nebo připojení streamu. Zachová rozpracovaný Intent, formulář, otevřený panel a sledovaný běh. Překládá ovládání, titulky, přístupné názvy, stavové popisky a známé chyby API. Uživatelský obsah, odpovědi agentů, zaznamenané výsledky akcí a diagnostika zůstávají původní.

Příručka má lokalizované ovládání a vyhledávání. Kapitoly jsou český dokument, označený `lang="cs"`; anglické rozhraní tuto skutečnost uvádí. Česká příručka jmenuje obě volby přesně jako ovládání.

Regrese pokrývá katalogy a komponenty i distribuované assety v browseru při šířkách 1366 a 390 px. Browser scénář zahrnuje české nastavení prohlížeče s výchozím EN, CS bez repozitáře, obnovení stránky, dvě repa, návrat EN, klávesnici, rozepsané formuláře a Intent, otevřeného průvodce, chybu API v EN/CS/EN a zachování streamu i posunu běhu. Kontroly provádí samostatný testovací krok workflow.
