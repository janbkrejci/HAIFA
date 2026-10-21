---
id: HAIFA-S05-T18
title: "Knihovna: položky všech připojených repo a ignore list pro repo"
status: done
depends_on: []
writes: [aifactory/, justfile, docs/]
---

## Zadání
Na stránce Knihovna zobrazit vedle sdílené knihovny také agenty, skilly a workflows ze všech připojených (registrovaných) repozitářů, včetně položek existujících pouze v repu. Jednotkou původu a nastavení je repo, nikoliv backlogový projekt; několik projektů ve stejném repu nesmí položky násobit.

Ověřený příklad: NEO_HEF má na develop .factory/workflows/haifa-implement-task.yaml, ale ve sdílené knihovně workflow není, a proto se na webu vůbec neukáže. LibrarySection.vue sestavuje seznam pouze z library.items; web/library.py v overrides přeskočí položky s lib is None. RepoItems.vue přitom odkazuje správu workflow a skillů právě na Knihovnu.

Požadované chování a akceptace:
1. Knihovna zahrne položky všech připojených repo i bez protějšku ve sdílené knihovně. U položky ukáže typ, název, zdrojové repo a cestu, dostupný detail a jasně rozliší sdílenou položku od položky pouze v repu. Stejné názvy v různých repech nesmí způsobit ztrátu obsahu či záměnu cíle operace. Zachovat přehled existujících overrides.
2. Ověřit inventarizaci nativních agentů a skillů v podporovaných repo adresářích harnessů, nejen .factory; respektovat kanonické zdroje a zrcadla .claude/skills a .agents/skills neduplikovat. Popsat podporované umístění a pravidla. BMAD je konkrétní případ desítek agentů a skillů v repu.
3. Zavést trvalý ignore list v rámci každého repo, spravovatelný z webu. Uživatel může skrýt jednotlivé položky i hromadně sadu/prefix/adresář (například BMAD), aniž by musel odkliknout desítky položek. Přesně definovat identitu/pravidla a jejich rozsah; ignorování v jednom repu nesmí skrýt stejný název v jiném repu či sdílené knihovně. Zvolit úložiště podle současné architektury a popsat persistenci.
4. Ignorované položky standardně nepřekážejí v přehledu; nabídnout zobrazení a správu ignorovaných, zrušení ignorování a obnovení položek. Nastavení přežije refresh i restart. Hromadná pravidla pokryjí i nově přidané odpovídající položky.
5. Ignore ovlivňuje pouze tento přehled a nabídku položek ke sdílení: nemaže soubory, nevypíná agenty/skilly při běhu a nemění resolver workflow. Pouhé objevení položky ji automaticky neimportuje ani nepřesouvá do sdílené knihovny. Existující explicitní operace importu/přesunu zachovat, umožnit je i pro vhodné položky pouze v repu.
6. Nedostupné/chybné repo zobrazit jako dílčí chybu, ostatní položky zůstanou dostupné. Zachovat filtrování podle typu a přidat použitelné rozlišení/filtrování podle repo a zdroje pro větší inventář.
7. Doplnit backend a frontend testy: položka pouze v repu (regrese haifa-implement-task), více repo a shodná jména, více projektů v jednom repu, nativní skilly/agenti a zrcadla, hromadné BMAD ignorování, persistence, obnovení a izolace pravidel, neovlivněné načítání při běhu, dílčí chyba repo. Ověřit cíleným browser testem přehled a skrytí/obnovení. Aktualizovat relevantní dokumentaci a distribuovaný frontend dle pravidel repa.

Výchozí místa: aifactory/web/src/components/setup/LibrarySection.vue, components/factory/RepoItems.vue, lib/library.ts, aifactory/src/aifactory/web/library.py a existující inventář položek repa. Implementovat jako jeden souvislý task s odpovídajícími API, persistencí, UI a testy.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-21 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/145 · náklady $0.00
