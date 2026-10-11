# HAIFA-S07-T06: Uživatelská a administrační příručka

- Příručka je v balíčku jako české markdown kapitoly `aifactory/src/aifactory/guide/<NN>-<id>.md` (úvod, instalace, první spuštění, dashboard, backlog, běhy, review, konfigurace repa, agenti a workflow, knihovna, počítač a harnessy, tým, aktualizace, CLI, řešení problémů). `aifactory.guide.chapters()` je řadí podle čísla, titul je první `# ` nadpis.
- Dashboard: `GET /api/guide` (jedno- i víceprojektová aplikace) vrací všechny kapitoly; stránka `#/guide[/<kapitola>[/<sekce>]]` (`GuideView.vue`) má seznam kapitol se sekcemi otevřené kapitoly, hledání bez diakritiky (`lib/guide.ts`) a odkazy předchozí/další. Do příručky vede ikona knihy v horní liště.
- Markdown renderer dashboardu nově umí pipe tabulky a odkazy `#/…` uvnitř aplikace (otevírají se na místě).
- Instalační příručka zvlášť: `bundle/build.py` zapíše kapitolu `instalace` jako `INSTALL.md` balíčku (`<verze>` nahradí verzí, odkazy `#/guide/…` zredukuje na text). Šablona `bundle/INSTALL.md` zanikla.
- `aifactory/README.md` je krátký rozcestník; testy obsahu se přesunuly z README na příručku (`tests/test_skill.py`: všechny kódy `factory check` včetně repa, všechny `factory …` příkazy existují v parseru). `tests/test_guide.py` hlídá pořadí a názvy kapitol, odkazy mezi kapitolami a sekcemi a shodu `INSTALL.md` s kapitolou.
- Rozpor v kódu: `factory check` zná jen macOS, Linux a WSL, takže nativní Windows dostane `unsupported_platform`, i když instalace na Windows je podporovaná; příručka to uvádí.
