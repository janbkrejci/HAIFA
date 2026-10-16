# HAIFA-REFINEMENT-T43 — Dropdown chipu necommitnutého backlogu

Červený chip „Necommitnutý backlog“ v horní liště otevírá panel s tlačítkem Commitnout backlog
(`UncommittedBanner.vue`, režim `chip` s `panel`).

- **Obsah panelu:** jen stručná věta „Commitne se N změn.“ (`data-test="backlog-summary"`),
  případný odkaz na pull request (`base_changes: pr`), chyba posledního commitu a tlačítko.
  Seznam souborů ani vysvětlení o base v panelu už nejsou. Banner v stránce (bez `chip`)
  soubory vypisuje dál.
- **Umístění:** panel má `position: fixed`. Po otevření se změří a položí pod chip zarovnaný
  k jeho pravému okraji, ale vždy aspoň 8 px od levého i pravého okraje okna. Znovu se
  počítá při změně velikosti okna a při scrollu. Šířka je podle obsahu, nejvýš 420 px
  a nejvýš šířka okna bez okrajů, takže na úzké obrazovce nepřeteče doleva a tlačítko
  zůstane dostupné.
