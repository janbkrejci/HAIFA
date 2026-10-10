# HAIFA-S03-T06 — Schválení: opakovat merge po přechodné chybě GitHubu

## Problém
`GitHubProvider.merge` (`aifactory/src/aifactory/providers/github.py`) volá `gh pr merge` jen jednou.
Po pushi commitu `status: done` GitHub občas odpoví přechodnou chybou
`Base branch was modified. Review and try the merge again. (mergePullRequest)`, i když se base
nezměnila. Kód pak jednou zavolá `_status_once`: když to není CONFLICT, hned vyhodí
`MergeFailed("merge_failed")`. Druhé ruční spuštění `factory task approve` PR sloučí.

Approve flow (`aifactory/src/aifactory/review/flow.py::_approve`) je už idempotentní:
`mark_done` vrátí stejný text, když je úkol `done` a v `## Běhy` je řádek pro URL PR, takže
druhý commit nevznikne; dočasný worktree z prvního pokusu zůstane a `_branch_worktree` ho
najde přes `checked_out_in`. **Ve `flow.py` se nic měnit nemusí.** Builder to jen ověří testem
(viz níže). Kdyby test ukázal druhý commit, oprava patří do `_approve`/`mark_done`, ne do provideru.

## Změny

### 1. `aifactory/src/aifactory/providers/github.py`
- Docstring modulu doplň jednou větou: merge, který GitHub odmítne přechodnou chybou
  („Base branch was modified“, „Head branch was modified“ … „try the merge again“), se po
  pauze zopakuje, nejvýš `attempts`-krát.
- Přidej konstantu (malými písmeny se porovnává `stderr.lower()`):
  ```python
  TRANSIENT_MERGE_ERRORS = (
      "base branch was modified",
      "head branch was modified",
      "try the merge again",
  )
  ```
  a helper `def _transient(detail: str) -> bool` (`any(m in detail.lower() for m in ...)`).
- Přepiš `merge`:
  ```python
  def merge(self, pr, head_sha, subject, strategy=None) -> str | None:
      chosen = self._strategy(strategy)
      current = self.status(pr)
      if current.state == MERGED: return current.merge_sha
      if current.state == CLOSED: raise MergeFailed("merge_failed", f"PR {pr.id} is closed")
      if current.mergeability == CONFLICT: raise MergeFailed("conflict", ...)   # beze změny
      for attempt in range(1, self.attempts + 1):
          try:
              self.gh.run("pr", "merge", pr.id, f"--{chosen}", "--match-head-commit", head_sha,
                          "--subject", subject)
          except GhError as exc:
              detail = exc.stderr.strip() or exc.message
              try:
                  after = self._status_once(pr)
              except ProviderError:
                  after = None
              if after is not None and after.state == MERGED:
                  return after.merge_sha          # merge přece jen proběhl
              if after is not None and after.state == OPEN and after.mergeability == CONFLICT:
                  raise MergeFailed("conflict", f"PR {pr.id} has conflicts: {detail}") from exc
              if after is not None and after.state == CLOSED:
                  raise MergeFailed("merge_failed", detail) from exc
              if _transient(detail) and attempt < self.attempts:
                  self.sleep(self.delay)
                  continue
              if _transient(detail):
                  detail = f"{detail} (gave up after {self.attempts} attempts)"
              raise MergeFailed("merge_failed", detail) from exc
          return self._status_once(pr).merge_sha
      raise AssertionError("unreachable")   # nebo strukturovat tak, aby mypy nechtěl return
  ```
  Pozn.: Konflikt má přednost před opakováním (kontrola stavu proběhne před rozhodnutím o
  opakování). Nepřechodná chyba (např. „head moved“) dál končí `merge_failed` hned, bez
  pauzy. Stejné `attempts`/`delay`/`sleep` jako u mergeability `unknown` (UNKNOWN_ATTEMPTS=5,
  UNKNOWN_DELAY=2.0) — žádné nové parametry konstruktoru. Pokud se nechce `raise AssertionError`,
  ať smyčka končí tak, aby mypy strict prošel (např. poslední pokus mimo smyčku nebo
  `while True` s počítadlem).
- Dodrž, že stávající testy dál platí: `test_merge_failure_turns_out_conflict` (attempts=1,
  view UNKNOWN→CONFLICTING; po chybě merge `_status_once` vrátí CONFLICTING → `conflict`),
  `test_merge_failure_other` (`head moved` → `merge_failed`, bez opakování), merge-default
  testy (view, MERGED). Pozor: fake `gh` u seznamu odpovědí opakuje poslední položku.

### 2. Testy provideru — `aifactory/tests/providers/test_providers_github.py`
Použij existující `view`, `reply`, `_provider`, `_pr_calls`, `DELAY`, `install_fake_gh`.
`BASE_MODIFIED = "GraphQL: Base branch was modified. Review and try the merge again. (mergePullRequest)\n"`
- `test_merge_retries_base_branch_modified`: `"pr view": [view(), view(), view("MERGED","UNKNOWN",MERGE_SHA)]`
  (1. status před merge, 2. `_status_once` po chybě = OPEN/MERGEABLE, 3. po úspěchu MERGED),
  `"pr merge": [reply(exit=1, stderr=BASE_MODIFIED), reply("")]`. Očekávej návrat `MERGE_SHA`,
  `len(_pr_calls(log, "pr merge")) == 2`, `sleeps == [DELAY]`.
