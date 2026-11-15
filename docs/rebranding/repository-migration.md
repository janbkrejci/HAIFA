# GIRO — provozní postup T06

T05 připravuje postup, nic nepublikuje. T06 jej provede jako vlastník
`janbkrejci`; po každé bráně uloží důkazy do svého cutover záznamu v
`factory/docs/HAIFA/S12-giro-rebranding-a-migrace/HAIFA-S12-T06-prepnuti-repozitare-a-vydani.md`.
Platí [kontrakt T01](giro.md) a [release protokol T04/T02](release.md).
Zdroj je **https://github.com/janbkrejci/HAIFA.git**, cíl
**https://github.com/janbkrejci/GIRO.git**. Vznikne nové samostatné repo;
původní se nepřejmenovává. PR, issues, releasy, diskuse a jejich URL zůstávají
v HAIFA. Git tagy se kopírují, GitHub release objekty a assety nikoli.

## 1. Ověřený výchozí stav a inventura

Read-only kontrola **2026-11-15**, lokální HEAD i vzdálený main
`60224cbf6f98b827b6ed37b58d08346519c889f8` (T03). `git remote -v` uvádí
HAIFA pro fetch i push. GitHub connector ověřil metadata, větve, otevřenou práci,
latest release a rulesets; administrativní endpointy doplnilo autentizované `gh api`.
Connector tyto administrativní inventury nepokrývá. Žádné tajné hodnoty se neukládají.

| Oblast | Zjištěno v HAIFA | Přesný krok T06 v GIRO |
| --- | --- | --- |
| Identita/visibility | `janbkrejci/HAIFA`, public, nearchivované; vlastník User | Znovu GET obou rep; založit prázdné public `janbkrejci/GIRO`, bez README, licence a .gitignore. 404 GIRO je pouze neviditelnost pro kontrolující identitu, není rezervace. Kolize zastaví cutover; vlastník musí potvrdit i kolize značky z T01. |
| Collaborators/teams | `janbkrejci`: admin, `JanKrejciASOL`: write; teams `[]` | Vlastník admin; pozvat `JanKrejciASOL` s write a ověřit přijetí. User repo nemá organizační teams; nezakládat je. |
| Default branch | `main` | Po importu nastavit `main`, ověřit vzdálený HEAD. |
| Merge možnosti | merge commit/rebase/squash povoleny, auto-merge false, update-branch false | Stejné volby, auto-merge ponechat false. |
| Ochrany | rulesets `[]`; main protection 404 „Branch not protected“; všechny níže uvedené větve protected false | Nastavit ochranu main proti force push/deletion a tagové rulesets pro oba přechodové tagy a `v*`. Výjimku k vytvoření release tagů přidělit publikační identitě, nikoli k jejich mazání/přepisu. Uložit export pravidel a vyzkoušet oprávnění před vydáním. Neslibovat required CI checks, které workflow nevytváří. |
| Webhooks | `[]` | Žádné nepřenášet; před cutoverem zopakovat inventuru. Pokud přibyly, zapsat jen jméno/ID/eventy a znovu autorizovat příjemce pro GIRO; signing secret vložit bezpečným kanálem. |
| Actions policy | enabled true, allowed_actions all, sha_pinning_required false | Před prvním pushem **vypnout Actions** v novém repo. Pak obnovit tuto policy; default token read, approve PR reviews false. Workflow má pouze na release jobu contents: write. |
| Environments | `total_count: 0` | Žádné. Pokud nově přibudou, inventarizovat jména, reviewers, wait timer a branch/tag policy, vytvořit ekvivalenty a ověřit vazbu `environment:` jobu. Samotné založení environment release nechrání. |
| Repo variables | `total_count: 0` | V GIRO `GIRO_RELEASE_ENABLED=false`, zapnout až v oddílu 4. V HAIFA zavést `HAIFA_TRANSITION_SHA` a `HAIFA_TRANSITION_PUBLISHED`, podle oddílu 4. Zde jsou uvedena jména a netajné řídicí stavy. |
| Repo secrets | `total_count: 0` | Žádné kopírování. `GITHUB_TOKEN` vytváří hosting pro každý job. Nově potřebné secrets znovu vložit ze správce tajemství, pouze jména do evidence. Nikdy nevypisovat env/config webhooku/tokeny. |
| Pages | GET /pages vrací 404 | Nevytvářet Pages ani měnit DNS. Vlastník ověří Settings → Pages; 404 není univerzální důkaz absence při jiných oprávněních. |
| Registries | Workflow vytváří ZIP s wheelem; nepublikuje PyPI, npm ani container. Účet má kontejnery `fit`, `tsmono-backend`, `tsmono-frontend` | Tyto kontejnery nejsou migrační cíle. V Settings/Packages ověřit associated repository a další registry typy; nepřenášet cizí balíčky. `aifactory` zůstává název distribuce, žádná publikace balíčku `giro`. |
| Git LFS/submodules | `.gitattributes` jen normalizuje LF; žádná sledovaná `.gitmodules` | Zopakovat kontrolu všech přenášených větví na LFS pointers a submodules. Pokud přibyly LFS objekty, `git lfs fetch --all` ve staging clone, `git lfs push --all "$DST"` před otevřením cíle. Submodule URL zachovat, pokud není samostatně schválena změna. |

