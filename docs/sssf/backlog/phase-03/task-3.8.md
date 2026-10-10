Přidej akceptační test F3 v prohlížeči: úkol jde v dashboardu založit, provázat, spustit, sledovat, schválit a mergovat bez terminálu.

Where: `aifactory/tests/e2e/`, `justfile`.

Done means:
- Test (Playwright) spustí `factory obs` nad dočasným repem s providerem `local` a falešným harnessem, v prohlížeči založí dva tasky, provede vazbu, spustí první, počká na běh v obrazovce Běhy, schválí PR v obrazovce Review, spustí druhý a schválí ho.
- Kontroly: oba tasky mají `status: done` v `base`, v obrazovce Backlog jsou `done`, žádný krok nepotřeboval terminál.
- `just e2e` test spustí a `just test` ho zahrnuje.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: běh proti GitHubu a skutečné modely.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.
