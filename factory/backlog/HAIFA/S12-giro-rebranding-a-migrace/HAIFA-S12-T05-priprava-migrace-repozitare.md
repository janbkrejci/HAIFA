---
id: HAIFA-S12-T05
title: GIRO — připravit nové repo a pořadí obou vydání
status: todo
depends_on: [HAIFA-S12-T03, HAIFA-S12-T04]
writes: [docs/rebranding/, docs/decisions.md]
---

## Zadání

Připrav konkrétní, proveditelný postup v `docs/rebranding/repository-migration.md`.
Výchozí remote je `https://github.com/janbkrejci/HAIFA.git`, nové repo předběžně
`janbkrejci/GIRO`; před použitím ověř skutečný stav a závěry T01.
Původní repo zůstane dostupné s posledním HAIFA vydáním a historickými záznamy.

Hotovo znamená:
- Postup založení nového repo obsahuje přesný zdroj/cíl, přenos Git historie
  a potřebných větví/tagů se zachováním SHA. Staré PR, issues a releasy zůstanou
  v HAIFA; otevřenou práci vyjmenuj a urči její dokončení nebo přenesení.
  Nepřipravuj alternativní přejmenování repo ani hromadný převod starých PR/issues.
- Inventura zahrne visibility, collaborators/teams, default branch, merge
  pravidla, webhooks, Actions permissions, environments, variables, secrets
  a případné registries/Pages. Zapisuj pouze názvy a postupy, nikdy tajné hodnoty.
- Zahrň HAIFA-LIBRARY: buď konkrétní migrace na dohodnutý GIRO název s návazností
  seedů a default URL, nebo zdůvodněná kompatibilní výjimka. Nedělej změny cizího
  repozitáře z tohoto checkoutu.
- Popiš změnu vývojářských remote URL, klonů na dalších strojích a případný přesun
  checkoutu HAIFA → GIRO včetně worktrees, registru továren, cache klíčů, IDE,
  služeb a automatizací. Žádný přesun pod aktivním během nebo dirty worktree.
- Pořadí je nové repo → funkční GIRO release → poslední HAIFA release s alertem
  z uchovaného zdroje T04 → přechod uživatele kliknutím. Dolož konkrétní zdrojový
  commit/ref pro každý bundle, číslování verzí a řízení automatických releases.
  HAIFA bundle se nesmí omylem sestavit z pozdějšího rebrandovaného main.
  Uživatel aplikace nemusí ručně klonovat repo ani měnit remote, aby přešel.
- Popiš návrat při selhání aktualizace a zachování posledního HAIFA releasu
  na staré adrese; automatické vydávání z HAIFA repo po něm skončí.
- Připrav přesný seznam následných změn odkazů, badge, update/library endpointů
  a repo description/topics. Pro T06 nesmí zbýt vágní „přesuň vše potřebné“.

Ověření: příkazy a Git část vyzkoušet v dočasných lokálních repozitářích;
hostingové předpoklady doložit aktuálními oficiálními zdroji/read-only kontrolou.
V tomto tasku se nemění žádný remote, hosting, lokální hlavní checkout ani knihovna.

## Běhy
<!-- doplňuje factory při schválení PR -->
