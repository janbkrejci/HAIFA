# HAIFA-S90-T01 — OB1: R1 se třemi harnessy (claude, codex, pi)

## Cíl
Ověřit riziko R1 (jeden workflow `simple-sdlc` přes tři harnessy: plan na claude,
build/fix/revise na codexu, review na pi) skutečným během
`just validate --remote github --roster <roster>` tak, aby `R1.json` mělo `outcome: passed`,
a výsledky z githubu commitnout do `aifactory/validation/results/`.

Předpoklady ze zadání jsou splněné v backlogu: HAIFA-S05-T05 (nativní načítání
kontextu a skillů) je `done`, OB5 (HAIFA-S90-T05) je `done` a vybral model pi
`nous-portal-api-key/meituan/longcat-2.5-preview:free` (roster `pi-longcat`,
běh 2026-10-08 bez `failed`). Kredit na codex ověří až preflight (`factory harness check`).

Jde o validaci, ne o změnu produktu. Kód v `aifactory/src/` se nemění.

## Povolené cesty
`aifactory/`, `justfile`, `specs/HAIFA-S90-T01-ob1-r1-se-tremi-harnessy.md`,
`app_docs/HAIFA-S90-T01-ob1-r1-se-tremi-harnessy.md`. Nic jiného neměň.
Pozor: `docs/decisions.md` v tomto worktree NENÍ (v hlavním checkoutu je `docs/`
netrackované) a není v povolených cestách. Viz krok 5.

## Krok 1 — nový roster `aifactory/validation/rosters/claude-codex-pi/`
Vzor: `aifactory/validation/rosters/pi-longcat/` a šablona
`aifactory/validation/template/.factory/`.

1. `aifactory/validation/rosters/claude-codex-pi/agents.yaml`:
   ```yaml
   # Agent roster claude-codex-pi for `just validate --roster aifactory/validation/rosters/claude-codex-pi`.
   #
   # OB1 (HAIFA-S90-T01): R1 over three harnesses in one workflow. Planner and
   # documenter on claude, builder on codex, reviewer on pi with the model chosen
   # in OB5 (longcat 2.5 preview, roster pi-longcat). The workflow
   # workflows/simple-sdlc.yaml names the harness of every step. The prompts (and
   # the validation rule of the reviewer) stay those of the template.
   defaults:
     thinking: low

   agents:
     - name: planner
       harness: claude
       model: sonnet
       purpose: Turn the task into a short plan the builder can follow.
       writes:
         - specs/

     - name: builder
       harness: codex
       model: gpt-5.5
       purpose: Implement the plan exactly; report every changed file.

     - name: reviewer
       harness: pi
       model: nous-portal-api-key/meituan/longcat-2.5-preview:free
       purpose: Confirm that what was built is what was asked for; change nothing.
       writes: []

     - name: documenter
       harness: claude
       model: haiku
       purpose: Write up the change from the diff; document only.
       writes:
         - app_docs/
   ```
   Model pi zkopíruj přesně z `rosters/pi-longcat/agents.yaml` (`defaults.model`),
   model codexu přesně ze šablony (`template/.factory/agents.yaml`, builder).

2. `aifactory/validation/rosters/claude-codex-pi/workflows/simple-sdlc.yaml`:
   kopie `aifactory/validation/template/.factory/workflows/simple-sdlc.yaml`
   (`cp`), jen hlavičkový komentář uprav na roster claude-codex-pi
   (plan claude, build/fix/revise codex, review pi, document claude). Struktura
   kroků a `harness:` musí zůstat shodná se šablonou.

3. `aifactory/validation/README.md`: v odstavci k `--roster` přidej druhý příklad
   `just validate --remote github --roster aifactory/validation/rosters/claude-codex-pi`
   (R1 i R10 ověřitelné: claude, codex i pi). Jedna věta, česky.

Ověření kroku (bez sítě, zdarma):
```
just validate --remote local --roster aifactory/validation/rosters/claude-codex-pi --only R1
```
Kód 0 a R1 `passed` (falešný harness, ale harness_per_step z rosteru musí pokrýt
claude, codex i pi). Lokální výsledky git ignoruje (`results/*/local-*/`).