Opakovat před cutoverem (GET, výstup redigovat, 403/404 nikdy nezaměnit za
prázdný úspěch). Pro `r=janbkrejci/HAIFA`, poté `janbkrejci/GIRO`:

```bash
r=janbkrejci/HAIFA
gh api "repos/$r" --jq '{full_name,visibility,default_branch,allow_merge_commit,allow_rebase_merge,allow_squash_merge,allow_auto_merge,allow_update_branch}'
gh api --paginate "repos/$r/collaborators?per_page=100" --jq '.[] | {login,role_name}'
gh api --paginate "repos/$r/teams?per_page=100" --jq '.[].slug'
gh api "repos/$r/rulesets"
gh api "repos/$r/branches/main/protection"
gh api --paginate "repos/$r/hooks?per_page=100" --jq '.[] | {id,name,active,events}'
gh api "repos/$r/actions/permissions"
gh api "repos/$r/actions/permissions/workflow"
gh api --paginate "repos/$r/environments?per_page=100" --jq '.environments[] | {name,protection_rules,deployment_branch_policy}'
gh api --paginate "repos/$r/actions/variables?per_page=30" --jq '.variables[].name'
gh api --paginate "repos/$r/actions/secrets?per_page=100" --jq '.secrets[].name'
gh api "repos/$r/pages" --jq '{status,html_url,build_type}'
gh api --paginate "repos/$r/pulls?state=open&per_page=100" --jq '.[] | {number,title,head:.head.ref,base:.base.ref}'
gh api --paginate "repos/$r/issues?state=open&per_page=100" --jq '.[] | {number,title,pull_request}'
```

Environment secrets/variables kontrolovat zvlášť po jménech přes
`repos/$r/environments/NAME/secrets` a `.../variables`; pravidla deployment
branch policies přes `.../deployment-branch-policies`. Prověřit také Settings →
GitHub Apps, deploy keys, runners a oprávnění případných externích automatizací;
nové repo není automaticky autorizováno jejich starou instalací.

## 2. Otevřená práce a refy

GET otevřených PR i issues vrátil `[]` (první stránka prázdná, nic dalšího).
Není co hromadně převádět. Před zmrazením znovu stránkovat obě kolekce.
Nově vzniklé PR dokončit v HAIFA **před snapshotem**; pokud to nejde, jejich
větev zachovat v importu, založit jeden konkrétní navazující GIRO PR s odkazem
na původní a starý uzavřít s odkazem zpět. Stejně ručně rozhodnout každé nové
issue; historické objekty se nepřepisují. Výsledek zapsat po číslech do evidence.

Přenést všechny `refs/heads/*` a `refs/tags/*`, včetně annotated tag objektů,
bez rebase, squash nebo filter-repo. Aktuálních devět vzdálených větví:

