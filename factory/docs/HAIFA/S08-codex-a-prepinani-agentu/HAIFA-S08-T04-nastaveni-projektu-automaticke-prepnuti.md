# Automatické přepnutí harnessu při vyčerpání kvóty: řetěz a návrat

Projekt může určit, na které harnessy a v jakém pořadí se jeho běhy přepnou, když harness
vyčerpá kvótu (selhání `quota`). Může také určit, jestli se běhy vrátí zpět, až má harness
výš v řetězu zase limit.

## Klíče v `index.md` projektu

```yaml
quota_switch: [claude, pi]   # záložní harnessy v pořadí; [] nebo nezadáno = vypnuto
quota_switch_back: true      # vrátit zpět při obnovení limitu (výchozí false)
```

- Oba klíče smí nastavit jen projekt (kontejner nejvyšší úrovně), stejně jako `harness`,
  `model` a `thinking`. Na kroku je editace odmítne s `invalid_value` („harness settings
  are only allowed on a project“). Tasky projektu je dědí.
- `quota_switch` je seznam známých harnessů (`claude`, `codex`, `pi`; alias `claude_code`
  se uloží jako `claude`). Žádný se nesmí opakovat. Neznámý harness nebo duplicita dají
  `invalid_value`. Hodnota, která není seznam řetězců, je v kontrole backlogu
  `invalid_field`.
- Bez hodnoty platí výchozí `quota_switch: []` a `quota_switch_back: false` s původem
  `výchozí`.

Řetěz běhu je `[harness projektu, *quota_switch]`. Harness projektu je ten, na který by
běh šel bez řetězu: `harness` z backlogu, jinak výchozí harness počítače, jinak harness
rosteru. Když je harness projektu v `quota_switch` také, v řetězu je jen jednou, na začátku.

## Nastavení v dashboardu

V Backlogu otevři projekt a jeho **Nastavení**. Řádek „Automaticky přepnout harness při
vyčerpání limitu tokenů“ (`quota_switch`):

- „Zdědit“ zaškrtnuté znamená bez vlastní hodnoty, tedy výchozí vypnuto.
- Bez „Zdědit“ je tu přepínač **Zapnuto** a pod ním řetěz harnessů. Harness se přidá
  výběrem, pořadí se mění šipkami ↑ ↓ a ✕ ho odebere. Nabízejí se jen harnessy povolené
  a dostupné na tomto počítači (stejný zdroj jako výběr harnessu projektu), bez těch, které
  už v řetězu jsou, a bez harnessu projektu.
- Zapnutý přepínač bez harnessu nejde uložit (hláška „vyber aspoň jeden harness“). Vypnutý
  přepínač uloží `quota_switch: []`.

Řádek „Vrátit zpět při obnovení limitu“ (`quota_switch_back`) je přepínač Zděděno /
Zapnuto / Vypnuto, stejně jako Auto continue. Platná hodnota ukazuje řetěz jako
`claude → pi`.

## CLI a API

```sh
factory backlog edit M01 --quota-switch claude pi --quota-switch-back on --json
factory backlog edit M01 --quota-switch --json          # [] = vypnuto
factory backlog edit M01 --clear quota_switch quota_switch_back --json
```

API: `POST /api/backlog/containers/{id}/edit` s `{"quota_switch": ["pi"], "quota_switch_back": true}`.
`null` nebo `clear` klíč odstraní. `GET /api/backlog/containers/{id}` vrací oba klíče
v `editable_keys` jen u projektu. Jako u ostatních klíčů backlogu se změna zapíše do
pracovního stromu a běhy ji použijí až po commitu backlogu do base.

## Přednost oproti `fallback`

1. Neprázdný řetěz projektu (`quota_switch`). Platí pro celý běh a `fallback`
   z `local.yaml` ani z `agents.yaml` se v něm nepoužije.
2. Bez řetězu projektu funguje záloha jako dřív, zkusí se jednou: `fallback`
   v `.factory/local.yaml`, pak `fallback` agenta v `.factory/agents.yaml`, pak
   `defaults.fallback`.

`auto_heal: false` vypne obojí.

## Průchod řetězem

Při selhání `quota` pokračuje běh (jako pokus téhož běhu, `retry_run`) na dalším
harnessu řetězu za tím, který kvótu vyčerpal. Vynechá harness, na kterém už tento běh
byl, a harness, o kterém počítač ví, že kvótu ještě nemá. Když dojde kvóta i jemu,
pokračuje se dál v pořadí. Když dojde celý řetěz, běh skončí selháním `quota` s varováním
`quota: chain of project <ID> exhausted`. Přepnutí na operátorův harness (**Pokračovat
s jiným harnessem**) a přepnutí na `fallback` se dál nikdy nepřepnou znovu.

## Stav kvóty a místo projektu v řetězu

Obojí je stav tohoto počítače v trace DB (`.factory/trace.db`) a nepotřebuje commit:

- `harness_quota`: harness, který vyčerpal kvótu, a čas `retry_at`, kdy ji může mít zpět.
  Zapíše ho každé selhání `quota`, i bez řetězu. Čas se vezme z hlášky harnessu (`try
  again in 3 days`, `in 45 minutes`, `resets 3pm (Europe/Prague)`, tedy nejbližší 15:00 v té
  zóně, u neznámé zóny v místním čase). Jinak platí za hodinu. Úspěšný běh záznam svého
  harnessu smaže.
- `project_harness`: harness řetězu, na kterém projekt právě je. Po přepnutí v řetězu se
  posune na nový harness, takže další běhy projektu začínají tam. Bez záznamu začínají na
  harnessu projektu.

## Návrat při obnovení limitu

Se zapnutým `quota_switch_back` začne nový běh o krok výš v řetězu, jakmile má ten harness
zase limit (nemá záznam v `harness_quota`, nebo jeho `retry_at` už minul). Další nový běh
jde zase o krok výš, až zpět k harnessu projektu (pak se záznam projektu smaže). Bez
návratu zůstávají nové běhy na harnessu, kde projekt je.

Vrací se jen na začátku nového běhu (`factory task run`, auto-continue), nikdy mezi fázemi
běhu ani při ručním pokračování (`factory task retry`). Agent na jiném harnessu přijde
o svou session agenta a pokračuje jen ze shrnutí a z `context_handoff/`. Přepnout uprostřed
běhu proto má smysl jen tehdy, když aktuální harness pokračovat nemůže. Běh startu
`resolve` a `ci-fix` řetěz nepoužívá.

## Kde je přepnutí vidět

- Přepnutí během běhu: `retries[].harness_switch` (zdroj `projekt <ID> (quota_switch)`),
  pokusy v detailu běhu, události fáze `request` a popis PR (sekce „Přepnutí harnessu“).
- Start běhu na jiném harnessu: sloupec `task_runs.harness_start` a `harness_start`
  v detailu běhu (API i dashboard, řádek „Start“), důvod `quota` (projekt je níž
  v řetězu) nebo `quota_return` (návrat, v textu „návrat (limit obnoven)“). V popisu PR
  je řádek `běh <id>, start: …` před pokusy toho běhu. Poznámka běhu nese
  `[přepis rosteru: harness=…]`, takže ruční pokračování zůstane na stejném harnessu.
