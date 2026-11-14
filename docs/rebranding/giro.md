# GIRO — kontrakt názvů a přechodu

Stav: implementační kontrakt T01, nikoli provedená migrace. Inventura 2026-11-14
nad commitem `17efaf164bb8c9d4fd7fecbae62f9612ddf0d301`. T02–T07 níže znamenají
`HAIFA-S12-T02` až `HAIFA-S12-T07` v
[backlogu stepu](../../factory/backlog/HAIFA/S12-giro-rebranding-a-migrace/index.md).
Tento dokument mění pouze dokumentaci; současný produkt stále používá HAIFA.

## 1. Závazná identita a kompatibilita

- Značka **GIRO**, slovní značka `giro`, přesný slogan **Goal in. Release out.**
  Aktivní texty odstraní spojení Helios AI Factory a zaměstnavatele. Slogan vyjadřuje
  zamýšlený cyklus práce, nikoli záruku automatického vydání každého projektu.
- Primární příkaz `giro`; `factory` je druhý entry point téže `aifactory.cli:main`,
  se stejnými operacemi, návratovými kódy, JSON envelope a jedním datovým domovem.
  Help/verze obou uvádějí GIRO. Deprekace patří na stderr, nikdy do JSON stdout;
  alias nesmí v podprocesech spustit jinou instalaci z PATH.
- **Distribuční jméno zůstává `aifactory`**, stejně jako Python namespace
  `aifactory`, zdroj `aifactory/src/aifactory/`, projektový adresář `aifactory/`,
  wheel `aifactory-<verze>-py3-none-any.whl` a `uv tool uninstall aifactory`.
  Neutrální technický název nevyžaduje přestavbu importů ani přechod mezi dvěma
  instalacemi. PyPI jméno `giro` je navíc obsazené (oddíl 6). Žádný shim balíček
  `giro` ani publikace na PyPI nejsou součástí přechodu.
- Veřejný ZIP a jeho kořen budou **`giro-<verze>.zip` / `giro-<verze>/`**.
  Obsah nadále zahrnuje wheel, constraints, stejné instalační/odinstalační skripty
  pro POSIX i Windows, INSTALL.md, THIRD_PARTY_NOTICES a SHA256SUMS.
  Poslední HAIFA má výhradně starý `haifa-<verze>.zip`; GIRO výhradně nový ZIP.
- **`.factory/` a `factory/` se nemění**: konfigurace, worktrees, běhy, backlog,
  specy, task docs, větve `factory-*`, routy `/factory` a JSON klíče jsou technický
  formát. Není důvod zavádět `.giro/`, přepisovat task ID či registrovat repa znovu.
- `factory`, dokumentované aliasy `HAIFA_*`, čtení legacy home a posledního HAIFA
  bundlu podporovat po celou GIRO řadu 1.x **a nejméně 12 měsíců od prvního
  stabilního GIRO vydání**. Odstranění nejdříve v major 2, po splnění obou podmínek,
  samostatném rozhodnutí a zveřejnění upozornění alespoň 90 dní předem.
  T06 zapíše datum prvního vydání a nejdřívější datum odstranění do cutover záznamu.
  Technické výjimky `aifactory`, `.factory/`, `factory/` nemají datum odstranění.
  Historické balíčky/releasy a původní repo se nemažou ani po skončení aliasů.

Podporovaná cesta je **stará HAIFA → poslední HAIFA s alertem → kliknutí → GIRO
z nového repo**. Nepřidávat GIRO assety pro všechny historické updatery.
Přechod nesmí vyžadovat klonování ani změnu remote uživatelova projektu.

## 2. Inventura a mapování podle vlastníka

Cesty jsou relativní ke kořeni repa; seznamy adresářů zahrnují spotřebitele uvnitř.
Každý řádek odkazuje na akceptaci Axx v oddílu 8. Výjimky jsou vědomé zachování
formátu, nikoli pokyn k plošnému přejmenování.