| Větev | SHA při inventuře | Dispozice |
| --- | --- | --- |
| `main` | `60224cbf6f98b827b6ed37b58d08346519c889f8` | Přenést, pak pokračovat T06 v GIRO. |
| `ci/release-only` | `a6ae7ccf8b900c1d29acf76021fc7ddafc7cb1b4` | Zachovat jako historickou větev, nespouštět starou CI. |
| `codex/fix-macos-process-identity` | `364560a9824dbda63011e2a0755f1904084882af` | Zachovat; nepovažovat samotnou existenci za otevřený PR. |
| `feat/archive-backlog-projects` | `a08bdfc40c2d0dfeef3bb4f8b8d71d52a6d2034f` | Zachovat, bez automatického merge. |
| `fix/codex-guide-isolation` | `accd398d132f1b6177f56637e84a09cbc4114dcc` | Zachovat, bez automatického merge. |
| `fix/obs-cpu-guide-scope-ci-billing` | `68779e1f5ba813a9f19233d5e2b5b24b02327071` | Zachovat, bez automatického merge. |
| `fix/project-chain-and-home-readiness` | `674a10746183da98d64db48da743b906daa8c261` | Zachovat, bez automatického merge. |
| `fix/task-archive-frontmatter` | `669a4d1feca4adf0bdd954dee02c483b9193b196` | Zachovat, bez automatického merge. |
| `perf/large-history-safe` | `42c24029ae5c88431d9fa2c5e10492051f15251d` | Zachovat, bez automatického merge. |

Backlog S12: T01/T04/T02/T03 hotovy; T05 dokončit v HAIFA před snapshotem,
T06 přepne vývoj a vydá oba bundly, T07 ověří přechod již v GIRO. ID a historie
backlogu se nemění. Žádný běžící task ani lokální neodeslaný commit nesmí zmizet:
sepsat `git worktree list --porcelain`, status každého worktree a lokální refs;
neodeslané větve dokončit/odeslat před snapshotem, dirty práci nejprve dokončit.

## 3. Založení a přenos Git historie

T06 nejprve zastaví nové běhy a zápisy vývojářů do HAIFA po dobu snapshotu.
Před vytvořením GIRO ověří vlastníka a souhlas s názvem dle T01, založí repo
v GitHub UI bez inicializačního commitu a ihned vypne Actions. Po dobu importu
nepřidává workflows ani obsah. Pokud cílové repo už obsahuje refy, **zastavit**,
nepřepisovat je. Nastavení hostingu z oddílu 1 se nekopíruje Gitem.

Následující blok spustit v Bashi, v novém izolovaném pracovním adresáři.
Proměnné SRC/DST/MIGRATION_DIR jsou vstupy; výchozí produkční URL jsou níže.
Staging není hlavní checkout, jeho Git konfigurace se nemění. Používají se jen
heads/tags refspecy, aby se nekopírovaly GitHub `refs/pull/*` a nesmazaly cílové
hostingové refs přes `--mirror`. `--atomic` zaručí přenos všech refů nebo žádného;
server bez podpory atomic znamená zastavení.

<!-- migration-git:start -->
```bash
set -euo pipefail
SRC=${SRC:-https://github.com/janbkrejci/HAIFA.git}
DST=${DST:-https://github.com/janbkrejci/GIRO.git}
: "${MIGRATION_DIR:?Zadejte novou absolutni cestu staging adresare}"
test "$SRC" != "$DST"
test ! -e "$MIGRATION_DIR"
mkdir -p "$MIGRATION_DIR"
git ls-remote --refs "$DST" > "$MIGRATION_DIR/destination-before.refs"
test ! -s "$MIGRATION_DIR/destination-before.refs"
git ls-remote --refs --heads --tags "$SRC" | LC_ALL=C sort > "$MIGRATION_DIR/source-before.refs"
git clone --bare "$SRC" "$MIGRATION_DIR/source.git"
git -C "$MIGRATION_DIR/source.git" for-each-ref --format='%(objectname)%09%(refname)' refs/heads refs/tags | LC_ALL=C sort > "$MIGRATION_DIR/snapshot.refs"
cmp "$MIGRATION_DIR/source-before.refs" "$MIGRATION_DIR/snapshot.refs"
git -C "$MIGRATION_DIR/source.git" fsck --full
git -C "$MIGRATION_DIR/source.git" push --atomic "$DST" 'refs/heads/*:refs/heads/*' 'refs/tags/*:refs/tags/*'
git ls-remote --refs --heads --tags "$DST" | LC_ALL=C sort > "$MIGRATION_DIR/destination-after.refs"
cmp "$MIGRATION_DIR/snapshot.refs" "$MIGRATION_DIR/destination-after.refs"
git ls-remote --refs --heads --tags "$SRC" | LC_ALL=C sort > "$MIGRATION_DIR/source-after.refs"
cmp "$MIGRATION_DIR/source-before.refs" "$MIGRATION_DIR/source-after.refs"
```
<!-- migration-git:end -->

