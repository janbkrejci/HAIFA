# HAIFA-S90-T03 — OB3: approve review jménem uživatele

Schválení PR úkolu (`factory task approve` i tlačítko v dashboardu, obojí přes
`review.flow.approve_task`) na GitHubu pošle před mergem approve review, když je
v `.factory/config.yaml` nastavený `github_approver`. Bez něj se nic neposílá
a PR se merguje jako dřív.

## Jak to funguje

- `github_approver` je GitHub login jiného účtu než autor PR. Účet musí být
  přihlášený v `gh` na počítači, který schvaluje (`gh auth login`, `gh` drží víc účtů).
- `GitHubProvider.approve` ověří, že PR je otevřený a jeho head je commit, který
  factory právě pushla. Token vezme z `gh auth token --user <login>` a pošle
  `gh api --method POST repos/{owner}/{repo}/pulls/<id>/reviews -f event=APPROVE
  -f commit_id=<head>` s tokenem v `GH_TOKEN`. Review je tak vázané na schválený commit.
- Merge pak proběhne účtem aktivním v `gh` jako dřív. Výsledek nese `reviewed: true`.
- Chyby (posunutý head, účet není přihlášený, GitHub review odmítne) vrátí
  `approve_failed`, merge se neprovede a commit `status: done` zůstane na větvi,
  takže schválení jde zopakovat. Už mergnutý PR vrátí `reviewed: false`.
- `base_pr_merge: auto` se nemění (`merge_own` dál merguje s `--admin`).

Příklad:

```yaml
git_provider: github
github_approver: JanKrejciASOL
```

## Ověření

- Testy: `tests/providers/test_providers_github.py::test_approve_*` (bez approvera
  žádné volání, review s tokenem schvalujícího, posunutý head, mergnutý PR,
  nepřihlášený účet, odmítnuté review).
- Živě (2026-10-12): `gh auth token --user JanKrejciASOL` vrátil token,
  `gh api user` s ním odpověděl `JanKrejciASOL` a `repos/{owner}/{repo}` se
  rozložilo na `janbkrejci/HAIFA` (veřejné repo).
- Neověřeno: skutečné APPROVE review na otevřeném PR s mergem. Builder nesmí
  pushovat větve ani zakládat PR. Postup pro operátora: nastavit
  `github_approver: JanKrejciASOL`, spustit `factory task approve <id>` na otevřeném
  PR factory v `janbkrejci/HAIFA` a ověřit review `APPROVED` od JanKrejciASOL,
  merge a `reviewed: true` v `--json` výstupu. JanKrejciASOL není collaborator, na
  veřejném repu se review zapíše, ale nezapočítá se do povinných schválení.

## Mimo rozsah

D11 v `docs/decisions.md` je mimo povolené cesty úkolu a zůstává neaktualizované.
Formulář nastavení v dashboardu `github_approver` nezobrazuje, uložení formuláře
klíč v `config.yaml` zachová.
