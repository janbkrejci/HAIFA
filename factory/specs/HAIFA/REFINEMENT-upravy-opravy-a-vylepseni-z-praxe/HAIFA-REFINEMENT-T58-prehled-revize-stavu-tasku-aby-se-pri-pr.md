# HAIFA-REFINEMENT-T58: souvislé zobrazení stavu tasku

Přehled a kanban odvozují stav ze stejného read-only snapshotu `task_runs` a
`task_prs`. Stav pro zobrazení není vstupem do plánování ani výpočtu kapacity.
Zůstávají stávající `BOARD_STATES`.

- Nejnovější úspěšný běh bez PR své větve a bez `pr_error` je `running`, dokud
  nevznikne PR nebo se backlog nezmění na `done`. Starší úspěch nepřekryje novější
  chybu či zastavení. Existující uzavřené PR samo nezpůsobuje čekání na publikaci.
- Nejnovější PR `merged` znamená pro dosud neuzavřený task `done`, pokud task
  neobsahuje záznam tohoto PR v historii (`has_entry`, stejně jako `_merged_outside`).
  Aktivní nový běh má přednost. Explicitní `done` a `cancelled` mají nejvyšší prioritu.
- Pokud starší trace DB nemá `branch`, úspěšný běh s neznámou větví nepřekryje
  známé sloučení čekáním na publikaci. Bez historie PR je task `done`, po záznamu
  stejného PR a znovuotevření `ready`; skutečný řádek `running` má nadále přednost.
- Nevyčištěný řádek `running` zůstává v obou pohledech `running`; Přehled zachovává
  informaci „proces skončil“. Samotné čtení kanbanu neprovádí reap běhů.
- Přehled zahrnuje čekání na publikaci i do seznamu `running`. Kontrola změny
  souboru tasku s úspěšným během nebo mergnutým PR obnoví cache backlogu před TTL,
  tedy i při dokončení bez PR a při znovuotevření tasku.
- `Slots`, `free_slots`, `factory.ready`, `can_start` a auto-continue zachovávají
  dosavadní výpočet. Počty chipů popisují stav zobrazení.

Revize přechodů a omezení zjistitelných dat jsou v dokumentaci stejného tasku;
tabulka je současně součástí popisu PR. Předzápisové spuštění a opakovaná publikace
s dosud uloženým `pr_error` vyžadují změny launcheru/procesů mimo povolené zápisy
tohoto tasku a jsou předány navazujícím taskem v reportu.
