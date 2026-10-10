# Globální API knihovny a kontroly stroje

Více-repozitářový dashboard poskytuje endpointy bez vybraného repa. Používají stejné
core funkce jako `factory library …` a `factory check` mimo repo a standardní obálku
`{ok, data, error, warnings}`. Prostředí knihovny má `HAIFA_HOME` dashboardu; serverový
`HAIFA_LIBRARY` má stejně jako v CLI přednost. Klient nemůže tyto cesty přepsat.

## Čtení

- `GET /api/machine/check?offline=1&fresh=1`: kompletní CLI report pouze pro stroj
  a knihovnu (`in_repo=false`, repo/state/base/commit jsou null), navíc `checked_at`
  v UTC a `cached`. Cache platí 60 sekund, online a offline mají oddělené položky.
  `fresh=1` přepočítá daný režim. I `checks_failed` má HTTP 200 a report v `data`.
  Offline přeskočí přihlašovací kontroly. Po pokusu o knihovní zápis se cache vyprázdní.
- `GET /api/library`: stav z `factory library status` bez fetch a `exists=true`.
  `items` obsahují type, name, version, short_version, commit, date, author a
  `repo_count`: počet unikátních registrovaných rep s používaným slotem. Alias a více
  slotů téhož repa se počítají jednou; modified/outdated položky se také počítají.
  Bez knihovny je `data` přesně `{exists: false}`. Bez registru jsou počty nulové;
  čtení registr nezakládá.
- `GET /api/library/items/agent/builder?version=HASH`: soubory s content, binary
  a executable, historie verzí, valid/ issues a `repos` s repo, slotem, verzí a stavem.
  Volitelná version vybírá historické soubory; použití ukazuje současné stavy rep.
  Chybějící repo zůstává řádkem `repo_missing`; bez registru je repos prázdné.

Čtení a plánování nefetchnou knihovnu ani nepřepisují refs. Detail může používat existující
odvozenou core cache historie. Kontrola stroje funguje i při spuštění dashboardu uvnitř git repa.

## Plán a provedení

`POST /api/library/plan` přijímá pouze action a options. Příklady JSON těl:

```json
{"action":"init","options":{"name":"team","remote":"/home/user/team.git"}}
{"action":"clone","options":{"url":"/home/user/team.git","branch":"main"}}
{"action":"import","options":{"path":"my-skills/lint","type":"skill","name":"lint"}}
{"action":"seed","options":{"take":["agent/builder"]}}
```

Init name/remote, clone branch, import name a seed take jsou volitelné; clone url a
import path/type jsou povinné. Typy odpovídají core ITEM_TYPES. Neznámá pole, options,
obsah souborů, target, prostředí ani klientský plán nejsou přijímány.

Plán obsahuje action, normalizované options, library, head, items, files, blockers
(`[{code,message}]`) a API digest. Import/seed zachovávají core plán včetně diffů a jeho
původní digest v `core_digest`. API digest je SHA-256 vázané na akci, volby, cílovou
knihovnu a pozorovaný stav. Warnings, čas ani náhodná UUID jej nemění. URL ve výstupech
neobsahují přihlašovací údaje.

Init je read-only náhled zabaleného seedu a library.yaml; id je výslovně označené jako
vygenerované až při apply. Clone používá read-only `git ls-remote --symref` a ukazuje
vybranou větev a remote_head, bez stažení objektů; validitu library.yaml ověří až core
clone při apply. Init remote musí být prázdné. Tyto dva plány mohou číst vzdálené refs;
GET a kontrola stroje neprovádějí fetch.

Provedení přijímá stejné action/options a digest z odsouhlaseného náhledu:

```json
{"action":"import","digest":"DIGEST_Z_PLANU","options":{"path":"my-skills/lint","type":"skill","name":"lint"}}
```

`POST /api/library/apply` přepočítá plán. Při jiném digestu vrátí HTTP 409
`plan_changed` s aktuálním plánem v data; klient jej znovu zkontroluje a odešle nový
digest. Při shodném digestu a blockeru vrátí HTTP 409 s jeho kódem. Úspěch zachovává
celý CLI výsledek a doplňuje action/reviewed_digest. Pole digest ve výsledku WriteResult
je **core digest**, nikoli API digest. No-op zachovává `committed=false`.

Import relativních cest začíná v uživatelském domově dashboardu, absolutní cesty musejí
ležet pod ním. Platí také původní hranice CLI (`Path.home()`); kontrolují se realpath
včetně vnitřních symlinků. Únik vrací HTTP 403 `outside_home` před čtením zdroje.

`POST /api/library/pull` a `/push` přijímají prázdné tělo nebo `{}` a vracejí celý CLI
výsledek. Pull pouze fast-forward, push nikdy force. Digest pro ně není vyžadován.

## Ochrany a chyby

Plan/apply/pull/push mají globální M1 ochranu Origin, Sec-Fetch-Site a JSON
(`cross_origin` 403, `unsupported_media_type` 415) i kontrolu `stale_code` (409).
Apply/pull/push sdílejí jeden neblokující zámek aplikace: souběžný zápis dostane HTTP
409 `busy`. Zámek se vždy uvolní a po pokusu o core zápis se invaliduje cache stroje,
i když operace selže.

HTTP chyby zachovávají core code/message/data/issues. Neplatné argumenty mají 400,
chybějící detail/položka/verze 404, provozní blokátory 409, odmítnutý push a selhání
fetch/clone/pull 502. `commit_failed` a neočekávaná selhání mají 500.

Core flock `library.lock` zůstává zachován a serializuje i CLI zápisy. Web digest
není atomická ochrana proti externímu CLI mezi přepočtem plánu a získáním core flocku.
Remote také může pokročit během operace; autoritativní fetch, behind/diverged a ochrana
push jsou nadále odpovědností core. Clone preview neověřuje obsah vzdálené knihovny.

## Ověření

Cílené backend testy:

```sh
cd aifactory
uv run pytest tests/web/test_web_library.py tests/web/test_web_machine.py tests/web/test_web_factory.py tests/web/test_web_write_guard.py tests/web/test_web_repos.py
```

Z kořene worktree: `just typecheck` a `just lint`. Testy používají dočasné domovy,
falešné strojové sondy/binárky a lokální bare remotes, bez modelů a sítě. Celou sadu
`just test` spouští následující testovací fáze workflow; builder spouští jen cílené soubory.
