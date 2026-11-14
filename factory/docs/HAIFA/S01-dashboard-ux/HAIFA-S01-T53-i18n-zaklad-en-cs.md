# HAIFA-S01-T53 — Použití lokalizačního základu

Dashboard používá `vue-i18n` z `src/lib/i18n`. Katalogy EN/CS zatím obsahují společný základ. Uživatelský přepínač není vystaven; kompletní migraci textů a jeho zpřístupnění řeší HAIFA-S01-T54. Současné české literály v obrazovkách nejsou hotové anglické UI.

## API pro migraci

```ts
import { computed } from 'vue'
import { useLocale } from '@/lib/i18n'
import { fmtNumber } from '@/lib/format'

const { locale, t, setLocale } = useLocale()
const saveLabel = computed(() => t('common.save'))
const validation = computed(() => t('validation.required', { field: fieldLabel.value }))
const itemsLabel = computed(() => t('counts.items', {
  count: fmtNumber(items.value.length),
}, items.value.length))
```

`setLocale('cs')` nebo `setLocale('en')` mění jedinou globální hodnotu a ukládá preferenci v localStorage pod klíčem `haifa.dashboard.locale`. Hodnota není závislá na repozitáři. Bez platné uložené volby je locale `en`, i v českém prohlížeči. Nepodporovaná volba nebo nedostupné úložiště vede k `en`. Při selhání zápisu se aktivní hodnota vrátí na `en`; preference není zaručeně uložená.

Překládejte přes veřejné `t`, které vyžaduje existenci EN zdroje. Nepoužívejte přímo globální překladovou metodu knihovny, která tuto podmínku nekontroluje. Překlad odvozených popisků a validací volejte v computed/renderu, nikoliv jednou při setupu. Formulářové hodnoty uchovávejte jako data, nikoliv jako přeložené texty. Locale nepoužívejte jako komponentový `key` a při přepnutí neměňte routu ani stav práce.

## Katalogy a plurály

Přidávejte stabilní klíče do `catalogs.ts` v EN i CS. `MessageKey` vychází z EN klíčů, typ CS katalogu kontroluje jejich přítomnost. `validateCatalogs` navíc v testu porovnává úplnost, placeholdery v každé větvi a plurálové struktury. Za běhu chybějící CS zpráva fallbackuje na EN. Chybějící EN zpráva vyvolá chybu i v českém režimu.

Větve se oddělují `|`. EN používá pořadí `one | other`; CS `one | few | many | other`. V češtině je `many` určeno desetinným hodnotám, `other` například 0 a 5. Číselný parametr pro zobrazení formátujte přes `fmtNumber`; jako třetí argument `t` předejte původní číslo pro výběr plurálu. Placeholdery musí být stejné ve všech větvích a jazycích. `pluralCategory` poskytuje přímo kategorii Intl.

Dosavadní `plural` v `format.ts` je přechodový helper pro existující české věty. Pro nové zprávy jej nepoužívejte; T54 převede jeho volající na katalogové plurály.

## Formátování a ověření

`fmtNumber`, `fmtInt`, `fmtTokens`, `fmtDuration`, `fmtCost`, `fmtMoney4`, `fmtTime`, `fmtDayTime`, `fmtClock` a `fmtAge` čtou aktuální locale, takže je lze volat v template/computed. Částky zůstávají v USD, časové údaje v časové zóně prohlížeče. Technické offsety a celočíselné doby zachovávají kompaktní zápis jednotek.

Diagnostika integrace je v `src/lib/i18n/i18n.test.ts`. Samostatný tester ověří upravené frontendové testy přes `just web-test`, dále `just lint`, `just typecheck`, `just web-build` a browser scénáře dotčených formátovaných údajů. Build aktualizuje distribuovaný frontend v `aifactory/src/aifactory/web/static/`. Backend se nemění; hledání ve všech `aifactory/tests/` nenalezlo přímé volání TypeScriptových formátovačů ani očekávání jejich původních českých časových nebo číselných výstupů.
