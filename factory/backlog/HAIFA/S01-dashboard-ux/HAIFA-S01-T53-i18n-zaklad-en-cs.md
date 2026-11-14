---
id: HAIFA-S01-T53
title: "Vícejazyčnost dashboardu: společný základ EN/CS a lokalizované formátování"
status: todo
depends_on: []
writes: [aifactory/web/, aifactory/src/aifactory/web/static/, aifactory/tests/]
---

## Zadání
Připravit jeden společný mechanismus lokalizace dashboardu pro en a cs. Výsledným požadavkem je kompletní anglické UI jako default a volitelná čeština; migraci textů a zpřístupnění přepínače dokončí navazující task. Tento základ sám nesmí uživateli nabízet nehotový překlad jako hotový jazyk.

Akceptace:
- Jediné reaktivní locale pro celou aplikaci, katalogy EN a CS se stabilními klíči, parametrizací a plurály. Použít nejmenší vhodné řešení pro Vue, bez vlastního překladatelského serveru a runtime překladů pomocí AI.
- Bez uložené platné volby je locale en, i při českém jazyku prohlížeče/OS. Explicitní volba cs přetrvá reload a změnu repozitáře v tomto prohlížeči. Nepodporovaná hodnota a nedostupné úložiště mají předvídatelný fallback en; jazyk není sdílenou konfigurací repozitáře a nevyžaduje commit.
- Přepnutí locale je reaktivní i pro odvozené popisky, validace a formátovače. Intl formátování data, času, čísel a plurálů respektuje locale; zachovat časovou zónu, význam hodnot a měnu nákladů (USD). Odstranit závislost společných formátovačů na natvrdo cs-CZ; samostatně ověřit 0/1/2/5 a desetinná čísla.
- Chybějící český překlad fallbackuje na anglický. Kontrola katalogů zachytí chybějící klíče a nekompatibilní placeholdery; chybějící anglický klíč nesmí být skryt tichým českým fallbackem.
- Stabilní IDs, API enumy/error codes, routy a data-test se nepřekládají. Přepnutí jazyka nesmí resetovat formuláře, filtry ani aktivní práci.

Testy: default en v českém prohlížeči, persistence cs, neplatná volba, úložiště nedostupné, reaktivní změna formátování, fallback a kontrola katalogů. Navazující migrace musí použít tento základ a zpřístupnit uživatelský přepínač až s dokončenými katalogy.

Ověření: vyhledat přímé volající v celém aifactory/tests/ a zvolit jen testy dotčeného chování. Spustit každý změněný testovací soubor, just lint, just typecheck, just web-test, just web-build a příslušné browser testy změněných obrazovek podle AGENTS.md. Testy bez živých modelů a služeb, s izolovaným HAIFA_HOME; nespouštět celou sadu v tasku.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
