---
id: HAIFA-REFINEMENT-T97
title: "Topbar: čip System info modře jako info, jen disk a RAM bez cest"
status: done
archived: true
workflow: build-test-review
depends_on: [HAIFA-REFINEMENT-T96]
writes: [aifactory/web/src/components/SystemInfoChip.vue, aifactory/web/src/components/SystemInfoChip.test.ts, aifactory/web/src/lib/system.ts, aifactory/web/src/App.test.ts, aifactory/src/aifactory/guide/08-aktualizace-a-reseni-problemu.md, aifactory/src/aifactory/web/static/]
---

## Zadání
## Zadání
Předěl čip System info v topbaru (`aifactory/web/src/components/SystemInfoChip.vue`, vznikl v HAIFA-REFINEMENT-T95):

- Barva a ikona: čip bude vždy modrý informační čip (`color: var(--blue)`) s ikonou `HardDrive` z `lucide-vue-next`. Žádná oranžová třída `warning` ani ikona `TriangleAlert`, a to ani při stavu `warning` z API, ani při chybě načtení. Spinner při načítání a úklidu zůstane.
- Obsah tooltipu: jen nadpis „System info“, řádek s diskem stroje, kde běží factory, a řádek s pamětí. Disk se bere z nového pole `disk` z HAIFA-REFINEMENT-T96, například „Disk: volné X GB / celkem Y GB“. Paměť zůstane jako „Paměť: volná X GB / celkem Y GB“. Hodnota `null` se zobrazí jako „nedostupné“. Žádné cesty, id svazků ani výpis `volumes`. Text chyby, výsledek úklidu a nápověda „Kliknutím uklidíš disk“ zůstanou jako text, ale barvu čipu nemění.
- `aifactory/web/src/lib/system.ts`: do typu `SystemInfo` přidej `disk: ResourceInfo`. Kontrola odpovědi v `load()` bude vyžadovat `disk` a `memory`, ne `volumes`.
- Úklid po kliknutí (potvrzovací dialog, `runCleanup`, obnova) se nemění.
- Testy: uprav `aifactory/web/src/components/SystemInfoChip.test.ts`. Čip má modrou info třídu i při `warning` a při chybě a nikdy třídu `warning`. Tooltip obsahuje disk a paměť a neobsahuje žádné cesty (např. `C:/haifa`). Hodnota `null` se ukáže jako „nedostupné“. Úklid funguje jako dřív. Pokud `aifactory/web/src/App.test.ts` mockuje `/api/machine/system`, doplň v mocku `disk`.
- Příručka `aifactory/src/aifactory/guide/08-aktualizace-a-reseni-problemu.md`: přepiš odstavec o čipu System info. Čip je modrý, ukazuje volné místo na disku stroje s factory a paměť, bez cest a bez oranžového varování. Odstavec musí dál projít stávajícím testem souladu příručky s UI. Ten test neměň.
- Na konci přegeneruj statický build příkazem `just web-build`.

Mimo rozsah: backend (HAIFA-REFINEMENT-T96), ostatní čipy topbaru, úpravy testu souladu příručky.

Hotovo znamená:
- Čip System info je v topbaru vždy modrý s ikonou disku, nikdy oranžový s výstražnou ikonou.
- Tooltip ukazuje jen disk a paměť stroje, kde běží factory, bez cest. Úklid po kliknutí funguje dál.
- Procházejí `SystemInfoChip.test.ts`, `App.test.ts` a stávající test souladu příručky s UI.
- Statický build v `aifactory/src/aifactory/web/static/` odpovídá zdrojům.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-27 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/186 · náklady $0.00
