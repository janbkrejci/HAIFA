# HAIFA-REFINEMENT-T14 — Rychlý stav konfigurace a seznamu rep

Konfigurační pathspecy jsou nyní `.factory/*`, `.claude/skills/*` a
`.agents/skills/*`. Výchozí gitový wildmatch dovoluje `*` odpovídat i lomítkům,
takže zahrnuje soubory v libovolné hloubce. Tím se obejde pomalá větev
`unpack_trees` v Git for Windows/VFS. Parsování `diff-index`, kontrola obsahu
pomocí `hash-object` při zastaralých stat datech a detekce nesledovaných souborů
zůstávají stejné. Žádný z těchto příkazů nezapisuje index.

`GET /api/repos` cachuje celý stav jednotlivého repa na 15 sekund. Cache patří
instanci aplikace, rozlišuje ID a cestu repa a při souběžných požadavcích počítá
stejný klíč jen jednou. Aktuální údaje z registru se přidávají i při cache hitu.
Odstraněné položky se z cache vyřazují.

Před použitím cache se porovnají stat údaje sdílených konfiguračních souborů a
adresářů, lokálního nastavení, `.gitignore`, indexu, HEAD a referencí. Kontrola
nevolá Git a neprochází zdrojové soubory ani `.factory/worktrees/`, trace DB či
transkripty. Změna přes dashboard, `factory config` v jiném procesu nebo externí
commit tak zneplatní cache hned při dalším čtení. Stejné zneplatnění používá
konfigurační cache overview; intervaly pollingu a ostatní gitová volání overview
se nemění. Podporované jsou i gitdir/commondir ukazatele propojených worktrees.

## Měření pro popis PR

Windows, Python 3.12.14, `git version 2.55.0.vfs.0.10`, lokální syntetický repozitář
s **61 558 soubory v indexu**: 61 556 malých textových souborů pod `src/` v 62
adresářích, `.factory/config.yaml` a `.factory/agents.yaml`; adresáře skills
neexistují. Všechny soubory jsou v pracovním stromu, stav je čistý.
Tři opakování ve stejném procesu, bez změny indexu mezi měřeními:

| Operace | Před (s) | Po (s) |
| --- | --- | --- |
| `working_tree_changes`, 1. čtení | 2,9279 | 0,1226 |
| `working_tree_changes`, 2. čtení | 2,8150 | 0,1232 |
| `working_tree_changes`, 3. čtení | 2,8680 | 0,1113 |
| `GET /api/repos`, 1. požadavek | 3,4873 | 0,3086 |
| `GET /api/repos`, 2. požadavek | 3,3060 | 0,0065 |
| `GET /api/repos`, 3. požadavek | 3,6546 | 0,0060 |

Počet gitových procesů pro tři požadavky `/api/repos`: před **7 / 7 / 7**,
po **7 / 0 / 0**. Medián výpočtu změn je přibližně **23× rychlejší**.
Cache hit při navigaci nespouští žádný gitový proces.

Pro srovnání byla původní verze simulována stejným čtecím algoritmem s pathspecy
`.factory`, `.claude/skills`, `.agents/skills` a vypnutou cache seznamu rep.
HTTP čtení probíhalo přes Starlette TestClient; gitové procesy se počítaly na
hranici `subprocess.run`. Jde o reprodukci s velkým indexem, nikoli nové měření
původního uživatelského repozitáře, kde zadání uvádí 12–19 s pro seznam rep a
10 s pro overview. Doba overview jako celku zde měřena nebyla.

## Ověření

Testy porovnávají původní adresářové a nové wildcard pathspecy pro modified,
added, deleted a untracked soubory, soubory ve vnořených adresářích a s mezerou
v názvu, zastaralá stat data, změny mimo pathspec a úplně odstraněný adresář
skills. Běží i při existujícím `index.lock` a kontrolují nezměněné bajty a mtime
indexu i obsah zámku.

API test ověřuje opakované čtení, vypršení TTL, runtime změny, změnu přes
dashboard, skutečný příkaz `factory config set` v podprocesu, externí commit
a vytvoření/odstranění vnořeného skillu. Overview má navíc test zneplatnění
před uplynutím TTL. Ostatní existující testy overview ověřují souběh repozitářů
a časový limit.

Factory ověřuje dotčené testy a statické kontroly podle AGENTS.md. Celou sadu
a e2e ověří CI na PR a auto-merge na ně čeká; výsledky celé sady z factory běhu
se podle upraveného zadání nevyžadují.

## Stabilita testu ukončeného procesu na Windows

`test_dead_process_is_shown_without_any_write` používal PID krátkého podprocesu,
jehož objekt `Popen` fixture ihned uvolnila. Windows po uzavření posledního
process handle může PID přidělit jinému procesu; při souběžných testech tak
overview mohlo správně vrátit `alive` pro již recyklovaný PID.

Fixture nyní drží objekt a handle skutečně ukončeného podprocesu v context
manageru až do konce testu. PID zůstává rezervovaný; kontrola OS ani tvrzení
o nezměněné trace DB se nemockují. Produkční detekce procesů zůstává stejná.

Cílený příkaz je `just pytest tests/web/test_web_overview.py::test_dead_process_is_shown_without_any_write -n0`.
V prostředí builderu chyběl `bash`, takže recept skončil před spuštěním pytestu.
Ekvivalentní výběr byl úspěšně spuštěn přes
`just --command uv run --directory aifactory pytest tests/web/test_web_overview.py::test_dead_process_is_shown_without_any_write -n0`.
