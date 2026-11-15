# Globální English/Čeština

Dashboard nabízí English/Čeština v horní liště i bez repozitáře. Otevřený AI průvodce má totožný přepínač uvnitř panelu. Obě ovládání používají existující přístupný SelectMenu a stejnou browser preferenci; přepnutí nemění URL ani data repozitáře. Výchozí EN a fallback při nedostupném úložišti zůstávají podle kontraktu i18n. Preference platí pro jeden origin, nikoli pro jiný browser nebo port dashboardu.

## Audit lokalizace

- Katalogy `catalogs`, `helpers`, `backlog`, `runs`, `review`, `factory` a `setup` mají společnou kontrolu úplnosti EN/CS, parametrů a plurálů v `lib/i18n/i18n.test.ts`.
- Prohledání produkčních Vue/TS zdrojů odhalilo chybějící překlad ovládání příručky a popisků „požadavek“/„kód“ v drahách časové osy. Tyto popisky nyní používají katalog.
- České komentáře, technická jména (Factory, Backlog, Review, Git, PR, harness, model), kódy protokolu a ID se nepřekládají. Výchozí zadání opravy Factory a výsledky provedených akcí průvodce jsou uložený obsah; změna locale je nepřepisuje. Raw chyby a výstupy modelů zůstávají diagnostikou vedle přeloženého vysvětlení.
- Kapitoly příručky zůstávají českým dokumentem; anglické rozhraní to výslovně uvádí. Ovládání, hledání, načítání a chyba příručky reagují na locale. Článek má `lang="cs"`. Průvodce prvním během uvádí přesné volby English/Čeština; shodu ostatních tučných popisků s výslednými zdroji hlídá `test_guide_consistency.py`.

## Regrese a distribuce

Komponentové regrese ovládají skutečný globální přepínač bez repozitáře a přepínač uvnitř otevřeného průvodce. Příručka zachovává dotaz i článek; časová osa překládá popisky drah a zachovává jména agentů.

`tests/e2e/test_locale_browser.py` obsluhuje pouze distribuované assety a předem daná API. Nepoužívá živé modely ani služby. Pokrývá EN navzdory českému browseru, CS bez repa, reload a dvě repa, návrat EN, klávesnici, absenci dodatečných API zápisů při přepnutí, zachování DOM a textu formuláře, Intentu a otevřeného panelu, přeložení chyby uložené po jediném API požadavku a zachování streamu, vypnutého následování a posunu sledovaného běhu včetně úzkého okna.

Frontend byl sestaven příkazem `bun x vite build` v `aifactory/web`; distribuované soubory jsou součástí změny. Diagnostický browser běh varianty 390 px zastavilo chybné očekávání nadpisu prázdného Přehledu (správně No repositories / Žádné repozitáře); očekávání bylo opraveno. Tento běh není dokladem průchodu celého scénáře. Výsledky lint, typecheck a regresních testů zaznamená samostatný testovací krok workflow.
