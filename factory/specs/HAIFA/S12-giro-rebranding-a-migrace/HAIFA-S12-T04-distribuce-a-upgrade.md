# HAIFA-S12-T04 — poslední HAIFA

Implementace zachovává HAIFA značku i bundle. Globální lokalizovaný alert volá
migrační variantu existujícího Updates/upgraderu, s pevnou identitou GIRO repo,
ZIP kořene a zachovaného aifactory wheelu podle T01. Žádné kliknutí neotevírá
externí návod a samotné načtení dashboardu nespouští instalaci.

Přechod má společné run/duplicate guards, procesní leases a prepared/committed
marker. Privátní supervisor nad zachovaným tool prostředím po odchodu dashboardu
vytvoří ověřenou offline zálohu, zavolá existující run_upgrade bez seed --all,
restartuje na stejném origin a ověří health/verzi/home/registry. Při selhání obnoví
HAIFA i data. Neúplná migrace zůstává blokována markerem pro kontrolovanou obnovu.

Závazný publikační a obnovovací postup, zdroj/cíl a způsob identifikace posledního
HAIFA zdroje popisuje [release.md](../../../../docs/rebranding/release.md).
Workflow povoluje jen schválený uchovaný SHA/tag a jednorázovou publikaci po GIRO.
T02 navazuje default-home resolverem a GIRO brandingem/health identitou;
T03 aktualizuje GIRO UI. T06 provádí skutečné tagování a vydání až po ověření G.

Regrese pokrývají fake hosting rozlišující oba repozitáře, explicitní GIRO asset,
checksums, wheel, verze, minulé distribuční chování, ochrany tasků/duplicit,
selhání přípravy/instalace/restartu, návrat a opakování v izolovaných adresářích.
Samostatný test krok provede povinné lint/typecheck, frontend sadu, web-build,
cílený browser scénář a vybrané backendové soubory; finální statiky musí být
součástí uchovaného ověřeného zdroje.
