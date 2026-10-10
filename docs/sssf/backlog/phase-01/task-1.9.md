Napiš validační scénáře prototypu: `just proto-validate` připraví testovací repo s backlogem a spustí scénáře, které ověřují rizika R1 až R5 a R10 z `docs/product-brief.md`. Výsledky uloží do `prototype/validation/`.

Where: `prototype/validation/` (skript scénářů, šablona backlogu), recept `proto-validate` v `justfile`, testy v `prototype/tests/`.

Done means:
- Cíl je parametr: `--remote local` (bare repo v dočasném adresáři, falešný harness, žádné náklady) nebo `--remote github` (repo z `HAIFA_SANDBOX_REPO` v `.env`, skutečné harnessy).
- Šablona backlogu: 2 moduly, 3 stepy, 6 tasků. Dva tasky mění týž soubor, jeden závisí na tasku jiného modulu. Úkoly jsou malé (řádově desítky řádků), aby běh se skutečnými modely stál málo.
- Scénáře: R1 `simple-sdlc.yaml` s plan na `claude`, build na `codex`, review na `pi`; R2 dva paralelní tasky nad sdíleným souborem až po konflikt PR; R3 schválení v HAIFA, ruční merge mimo HAIFA + `backlog sync`, vrácený a zavřený PR; R4 změna promptu necommitnutá v hlavním checkoutu a běh, který ji nevidí; R5 čas a místo na disku na jeden worktree; R10 opravné kolo na Codexu.
- Každý scénář zapíše JSON s výsledkem (prošel, selhal, pozorování), důkazy (run-id, PR, cesty do trace) a měřením do `prototype/validation/results/<datum>/`.
- `just proto-validate --remote local` projde v testu bez sítě a bez modelů.

Out of scope: samotná zpráva (1.10), Azure DevOps.

Pevná omezení:
- `--remote github` se v testech nikdy nespouští. Spouští ho engineer ručně.
- Skript nemaže nic mimo dočasné adresáře a sandbox repo.
- `vendor/` se neupravuje.
