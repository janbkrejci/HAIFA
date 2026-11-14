# HAIFA-S01-T53 — Společný základ lokalizace EN/CS

Tento task zavádí mechanismus, nikoliv kompletní překlad dashboardu. Texty stávajících obrazovek a uživatelský přepínač migruje existující task HAIFA-S01-T54. V této fázi se žádný nehotový jazyk nenabízí jako dokončený překlad.

## Návrh

- `vue-i18n` v composition režimu má jedinou globální reaktivní hodnotu locale. Aplikační API vystavuje locale pouze pro čtení a změnu přes `setLocale`.
- Default je vždy `en`; jazyk prohlížeče se nepoužívá. `haifa.dashboard.locale` v localStorage obsahuje explicitní volbu `en` nebo `cs`, společnou pro všechny repozitáře daného originu. Chybějící či nepodporovaná hodnota a chyba přístupu do úložiště znamenají `en`. Selhání zápisu také nastaví aktivní locale na `en`.
- EN je povinný zdroj. CS může za běhu fallbackovat do EN. Veřejné `t` při chybějícím EN klíči vyhodí chybu, i když je klíč v CS.
- Statické katalogy mají stabilní klíče, pojmenované parametry a plurály. Angličtina má dvě větve (`one`, `other`), čeština čtyři (`one`, `few`, `many`, `other`). Výběr určuje `Intl.PluralRules`, včetně desetinných hodnot.
- Kontrola katalogů hlásí chybějící klíče obou jazyků, prázdné zprávy, nekompatibilní parametry jednotlivých větví a neplatný počet plurálových větví.
- Sdílené formátovače čtou locale při volání. `en` mapují na `en-US`, `cs` na `cs-CZ`. Časová zóna zůstává zónou prohlížeče; vstupní timestampy a částky se nepřevádějí. Měna nákladů zůstává USD.
- Přepnutí neprovádí reload, změnu routy ani remount komponent. Odvozené texty a validace se vytvářejí uvnitř computed nebo renderu.
- API enumy, error codes, ID, routy, data-test a uživatelská data se nepřekládají. Volba jazyka se neposílá do konfigurace repozitáře.

## Hranice migrace

Stávající `plural(n, one, few, many)` vybírá české literály v dosud nemigrovaných větách. Zachovává se jeho současné chování. Nové překlady používají katalogové plurály a `pluralCategory`; při migraci T54 se české literály i tento přechodový helper nahradí katalogy. Sdílené číselné, časové a relativní formátování již respektuje nové locale. Nejde tedy dosud o dokončené anglické UI.

## Ověření

Regresní testy pokrývají český prohlížeč s výchozím EN, reload explicitního CS, změnu repozitáře, neplatnou volbu, nedostupnost úložiště při čtení i zápisu, fallback, povinný EN zdroj, kontrolu katalogů a plurály 0/1/2/5/1,5. Test reaktivity ověřuje odvozený popisek, validaci, formátování a zachování rozepsaného formuláře a filtru bez remountu. Datum a čas se porovnávají s Intl ve stejné lokální časové zóně; náklady v obou locale zachovávají USD.