`--refs` vynechá pouze odvozené peeled řádky `^{}`; SHA annotated tag objektů
zůstávají v manifestu. Lokální regresní test navíc porovná i peeled SHA.

Po úspěchu ponechat manifesty jako důkaz přesné shody SHA a Git objektů.
Nastavit default `main` a ověřit `git ls-remote --symref "$DST" HEAD`.
Před obnovením Actions zkontrolovat **všechny přenesené workflow větve**:
staré workflow na historických větvích může po pushi/dispatch vydávat.
Povolit provoz jen z main s novým gate, ostatní větve jsou historické a bez
pushů. Na HAIFA se totéž omezení vztahuje i na staré větve/tagy: zrušit queued
staré releasy, omezit zápisy vlastníkem, nikdy nespouštět starý workflow ref.

## 4. Dva zdroje a pořadí vydání

| Bundle | Závazný zdroj | Verze/tag/asset |
| --- | --- | --- |
| Poslední HAIFA H | **`4dd3ddf1ea18f672674123df94dc4643a4868f52`**, T04, budoucí lightweight tag `haifa-transition-source` právě na tomto commitu | `0.1.N`, `v0.1.N`, `haifa-0.1.N.zip` |
| První GIRO G | Nový GIRO `refs/heads/main` po schváleném T06 commitu; jeho SHA před dispatch uložit jako `G_SHA`. Ověřený základ obsahující T02/T03 je `60224cbf6f98b827b6ed37b58d08346519c889f8`, nejde o finální T06 commit. | `1.0.M`, `v1.0.M`, `giro-1.0.M.zip` |

G_SHA není libovolný pozdější main: během prvního vydání držet freeze, před
spuštěním i po doběhu porovnat main SHA, run.head_sha a release tag commit.
Workflow stampuje verzi a update repo pouze v build workspace; wheel proto není
byte-for-byte obsah stromu commitu. Evidovat workflow run ID/attempt/number,
zdrojový SHA, výslednou verzi, asset digest a vnitřní SHA256SUMS. N/M jsou skutečná
`GITHUB_RUN_NUMBER` **daného workflow**, nelze je dnes poctivě předpovědět.
Aktuální latest HAIFA je `v0.1.613`, zdroj
`93518ead08d3c85089b1f907c9219460e454a272`, není to přechodový H.
N musí být > 613 i vyšší než aktuální latest při cutoveru; G je vždy > H.
Pokud run number H tuto podmínku nesplní, zastavit před publikací a upravit
číslovací mechanismus v T06 s testem, nevydat nižší verzi ani posouvat source tag.

Pořadí operací T06:

1. Import dokončen, GIRO main obsahuje schválené změny z oddílu 7, test krok
   ověřil produkt, statiky a relevantní platformy. V HAIFA ověřit
   `git show 4dd3ddf1ea18f672674123df94dc4643a4868f52:.github/workflows/ci.yml`,
   builder, HAIFA UI a statiky. SHA/tag nepřepisovat. Vlastník vytvoří
   `haifa-transition-source` v HAIFA právě na uvedeném SHA; před H jej není
   potřeba dodatečně kopírovat do GIRO. Import již zachoval samotný commit.
2. V GIRO nejprve nastavit `GIRO_RELEASE_ENABLED=false`, obnovit Actions policy
   a ověřit workflow. Pak při zamčeném main nastavit true a spustit
   `gh workflow run giro-release.yml -R janbkrejci/GIRO --ref main`.
   Automatický trigger je pouze push main; přepnutí variable samo push nevytvoří.
   Nenahrazovat dispatch novým prázdným commitem. Po doběhu opět false až do
   ověření G; při souběžném pushi zkontrolovat queued runs a zastavit duplicitní.