## Krok 2 — preflight
```
gh auth status
echo "$HAIFA_SANDBOX_REPO"       # musí být nastavené (shell nebo .env v kořeni HAIFA)
cd aifactory && uv run factory harness check   # claude, codex i pi
pi --list-models | grep longcat  # model z rosteru musí existovat (OB5: F2 napoprvé selhal na „model nenalezen“)
```
Když preflight selže (chybí sandbox, `gh`, codex bez kreditu / nepřihlášený, pi model
chybí): NIC nevymýšlej a neobcházej. Ukonči s neúspěchem a v reportu napiš, co
chybí (validace pak vrátí kód 2). Výsledek R1 nesmí být fingovaný.

## Krok 3 — běh na githubu
Z kořene worktree:
```
just validate --remote github --roster aifactory/validation/rosters/claude-codex-pi
```
(Celý běh dle Done means: 13 běhů simple-sdlc + resolve; R1 jde první. R10 se tím
s codexem ověří také — bonus, ne podmínka. Když je potřeba šetřit, přípustný je
`--only R1`, ale Done means cituje celý příkaz, preferuj ho.)
Běh trvá dlouho — pusť ho na pozadí s dlouhým timeoutem a počkej na dokončení.

Vyhodnocení podle souboru, ne podle textu výstupu:
`aifactory/validation/results/<YYYY-MM-DD>/github-<HHMMSS>/R1.json` → `"outcome": "passed"`.
Zkontroluj i `summary.json`: `roster` ukazuje na claude-codex-pi a `harness_per_step`
má plan=claude, build/revise_1=codex, review_1/review_2=pi.

- R1 `inconclusive` kvůli reviewerovi, který schválil hned napoprvé (pravidlo
  haifa-validate): opakuj běh jednou (`--only R1`). Pořád inconclusive → report jako neúspěch s detailem.
- R1 `failed`: přečti `checks`/`observations` v R1.json a `logs/`. Pokud jde o
  chybu rosteru (model, název), oprav roster a opakuj. Pokud jde o chybu produktu,
  produkt neopravuj (mimo rozsah) — skonči neúspěchem, popiš příčinu a navrhni task.
- Ostatní scénáře (`failed` jinde) nejsou podmínkou tohoto tasku, ale uveď je v app_docs.

## Krok 4 — výsledky do repa
Adresář `aifactory/validation/results/<datum>/github-<čas>/` nech v pracovním stromu
(trace/ a logs/ git ignoruje, `R*.json`, `summary.json` atd. se commitují).
Necommituj — commit dělá workflow. Zbytečné/opakované neúspěšné github běhy
smaž, ať v repu zůstane jen platný běh (nebo ponech a zmiň v app_docs; preferuj
ponechat jen ten s R1 passed).

Úklid na GitHubu podle README („Úklid po běhu na GitHubu“): zavři zbylé PR
(`gh pr close`) a smaž větve `factory/*`, `factory-sync/*`, `haifa-validate/<stamp>`
v sandboxu. Dělej to jen v sandbox repu `$HAIFA_SANDBOX_REPO`, nikdy v HAIFA repu.

## Krok 5 — zápis v docs/decisions.md (mimo povolené cesty)
`docs/decisions.md` je jen v hlavním checkoutu jako netrackovaný soubor a do
povolených cest nepatří — builder ho NEMĚNÍ. Do app_docs (a do reportu pro
operátora) dej hotový řádek k vložení do tabulky v `docs/decisions.md`, ve stylu
existujícího řádku `F2 core a CLI`:

`| OB1 R1 se třemi harnessy | <YYYY-MM-DD> | \`aifactory/validation/results/<datum>/github-<čas>\`, roster \`claude-codex-pi\`: R1 \`passed\` (plan claude, build a revise codex, review pi). R1 je ověřený. <stav R10 a ostatních scénářů> |`

## Krok 6 — dokumentace
`app_docs/HAIFA-S90-T01-ob1-r1-se-tremi-harnessy.md` (česky, krátce): roster a
proč tyhle modely, přesný příkaz, cesta k výsledkům, výsledek každého scénáře,
`harness_per_step` R1, náklady/tokeny z `measurements` R1, řádek pro decisions.md
z kroku 5, a úklid na GitHubu.

## Kontrola na konec
- `git status` ukazuje jen povolené cesty: nový roster, README validace, adresář
  výsledků github, spec, app_docs.
- `just test` (validace má test `tests/validation/test_validation_local.py`) projde;
  roster nezměnil šablonu.
- R1.json z github běhu má `outcome: passed`.
