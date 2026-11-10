---
id: HAIFA-REFINEMENT-T109
title: "Zrychlit kanban a kontrolu počítače: odstranit opakovaná Git čtení"
status: done
archived: true
depends_on: []
related: [HAIFA-REFINEMENT-T108]
writes: [aifactory/]
---

## Zadání
Diagnostika 2026-11-10 na Windows, base cc83959072168784b40e1acd69aaa2591fbc25fd, 321 tasků. Opravit doložené příčiny pomalého kanbanu a readiness kontroly počítače. Navazuje tematicky na T108 (průběh/timeout/invalidace), ale tento task řeší výkon; neduplikovat jeho UI a timeoutový rozsah.

Naměřeno přímým voláním web.backlog.backlog_view(Path.cwd()) přes uv run --project aifactory python a cProfile: 68,456 s, 674 volání _merge_policy, z toho 67,864 s v _merge_policy a 67,590 s v repository_identity. _task_json se volá 642x (strom + plochý seznam), dalších 32 čtení pochází z kontejnerů. Každé vytvoření RepositorySettings spouští git rev-parse --path-format=absolute --git-common-dir. Celkem 675 subprocess.run. Diagnostický experiment pouze v paměti procesu: načíst _merge_policy jednou a patch.object(web.backlog, '_merge_policy', return_value=policy) pro jedno backlog_view; 0,402 s a stejných 321 tasků, 674 nahrazených čtení. Nejde o hotovou implementaci ani garantovaný čas na každém stroji.

web/src/lib/readiness.ts::check po machine/library/registry načítá celý /repos/{id}/backlog jen pro backlog.items.length. Kontrola v chipu tak čeká také na tentýž drahý kanban; při otevření kanbanu mohou vzniknout dva samostatné požadavky na plný backlog. SetupView a readiness chip rozlišovat.

Samostatné web.machine.check_view(haifa_home(), GlobalState(), offline=False, fresh=True, machine=None): 9,165 s; následné fresh=False se stejným GlobalState: 1,288 s a 12 subprocess.run. I cache hit v check_view znovu vytváří CheckContext pro registrovaná repa a načítá roster/base konfiguraci. Čerstvá kontrola navíc provádí CLI probes; tyto časy nejsou důkaz deadlocku. Cache_lock je během run_check držený, souběh/timeouty řeší související T108.

Hotovo znamená:
- Kanban používá jeden čerstvě validovaný snapshot merge policy/identity pro jeden read request, sdílený stromem, plochým seznamem, kontejnery, stavy a součty. Počet Git zjištění identity kvůli policy neroste s počtem tasků/kontejnerů, včetně mnoha otevřených PR. Zachovat shodný obsah API, filtrování, pořadí a význam stavů.
- Nezavádět globální trvalou cache RepositorySettings ani oslabit bezpečnostní kontrakt repo_settings.py. Nový request musí vidět změnu souboru, chybějící soubor znamená vypnuté automatiky; poškozený/nepodporovaný soubor vrací chybu místo staré zapnuté hodnoty. Rozhodnutí pro spuštění/merge dál čtou a validují aktuální stav podle existujícího kontraktu. Detail tasku, graf a advice save nesmějí získat zastaralou policy.
- Readiness pro existenci/počet projektů použije lehké čtení nebo vhodný existující souhrn; nemusí sestavovat celý kanban. Zachovat onboarding pro prázdné repo, archivované projekty a chybové stavy. Ověřit, že kontrola nevydává druhý plný backlog request.
- Zmenšit náklady opakovaného machine cache hitu na načtení rosterů; vycházet z měření a zachovat reakci na změnu registru, base/config i knihovny a nastavení harnessů. Případná cache musí mít ověřenou invalidaci, nepoužít jen neomezeně staré počty. Pokud se tato část překrývá s implementací T108, sjednotit řešení.
- Přidat deterministické regresní testy počtu Git/policy čtení na větším syntetickém backlogu, konzistence strom/seznam/stavy, změny settings mezi requesty, implicitních výchozích hodnot a neplatného settings souboru po předchozím úspěchu. Testy bez živých modelů a služeb; výkon netestovat křehkým wall-clock limitem v CI. Doložit srovnatelné lokální měření před/po pro kanban i fresh/cached machine check.

Testovací plán: před implementací vyhledat přímé volající změněných funkcí v celém aifactory/tests/. Již nalezeni web/test_web_backlog.py (strom, filtry, auto_merge, detail, handoff), web/test_web_backlog_graph.py, web/test_web_backlog_queue.py, web/test_web_overview.py, web/test_web_monitoring.py, web/test_web_cleanup.py, run/test_unchanged.py a web/test_web_workflow_advice.py (test_add_and_edit_save přímo patchuje _merge_policy). Vybrat pouze testy skutečně dotčeného chování; při změně machine čtení zahrnout web/test_web_machine.py zejména test_machine_cache_and_offline a test_harness_repo_counts_follow_registry_with_cached_probes, případně dotčené check testy. Při změně repo_settings vyhledat také jeho přímé volající a ochranné testy. Vždy just lint a just typecheck. Pro frontend just web-test a just web-build; cílený browser test jen změněné obrazovky, pokud se mění její chování/layout. Každý editovaný testový soubor spustit celý alespoň jednou. Ve factory běhu nespouštět celou sadu. Writes aifactory/ zahrnuje backend, frontend, testy a shipped static; případné další cesty přidat do vlastního writes před během.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-10 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/213 · náklady $0.00