3. Zaznamenat G_SHA a G z runu, ověřit tag commit, stabilní non-draft/non-prerelease
   latest, jediný kanonický asset, ZIP kořen, wheel `aifactory`, constraints,
   licence, SHA256SUMS, čistou instalaci a oba entry pointy. Izolovaným přechodem
   z H ověřit restart/registry/rollback dle release protokolu. Teprve funkční G
   dovoluje následující krok. GIRO gate lze po tomto ověření zapnout pro další
   automatické main releasy; během H držet G stabilní.
4. V HAIFA nastavit `HAIFA_TRANSITION_SHA=4dd3ddf1ea18f672674123df94dc4643a4868f52`
   a `HAIFA_TRANSITION_PUBLISHED=false`. Ověřit lightweight tag na přesném SHA,
   nepřítomnost `haifa-transition-published`, aktuální latest G i monotonii H.
   Workflow `ci.yml` s workflow_dispatch musí být přítomen také na default main.
   Spustit **výhradně**
   `gh workflow run ci.yml -R janbkrejci/HAIFA --ref haifa-transition-source`.
   Checkout je schválený SHA, nikdy rebrandingový main. Gate současně kontroluje
   repo, ref, SHA, boolean, dostupné GIRO a verzi; kontrolu opakuje před publikací.
5. Workflow rezervuje jednorázový tag `haifa-transition-published` před draftem.
   Úspěšné H označí latest na staré adrese. Ověřit asset, zdroj tagu, čistý
   legacy upgrade na H a **kliknutí** na „Klikněte zde pro přechod“: GIRO fetch
   míří do nového repo, data a origin dashboardu zůstanou, další update používá
   GIRO. Uživatel aplikace neklonuje repo ani nemění projektové remotes.
6. Nastavit `HAIFA_TRANSITION_PUBLISHED=true`, zakázat `ci.yml` i všechny další
   workflow v HAIFA a nakonec repo Actions. Zachovat oba pojistné tagy, veřejné
   repo, release H jako latest i všechny historické releasy. README/description
   starého repo odkáže na GIRO a vysvětlí H → kliknutí. Repo lze archivovat až po
   uzavření administrativních změn; archivace není podmínka dostupnosti H.

Pokud G selže, HAIFA proměnnou false vůbec nepovolit; vypnout GIRO gate,
opravit G a znovu ověřit. Pokud H selže po rezervaci tagu, **tag nemazat** a
nezkoušet nový run number. Z logu získat původní H, SHA a digest; dokončit týž
draft/tag/asset ručně. Pokud nebyl draft vytvořen, použít ověřený artefakt
původního runu nebo reprodukovat build stejného SHA a stejného run number v
izolaci; nedostupný artefakt znamená nejprve obnovit tento build, nevydat jiný H.
Před odemčením zápisů zkontrolovat, že žádný starý queued run nemůže publikovat.

## 5. Knihovna jako kompatibilní výjimka

`janbkrejci/HAIFA-LIBRARY` je public, nearchivovaná, default main, auto-merge false.
Zůstává **https://github.com/janbkrejci/HAIFA-LIBRARY.git**. T01 záměrně zachovává
UUID knihovny, existující klony/forky/PR a `skill/factory`; změna názvu by přidala
riziko bez přínosu pro klikací upgrade. `GIRO_LIBRARY_URL` i alias
`HAIFA_LIBRARY_URL` nadále mohou volit firemní knihovnu. Default v
`aifactory/src/aifactory/library/share.py`, návodech a instalátorech zůstává.
Seeds agentů/workflow a generovaný `giro --skill` nadále dodávají položku
`skill/factory`; `.factory/` overrides mají přednost. Přechod nepoužívá
`library seed --all`; nedestruktivní plán zachová `kept` a dirty knihovnu.

T06 ve vlastním checkoutu knihovny pouze případně upraví aktivní README/popisek
na „Shared library for GIRO (HAIFA compatibility)“, zachová URL, library.yaml,
min_factory_version a všechny historické reference. Žádné změny této knihovny
z checkoutu HAIFA/GIRO. Předem read-only zopakovat inventuru nastavení jako
v oddílu 1; nic nekopírovat na neexistující GIRO-LIBRARY.

