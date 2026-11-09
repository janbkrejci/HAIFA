# HAIFA-S11-T05 — Ovládání automatizací a harnessu na Přehledu

Přehled nabízí u každého repozitáře sekci **Na tomto počítači** s auto merge,
auto continue a výchozím harnessem z místního katalogu. Platí pro novou Factory
na tomto počítači. Změna se ukládá ihned přes službu T01 do HAIFA_HOME, bez
commitu nebo apply. Jiné klony a jiné repozitáře mají své vlastní volby.

Při vypnutí auto continue se zobrazí „Aktuální běhy doběhnou, další se nespustí“.
Přijatý běh se nezastavuje. Běžící worker při dalším automatickém přijetí čte
stejnou místní službu. Vypnutí auto merge brání dalším automatickým odesláním
merge; již odeslaný požadavek nelze stáhnout.

Ovladače zobrazují poslední potvrzené hodnoty. Po dobu ukládání jsou uzamčené;
při chybě zápisu se nezobrazuje požadované vypnutí jako účinné. Chyby čtení,
nedostupný katalog a nedostupný výchozí harness mají textové vysvětlení.
Checkboxy a sdílená komponenta SelectMenu mají přístupné popisky a ovládání
klávesnicí. Nedostupný uložený harness zůstává čitelný, ale není nabízen k výběru.

## API

- `GET /api/repos/{id}/settings/local` vrací payload `RepositorySettings.show()`.
- `PATCH /api/repos/{id}/settings/local` přijímá pouze změněná pole
  `auto_merge`, `auto_continue`, `harness` (null dědí nastavení počítače).
- Aktualizace používá `update_and_show()`: pod zámkem znovu načte ostatní pole
  a atomicky uloží změnu. Souběžné záložky si nepřepisují jiná pole.
- Explicitní harness musí být v místním katalogu dostupný a zapnutý.
- Chyby místního úložiště vracejí 503, neplatné hodnoty 422, nedostupný harness
  400. Standardní ochrana zápisů API platí i pro PATCH.
- Přehled přidává `local_settings` a `local_settings_error`; hodnoty se neberou
  z TTL cache konfigurace. Při nečitelných volbách nezobrazuje odhad účinného stavu.

Backlogové formuláře a strom už nenabízejí editaci těchto tří provozních voleb.
Staré záznamy se při běžné editaci nepřepisují. Vyloučení tasků z kanbanu,
nastavení modelů počítače a jednorázový override v RunDialog zůstávají zachované.
Importní API T06 zatím není přítomné; UI proto vysvětluje stav bez tlačítka,
které by nemělo funkční náhled a převzetí. Kompatibilní legacy API není odstraněno.

## Regresní pokrytí

Backendové testy pokrývají okamžité čtení, restart aplikace, souběžné dílčí
změny, oddělení repozitářů, nezměněný Git, chybu zápisu/čtení a katalogu a
odmítnutí nedostupného harnessu. Falešný dlouho žijící worker po vypnutí dokončí
přijatou práci a odmítne další přijetí. Vue testy ověřují potvrzené hodnoty,
ukládání, chybu, dílčí payloady a refresh přes kartu i klidový řádek Přehledu.
Browser scénář Přehledu vypíná auto continue mezerníkem během běhu falešného
harnessu a ověřuje reload, Git i druhý repozitář. Scénář Backlogu ověřuje absenci
starých ovladačů.

V builder fázi prošel jediný diagnostický test
`test_local_settings_errors_do_not_acknowledge_off`. Úplné ověření včetně
`just lint`, `just typecheck`, Vue testů, `just web-build` a obou upravených
browser souborů náleží samostatnému testovacímu kroku. Frontend je třeba před
browser testy sestavit, aby dashboard podával nové statické soubory.
