# HAIFA-S02-T03 — Waterfall běhu podle sssf

Detail běhu (`#/runs/<běh>`) už neukazuje tabulku fází (`table.phases`). Místo ní je waterfall
(gantt) převzatý z `vendor/sssf/apps/visualizer/src/components/SessionTrace.vue`. Hlavička běhu
(task, stav, Zastavit, údaje, statistiky) a panel fáze (`PhaseDetail`) zůstávají beze změny.

## Soubory (vše pod `aifactory/web/src/`)

- `lib/waterfall.ts` (nový) – čisté výpočty bez DOM:
  - `buildLanes` – dráhy: `engineer`, `code` (všechny kódové fáze), pak `agent:<jméno>`
    v pořadí prvního výskytu. Agent ve více fázích má jednu dráhu.
  - `buildTimeline` – rozsah osy, vyhrazený úsek pro požadavek engineera (`REQ_ZONE_PCT` = 16 %),
    značky osy a geometrie bloků. Bloky mají minimální šířku `MIN_BLOCK_PCT` = 3,5 % a nikdy se
    nepřekrývají. Když se nevejdou, zmenší se mezery a delší bloky.
  - `blockDurationMs`, `phaseEndMs`: běžící fáze končí v „teď“. `isLive`: běh nebo některá
    fáze ještě běží.
  - `toolTicks` – pozice tool calls v bloku. Chybu pozná `eventOk`.
  - `laneContext` / `contextLabel` / `contextFill` – zaplnění kontextu agenta, když je známé.
- `components/runs/RunWaterfall.vue` (nový) – vykresluje dráhy (model s ikonou poskytovatele,
  kontext, barva agenta), osu, bloky (stav, název, doba, popis), značky tool calls a tooltip
  (stav, popis, harness, model, pokus, doba). Neúspěšný blok má třídu `failed` a červený okraj.
  Fáze bez začátku jsou čárkované („ve frontě“). Klik na blok nastaví `#/runs/<běh>/<fáze>`,
  klik na vybraný blok vrátí `#/runs/<běh>`.
- `components/runs/RunDetail.vue` – místo tabulky je `<RunWaterfall>`. Přes `useNow` tiká čas.
  Statistika `runtime` u běžícího běhu roste od `started_at`.
- `components/runs/StatChip.vue` – nový prop `plain`: bez tooltipu a `tabindex`, pro použití
  uvnitř tlačítka bloku.
- `lib/clock.ts` (nový) – `useNow(active, intervalMs = 1000)`: reaktivní epoch ms. Tiká jen
  při `active()`, při zrušení scope se zastaví. Dokončený běh žádný časovač nemá.
- `lib/events.ts` – `AGENT_FALLBACK_COLORS` a `agentColor(config, payload, index)`. Prázdná nebo
  jen bílá barva se bere jako nenastavená a použije se paleta podle indexu dráhy. Dále `hexAlpha`.
  `eventOk` vrací false i pro nenulový `returncode`, takže u kódových fází (`quality:*`)
  rozhoduje výsledek příkazu.
- `lib/format.ts` – `ts`, `fmtOffset`, `axisTicks`.
- `lib/runs.ts` – typ `PhaseKind`, exportovaný `bySeq`.

## Mimo frontend

- Build: `aifactory/src/aifactory/web/static/index.html` odkazuje na nové
  `assets/index-Dowe2FNV.js` a `assets/index-CK5DVINy.css`. Staré `index-DyOEKdbR.js`
  a `index-CEAt3BWz.css` jsou smazané.
- `aifactory/tests/e2e/test_f3_browser.py` – kontroluje, že `table.phases` chybí a že jsou
  vidět dráhy `engineer` a `agent:planner` a bloky. Pak vybere fázi klikem na
  `button.block[data-name="plan"]` a ověří adresu i to, že druhý klik výběr zruší.
- `aifactory/tests/web/test_web_launcher.py` – jeden `_until` čeká déle (`timeout=60`).
- Seed prompty `seed/agents/builder/system.md` a `seed/agents/reviewer/system.md`: builder
  pouští jen cílené testy, nikdy celou sadu. Reviewer nespouští žádné testy ani kontroly.

## Ověření

- Unit testy: `lib/waterfall.test.ts` (pořadí drah, jedna dráha agenta, nepřekrývání,
  minimální šířka, záložní barva), `RunWaterfall.test.ts` (dráhy, bloky, chybná značka,
  výběr a jeho zrušení), `RunDetail.test.ts` (růst doby s falešnými časovači bez `fetch`,
  dokončený běh netiká), `events.test.ts` a `format.test.ts`.
- `just test`, `just typecheck`, `just lint`, `just e2e`.
- Ručně: otevřít běžící běh. Bloky a doba se prodlužují každou sekundu. Klik na blok otevře
  panel fáze, druhý klik ho zavře.
