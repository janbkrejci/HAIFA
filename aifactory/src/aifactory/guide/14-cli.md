# Příkazová řádka

Všechno, co umí dashboard, jde udělat i nástrojem `factory`. Podrobnou nápovědu ke každému příkazu vypíše `factory <příkaz> --help`. Příkazy s `--json` vracejí jednotnou obálku `{ok, data, error, warnings}` s kódy chyb; úplný popis pro agenty vypíše `factory --skill`.

Příkazy, které pracují s repem, berou repo z aktuálního adresáře; jiné určíš přes `--repo CESTA`.

## Kontrola a instalace

| Příkaz | Co dělá |
| --- | --- |
| `factory --version` | Verze HAIFA. |
| `factory check` | Jen čte: zkontroluje počítač, knihovnu a (v repu) repo; `--offline` vynechá hosting a přihlášení. |
| `factory init` | Nainstaluje HAIFA do repa: `.factory/config.yaml`, adresář backlogu, `.gitignore`. `--dry-run` ukáže plán a digest, `--commit --expect DIGEST` ho commitne do base, `--pr` místo toho otevře pull request. |
| `factory obs` | Spustí dashboard (`--port N`, `--repo CESTA` zaregistruje repo, `--no-open` neotevře prohlížeč, `--host ADDR` jiná adresa; `0.0.0.0` zpřístupní dashboard celé síti bez přihlášení). |
| `factory upgrade BUNDLE` | Nainstaluje novější HAIFA z `haifa-<verze>.zip` (cesta nebo `https` URL); `--dry-run` jen ověří. |
| `factory --skill` | Návod pro agenty, který HAIFA ovládají. |

## Tasky

| Příkaz | Co dělá |
| --- | --- |
| `factory task list` | Tasky s odvozeným stavem. |
| `factory task show ID` | Task a jeho stav. |
| `factory task add STEP TITLE` | Nový task ve stepu (`--workflow`, `--depends-on`, `--writes`, `--body` pro text zadání). |
| `factory task edit ID` | Změna polí v hlavičce tasku. |
| `factory task link ID` | Přidá nebo odebere `depends_on` a `related`. |
| `factory task run ID` | Spustí běh v novém worktree a větvi. `--note` přidá poznámku pro agenty, `--auto` po úspěchu pokračuje dalším připraveným taskem, `--harness`, `--model`, `--thinking` přepnou agenty jen pro tento běh, `--force` ignoruje nedokončené závislosti. |
| `factory task stop ID` | Zastaví běžící běh. |
| `factory task pause ID` | Pozastaví běh před další fází. |
| `factory task resume ID` | Pozastavený běh pokračuje další fází. |
| `factory task publish ID` | Odešle větev posledního úspěšného běhu a otevře pull request. |
| `factory task approve ID` | Zapíše `status: done`, mergne pull request, srovná base s remote a uklidí worktree. |
| `factory task return ID --note TEXT` | Vrátí task agentům s připomínkou; nový běh na stejné větvi aktualizuje pull request. |
| `factory task resolve ID` | Přenese pull request na aktuální base (rebase) a vyřeší konflikty. |
| `factory task clean` | Smaže worktree běhů s mergnutým nebo zavřeným PR a opuštěných běhů. |

## Backlog

| Příkaz | Co dělá |
| --- | --- |
| `factory backlog list` | Strom backlogu se stavy. |
| `factory backlog check` | Ověří backlog a vypíše všechny problémy. |
| `factory backlog add` | Nový projekt, nebo step v projektu. |
| `factory backlog edit` | Název a nastavení projektu nebo stepu (`index.md`). |
| `factory backlog auto-continue` | Zapne, vypne nebo vrátí na zděděné auto-continue projektu či stepu. |
| `factory backlog auto-merge` | Totéž pro auto-merge. |
| `factory backlog commit` | Commitne změny backlogu do base. |
| `factory backlog sync` | Jedním PR označí jako hotové tasky, jejichž PR byl mergnut mimo HAIFA. |

## Konfigurace repa

| Příkaz | Co dělá |
| --- | --- |
| `factory config show` | Konfigurace, kterou by použil běh. |
| `factory config status` | Necommitnuté změny `.factory/`, které běhy nevidí. |
| `factory config commit` | Commitne sdílenou konfiguraci do base (nejdřív push, pak posun base). |
| `factory config pull` | Posune lokální base na remote (fast-forward). |
| `factory config roster show` | Platné nastavení agentů (harness, model, thinking). |
| `factory config roster set` | Předvolba `claude` nebo `codex` pro celý roster, nebo `--agent JMÉNO` s `--harness`, `--model`, `--thinking`. |
| `factory config set` | Změní vazby jednoho agenta v `.factory/agents.yaml`. |
| `factory config remove` | Odebere vlastní kopii položky z repa (platí pak verze z knihovny). |
| `factory config move` | Přesune vlastní kopii položky z repa do knihovny. |
| `factory workflow check` | Ověří workflow proti registru rolí a agentům. |
| `factory harness check` | Ověří, že CLI harnessů jsou na PATH, a vypíše jejich verze. |
| `factory skills sync` | Zapíše `.agents/skills` jako přesnou kopii `.claude/skills` (pro codex a pi). |

## Knihovna

| Příkaz | Co dělá |
| --- | --- |
| `factory library init` | Založí knihovnu ze semínka (`--name`, `--remote URL` prázdného repa). |
| `factory library clone URL` | Naklonuje sdílenou knihovnu. |
| `factory library status` | Remote, větev, náskok a zpoždění, necommitnuté změny (`--fetch` nejdřív stáhne). |
| `factory library pull` | Posune knihovnu na remote. |
| `factory library push` | Odešle lokální commity knihovny (nikdy force). |
| `factory library list` | Položky knihovny s verzemi. |
| `factory library show` | Soubory a historie verzí položky. |
| `factory library import CESTA --type TYP` | Importuje složku (agent, skill, rozšíření) nebo soubor (workflow) z domovského adresáře. |
| `factory library seed` | Po aktualizaci HAIFA převezme nové verze ze semínka (`--dry-run`, `--take TYP/JMÉNO`). |
