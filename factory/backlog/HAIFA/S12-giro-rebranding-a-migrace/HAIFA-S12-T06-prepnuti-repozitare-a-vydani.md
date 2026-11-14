---
id: HAIFA-S12-T06
title: Vydat GIRO v novém repo a potom poslední HAIFA s alertem
status: todo
assignee: human
workflow: null
auto_continue: false
auto_merge: false
depends_on: [HAIFA-S12-T05]
writes: [README.md, AGENTS.md, CLAUDE.md, .github/, .factory/config.yaml, aifactory/, giro/, justfile, docs/rebranding/, docs/decisions.md]
---

## Zadání

Ruční provozní krok vlastníka projektu podle hotového postupu T05 a vydání T04.
Tento task se nespouští jako automatický agentní běh. Konkrétní operace na
hostingu a dalších strojích prováděj až podle ověřeného cíle a postupu návratu.

Hotovo znamená:
- Určeno přesné nové `owner/repo`; ověřena dostupnost a potřebná
  oprávnění. Zálohy, rozpracované PR, běhy a worktrees mají vyřešený stav.
- Nové GIRO repo obsahuje Git historii a potřebná nastavení podle T05;
  oprávnění, ochrany větví, CI a integrace jsou funkční. Původní HAIFA repo
  zůstává na staré adrese, se svými PR, issues a releasy a odkazem na GIRO.
- Provedeny dohodnuté změny knihovny, remotes a případného lokálního umístění.
  Živé provozní soubory nejsou commitnuté; historické task ID zůstávají platné.
- Nejprve zveřejněn a ověřen GIRO bundle v novém repo. Potom z uchovaného zdroje
  T04 vydána poslední HAIFA s alertem „HAIFA se přejmenovává na GIRO“ a akcí
  „Klikněte zde pro přechod“. Dosavadní HAIFA updater toto poslední vydání najde.
- Kliknutí v poslední HAIFA provede upgrade z nového repo, restartuje dashboard
  do GIRO a zachová uživatelská data. Následující update dotaz míří do GIRO repo.
  Po posledním HAIFA vydání je další publikace z původního repo vypnutá.
- Čistá instalace GIRO funguje z nového repo. Aktivní odkazy a popis produktu
  míří na GIRO, historické HAIFA odkazy zůstávají dostupné.
- Do `docs/rebranding/cutover.md` zaznamenej datum, cílové URL, commit/tag,
  výsledky platformních smoke kontrol, stav knihovny, zbývající omezení a návrat.
  Pokud některá platforma není ověřená, výslovně ji označ a neuzavírej T07.

Tento task lze označit hotový až po provedení a doložení migrace; samotný
postup, připravené příkazy ani přejmenovaný adresář jeho dokončení nenahrazují.

## Běhy
<!-- ruční provedení a důkazy doplní vlastník -->