- `test_merge_transient_runs_out`: `"pr view": view()`, `"pr merge": reply(exit=1, stderr=BASE_MODIFIED)`,
  `attempts=3` → `MergeFailed` s `code == "merge_failed"`, `"Base branch was modified" in message`,
  3 volání `pr merge`, `sleeps == [DELAY, DELAY]`.
- `test_merge_transient_but_conflict`: `"pr view": [view(), view(mergeable="CONFLICTING")]`,
  merge vrací BASE_MODIFIED → `code == "conflict"`, jen 1 volání `pr merge`, `sleeps == []`.
- (volitelně) `test_merge_failure_but_merged`: merge chyba, další view MERGED → vrátí MERGE_SHA.
- Do `test_merge_failure_other` přidej `assert len(_pr_calls(log, "pr merge")) == 1` (žádné opakování
  nepřechodné chyby), pokud tam ještě není; `sleeps` bude prázdné.

### 3. Test opakovaného approve — nový `aifactory/tests/review/test_approve_merge_retry.py`
Adresář `aifactory/tests/review/` neexistuje — vytvoř jen soubor (bez `__init__.py` a bez
`conftest.py`; mypy by hlásil duplicitní moduly). Vzor importů podle `tests/web/test_web_review.py`:
```python
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "run"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "providers"))
from run_repo import SPEC, T01, Script, fake_env, git, make_run_repo, ok, write  # noqa: E402,I001
from gh_fake import install_fake_gh, prepare_shared_gh, reply  # noqa: E402
```
Fixtures: `script` (`yield from fake_env(monkeypatch)`), `repo` (`make_run_repo(tmp_path/"repo")`),
module-scoped autouse `prepare_shared_gh(tmp_path_factory.mktemp("ghwarm"))`.

Scénář (vzor: `test_approve_catches_up_base` v `tests/run/test_task_pr_flow.py`):
1. Holý `origin.git` (`git init --bare -b main`), `git remote add origin`, `git push -u origin main`.
2. `install_fake_gh(tmp_path, monkeypatch, {...})` s:
   - `"pr create": reply("https://github.com/o/r/pull/7\n")`
   - `"pr view"`: JSON `{"state":"OPEN","mergeable":"MERGEABLE","headRefOid":"x","mergeCommit":None}`
   - `"pr merge": reply(exit=1, stderr=BASE_MODIFIED)`
3. `provider = GitHubProvider(repo, load_run_config(repo).config.settings, attempts=2, delay=0, sleep=lambda _: None)`.
   (Settings z run repa mají `git_provider` local — GitHubProvider ho nečte; pokud by
   validace vadila, použij `settings.model_copy(update={"git_provider": "github"})`.)
4. `succeed(script)` (planner zapíše SPEC, `ok(artifacts=[SPEC], ...)`), `run = run_task(repo, T01, provider=provider)`; assert `run.ok`.
5. `with pytest.raises(ReviewError) as info: approve_task(repo, T01, provider=provider)`;
   `info.value.code == "merge_failed"`. Ulož `tip = git(origin, "rev-parse", BRANCH)`;
   ověř, že `git log --format=%s BRANCH` obsahuje přesně jeden `f"{T01}: status done"`.
   Uložený PR (`TaskRunStore(...).pr_for_branch(BRANCH)`) je dál `open`.
6. `log.respond("pr merge", reply(""))`, `log.respond("pr view", [open_view, merged_view])`
   kde merged_view = `{"state":"MERGED",...,"mergeCommit":{"oid": "b"*40}}`.
   (Pořadí volání view ve 2. approve: `_checked_pr` → status (1×, MERGEABLE), merge →
   `self.status` (1×), po úspěchu `_status_once` → MERGED. Tedy `[open, open, merged]`.)
7. `result = approve_task(repo, T01, provider=provider)`; `result.merge_sha == "b"*40`;
   `git(origin, "rev-parse", BRANCH) == tip` (žádný nový push/commit); znovu přesně jeden
   commit `status done` na větvi; uložený PR `merged`.
   Ověř i, že `pr merge` se ve 2. approve volal s `--match-head-commit tip`.
Pokud `run_task` s GitHubProvider volá další `gh` příkazy (`pr edit`, `pr comment`), fake `gh`
na ně odpoví prázdně s exit 0 — nevadí. `_catch_up_base` po „merge“ jen fetchne nezměněný
origin/main — bez varování nebo s neškodným; neassertuj `warnings == []`, pokud to padá.
Test nesmí volat síť ani model (fake harness + fake gh).

### 4. Dokumentace
`app_docs/HAIFA-S03-T06-schvaleni-opakovat-merge-po-prechodne-ch.md` — krátce česky: co se
opakuje (markery chyb), kolikrát/po jaké pauze, že konflikt má přednost, že opakovaný approve
nepřidá druhý commit done.

## Ověření
- `just test` (případně nejdřív `cd aifactory && uv run pytest tests/providers/test_providers_github.py tests/review -n0`)
- `just typecheck`
- `just lint` (`ruff format` nové soubory)

## Mimo rozsah
Approve review v hostingu (D11/OB3), provider Azure DevOps, `vendor/`, `prototype/`.
