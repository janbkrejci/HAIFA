# HAIFA-S01-T21: Instalace, aktualizace a commit konfigurace

Dashboard nyní provádí instalaci factory, aktualizaci z knihovny, commit konfigurace a dorovnání base přes serverový plán a vlastní potvrzovací dialog. Uživatel před zápisem vidí všechny měněné soubory, včetně manifestu, jejich celý obsah nebo diff, varování, blokátory a skutečnou base, SHA a remote.

## Použití

Na **Přidat repozitář** vyber složku, použij **Zkontrolovat** a u repa bez factory **Pokračovat instalací**. Průvodce repo dočasně zaregistruje. **Zrušit** odstraní pouze registraci vytvořenou tímto průvodcem a do repa nic nezapíše. Interní navigace také čeká na odstranění; při chybě lze odstranění zopakovat.

Instalační formulář přebírá zjištěnou base, provider, adresáře a výchozí položky knihovny: planner, builder, reviewer, documenter a workflow `simple-sdlc`. Azure má pole organizace, projektu a repozitáře. Každý agent má vlastní harness, model a thinking; chybějící CLI vyvolá varování. Každá změna přepočítá plán a zruší staré potvrzení. Workflow může doplnit potřebné agenty při zachování vlastních vazeb.

Na záložce **Factory** otevře **Aktualizovat z knihovny** skupiny aktualizovaných souborů, ponechaných místních změn a změn v obou verzích. Konflikt ukazuje dva diffy a volbu **Převzít**; **Sloučit** se nabídne při serverem ověřeném validním sloučení. Migrace se provedou po zaškrtnutí. Bez manifestu aktualizaci blokuje `not_onboarded`.

**Commitnout konfiguraci** na Factory i v banneru otevře náhled. **Provést** následně vyžaduje samostatný modál s počtem souborů a cílem. Klient posílá povolené volby, cíl, zprávu a digest; obsah ani seznam zapisovaných souborů neposílá. `plan_changed` načte nový plán a vyžaduje nové ruční potvrzení.

Při aktivních bězích se zobrazí „V repu běží N běhů, počká se, až doběhnou“ a odkazy na běhy. Provádění je zakázané i při neověřeném stavu běhů. Stav se obnovuje přes SSE a při návratu do okna.

Odmítnutý push ukáže důvod a „V repozitáři se nic nezměnilo“. **Otevřít jako PR** zachová volby a při nezměněném plánu digest, ale vyžaduje nový náhled a potvrzení. Úspěch ukáže commit nebo PR, obnoví kontroly a nabídne **Otevřít backlog**. Po PR běhy počkají na merge; následně použij **Dorovnat base**. Tato akce je dostupná také při zpoždění za remote a ukazuje vlastní plán s SHA před a po. Divergence, necommitnuté změny a aktivní běhy ji blokují.

## Kde změna žije

- `aifactory/web/src/components/factory/FactoryOperation.vue`, `FactoryPlanView.vue`, `InstallForm.vue` a `UpdateChoices.vue` řídí formulář, náhled, potvrzení a výsledek. `aifactory/web/src/lib/api.ts` definuje typované požadavky a whitelist; `aifactory/web/src/lib/factory.ts` drží instalační volby a vlastnictví dočasné registrace.
- `aifactory/web/src/views/FactoryView.vue`, `ReposAddView.vue`, `aifactory/web/src/App.vue`, `aifactory/web/src/components/RepoScreen.vue`, `repos/InspectCard.vue` a `ConfigStatusBanner.vue` propojují operace s navigací a obnovou stavu. `components/review/DiffContent.vue` sdílí renderer s `DiffView.vue`.
- `aifactory/src/aifactory/web/app.py`, `web/factory.py`, `config/commit.py` a `providers/publish.py` přidávají GET `config/pull/plan` a povinný digest pro dashboardový POST `config/pull`; před posunem base ověřují aktuální plán. `aifactory/src/aifactory/library/update.py` poskytuje `merge_available`.
- `aifactory/src/aifactory/web/static/index.html` odkazuje na obnovené JS/CSS assets. `aifactory/tests/e2e/test_factory_install_browser.py` ověřuje Cancel bez zápisu a jeden instalační commit v repu i lokálním bare remote s builderem na jiném harnessu.

Doprovodné opravy v `aifactory/src/aifactory/onboard/onboard.py` porovnávají zdroje přes Git clean filtry bez změny indexu. `aifactory/src/aifactory/engine/quality.py` při timeoutu ukončí i potomky a zachová částečný výstup. `justfile` doplňuje diagnostiku prvního selhání scoped kontrol. Testové opravy upravují očekávání workflow, izolují kontrolu portu, zachovávají Git revision argumenty na Windows a čekají na skutečné vykreslení grafu.

## Ověření

Konečný předaný protokol `C:/Users/jan.krejci/Documents/HAIFA/.factory/data/sessions/d4f262d7/context_handoff/quality/11_retest/command.log` dokládá `just check e2e`, **exit 0**, délku 2582,922 s:

- Frontend: 76 souborů, 863 testů a typecheck prošly.
- Backend: 2190 testů prošlo, 30 přeskočeno; mypy bez chyb v 366 souborech.
- Ruff a formátování prošly; 380 souborů již správně formátovaných.
- Všech 7 sériových browser testů prošlo, včetně instalačního scénáře nad statickým buildem.

Tento úplný běh dokládá požadované testy, typecheck, lint i e2e a uzavírá původní validační mezeru. Dokumentační fáze testy neopakovala. Log obsahuje neblokující Vue prop warnings a Pydantic deprecation warnings.
