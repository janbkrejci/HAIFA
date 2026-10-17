# START-S01-T02: Vyzkoušet na ukázce z prázdného Přehledu

## Co se změnilo

- **Vyzkoušet na ukázce** je na prázdném Přehledu (žádné repo) vedle **Přidat repozitář** a na stránce Problémy a řešení u kroku **Repozitář**, tedy na konci kroků nastavení.
- Tlačítko zavolá `POST /api/demo` (to samé co `factory try` bez složky: ukázka v `$HAIFA_HOME/demo`, provider `local`, registrace v dashboardu). Pak vybere první otestovaný harness počítače (výchozí harness, pak claude, codex, pi; jeho model s úspěšným testem v `harness-tests.json`), spustí `DEMO-S01-T01` s tímto harnessem a modelem a otevře backlog ukázky na tom tasku. Když žádný harness test neprošel, běh dostane roster repa. Když se běh nespustí, ukázka zůstane a lišta ukázky řekne proč.
- `GET /api/repos` má u každého repa `demo` (true pro ukázku ve výchozí složce). Repo screen ukázky má nad obsahem lištu: co ukázka je, odkaz na spuštěný běh, **Přidat vlastní repozitář** a **Odebrat ukázku**.
- Detail běhu ukázky má panel „Co se právě děje“ s kroky worktree, build, test, review, PR a merge. Hotové kroky jsou zelené, aktuální má krátké vysvětlení. Když běh skončil a PR čeká, panel odkáže na Review. Po merge nabídne **Přidat vlastní repozitář** a **Odebrat ukázku**.
- **Odebrat ukázku** se zeptá v dialogu dashboardu a zavolá `DELETE /api/demo`: odebere záznam z registru a smaže celou výchozí složku ukázky (read-only soubory gitu taky). Dokud běh ukázky žije, vrátí `run_in_progress` a nic nezmění. Jinou složku, než je výchozí, nikdy nemaže.

## Jak ověřit

- `cd aifactory && uv run pytest tests/demo/test_demo_web.py tests/demo/test_demo_try.py -n0`
- `cd aifactory/web && bunx vitest run src/lib/demo.test.ts src/components/demo/Demo.test.ts`
- `cd aifactory && uv run pytest tests/e2e/test_demo_browser.py -n0`: od prázdného Přehledu přes běh s fake harnessem a schválení PR po odebrání ukázky.
