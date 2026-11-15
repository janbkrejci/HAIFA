# GIRO — CLI, konfigurace a data

GIRO 1.0 zachovává distribuci a Python namespace aifactory, `.factory/`, task ID,
registry ID i absolutní cesty checkoutů. Entry pointy giro a factory volají stejný
main; help a verze identifikují GIRO. ZIP používá giro-<verze> a stejný wheel.
Uchovaný přechodový zdroj T04 a oddělení release zdrojů popisuje
[release kontrakt](../../../../docs/rebranding/release.md).

Resolver v environment.py vybírá neprázdný GIRO klíč před legacy klíčem ve stejné
vrstvě, shell před env souborem. Konflikty vypisuje na stderr bez hodnot.
Podprocesy sjednocují oba aliasy, včetně home, run ID a guide scope. Env soubor
nesmí přesměrovat home. Legacy update zdroj janbkrejci/HAIFA se v GIRO ignoruje;
explicitní GIRO override i vlastní firemní legacy zdroj fungují.

Default je XDG_CONFIG_HOME/giro nebo ~/.config/giro i na Windows. Explicitní home
se nestěhuje. Legacy-only start vyžaduje potvrzený přechod; dva odlišné defaulty
bez dokončeného manifestu blokují start. Offline `giro migrate --confirm
--haifa-bundle PATH` používá stejný zálohovací a manifestový protokol jako T04.
Zdroj, knihovní Git a dirty soubory, runtime, SQLite data i externí mutable cesty
zůstávají obnovitelné. Pád mezi zápisy manifestu blokuje další zápisy do obnovy.
Návod k návratu je v release kontraktu a v instalačních instrukcích bundlu.

Diagnosticky byl spuštěn pouze tests/test_giro_migration.py -n0: 32 passed,
1 failed (oprávnění explicitního stejného home). Implementace následně sjednotila
oprávnění targetu i v této větvi. Testovací krok ověří opravu a doplněné případy.
Build, lint, typecheck a platformní instalace patří samostatnému testerovi.
Lock neobsahuje verzi editable rootu ani změněné závislosti, proto se nemění.

Po prvním testovacím kroku byly opraveny typy migračního manifestu a obnovy
prostředí, importy, katalog přechodových chyb a historické HAIFA fixture.
Testovací home nyní izoluje obě sady produktových proměnných od factory runneru;
simulace cizího procesu odstraňuje obě run ID. Přepnutí knihovního testovacího
home nastavuje obě jména. Validace bundlů i rollback mají explicitně zdrojový home,
aby nikdy nehledaly knihovnu v provozním defaultu vývojáře.
Jediný diagnostický test této opravy, parametr `True-restart-None` v
`test_worker_installs_with_existing_updater_validates_and_rolls_back`, prošel.
Úplné opakování kontrol zůstává součástí samostatného testovacího kroku.

Po review je automatický výběr mezi odlišnými defaulty svázán s kanonickou
identitou právě legacy zdroje a GIRO cíle. Manifest explicitní migrace jiného
home, včetně migrace GIRO home do sebe, nesmí skrýt nesouvisející legacy data.
Před přijetím markeru se kontroluje schéma, verze, cesty obnovy, uchovaný software,
kontrolní součty jako záznamy, úplný seznam uchovaných dat a shoda cílového markeru
s plánem a zdrojovým ukazatelem. T04 navíc vyžaduje záznamy uchovaného toolu.
Prepared ukazatel zdroje může předcházet doplnění datových záznamů pracovníkem;
autorizovaný prepared cíl už musí mít kompletní zálohu. Committed kopie musejí
být úplné a shodné. Tyto kontroly nepřepočítávají obsahové hashe při každém startu;
kontrola obsahu zálohy zůstává součástí kopírování a obnovy.
Regrese pokrývají chybějící pole, chybné typy, chybějící zálohy, neúplné záznamy
a cizí zdroj bez změny dat při odmítnutí. Diagnostický test autorizovaného prepared
restartu a committed zápisu prošel; scoped ověření provede testovací krok.
