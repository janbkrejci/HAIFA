# HAIFA-S05-T12: API položek, onboardingu a více repozitářů

Factory API používá stejné core funkce jako CLI. V dashboardu více repozitářů mají
repo trasy prefix `/api/repos/{id}`; v `create_app(repo)` mají prefix `/api`.
Globální `POST /api/library/repos-plan` funguje v obou režimech a vybírá repozitáře
z registry v dashboardovém HAIFA_HOME. Výslovné HAIFA_LIBRARY má stejný význam jako v CLI.

## Stavy položek

`GET …/factory/items` vrací standardní obálku s výsledkem `factory config items`:
manifest, knihovnu, položky, aliasy a repo/manifest/library verze. Zachovává stavy
synced, local, modified, outdated, diverged, missing a unknown. Bez parametru
`base` čte pracovní strom; `?base=` čte nakonfigurovanou base, `?base=main`
konkrétní referenci. Nezapisuje cache historie.

## Plán a provedení

`POST …/factory/plan` přijímá `{action, options?, target?}`.
`POST …/factory/apply` přijímá stejné volby a `digest`, případně `message`.
Výchozí target je base (CLI commit); pr znamená commit do PR větve.

| Akce | Options |
| --- | --- |
| add | type, name, slot, harness, model, thinking, agent |
| set | type, name, harness, model, thinking, tools, writes, color |
| remove | type, name, prune |
| export | type, name, slot |
| revert | type, name, to (manifest nebo head) |
| update | item, take, merge, migrate |
| onboard | keep_local, names, workflows |
| adopt | žádné |

Dosavadní init a config_commit zůstávají podporované. U položkových akcí jsou
type/name povinné neprázdné řetězce; typy jsou agent, workflow, skill a extension.
Slot odpovídá CLI `--as`. Bindingy jsou řetězce; tools/writes jsou CSV se stejným
významem prázdného řetězce jako CLI. Prune a onboard workflows jsou booleany.
Update volby jsou seznamy řetězců, například `item: ["agent/builder"]` a
`take: ["agent/builder:system.md"]`. Onboard keep_local je seznam `TYPE/NAME`,
names seznam `TYPE/NAME=NEW`; podporované selektory odpovídají CLI.

Příklad přidání agenta pod jiným slotem:

```json
{"action":"add","options":{"type":"agent","name":"builder","slot":"extra"}}
```

Po kontrole odpovědi pošlete stejné volby a vrácený digest:

```json
{"action":"add","options":{"type":"agent","name":"builder","slot":"extra"},"digest":"<digest plánu>","target":"base","message":"factory: add extra"}
```

Server vždy znovu sestaví core plán. Request nepřijímá cesty, obsah souborů
ani hotový plán pro provedení. Neznámé klíče a chybné JSON typy mají 400
usage_error; sémantické chyby mají 422. Změněný plán má 409 plan_changed s novým
plánem v data; blokátory zachovávají kód, issues a doporučený fix. Odmítnutý push
má 502 push_failed. Souběžný zápis má 409 busy.

Plány zachovávají úplný core JSON. Výsledky položkových akcí zachovávají podrobnosti
změny, bindings a publish údaje. Export a onboard zapisují knihovnu před repozitářem;
library_commit zůstává dostupný i při následné publish chybě. Onboard vrací
library_plan, repo plán, report s kódy, text message a objekt remote. Export,
onboard a adopt sdílejí zámek s globálními zápisy knihovny; ostatní repo apply
mohou běžet nezávisle v jiném repozitáři.

Adopt zapisuje pouze knihovnu. Commit ve výsledku označuje zdrojový commit repozitáře,
library_commit provedený import a repo_changed zůstává false. PR target a nenulová
message jsou 422 conflicting_options. API poskytuje stabilní digest i pro no-op;
zahrnuje zdrojové repo, base commit a identitu/HEAD knihovny. Před importem znovu
plánuje pod API zámky a odmítne změněný digest. Zámky koordinují požadavky dashboardu;
nepřidávají transakční garanci vůči externím procesům.

## Plány ve více repozitářích

`POST /api/library/repos-plan` přijímá action add/update, povinné type/name,
repos a nepovinné options. Repos je neprázdný seznam unikátních registrovaných ID,
řetězec all nebo ID oddělená čárkou. Neznámé ID má 404 unknown_repo, chybějící registry
409 registry_missing. ID nikdy neznamená cestu.

```json
{"action":"add","type":"agent","name":"builder","repos":["repo-a","repo-b"],"options":{"slot":"extra","target":"base"}}
```

Add options odpovídají add bez type/name, update přijímá take/merge/migrate.
Options target může být base/pr. Update vždy cílí jen na uvedené type/name;
neaktualizuje všechny položky. Endpoint volá L9 core v dry-run režimu a nic neprovádí.

Výsledek obsahuje repos řádky s repo, plan, result, status a případnou error.
Každý dostupný plan má action, apply_options a apply_target. Jeho původní digest
se použije při jednotlivém `POST /api/repos/{id}/factory/apply` s těmito options
a targetem. Do requestu se neposílají files ani celý plan. Řádek s blockers má
status blocked a celkový partial=true. Chyba jednoho repa zachovává ostatní plány;
platná částečná odpověď má HTTP 200. Operace nejsou transakcí přes všechna repa.

## Ověření

Regresní testy používají TestClient, dvě registrovaná repa, dočasnou knihovnu
a lokální bare remotes. Pokrývají položkové operace, export do druhého repa,
cílený update s take, migraci sssf, adopt a stale/no-op digest, chybové obálky,
sdílené zámky, striktní requesty a oba režimy aplikace. Nevolají model ani síť.
