# Zalamování fází v seznamu běhů

Seznam běhů nyní zalamuje fáze do více řádků v omezeném sloupci. Zůstává dostupná každá fáze i její tooltip při najetí myší nebo zaměření klávesnicí. Dlouhý název tasku se zalamuje včetně slov bez mezer.

Pokud se tabulka nevejde do okna, lze ji vodorovně posouvat uvnitř seznamu. Oblast „Seznam běhů“ lze zaměřit klávesou Tab a posouvat šipkami. Odkazy a akce archivace, vrácení z archivu a mazání fungují stejně jako dříve.

Ovládací prvky horní lišty se na úzké obrazovce zalamují do dalších řádků a zůstávají dostupné uvnitř viewportu.

Regresi pokrývají komponentové testy obou komponent a `tests/e2e/test_runs_overflow_browser.py`. Browser test používá distribuovaný frontend, syntetický běh se 100 fázemi, dlouhý název a viewporty 1366 a 390 px; nepotřebuje běžící backend, model ani externí službu.

Distribuovaný frontend byl aktualizován příkazem `just web-build`. Kontroly `just lint`, `just typecheck`, `just web-test` a `just pytest tests/e2e/test_runs_overflow_browser.py -n0` provádí samostatný testovací krok workflow.
