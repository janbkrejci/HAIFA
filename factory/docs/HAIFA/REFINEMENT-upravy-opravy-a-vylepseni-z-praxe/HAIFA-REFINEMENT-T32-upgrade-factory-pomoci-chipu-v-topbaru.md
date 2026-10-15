# HAIFA-REFINEMENT-T32: Upgrade factory pomocí chipu v topbaru

## Lze aktualizovat, když běží tasky?

Ne, blokace zůstává. Každý běh tasku je samostatný proces `python -m aifactory` (`RunLauncher`, řetěz auto-continue) ze stejného uv tool prostředí, které aktualizace přes `uv tool install --force` nahrazuje:

- Na Windows má běžící proces zamčené soubory prostředí. uv prostředí nejdřív maže a pak selže, takže instalace zůstane rozbitá. Předávací skript (`upgrade_handoff.ps1`) čeká jen na proces dashboardu, ne na běhy.
- Na macOS/Linuxu by instalace prošla, ale běžící task dál načítá moduly líně (desítky importů uvnitř funkcí v `run/`, `workflow/`, `engine/`, `harness/`, `review/`) a dostal by kód nové verze do procesu staré verze; běh by mohl spadnout uprostřed.

## Co se změnilo

- Odmítnutí (`runs_active`, HTTP 409) má nový text: „Aktualizace počká, běží N tasků. Instalace nahrazuje soubory HAIFA, které běžící tasky používají, a mohla by je shodit. Až tasky doběhnou, klikni na chip znovu.“ (se správným skloňováním počtu).
- Chip po takovém odmítnutí už neukazuje „Nepodařilo se zkontrolovat aktualizace“, ale nový stav **Aktualizace čeká na tasky** (oranžový) s textem odmítnutí v tooltipu. Kliknutí zkusí instalaci znovu; pravidelná kontrola stav vrátí na „Je k dispozici aktualizace“.
- Příručka (kapitola Aktualizace) popisuje nový stav a důvod.

## Ověření

`just pytest tests/web/test_web_updates.py`, `just web-test` (`src/lib/updates.test.ts`).