## 6. Vývojářské klony a volitelný přesun checkoutu

Nejbezpečnější je ponechat cestu `/Users/jbk/Documents/HAIFA` a měnit jen remote.
Po dokončení běhů, clean status všech worktrees a odeslání lokální práce, v každém
samostatném klonu na macOS/Windows/Linux provede jeho vlastník:

```bash
git remote -v
git worktree list --porcelain
git status --porcelain=v1 --untracked-files=all
git remote rename origin haifa-history
git remote add origin https://github.com/janbkrejci/GIRO.git
git fetch origin --prune
git branch --set-upstream-to=origin/main main
git remote -v
```

Předem ověřit, že `haifa-history` neexistuje a origin opravdu ukazuje do HAIFA;
jinak zastavit a opravit mapování podle konkrétního klonu. Pro každou zachovanou
vývojovou větev nastavit upstream `origin/<stejná-větev>` a zkontrolovat
`remote.pushDefault`, `branch.*.pushRemote` a případné pushurl (nesmějí dál
posílat do HAIFA). SSH uživatelé použijí `git@github.com:janbkrejci/GIRO.git`.
Origin je sdílená Git konfigurace všech worktrees jednoho klonu; ostatní klony
na dalších strojích potřebují vlastní změnu. `haifa-history` zůstane read-only
konvencí a serverovými oprávněními; nepřepisovat historické tagy po dalších fetch.

Přejmenování složky HAIFA → GIRO není potřeba pro produkt ani aktualizaci.
Pokud jej vlastník chce, provést jako oddělenou odstávku až po migraci a záloze:

1. Zastavit dashboard, tasky, workers, scheduled jobs, IDE terminály, launchd/
   systemd/Windows Task Scheduler a všechny procesy používající checkout nebo
   `.factory/`. Neznámý aktivní stav či jediný dirty worktree přesun blokuje.
   Zálohovat celý main i linked worktrees, společný Git dir, home registry,
   `.factory/data`, externí DB, lokální nastavení a absolutní cesty automatizací.
2. Uložit mapu old→new absolutních cest každého worktree z
   `git worktree list --porcelain`. Hlavní worktree s `.git` adresářem nepřesouvat
   přes `git worktree move`; po ukončení procesů jej přesunout filesystemem,
   v novém main spustit `git worktree repair`. Linked worktrees mimo main lze
   přesunout `git worktree move OLD NEW`; pro vnořené `.factory/worktrees`, které
   se přesunuly s main, spustit v novém main `git worktree repair NEW1 NEW2 ...`
   s konkrétními cestami z mapy. Ověřit common-dir, gitdir a clean status každého.
3. V zastaveném systému v `dashboard.yaml` změnit pouze path/name záznamu při
   zachování ID, added_at a library rules; neprovádět remove/add registraci.
   `repositories/<key>.json` v home používá SHA256 kanonického common Git dir
   (`repo_settings.repository_identity`): po přesunu se klíč změní. Zachovat
   původní auto-merge/auto-continue/harness pod novým klíčem; JSON obsahuje
   pouze `version`, `auto_merge`, `auto_continue`, `harness`, nepřidávat identity; neaktivovat automatiky během validace.
   Záloha původních souborů zůstane mimo aktivní adresář. Pouhá změna remote
   tento klíč nemění. Explicitní GIRO_FACTORY_REPO zůstává stejné registry ID.
4. Prověřit absolutní cesty uvnitř `.factory/` konfigurace, runtime záznamů,
   journalu `<git-common-dir>/haifa`, DB, env a vlastních skriptů. Historické běhy
   a trace nepřepisovat plošně; pokud některý aktivní odkaz nelze bezpečně opravit,
   přesun zrušit a vrátit původní cestu. `.factory/` a common-dir `haifa` neměnit.
   Build/mypy cache navázané na absolutní cestu lze znovu vytvořit; knihovní
   cache `cache/library/<type>/<name>.json` není repo klíč, zachovat její identitu.
5. Opravit IDE workspace/project paths, shell cwd/bookmarks, CI working-directory,
   lokální shortcuts, launchd ProgramArguments/WorkingDirectory, systemd
   WorkingDirectory/ExecStart, Windows task action/start-in, zálohovací skripty
   a plánované automatizace. Stejně aktualizovat explicitní checkout cesty ve
   všech ostatních strojích; home přesouvá produktový protokol, nikoli tento krok.
