# HAIFA-REFINEMENT-T18 — Návrh workflow bez kopie celého repa a bez úniku dočasných adresářů

Návrh workflow i parametrů tasku (`workflow/adaptive.py`) pracuje v izolovaném
klonu v `%TEMP%\factory-advice-*`. Klon vzniká přes `git clone --shared
--no-checkout` a pak `checkout --detach` potvrzeného commitu: objekty repa se
nekopírují, klon si je půjčuje přes `objects/info/alternates`. Dočasný adresář
tak obsahuje jen pracovní strom a index, ne historii. Pracovní strom zůstává
celý, protože plánovač čte kód repa.

Každý návrhový adresář má soubor `owner.pid` s PID procesu, který ho vytvořil.
Před každým návrhem a jednou při startu dashboardu `cleanup_orphans()` smaže
`factory-advice-*` adresáře, které neběží:

- vlastník je mrtvý proces, nebo je to tentýž proces a adresář nepatří žádnému
  běžícímu návrhu,
- adresář bez `owner.pid` (starší verze HAIFA) je osiřelý až po hodině, aby se
  nesmazal adresář, který jiný proces právě zakládá.

Adresáře `factory-advice-save-*` (krátké ověření při uložení návrhu) se
nemažou. Mazání (`remove_tree`) při chybě odebere souboru příznak jen pro čtení
a zkusí to znovu, takže zvládne read-only objekty gitu na Windows.

Ověření:

```sh
cd aifactory
uv run pytest tests/workflow/test_workflow_advice.py tests/web/test_web_workflow_advice.py tests/web/test_web_task_advice.py
```

Test nad repem s historií ověří, že klon má `alternates` a jeho dočasný adresář
je víc než desetkrát menší než `.git` zdrojového repa, a že osiřelé adresáře
(mrtvý vlastník s read-only souborem, starý bez vlastníka) se při návrhu smažou,
zatímco čerstvý, cizí živý a `save` adresář zůstanou.