| Skupina a současné cesty/výskyty | Cíl / zdůvodněná výjimka | Vlastník; akceptace |
| --- | --- | --- |
| `README.md`, `aifactory/README.md`, `AGENTS.md`, `CLAUDE.md`; HAIFA / Helios AI Factory | Aktivní popis GIRO a slogan; historické záznamy a původní autorství ponechat | T03; A01 |
| `aifactory/pyproject.toml`, `uv.lock` uvnitř `aifactory/`, `src/aifactory/__init__.py` uvnitř projektu | Distribuce, namespace a cesty `aifactory` beze změny; description/docstring GIRO, verze dle oddílu 7; lock jen pokud to metadata vyžadují | T02; A02 |
| `aifactory/src/aifactory/cli.py`, volání v `run/`, `workflow/`, `web/`, `harness/`, `library/`, `demo/`, `testing/`, `validation/` a `justfile` | `giro` primární a bezpečně lokalizovaný příkaz; `factory` stejný alias; technické názvy funkcí a importů zachovat | T02; A02, A03 |
| `aifactory/src/aifactory/home.py`, `config/loader.py`, `harness/settings.py`, `engine/slots.py` | Výchozí `~/.config/giro` nebo `$XDG_CONFIG_HOME/giro`; explicitní home podle oddílů 3–4 | T02; A04–A07 |
| `web/registry.py`, `repo_settings.py`, `web/assistant.py`, `web/backlog.py`, `learn/`, `library/history.py` pod `aifactory/src/aifactory/` | Zachovat dashboard.yaml, repositories/*.json a jejich identitu, harnesses.json, env, database.yaml, library, logs, cache, assistant, follow-ups i soubory locků uvnitř zvoleného home; kopírovat konzistentně bez aktivních procesů | T02; A05–A08 |
| `aifactory/src/aifactory/config/settings.py`, `run/store.py`, `engine/tracer.py`, `run/`, `database/` | `.factory/trace.db`, `.factory/data/`, `.factory/worktrees`, sessions a libovolné nakonfigurované cesty zůstávají; DB tabulky `haifa_owners`, `haifa_backlog*` se nepřejmenovávají: zabránit rozdělení historie | T02; A08 |
| `run/basemoves.py`, `run/mainwrites.py`, `web/workflow_advice.py`, `justfile` | `<git-common-dir>/haifa/` (journal, ochrany zápisů, locky, mypy cache) ponechat: sdílený protokol a ochrany běhů; pouhé přejmenování by je rozdělilo | T02; A08 |
| `aifactory/src/aifactory/upgrade.py`, `upgrade_handoff.ps1`, `web/updates.py`, `web/server.py`, `web/app.py` | ZIP detekce GIRO a přechodová HAIFA dle oddílu 7; nový restart `giro obs`, interní restart env alias dle oddílu 3; nové logy/dočasné prefixy `giro-*`, staré nesmazat | T04 připraví HAIFA; T02 GIRO; A09–A12 |
| `aifactory/bundle/{build.py,release.py,install.sh,install.ps1,install.bat,uninstall.sh,uninstall.ps1,uninstall.bat}`, `justfile` | GIRO ZIP, wheel stále aifactory; kontrola kolize `giro` na PATH, shodná precedence env a bezpečný uninstall; T04 zachová starý bundle | T04 → T02; A03, A09–A12 |
| `aifactory/src/aifactory/web/updates.py`, `aifactory/bundle/release.py`, instalační kapitola guide, `README.md`, `.github/workflows/ci.yml` | `janbkrejci/HAIFA` → navržené `janbkrejci/GIRO` pro budoucí vydání; staré URL patří historii a HAIFA updateru; neaktivovat fiktivní instalační URL před T06 | T04, T02, T03, T05, T06; A10, A13 |
| `aifactory/src/aifactory/library/{share.py,store.py,remote.py,reseed.py}`, instalátory, guide | Default URL **zůstává** `https://github.com/janbkrejci/HAIFA-LIBRARY.git`; library.yaml, `min_factory_version`, seed type/name, `haifa-library/` větve a `.git/haifa-pull-requests.json` zachovat kvůli návrhům a historii | T02, T03, T05; A07, A14 |
| `aifactory/web/index.html`, `src/App.vue`, `src/lib/library.ts`, CSS/ikony v `aifactory/web/`, `aifactory/web/package.json`, `bun.lock` | Titulek, wordmark a aktivní diagnostika GIRO; privátní frontend package `giro-dashboard`. Respektovat převzatý vzhled a licence, bez redesignu | T03; A01, A15 |
| `aifactory/src/aifactory/web/server.py` APP_NAME `haifa-dashboard` | Nová health identita `giro-dashboard`; koordinovat backend, klienta a health/restart testy v obou větvích vydání | T02, T04; A11 |
| `aifactory/web/src/lib/{theme.ts,i18n/index.ts,overview.ts,backlog.ts,review.ts,assistant.ts}`, `aifactory/web/src/components/backlog/FollowUpDialog.vue` | Storage klíče **ponechat** přesně dle seznamu níže: preference, rozepsaná práce a idempotence nesmějí zaniknout | T03; A15 |
| `web/assistant.py`, `web/assistant_codex.py`, `web/assistant_mcp.py`, `web/app.py`, `web/library.py` v Pythonu; frontend `aifactory/web/src/lib/assistant.ts`; `seed/agents/guide/system.md` | `haifa-action` fence, `haifa_guide` MCP/`haifa-guide`, `haifa.repo`, `haifa-library-api-plan-v1` zachovat jako protokol, včetně historických zpráv; aktivní role/texty GIRO. Technický `guide@haifa.invalid` zachovat jako Git identitu historických návrhů | T03; A16 |
| `aifactory/src/aifactory/skill/`, `seed/agents/`, `defaults/`, `demo/`, `aifactory/validation/` | Generovaný `giro --skill`, seedy, návody a nové demo GIRO; `skill/factory` ponechat jako identitu položky knihovny, aby nevznikly dvě kopie. Refresh chrání úpravy dle oddílu 4 | T03, T02; A07, A16 |
| `.claude/skills/factory/`, `.agents/skills/factory/` | V tomto commitu nejsou sledované v Gitu; běhové kopie z knihovny, needitovat jako zdroj. Generovat z produktu a distribuovat přes seed; repo-owned skilly syncnout jen tam, kde skutečně existují | T03, T05; A16 |
| `.gitignore` (HAIFA runtime komentář a pravidla) | Aktivní komentář GIRO, pravidla pro zachované `.factory/`/`aifactory/` se nemění bez důvodu; žádné runtime soubory do Gitu | T02; A08, A17 |
| `.github/workflows/ci.yml`, `aifactory/bundle/release.py`, `aifactory/tests/test_release_workflow.py`, `test_release.py` | Dva oddělené publikační zdroje s explicitním gate; současný stav a požadovaný release režim v oddílu 7 | T04, T02, T05, T06; A12, A13 |
| `.factory/config.yaml`, `factory/backlog/HAIFA/`, `factory/specs/HAIFA/`, `factory/docs/HAIFA/`, historické docs a obrázky `aifactory/web/docs/images/HAIFA-*` | Prefixy tasků, project ID, commit/PR/release odkazy a evidence zůstanou. Aktivní hosting/config inventuru provede T05, případnou změnu T06. Rebrand není přepis historie | T05, T06, T07; A08, A13, A17 |
| `THIRD_PARTY_NOTICES`, `aifactory/THIRD_PARTY_NOTICES`, `LICENSE`, vendor/portovaný engine, komentáře původu `aifactory 2.9`, copyrighty | Zachovat právní a věcnou přesnost, beze slepého nahrazení HAIFA/Helios/aifactory ve zdrojích třetích stran | T03, T07; A01, A17 |
| `aifactory/tests/`, `aifactory/web/src/**/*.test.ts`, validation fixtures | Aktivní očekávání změnit spolu s implementací, legacy fixture ponechat pro kompatibilitu; žádný globální test zakazující slovo HAIFA | T02–T04, T07; A01–A17 |

Frontendové klíče zachované bez přejmenování:
`haifa-theme`, `haifa.dashboard.locale`, `haifa.overview.showFinished`,
`haifa.overview.byProject`, `haifa.backlog.expanded`, `haifa.backlog.project.${repoId}`,
`haifa.backlog.hideDone`, `haifa.backlog.showArchived.done`,
`haifa.backlog.showArchived.cancelled`, `haifa.review.showDone`,
`haifa.assistant.thread`, `haifa.assistant.open`,
`haifa.follow-up.${window.location.hash}.${taskId}`. Platí jen v témže browser origin;
změna hostu/portu nepřenese local/sessionStorage a migrace nesmí takový přenos slibovat.

## 3. Proměnné a precedence

T02 zavede stejné přípony `GIRO_*` a centralizuje resolver i konstrukci prostředí
podprocesů. Nesmí zůstat přímý legacy-only `os.environ.get` v některé cestě.

| Současná proměnná | Nová proměnná; zdroj/spotřebitel |
| --- | --- |
| `HAIFA_HOME` | `GIRO_HOME`; home.py, CLI, web/machine.py, assistant*, library, všechny domovské služby a uninstall |
| `HAIFA_LIBRARY` | `GIRO_LIBRARY`; library/store.py a uninstall; explicitní externí cesta se nestěhuje |
| `HAIFA_LIBRARY_URL` | `GIRO_LIBRARY_URL`; library/share.py, bundle/install.*, guide |
| `HAIFA_UPDATE_REPO` | `GIRO_UPDATE_REPO`; web/updates.py, výjimka přechodu níže |
| `HAIFA_DATABASE_URL` | `GIRO_DATABASE_URL`; database/__init__.py; konfigurace URL jinak drží stávající prioritu |
| `HAIFA_DASH_HOST` | `GIRO_DASH_HOST`; web/server.py a CLI; explicitní --host stále vítězí |
| `HAIFA_FACTORY_REPO` | `GIRO_FACTORY_REPO`; learn/sources.py; hodnota je stále registry ID, ne nové jméno repa |
| `HAIFA_RUN_ID` | `GIRO_RUN_ID`; run/basemoves.py, workflow/{adaptive,propose}.py, run/triage.py, learn/scan.py, web/assistant*; journal atribuce musí být shodná |
| `HAIFA_GUIDE_REPO` | `GIRO_GUIDE_REPO`; web/assistant_gate.py, assistant*, MCP subprocess |
| `HAIFA_OBS_RESTART` | `GIRO_OBS_RESTART`; web/server.py, upgrade a restart subprocess |
| `HAIFA_SANDBOX_REPO`, `HAIFA_AZURE_SANDBOX_REPO` | `GIRO_SANDBOX_REPO`, `GIRO_AZURE_SANDBOX_REPO`; validation/{runner,sandbox}.py, test helpers |
| `HAIFA_VALIDATE_FAKE`, `HAIFA_VALIDATE_HIDDEN` | `GIRO_VALIDATE_FAKE`, `GIRO_VALIDATE_HIDDEN`; validation/{worker,hidden,context}.py; obě podoby odstranit před předáním agentovi jako dnes legacy kanál |
| `HAIFA_E2E_CHANNEL`, `HAIFA_LAUNCH_STUB` | `GIRO_E2E_CHANNEL`, `GIRO_LAUNCH_STUB`; tests/e2e/test_f3_browser.py, tests/web/launch_stub.py a volající; interní test kanály převést spolu s testy |
| `HAIFA_TEST_FROM_FILE`, `HAIFA_TEST_KEPT` | Libovolná testovací jména v tests/test_distribution.py, nejsou produktové API; ponechat jako test čtení obecných env klíčů |
| `HAIFA_ROOT`, `HAIFA_AGENTS` | Python konstanty v validation/ a tests/, nikoli env API; zachovat jako interní výjimku, žádný resolver |

Rozhodování pro každou dvojici (včetně bool/ID/URL) je:

1. Explicitní CLI parametr, pokud jej daná operace podporuje.
2. Neprázdné `GIRO_X` z procesového prostředí, pak neprázdné `HAIFA_X` z téhož prostředí.
3. Neprázdné `GIRO_X` z vybraného `<home>/env`, pak `HAIFA_X` z tohoto souboru.
4. Dosavadní konfigurační/default pravidlo služby; rebranding nemění prioritu
   repo-local database konfigurace ani lokálních provozních voleb.

Prázdný řetězec znamená nenastaveno; syntakticky neplatná neprázdná hodnota znamená
chybu, nikoli fallback na legacy. Konfliktní dvojice vydá warning s názvy proměnných
bez tajných hodnot; nová vyhraje ve stejné vrstvě. Shell legacy tedy vítězí nad
novým klíčem v env souboru. Resolver musí zachovat původ hodnot před flatteningem
`load_env_file`, jinak toto pořadí nejde dodržet.
Home se vybírá pouze z prostředí před načtením env souboru. HOME/GIRO_HOME/HAIFA_HOME
uvnitř env nesmějí přesměrovat již vybraný domov ani vyvolat další načtení.
`XDG_CONFIG_HOME`, `HOME`, systémové Windows home, `UV_TOOL_DIR`, `UV_TOOL_BIN_DIR`,
`CLAUDE_CONFIG_DIR` a bezpečnostní `*_SAFE_MODE` zůstávají beze změny.

Podproces dostane obě jména s **tutéž efektivní hodnotou**, nikoli konflikt zděděný
od rodiče. Zvlášť předat home, run ID a guide repo. Interní kanály nevydávat za
uživatelské nastavení. JSON stdout a diagnostika nikdy neobsahují obsah env souboru.

Výjimka update zdroje: přechodové tlačítko T04 vždy používá pevné `janbkrejci/GIRO`,
nikoli HAIFA_UPDATE_REPO. Po přechodu GIRO ignoruje legacy hodnotu označující přesně
`janbkrejci/HAIFA` (také v migrovaném env) s vysvětlením a použije GIRO default.
Jiné explicitní firemní legacy repo se dál respektuje. Výslovné GIRO_UPDATE_REPO
zůstává administrátorský override. Migrace nepřepíše shell profil ani jinou URL.

## 4. Datový kontrakt, záloha a návrat

Výchozí legacy home je `$XDG_CONFIG_HOME/haifa`, jinak `~/.config/haifa`;
nový je vedle něj `giro`. Na Windows zachovat dosavadní výpočet základního home
z home.py/Path.home, nepřecházet svévolně na AppData. Porovnání cest musí zohlednit
resolve/symlinky a Windows normcase; dvě jména stejného adresáře nejsou kolize.

| Stav při startu GIRO | Povinné chování T02 |
| --- | --- |
| Explicitní GIRO_HOME nebo HAIFA_HOME | Použít vítěznou cestu, bez implicitního stěhování. Legacy-only explicitní home se nestává novou prázdnou instalací. Při přechodu připravit zálohu a marker i při stejné cestě. |
| Neexistuje žádný default home | Založit pouze nový giro, žádný prázdný haifa. |
| Jen legacy default | Nabídnutý přechod přes T04 autorizuje migraci do giro; samostatný start GIRO vyžaduje explicitní potvrzení migrace. Do potvrzení nic nezapisovat, vrátit konkrétní postup i v JSON režimu. |
| Jen nový default | Použít giro; nerozhodovat podle chybějícího legacy home, nevytvářet jej. |
| Existují oba defaulty, i prázdný nový | Bez platného dokončeného migračního manifestu odmítnout zápis a start workerů; žádné sloučení ani volba podle mtime. Uvést obě cesty a možnost explicitního GIRO_HOME po kontrole/záloze. |
| Oba + platný manifest z téhož přechodu | Použít nový, legacy je zachovaná záloha/ukazatel. Odlišná zdrojová/cílová identita či neúplný manifest znamenají blokaci, nikoli úspěch. |

Migrace je jedna obnovitelná operace po zastavení tasků, workerů, knihovních zápisů
a dashboardů kromě koordinátoru upgradu. Před změnou zjistit aktivní procesy a
získat společný migrační zámek, který respektuje poslední HAIFA i GIRO. Aktivní běh,
nezjištěný stav, nedostatek místa/práv nebo nemožnost konzistentní zálohy znamenají
odmítnutí bez přepisu. Upgrade UI vysvětlí čekání; nesmí procesy tajně zabíjet.

Postup T04/T02:

1. Před instalací uložit původní verzi, ověřený HAIFA bundle/wheel a manifest
   zdrojových/cílových cest a kontrolních součtů do privátního záložního adresáře
   vedle home (`<home>.pre-giro-<UTC>-<unikátní-id>`), nikdy do Gitu. Záloha se
   neodstraňuje automaticky ani uninstallem. Zachytit celý home včetně env,
   knihovního `.git`, dirty/untracked souborů, nastavení a vláken; externí knihovnu
   a jiné externí mutable datové cesty zahrnout samostatně, nepřepisovat je kopírováním.
2. Konzistentně zálohovat DB (SQLite backup/checkpoint v klidovém stavu včetně
   souvisejících dat, ne živý samotný .db soubor), `.factory/` runtime data a journal
   v common Git dir všech dotčených registrací. Externí sdílený DB server vyžaduje
   koordinovanou zálohu; pokud ji nelze zajistit, upgrade se bezpečně zastaví.
3. Kopírovat do privátního staging adresáře na cílovém filesystému, ověřit obsah,
   oprávnění (POSIX home 0700, env 0600; Windows ACL neoslabit) a reference. Nepřenášet
   zamčené procesové stavy jako živé zámky. Zdroj zůstává obnovitelný. Dokončit
   atomickým zveřejněním cíle a manifestu; při více krocích journal umožní obnovu.
4. Manifest `giro-migration.json` v dotčeném home má formát/verzi, ID operace,
   kanonický zdroj/cíl, původní/cílovou verzi, cestu zálohy a stav
   `prepared`/`committed`. Do legacy home zapsat ukazatel s týmž ID. Neobsahuje
   tajné hodnoty. Poslední HAIFA od T04 musí rozpoznat oba stavy a před běžným
   zápisem/startem odmítnout práci s návodem na dokončení či rollback. Složky a
   marker se nesmí mazat „pro uvolnění“ při opakování. Pád mezi kroky se obnoví
   z journalu nebo ze zálohy; není novou migrací a nepřepíše existující cíl.
5. Obnovit dashboard na stejné adrese, ověřit GIRO health/verzi a registry. Teprve
   potom označit přechod dokončený. Selhání instalace/restartu/validace vrátí
   předchozí software i data a funkční HAIFA alert s konkrétní chybou a opakováním.

Neměnit registracím ID (`haifa` je platné historické ID), repo/task/run UUID,
remote, absolutní cesty checkoutů ani worktree při migraci home. Knihovna
zachová UUID, HEAD, lokální commity, origin i dirty soubory. Současný upgrade
volá `library seed --all`, který úpravy nahrazuje: pro tento přechod jej **nepoužít**.
Použít nedestruktivní seed plán, zachovat `kept`; při dirty knihovně refresh přeskočit
s konkrétní diagnostikou a zachovat ji použitelnou. `.factory/` overrides neměnit.

Rollback se provádí jen po zastavení GIRO a všech zápisů: nejprve zálohovat i nový
stav, potom obnovit původní software z ověřeného posledního HAIFA bundlu a celou
konzistentní sadu původních dat na původní cesty, včetně externí knihovny/DB.
Po ověření obnovy zrušit marker v obnovené sadě; nikdy jej jen smazat nad živými
migrovanými daty. GIRO home odložit, nesloučit. Novější práci z GIRO rollback
automaticky nepřenáší; vlastník ji musí uchovat/exportovat před obnovou.

Poslední HAIFA nad migrovanou sadou bez rollbacku pracovat nesmí. Starší verze
marker neznají: jejich souběžné spuštění či downgrade nad migrovanými daty je
**nepodporovaný**, neposkytujeme tvrzení, že jej dokážeme technicky zastavit.
Návrat vede vždy přes poslední HAIFA a zálohu. T07 tuto hranici výslovně ověří.

Přesun vývojářského checkoutu HAIFA → GIRO je oddělená operace T05/T06. Nesmí
přepsat historii ani vytvořit nový prázdný registry záznam. S11 dnes identifikuje
lokální volby hashem kanonické cesty common Git dir; změna cesty proto vyžaduje
výslovný mapovaný přesun nastavení, registru, worktree Git referencí a cache po
záloze. Bez ověřeného postupu ponechat checkout na původní cestě. Alias ani změna
remote sama o sobě přesun adresáře nevyžaduje.

## 5. Skilly a technické výjimky

Seed skill `factory` generovat z nového CLI a udržet jedinou položku knihovny;
název položky není značka produktu. README/guide vysvětlí, že jde o kompatibilní
technické ID. Negenerovat další `skill/giro` vedle uživatelské upravené položky.
Repo-owned kopie mají standardní synchronizaci `.claude/skills/` → `.agents/skills/`;
běhové nesledované kopie se neopravují ručně.

Ponechané `haifa-action` bloky, storage klíče, DB tabulky, common-dir journal,
`min_factory_version` a library PR metadata nejsou aktivní marketingové texty.
Jejich změna nemá přínos přiměřený riziku ztráty historie; nepatří do T02/T03.
Nové uživatelské příklady používají GIRO a rozlišují současný stav od cílového.

## 6. Hosting a jméno: důkazy a rozhodnutí pro T06

Navržený přesný nový repozitář: **`janbkrejci/GIRO`**, budoucí clone URL
`https://github.com/janbkrejci/GIRO.git`, release API
`https://api.github.com/repos/janbkrejci/GIRO/releases/latest`.
**Tyto adresy nejsou k datu inventury funkční instalační zdroj.**

