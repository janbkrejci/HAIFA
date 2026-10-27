---
id: HAIFA-REFINEMENT-T95
title: "Topbar: čip System info s místem na disku, pamětí a úklidem"
status: done
workflow: build-test-review
depends_on: [HAIFA-REFINEMENT-T93, HAIFA-REFINEMENT-T94]
writes: [aifactory/web/src/App.vue, aifactory/web/src/App.test.ts, aifactory/web/src/lib/system.ts, aifactory/web/src/components/SystemInfoChip.vue, aifactory/web/src/components/SystemInfoChip.test.ts, aifactory/src/aifactory/guide/08-aktualizace-a-reseni-problemu.md, aifactory/src/aifactory/web/static/]
---

## Zadání
Do topbaru (`aifactory/web/src/App.vue`, `.topbar-right`, vedle čipů z HAIFA-REFINEMENT-T93) přidej čip System info. Stavy převezme z API `GET /api/machine/system` z tasku HAIFA-REFINEMENT-T94.

Co udělat:
- `aifactory/web/src/lib/system.ts`: typy odpovědi, `fetchSystemInfo()` a `runCleanup()` (POST `/api/machine/cleanup`) přes sdílené `lib/api.ts`. Obnova se spustí při načtení a pak periodicky, například každou minutu, a po úklidu hned.
- `aifactory/web/src/components/SystemInfoChip.vue`: kompaktní ikonový čip ve stejném stylu jako ostatní čipy po T93 (ikona HardDrive nebo Gauge z `lucide-vue-next`, zelená u `ok`, oranžová u `warning` s ikonou TriangleAlert, spinner při načítání a úklidu). Tooltip ukáže volné a celkové místo každého svazku (s cestami, které na něm leží) a volnou paměť ve čitelných jednotkách (GB), `null` jako „nedostupné“, a nápovědu „Kliknutím uklidíš disk“.
- Klik otevře potvrzovací dialog (`lib/confirm.ts`, vlastní modál, ne systémový), který řekne, co se smaže: osiřelé dočasné adresáře návrhů a hotové worktrees a větve sloučených PR ve všech repech. Po potvrzení zavolá úklid a výsledek (počet odstraněných položek, uvolněné místo, varování) ukáže v tooltipu nebo krátkém hlášení. Chyba se ukáže, nespadne.
- `aifactory/web/src/components/SystemInfoChip.test.ts`: zobrazení ok, warning a nedostupné paměti, tooltip s hodnotami, potvrzení a zrušení úklidu, obnova po úklidu.
- Krátce popiš čip v příručce `aifactory/src/aifactory/guide/08-aktualizace-a-reseni-problemu.md`, aby dál procházel test souladu příručky s UI.
- Na konci přegeneruj statický build `just web-build`.

Mimo rozsah: změny backendu (T94), úprava ostatních čipů (T93).

Hotovo znamená:
- V topbaru je čip System info. V tooltipu je volné místo na disku a volná paměť a při nedostatku je čip oranžový.
- Klik po potvrzení spustí úklid disku a čip se pak obnoví s novými hodnotami.
- Prochází `SystemInfoChip.test.ts`, `App.test.ts` a test souladu příručky s UI.
- Statický build v `aifactory/src/aifactory/web/static/` odpovídá zdrojům.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-27 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/184 · náklady $0.00
