# T28: Lokalizace Přehledu, problémů a dema

Přehled a jeho filtry, karty, automatizace, ovládání a demo používají katalogy EN/CS. Změna jazyka nepřipojuje komponenty znovu, nemění výběr filtrů, projektové volby, sledovaný běh ani potvrzená místní nastavení. Výsledky akcí a otevřená potvrzení se překládají i po dokončení původního požadavku.

Popisky automatických zásahů vycházejí z `action`, `ok`, identifikátorů a strukturovaného `detail`. Nálezy a chyby používají stabilní kódy. Původní diagnostika, cesty, názvy projektů a tasků zůstávají zachované; diagnostika nálezů a přeskočených tasků je dostupná v rozbalovacích technických podrobnostech. Chyba místních nastavení v Přehledu nově poskytuje `local_settings_error_code`. Server nemá globální locale a vrací stejná data souběžným klientům.

Na šířce 390 px se filtry skládají do dvou sloupců a hlavička se zalamuje. Browser scénáře vybírají jazyk explicitně, nové scénáře pokrývají EN i CS. Komponentové regrese ověřují přepnutí bez remountu, potvrzení, výsledky akcí, nálezy a demo; místní ovládání ověřuje přepnutí během ukládání.

Jeden diagnostický běh `bun run test src/views/OverviewLocale.test.ts` prošel (8 testů). Po něm byly doplněny další regrese a dokončeny popisky chyb; úplné ověření patří samostatnému testovacímu kroku. První pokus o diagnostiku použil chybnou cestu při vytváření testu z adresáře webu a žádný test nespustil; správný příkaz výše se spouští z `aifactory/web/`.

Globální přepínač a finální audit lokalizace vlastní navazující T35. Při testovacím kroku byly sestaveny také distribuované assety. Sdílené navigační a registrační dialogy mají vlastní migrační tasky; tento díl je nezpřístupňuje jako dokončenou celkovou lokalizaci.

Timeouty nyní uchovávají identitu kroku (`machine`, `library`, `repos`, `roster`, `backlog`, `evaluation`) a případný technický detail odděleně od přeloženého textu. Serverový timeout, transportní `request_timeout` i pomocné chyby lze přepnout CS → EN → CS bez dalšího požadavku. Cílený diagnostický běh čtyř nových scénářů v `OverviewReadiness.test.ts` prošel.

Repozitářová varování vracejí vedle kompatibilního pole `warnings` strukturované `warning_details` s kódem, parametry a původní diagnostikou. Karta překládá popis podle kódu; původní text je zachován v technických podrobnostech. Backendové regrese pokrývají nečitelnou databázi, nedostupné změny konfigurace, timeout a chybu repozitáře; komponentové regrese ověřují přepnutí již zobrazených varování a kompatibilitu starších odpovědí bez kódů.
