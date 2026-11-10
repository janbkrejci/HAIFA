# T112: Posun dlouhého Ganttu uvnitř detailu běhu

`buildTimeline(detail, now, trackPx)` v `aifactory/web/src/lib/waterfall.ts` počítá
rozložení v pixelech pro viditelnou šířku stopy (`trackPx`, bez sloupce popisků) a vrací
geometrii v procentech plátna. Bloky se kladou sekvenčně podle začátku: každý dostane
nejméně `MIN_BLOCK_PX` (132 px) a od předchozího bloku nejméně `BLOCK_GAP_PX` (6 px).
Fáze bez `started_at` následují za časovanými bloky v pořadí `seq`, každá
`QUEUED_BLOCK_PX` (170 px) široká. Žádné dva bloky tak nesdílejí vodorovný rozsah,
ani v rámci jedné swimlane.

Pokud se rozložení vejde do viditelné stopy, časové měřítko se stlačí tak, aby plátno
mělo šířku stopy (`overflow: false`). Pokud nestačí ani samotné minimální šířky a mezery,
plátno se rozšíří (`width`, `overflow: true`) a minimum zůstane zachováno. Zóna požadavku
inženýra má 16 % viditelné stopy. Osa mapuje čas přes hrany bloků, takže popisky odpovídají
posunutým blokům. Popisky bližší než `MIN_TICK_GAP_PX` se vynechají.

`RunWaterfall.vue` měří stopu pomocí `ResizeObserver` a osu i všechny swimlanes vykresluje
v jediné oblasti `[data-test="waterfall-scroll"]` s `overflow-x: auto`. Popisky swimlanes
jsou ukotvené vlevo (`position: sticky`). `RunDetail.vue` drží detail v šířce sloupce
(`min-width: 0`). Hlavička ani panel fáze tak nepřetékají.
