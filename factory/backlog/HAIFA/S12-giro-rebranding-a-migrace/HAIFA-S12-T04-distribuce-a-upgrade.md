---
id: HAIFA-S12-T04
title: Poslední HAIFA — alert a upgrade na GIRO z nového repo
status: todo
depends_on: [HAIFA-S12-T01]
writes: [aifactory/, giro/, .github/workflows/, justfile, README.md, docs/rebranding/, docs/decisions.md]
---

## Zadání

Připrav poslední vydání HAIFA z původního repo. Zachovej jeho HAIFA značku
a dosavadní distribuční formát, aby ho získaly stávající instalace. Jediná
migrační cesta bude akce v dashboardu, která provede upgrade z nového GIRO repo.
Využij existující update/upgrade a restart mechanismus; nevytvářej druhý updater.
Relevantní místa: Vue App a update UI, backend web updates/server, `upgrade.py`,
`bundle/` a `.github/workflows/ci.yml`.

Hotovo znamená:
- Dashboard zobrazuje alert „HAIFA se přejmenovává na GIRO“ a akci
  „Klikněte zde pro přechod“. Je dostupný napříč obrazovkami bez dalšího hledání
  v nastavení. Kliknutí zahájí upgrade, neotevírá jen stránku GitHubu nebo návod.
- Backend získá stabilní vydání z pevně určeného nového GIRO repo dle T01,
  vybere správný bundle, ověří kontrolní součty a provede existující upgrade
  a předání/restart dashboardu. Přejmenovaný wheel/asset podporuje výslovně;
  aktuální detekce `aifactory` a `haifa-<verze>.zip` se nesmí použít slepě.
- Zachová nastavení, knihovnu, repozitáře a historii. GIRO po restartu používá
  nové repo i pro další aktualizace. Číslování vydání nesmí zablokovat přechod
  ani umožnit nechtěný downgrade; pravidlo urči podle kontraktu T01.
- UI ukáže průběh, během upgradu zabrání duplicitnímu spuštění a po úspěchu
  přejde na GIRO bez původního alertu. Kliknutí za aktivního tasku nebo upgradu
  respektuje existující ochrany a vysvětlí, proč je potřeba počkat.
- Nedostupný release/síť, chybný hash nebo selhání instalace zanechá funkční
  HAIFA a data; alert nabídne opakování s konkrétní chybou. Upgrade se
  nespouští samotným načtením dashboardu.
- Původní update cesta stále doručí poslední HAIFA jako HAIFA bundle. Zachovej
  sestavitelný zdroj této verze před T02/T03 a zapiš způsob jeho identifikace
  pro T06. Omez release workflow tak, aby další rebranding commity nevydávaly
  z HAIFA repo nové releasy. Poslední HAIFA se publikuje až po dostupném GIRO.
- V `docs/rebranding/release.md` popiš tuto jedinou cestu, zdroj/cíl vydání,
  migrační akci a návrat při selhání; bez dalších kompatibilních assetových variant.

Ověření: společné kontroly stepu, `just web-test`, `just web-build`, cílený browser
test alertu a backendové testy upgradu. Fake hosting musí odlišit staré a nové
repo a ověřit, že kliknutí stáhne GIRO z nového. Pokryj blokované a duplicitní
kliknutí, nedostupný release, hash, chybu instalace, opakování a restart.
Použij izolované home/tool adresáře a falešné nástroje; nic nepublikuj.

## Běhy
<!-- doplňuje factory při schválení PR -->