6. Spustit jeden dashboard na stejné adrese, ověřit všechna registry ID, historii,
   lokální volby a worktrees, pak obnovit služby a automatiky. Při chybě znovu
   zastavit procesy, obnovit původní složky, opravit Git vazby opačným směrem a
   obnovit registry/nastavení ze zálohy; nedržet aktivní dvě registrace téhož repa.

## 7. Přesná mapa změn T06

T06 před G upraví a ověří následující řádky. Kontrolní inventuru provede
`rg -n 'janbkrejci/(HAIFA|GIRO)|api.github.com/repos|badge' README.md aifactory .github docs`.
Každý zbylý aktivní legacy endpoint musí odpovídat explicitní výjimce níže.

| Místo | Změna / cílová hodnota | Ověření |
| --- | --- | --- |
| GIRO `README.md`, `aifactory/README.md`, guide `02-instalace.md` i `en/02-instalace.md` | Nahradit dočasné „získáš od správce / až po T06“ funkčním `https://github.com/janbkrejci/GIRO/releases/latest`; konkrétní G asset `https://github.com/janbkrejci/GIRO/releases/download/vG/giro-G.zip` (G nahradit skutečnou verzí). | HTTP, čistá instalace dle obou jazyků; nepublikovat odkazy jako funkční před G. |
| Aktivní repo/clone/source/support odkazy, repo description/homepage/topics | GIRO `https://github.com/janbkrejci/GIRO`, clone `.git`, issues `/issues`; description `GIRO — Goal in. Release out.`, topics `giro`, `ai-agents`, `developer-tools`, `automation`; homepage jen existující GIRO README, žádná fiktivní doména. | GET metadata/topics; ručně projít odkazy. |
| Badge, pokud je T06 přidá nebo nalezne při nové inventuře | Inventura aktivních README nenašla badge. Release badge `https://img.shields.io/github/v/release/janbkrejci/GIRO` → GIRO latest; Actions badge `https://github.com/janbkrejci/GIRO/actions/workflows/giro-release.yml/badge.svg` → stejný workflow bez `/badge.svg`. | SVG a cílová stránka fungují; badge nesmí tvrdit PR test gate. |
| `aifactory/src/aifactory/web/updates.py`, `environment.py`, `bundle/release.py`, GIRO workflow | Ověřit již implementovaný GIRO default `janbkrejci/GIRO`, API `https://api.github.com/repos/janbkrejci/GIRO/releases/latest`, kanonický `/releases/download/vG/giro-G.zip`, ignorování přesného legacy HAIFA override; firemní override zachovat. | Další update po kliknutí používá GIRO, fake-host regresní testy T02/T04. |
| Uchovaný T04 updater / starý HAIFA latest | Beze změny `https://api.github.com/repos/janbkrejci/HAIFA/releases/latest` a `haifa-H.zip`; migrační akce má pevné GIRO repo. Starý README odkaz na nový vývoj a poslední H; description
   `HAIFA — historical repository; development moved to janbkrejci/GIRO`,
   topics `haifa`, `giro`, `migration`, homepage `https://github.com/janbkrejci/GIRO`. | Starší klient najde H, alert kliknutím najde G. |
| `.github/workflows/giro-release.yml`, `ci.yml`, host settings | GIRO main gate + proměnná; starý H dispatch jen z uchovaného refu a po něm všechny Actions HAIFA disabled. Žádný release ze starých vývojových větví. | Run SHA, gate, zdrojový tag a asset evidence z oddílu 4. |
| `library/share.py`, `bundle/install.sh`, `bundle/install.ps1`, guide CS/EN, skill text a seedy | Ponechat `https://github.com/janbkrejci/HAIFA-LIBRARY.git`, `skill/factory`, `haifa-library/` a `.git/haifa-pull-requests.json`; aktivní název produktu GIRO. | Existující i nový library clone, zachování UUID/PR/kept dat. |
| `.factory/config.yaml`, AGENTS/CLAUDE, generovaný skill, home env a developer automatizace | Zkontrolovat případné repo URL a aktivní návod podle konkrétních výskytů; registry ID, task prefixy, `.factory/`, `factory/`, aifactory a provozní aliasy neměnit. Regenerovat distribuovaný skill ze stejného GIRO zdroje, ne runtime kopie. | Žádný aktivní publikační endpoint HAIFA mimo H; ostatní stará URL jsou historické nebo knihovní. |
| Historické docs, backlog, PR/issues, release notes, licence, THIRD_PARTY_NOTICES | Zachovat přesné historické HAIFA URL a původ. Kopie tagu není přesun starého GitHub release objektu. | Staré odkazy zůstávají dostupné v původním public repo. |

