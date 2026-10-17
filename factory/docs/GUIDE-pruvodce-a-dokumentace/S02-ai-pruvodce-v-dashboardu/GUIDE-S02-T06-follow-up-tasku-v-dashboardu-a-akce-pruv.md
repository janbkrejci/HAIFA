# Follow-up hotového tasku v dashboardu a od průvodce

Hotový task se znovu nespouští ani neupravuje. Když je potřeba něco změnit, předělat nebo
dodělat, založí se nový task, který na něj navazuje. Dashboard i AI průvodce to dělají
stejně jako `factory task follow-up ID --body TEXT [--title TEXT] [--run]`.

## V detailu tasku

- Hotový task má tlačítko **Navázat follow-upem**. Formulář chce zadání (co změnit,
  předělat nebo dodělat), volitelně titulek (výchozí „Navazuje na ID: titulek“) a volbu
  **Commitnout a spustit** (zapnutá).
- Nový task vznikne ve stejném stepu, dostane `follows: ID` a převezme vlastní `writes`
  a `workflow` původního tasku. Co původní task dědil od stepu nebo projektu, nový dědí
  taky.
- S volbou **Commitnout a spustit** se backlog commitne do base a nový task se hned
  spustí. Bez ní se task jen založí a backlog se commitne.
- Detail ukazuje, na který task task navazuje („Navazuje na“), a seznam tasků, které na
  něj navazují („Navazují na něj“), obojí s odkazy.

## Od průvodce

- Průvodce může navrhnout akci `follow_up` (task, zadání, volitelně titulek a spuštění).
- Karta ukáže titulek nového tasku, převzaté writes a workflow, zadání a co se stane po
  založení. U tasku, který není hotový, karta upozorní, že ho navázat nejde.
- Teprve **Provést** task založí, přes stejné API jako tlačítko v detailu. Bez
  potvrzení se nic nezapíše. Když spuštění chybí, task se jen založí a backlog zůstane
  necommitovaný (jako `factory task follow-up` bez `--run`).

## Omezení

- Navázat jde jen hotový task; jiný stav server odmítne (`not_done`).
- Převezmou se jen writes a workflow uvedené přímo u původního tasku, ne vazby
  ani parametry harnessu.
