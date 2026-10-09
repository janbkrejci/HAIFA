---
id: HAIFA-S90-T02
title: OB2 R10 opravné kolo v Codex threadu
status: done
workflow: manual-r10-validation
depends_on: []
writes: [aifactory/validation/results/]
---
## Zadání
Ověř riziko R10: opravné kolo běží v tomtéž Codex threadu (`codex exec resume`) a neztratí kontext.

## Podmínka spuštění
Spustit ručně, až bude dostupný kredit na Codex. Do té doby nespouštět přes factory; workflow ponechat bez přiřazení.

## Postup
- Použít existující validační scénář R10 v režimu GitHub se skutečnými harnessy. Ověřit dostupnost `HAIFA_SANDBOX_REPO`, přihlášení `gh` a harnessů použitého rosteru.
- Spustit `just validate --remote github --only R10`. Výchozí validační šablona již používá Codex pro build i fix. Při použití jiného rosteru přidat `--roster DIR` a ověřit, že oba kroky skutečně běží na Codexu.
- Vyhodnotit výsledek scénáře a uložené důkazy; samotný návratový kód 0 nestačí, protože připouští i `inconclusive`.

## Done means
- `R10.json` obsahuje `outcome: passed` při běhu s `remote: github` a build i fix běží na Codexu.
- Skrytý test způsobí selhání prvního testovacího kola, proběhne fix a následný test projde.
- Kontroly `same_session` a `thread_resumed` projdou: build a fix mají shodné session ID a uložený stav a raw události dokládají pokračování jednoho Codex threadu.
- Výsledky jsou v `aifactory/validation/results/<YYYY-MM-DD>/github-<HHMMSS>/`, včetně `R10.json`, `summary.json` a odkazovaných trace souborů se stavem Codex session a raw výstupem.
- Výsledek `inconclusive`, lokální běh s falešným harnessem ani nedostupný kredit neznamenají splnění úkolu.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-08 · workflow manual-r10-validation · PR https://github.com/janbkrejci/HAIFA/pull/98 · náklady $0.00