Read-only kontrola 2026-11-14:

- `git remote -v`: origin `https://github.com/janbkrejci/HAIFA.git` pro fetch/push.
- Autentizované `gh api user --jq .login`: `janbkrejci`.
  `gh api repos/janbkrejci/HAIFA` vrací full_name `janbkrejci/HAIFA`,
  `private: false`, default branch `main`, admin/push oprávnění true.
  [Veřejný původní repozitář](https://github.com/janbkrejci/HAIFA) je dostupný.
- `gh api repos/janbkrejci/GIRO` vrací **HTTP 404 Not Found**, stejně jako
  [veřejná cílová stránka](https://github.com/janbkrejci/GIRO).
  Závěr: žádné repo pod tímto jménem není pro tuto identitu viditelné. Je to
  kandidát dostupný podle tohoto pozorování, nikoli rezervace nebo důkaz možnosti
  založení. T06 znovu ověří jméno i oprávnění a zapíše skutečný owner/repo;
  při obsazení či nejasném vlastnictví zastaví publikaci a rozhodne o novém cíli,
  který musí být konzistentně změněn v kontraktu, T04 updateru i všech GIRO zdrojích.
- [HAIFA-LIBRARY](https://github.com/janbkrejci/HAIFA-LIBRARY) je dostupná.
  Zvolená kompatibilní výjimka: hosting knihovny **nepřejmenovávat**, zachovat
  default URL i existující klony/forky/PR. GIRO není vázáno na jméno remote;
  T05 inventarizuje nastavení a T06 případně upraví jen aktivní popis/README knihovny
  v jejím vlastním repozitáři. V tomto checkoutu se knihovna neupravuje.

Relevantní použití GIRO v softwaru, ověřená z primárních zdrojů:

| Zdroj | Nález a dopad |
| --- | --- |
| [PyPI giro](https://pypi.org/project/giro/) | Existující Python nástroj pro orchestraci AI coding agentů, jeho instalační příklad používá `uv tool install giro` a CLI `giro`. Přímá věcná i příkazová kolize; naše distribuce zůstává aifactory a návody nikdy nedoporučí instalaci cizího PyPI giro. |
| [GIRO Inc. / HASTUS](https://www.giro.ca/en-us/our-solutions/segments/workforce-management/) | GIRO je aktivní jméno dodavatele softwaru pro dopravu/plánování; nejde o unikátní nové slovo v softwaru. |
| [Rust crate giro](https://docs.rs/crate/giro/0.1.2/source/README.md) | Existující nástroj pro rozpoznání příslušnosti cesty ke Git repozitáři. |
| [kevinraymond/giro](https://github.com/kevinraymond/giro) | Další GitHub projekt, experimentální zpracování obrazu/3D; název je používán i mimo dopravu a AI workflow. |

Toto je technická rešerše, **nikoli tvrzení o právní dostupnosti značky** nebo
právní posudek. Značka a CLI GIRO zůstávají zadáním; T06 musí před zveřejněním
výslovně zaznamenat rozhodnutí vlastníka vzhledem k výše doložené blízké kolizi.
Instalátor T02 nesmí přepsat cizí executable `giro`: zjistí vlastnictví cílového
entry pointu, při kolizi zastaví instalaci před změnou a vysvětlí ruční vyřešení.
Žádné automatické odinstalování cizího balíčku nebo předpoklad, že `giro` na PATH je náš.

## 7. Dva zdroje vydání a skutečná hranice CI

Současný `.github/workflows/ci.yml` obsahuje jediný job `release`:

- Trigger push na main kromě změn výhradně `factory/**`, `docs/**`, `.factory/**`,
  plus workflow_dispatch. Job běží pouze na main a veřejném repo (`private == false`).
- Ubuntu, Python 3.12, uv, Bun; frozen frontend install/build, `uv sync --locked`,
  stamp verze `<major>.<minor>.<GITHUB_RUN_NUMBER>` a UPDATE_REPOSITORY z
  GITHUB_REPOSITORY, sestavení ZIP, čerstvá instalace a kontrola `factory --version`.
- Před publikací kontroluje aktuální main proti zastaralému produktu. Vytváří
  draft tagu `v<verze>`, nahraje ZIP a zveřejní jej jako latest. Concurrency na ref
  ruší předchozí běh. Není to obecný release engine uživatelských projektů.
- Žádný pull_request trigger, pytest, lint, mypy ani Windows/macOS job. Frontend
  build zahrnuje vue-tsc, nikoli Vitest/browser testy. Tato CI negarantuje kvalitu PR;
  approve/auto-merge může přijmout PR bez checků. Lokální/tester kontroly jsou nutné.

Produkt nyní řídí backlog → běh workflow → PR/approve/merge; release konkrétního
repo závisí na jeho CI a nastavení. GIRO UI ani README nesmějí sloganem tvrdit,
že je automatické vydání výsledku již obecně implementované. T07 demo výslovně
rozliší produktový PR/merge a následné release CI testovacího projektu.

T04 musí před první rebrandingovou produktovou změnou zavést publikační gate
v HAIFA repo: automatické push vydávání vypnout. Poslední HAIFA se později smí
vydat pouze explicitním dispatch schváleného uchovaného SHA, nikoli náhodného
main. Gate musí fungovat i v uchovaném zdroji, ověřit owner/repo a povolený ref,
a po posledním HAIFA vydání zablokovat i opakovaný dispatch nové publikace.
T02 připraví GIRO větev workflow s povolením pouze skutečného nového owner/repo;
žádný rebrandingový commit publikovaný do starého main nesmí vydat ZIP.
T05 popíše konkrétní ovládání gates a T06 je provede a doloží.

Uchování a verze:

1. T04 dokončí HAIFA alert a updater nad HAIFA značkou/bundlem. Před T02 zaznamená
   přesný commit a stabilní ref `haifa-transition-source` v release dokumentu;
   workflow později vytvoří/uchová odpovídající tag/ref, builder jej sám nezakládá.
   Zdroj včetně frontendových statik musí jít sestavit bez checkoutu pozdějšího main.
2. Vyhradit poslední HAIFA verzi **H = `0.1.N`**; T05/T06 určí konkrétní N podle
   posledního skutečného releasu a CI run number, H musí být vyšší než předchozí HAIFA.
   První GIRO **G = `1.0.M`**, kde M je run number nového repo, musí splnit G > H.
   T04/GIRO zachovají třísložkové porovnání verzí a min_factory_version knihovny.
   Restart číslování CI v novém repo nesmí způsobit downgrade; major skok tomu brání.
3. T06 založí nové repo s historií/SHA dle T05, ověří nastavení a vydá G jen z GIRO
   zdroje. Zkontroluje stabilní release, ZIP, SHA256SUMS, instalaci všech platforem
   a update/restart. Teprve poté vydá H z uchovaného HAIFA SHA na starém repo.
   Přechodový build nesmí přepsat pevný GIRO cíl stampováním HAIFA repo.
4. Starší HAIFA dál hledá H přes starý latest endpoint a starý formát ZIP. H nabídne
   globální alert „HAIFA se přejmenovává na GIRO“ a „Klikněte zde pro přechod“.
   Až kliknutí stáhne stabilní G z pevného nového repo, ověří URL/ZIP/hash/wheel,
   nainstaluje jej existujícím updaterem a předá/restartuje dashboard. Žádný druhý
   updater a žádné spuštění při načtení stránky. GIRO dále používá nové repo.
5. HAIFA repo zůstává dostupné pro H, historické releasy, issues a PR; nové GIRO
   releasy pouze v novém repo. Původní main ani tagy se nepřepisují. T05 připraví
   přesný seznam otevřené práce, konfigurace hostingu a změn odkazů; T06 zaznamená
   skutečné H/G, SHA/ref, časy a výsledky do `docs/rebranding/cutover.md`.

## 8. Akceptační scénáře a předání ověření

Každý řádek je povinné ověření změny/výjimky z mapy. T07 zopakuje výslednou
matici na macOS, Linux a Windows s konkrétními H/G a evidencí; chybějící platforma
není úspěch. Implementační task přidá regresní testy, včetně všech selhání limitů.

| ID | Vlastník | Scénář a očekávaný výsledek |
| --- | --- | --- |
| A01 | T03 → T07 | Čistý dashboard, title, onboarding, guide, diagnostika a help ukazují GIRO a přesný slogan; vyhledané zbylé výskyty mají výjimku z mapy. Licence, původ a historické odkazy beze změny; docs neslibují univerzální autorelease. |
| A02 | T02 → T07 | Wheel se instaluje jako aifactory, import aifactory funguje, giro i factory mají shodné operace/JSON/exit a jednu instalaci/home; verze a help GIRO. Build/import cesty a self-repo detekce learn/sources.py zůstávají funkční. |
| A03 | T02 → T07 | Izolovaný PATH s cizím giro: instalace nic nepřepíše a oznámí kolizi. Bez kolize POSIX/Windows instalátory vytvoří oba entry pointy. Uninstall odstraní naši distribuci, keep-data zachová obě sady a zálohu; purge vyžádá explicitní výběr dat, neodstraní slepě druhý home nebo externí knihovnu. |
| A04 | T02 → T07 | Pro každou env dvojici otestovat novou, legacy, obě, prázdnou, neplatnou a konflikt shell/env. Efektivní hodnota i subprocess shodné; secret hodnoty se neobjeví v diagnostice. Explicitní home nenastartuje druhou prázdnou továrnu. |
| A05 | T02 → T07 | Clean/legacy-only/new-only/oba home, oba včetně prázdného cíle, symlink a Windows case varianta podle tabulky oddílu 4. Konflikt bez manifestu odmítne zápisy a workery, zdroj nedotčený; platná dokončená migrace použije jediný cíl. |
| A06 | T04 + T02 → T07 | Aktivní task, aktivní upgrade, nedostatečná práva/místo, poškozená data, pád po každém migračním kroku: žádné tiché přepsání, druhý start ani false success. Záloha obnovitelná, opakování použije journal a po dokončení nic znovu nepřenáší. |
| A07 | T02 + T03 → T07 | Knihovna s lokálními commity, dirty/untracked daty, vlastními seed úpravami a externí cestou zachová obsah/HEAD/UUID/origin. Žádný seed --all; kept zůstane, dirty refresh se bezpečně odloží. Default HAIFA-LIBRARY i obě env URL fungují. |
| A08 | T02 + T05 + T06 → T07 | Registrovaná repa, lokální volby, trace/historie, přepisy, PR odkazy a worktrees stejné před/po; home migrace nepřepisuje repo cesty. V izolaci vyzkoušet i výslovný přesun checkoutu/common-dir s remapováním S11 identity, bez duplicit; při neověřeném přesunu zůstane původní cesta. |
| A09 | T04 + T02 → T07 | Starší podporovaná HAIFA najde H jako haifa ZIP, H výslovně přijme G jako giro ZIP s aifactory wheelem. G > H i při menším CI run number; stejná/nižší verze a nevyhovující min_factory_version neprojdou nechtěným downgradem. |
| A10 | T04 + T02 → T07 | Fake hosting rozliší HAIFA a GIRO: kliknutí míří jen do nového repo; GIRO další update také, i s převzatým HAIFA_UPDATE_REPO=janbkrejci/HAIFA. Firemní override a GIRO override se chovají dle oddílu 3. |
| A11 | T04 → T02 → T07 | Alert viditelný napříč HAIFA obrazovkami, až kliknutí zahájí upgrade; duplicitní/aktivním během blokované kliknutí má vysvětlení. Výpadek sítě, chybějící release, špatný hash/wheel/URL, chyba instalace či restartu ponechá obnovitelnou funkční HAIFA; opakování uspěje, GIRO alert nemá. |
| A12 | T04 + T02 + T05 → T06/T07 | Sestavit H z uchovaného SHA a G z GIRO SHA. Simulovat push/dispatch/ref/owner gates: rebranding na HAIFA main nic nepublikuje; nový repo publikuje jen GIRO; H lze vydat pouze z povoleného zdroje a až po ověřeném G; další HAIFA publikace zakázána. |
| A13 | T05 → T06 → T07 | Reálná kontrola cíle, oprávnění, historie SHA, nastavení hostingu, seznamu otevřené práce a přesných endpointů. G dostupné před H; staré URL, issues/PR a poslední HAIFA zůstanou. Docs odliší neaktivní plánované URL od skutečných. |
| A14 | T05 → T06/T07 | Výchozí i vlastní knihovna jsou dostupné, remote nezměněn, existující PR návrhy dál rozpoznané a knihovna se kvůli nové značce nereinicializuje. |
| A15 | T03 → T07 | Před upgradem nastavit všechny storage preference a rozpracovaný follow-up v témže origin. Po přechodu stejné hodnoty, thread a request ID; opakování follow-upu nevytvoří duplikát. Frontend private package/health metadata konzistentní; regenerovat statiky just web-build. |
| A16 | T03 → T07 | Generovaný skill, seed a demo používají giro/GIRO; změněný seed zachová uživatelské úpravy. Starý haifa-action ze zprávy i nový návrh se renderují/provedou stejně; MCP průvodce a idempotentní API plány fungují beze změny protokolu. |
| A17 | T02 + T04 + T07 | Obnova zálohy v izolaci vrátí H, registry i knihovnu; poslední HAIFA odmítne zápis nad prepared/committed markerem bez rollbacku. Výslovně zaznamenat nepodporované pre-H procesy. Kompletní cyklus demo PR/merge a release CI doložit odděleně, beze změny uživatelského repa. |

Pro T02/T04 hledat přímé volající v celém `aifactory/tests/`, zejména soubory
`test_distribution.py`, `test_bundle.py`, `test_upgrade.py`, `test_release.py`,
`test_release_workflow.py`, `test_repo_settings*.py`, `test_remote_database.py`,
`library/`, `web/`, `run/`, `learn/`, `validation/`. Pro T03 `test_skill.py`,
`test_guide*.py`, demo a dotčené Vue testy/konkrétní e2e obrazovky. Jde o místa pro
výběr, ne příkaz spustit všechny tyto adresáře. Tester zúží na skutečně změněné
chování, vždy zahrne každý změněný testový soubor a povinné lint/typecheck podle
stepu; implementační builder v tomto workflow kontroly rutinně nespouští.

## 9. Potřebný rozsah dalších tasků

T01 nemění backlog. Před spuštěním dalších tasků musí workflow upravit jejich
front matter a commitnout případná rozšíření; nejde o samostatné nové úkoly:

| Task | Stávající scope / potřebné doplnění |
| --- | --- |
| T02 | `aifactory/`, `justfile`, `.github/workflows/`, `.gitignore`, docs/rebranding a decisions již pokrývají zvolenou technickou variantu; `giro/` se nezakládá. Žádné další cesty potřeba. |
| T03 | Stávající aifactory, README, AGENTS, CLAUDE, docs a justfile stačí; sledované repo skilly dnes neexistují. Kdyby se před během staly repo-owned, doplnit přesné `.claude/skills/factory/` a `.agents/skills/factory/` před jejich editací. |
| T04 | Stávající aifactory, workflows, justfile, README a rebranding docs stačí i pro marker guard poslední HAIFA a publikační gate. |
| T05 | Dokumentační scope stačí; pouze read-only inventura hostingu/knihovny, žádný zápis jiného repa. |
| T06 | Stávající scope pokrývá cutover. Pokud T05 určí změnu `.gitignore` kvůli checkoutu/artefaktům, doplnit **`.gitignore`** před krokem; jiný repo HAIFA-LIBRARY má vlastní provozní akci, ne zápis z tohoto checkoutu. |
| T07 | Doplnit **`.gitignore`** před během, pokud bude opravovat pravidla zavedená T02; současný scope ji neobsahuje. Ostatní opravy a evidence jsou pokryté. |

Skutečné rozšíření je podmíněné konkrétní změnou, nikoli licence k editaci cizích
cest. T06 již existuje jako ruční task pro hosting a rozhodnutí o názvu; nevytvářet
duplicitní lidský follow-up. Žádná registrace domény nebo ochranné známky není v rozsahu.

## 10. Reprodukce inventury T01

Použity read-only kontroly `git rev-parse HEAD`, `git remote -v`, `git ls-files`,
`rg -n 'HAIFA|haifa|Helios|aifactory|factory'` nad zdroji, bundle, frontendem,
CI, testy a instrukcemi; zvlášť `rg -o 'HAIFA_[A-Z0-9_]+'` se sjednocením výsledků.
Zkontrolovány skutečné implementace home, registry, repo_settings, DB, upgrade,
library/share, bundle/build, bundle/release a celé ci.yml, nikoli jen příklady v guide.
`factory check --offline --json` vrátil installed, žádné chyby, upozornění na ruční T06
bez workflow (záměrné); hosting zde doložen zvlášť read-only API a odkazy v oddílu 6.

Ověření dokumentu v test kroku: všechny relativní odkazy a konkrétní zdrojové cesty,
úplnost env/storage seznamů proti rg, návaznost každého řádku mapy na Axx a T02–T07,
shoda s decisions a závislostmi backlogu. T01 nepřidává produktové chování ani testy;
neprovádí publikaci, hostingové změny nebo manipulaci s živými daty.

## 11. Povinný plán ověření tohoto dokumentačního tasku

T01 má samostatný test krok. Dokumentační rozsah není výjimkou z pravidla
AGENTS.md „just lint a just typecheck, vždy“. Tester musí předat runneru neprázdný
plán s následujícími kontrolami z kořene tohoto worktree:

| Kontrola | Příkaz / postup | Podmínka úspěchu a evidence |
| --- | --- | --- |
| Statická kontrola Pythonu | `just lint` (timeout 120 s) | Exit 0; uložit příkaz, exit a log. |
| Typová kontrola Pythonu | `just typecheck` (timeout 180 s) | Exit 0; uložit příkaz, exit a log. |
| Cílená kontrola kontraktu | `python3 <context_handoff_dir>/verify_contract.py` (timeout 60 s); skript předaný builderem v handoff tohoto běhu | Exit 0; kontroluje relativní odkazy nové dokumentace, konkrétní zdrojové soubory mapy, množinu HAIFA_* proti sledovaným zdrojům, frontendové storage klíče a vazby každého řádku mapy na existující A01–A17 a T02–T07. Log obsahuje počty ověřených položek. |
| Věcná kontrola | Tester přečte mapu a rozhodnutí proti uvedeným zdrojům, ci.yml a front matter T02–T07 | Zapsat výsledek s cestami/řádky pro shodu rozhodnutí, závislostí, vlastníků, výjimek a adresářových skupin; budoucí provozní cesty a uchovaný ref nesmějí být zaměněny za již existující artefakty. |

`<context_handoff_dir>` je absolutní handoff adresář dodaný workflow, nikoli
adresář uvnitř repa. Skript je pomůcka tohoto ověření, není součást produktu.
Automatická kontrola struktury nenahrazuje věcnou kontrolu správnosti pravidel.
Výsledky všech příkazů a věcné kontroly musí být v test reportu; prázdné checks,
coverage=none nebo samotný plán nejsou provedené ověření. Timeout je neúplná
kontrola. Builder tyto příkazy nepředstírá jako vykonané a nespouští je místo runneru.
Produktové regresní testy, frontend build, browser kontroly a plná sada nejsou
pro samotnou změnu tohoto kontraktu potřebné.
