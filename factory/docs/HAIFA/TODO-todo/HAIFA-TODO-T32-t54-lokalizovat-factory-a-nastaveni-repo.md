# Factory a nastavení repozitáře v EN/CS

Factory překládá kontrolu, instalaci a konfiguraci repozitáře, commit preview, roster, dědičnost, nastavení a lekce pomocí katalogu `factoryUi`. Výchozí jazyk určuje stávající klientská infrastruktura; tento díl nezpřístupňuje nový globální přepínač.

Změna jazyka upraví i otevřené potvrzení a již zobrazenou chybu. Nevytváří požadavky na API a nemaže rozepsané hodnoty. Hodnoty `local`, `github`, `azure`, `direct`, `pr`, `manual`, `auto`, identifikátory harnessů a úrovně thinking zůstávají hodnotami protokolu. Obsah lekcí, diffů a generovaného opravného tasku se nepřekládá.

Kontrola zobrazuje překládaný název nálezu a postup podle jeho kódu. Technické podrobnosti uchovávají původní zprávu a přesný příkaz nebo cestu. Stejně se zobrazují blokátory a diagnostika operací. Validace nastavení přidává do API issues `message_code` z typu validace a případně `params.limit`; původní API kódy a texty zůstávají zachovány. Server nepřepíná jazyk.

## Ověření

Testy komponent ověřují EN → CS → EN bez ztráty nastavení, instalačních voleb, commit message, vybraných nálezů a rozpracovaného rosteru. Další regrese pokrývají zamítnuté uložení, přepnutí otevřeného potvrzení a náhledu, projekt u lekce a původní autorský obsah. API test ověřuje metadata validace, shodnou odpověď pro EN/CS požadavky a zachování souboru po odmítnutém zápisu. Browser test lekcí obsahuje výchozí EN i explicitní CS.

Samostatný testovací krok úspěšně provedl lint, sestavení frontendu, 38 testů nastavení a konzistence příručky a čtyři browser scénáře. Cílené frontendové testy odhalily očekávání anglického popisku v testu spuštěném v CS. Regrese náhledu nyní ověřuje binární soubory i změny režimu v EN a CS. V katalogu byly také odděleny klíče doporučených oprav od skalárního popisku „Oprava“, aby nekolidovaly při zpracování vue-i18n; regresní test hlídá tuto vlastnost katalogu i konkrétní překlad opravy.

Další testovací krok úspěšně dokončil lint, typecheck (66,5 s), sestavení distribuovaných assetů a všech 163 cílených frontendových testů v 16 souborech. Ze čtyř browser scénářů prošly tři; EN scénář lekcí vyčerpal výchozí pětisekundový limit Playwright assertion při čekání na navrženou lekci.

Browser test nyní explicitně čeká na dokončený sken a používá 20sekundový limit assertions pro načtení sekce a asynchronní výsledky. Nastavení timeoutu akcí stránky totiž nemění timeout assertions. Všechny kontroly počtu lekcí, pravidla, výskytů, přijetí a uloženého tasku zůstávají zachovány. Jediný diagnostický běh buildera před doplněním limitu úvodního načtení selhal na stejném pětisekundovém limitu při stále probíhající kontrole Factory. Konečnou úpravu čekání ověří samostatný testovací krok. Aktivace globálního přepínače zůstává součástí HAIFA-TODO-T35.