## 8. Návrat uživatele a cutover evidence

Síťová/checksum chyba před instalací nic nezmění. Po selhání instalace či restartu
koordinátor podle [release protokolu](release.md) zachová nový stav, obnoví
software H i všechny zálohované datové cesty a spustí HAIFA na původní adrese
s konkrétní chybou a možností opakovat kliknutí. Výpadek stroje vyžaduje obnovu
z plánu a kontrolních součtů; marker se nemaže jako obcházení ochrany. Zálohy
ani starý release se automaticky nemažou. Nebezpečný G se při zastavených zápisech
nahradí opraveným G; vrácení endpointu GIRO na HAIFA není rollback.

T06 uloží: datum/operátora a potvrzení cíle i značky, inventuru s HTTP statusy,
seznam otevřené práce a její dispozice, manifesty refů před/po, nastavení hostingu,
source H SHA/tag, G_SHA, H/G čísla/tagy/run ID/attempt, ZIP digest + SHA256SUMS,
výsledky čisté instalace, kliknutí, dalšího update a návratu na podporovaných
platformách, stav pojistných tagů, disabled Actions HAIFA a mapu vývojářských
klonů/služeb. Zapsat také datum prvního stabilního G a nejdřívější konec aliasů
(maximum z major 2 a 12 měsíců, navíc 90denní upozornění podle T01).

## 9. Ověření postupu v test kroku

`verify_repository_migration.py` spouští **přímo Git blok z tohoto dokumentu**
v dočasných lokálních repozitářích bez GitHubu. Ověří dvě větve, lightweight i
annotated tag, shodu objektových i peeled SHA, nedotčený zdroj a odmítnutí
neprázdného cíle i shodného source/destination. Tester spustí:

```bash
python3 docs/rebranding/verify_repository_migration.py
```

Builder tento samostatný workflow test krok nenahrazuje. Hostingové mutace ani
skutečné vydání nejsou součástí testu. Tester dále zkontroluje dokumentované
příkazy proti aktuálním workflow a povinné projektové lint/typecheck v samostatném
gate; žádný produktový kód ani obrazovka se v T05 nemění.

## 10. Oficiální hostingové podklady

Ověřeno 2026-11-15. [GitHub: duplicating a repository](https://docs.github.com/en/repositories/creating-and-managing-repositories/duplicating-a-repository)
popisuje bare clone, přenos historie do nového repa a zvláštní přenos LFS;
zde je rozsah zúžen na heads/tags s ověřením manifestů.
[REST repository metadata](https://docs.github.com/en/rest/repos/repos)
je podkladem kontroly cílového repa a jeho nastavení.

[Manually running a workflow](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
dokládá požadavek workflow_dispatch i přítomnosti workflow na default branch.
[Actions permissions](https://docs.github.com/en/rest/actions/permissions)
dokládá samostatnou správu povolených Actions a token policy; Git import tato
nastavení nekopíruje.

Inventuru oddělených hostingových objektů opírají oficiální API pro
[webhooks](https://docs.github.com/en/rest/repos/webhooks),
[environments](https://docs.github.com/en/rest/deployments/environments),
[variables](https://docs.github.com/en/rest/actions/variables) a
[secrets](https://docs.github.com/en/rest/actions/secrets). U secrets se čtou pouze
metadata, jejich hodnoty se nezískávají ani neexportují.
[Packages API](https://docs.github.com/en/rest/packages/packages) rozlišuje registry
a přístupová oprávnění; seznam kontejnerů účtu není důkaz absence jiných balíčků.
