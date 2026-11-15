# Lokalizace běhů

Texty obrazovky Běhy jsou v EN/CS katalogu `aifactory/web/src/lib/i18n/runs.ts`, připojeném ke společnému katalogu. Reaktivní popisky a odložené formátování chyb a potvrzení umožňují změnit jazyk bez ztráty rozpracovaného stavu nebo přerušení živého sledování.

`runMessages.ts` převádí existující API kódy na lokalizované hlášky. Originální výjimky zůstávají nezměněné. Řetězy zobrazují lokalizovaný stav podle kódů a původní podrobnosti v rozbalovací technické diagnostice. Záznamy běhů, logy, prompty a agentem vytvořený obsah se nemění.

Nové integrační testy jsou v `RunsView.locale.test.ts`, mapování API kódů v `runMessages.test.ts`. Existující české testy mají explicitní locale a odpovídající číselné formáty. Upravené browser testy ověřují českou variantu dlouhého seznamu a waterfallu.

Samostatný testovací krok odhalil zastaralá očekávání české měny a lokalizované API chyby, chybějící mezeru před stavem review a dvě typové chyby. Očekávání byla upravena, mezera je explicitní a její regrese pokrývá oba jazyky; nepoužitý import a typově neplatné volání testovacího wrapperu byly odstraněny. Ověření oprav přísluší samostatnému testovacímu kroku workflow. Distribuované assety a globální zpřístupnění přepínače jsou součástí navazujícího HAIFA-TODO-T35.
