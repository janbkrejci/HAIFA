# HAIFA-REFINEMENT-T15 — Zrychlení nejen na Windows

Měření na Windows (repo HAIFA, 1 146 souborů, 13 MB packů) ukázalo tři místa, kde HAIFA
čekala zbytečně dlouho mimo samotného agenta. Všechna tři jsou opravená a platí na všech
systémech.

## Naměřené příčiny a opravy

1. **Parsování YAML v čistém Pythonu.** Každé načtení backlogu parsuje hlavičku každého tasku
   a každé načtení konfigurace parsuje YAML z `.factory/`. PyYAML ale ve wheelu pro Windows,
   macOS i Linux nese C parser libyaml.
   - Nový modul `aifactory/yamlload.py` má `safe_load`, který použije `yaml.CSafeLoader`,
     a když chybí, `yaml.SafeLoader`. Chování i výjimky (`yaml.YAMLError`) jsou stejné.
   - Všechna volání `yaml.safe_load` v `aifactory/src/aifactory/` jdou přes něj. V `engine/`
     jsou změny označené `# aifactory 3.1:`.
   - Parsování je asi 4× rychlejší. `load_for_edit` backlogu HAIFA kleslo z 0,25 s na 0,11 s.
     Dashboard i `factory` CLI to dělají při skoro každém požadavku.
2. **Kopie celého repozitáře pro návrh parametrů tasku a návrh workflow.** Agent pracuje
   v izolovaném klonu. Klon `--no-hardlinks` kopíroval všechny objekty, takže doba rostla
   s velikostí historie.
   - Klon je teď `--shared`. Objekty si půjčuje přes alternates, nic nekopíruje a agent do
     zdrojového repozitáře přes alternates zapsat nemůže. Klon žije jen po dobu jobu.
   - Klonování kleslo z 1,1 s na 0,23 s. U velkých repozitářů je rozdíl desítky sekund.
3. **Jednovláknový checkout.** Na Windows stojí každý zapsaný soubor hodně (antivir, NTFS).
   - Konstanta `PARALLEL_CHECKOUT = ("-c", "checkout.workers=0")` v `providers/git.py`
     zapne paralelní checkout (počet workerů podle CPU).
   - Používá ji checkout izolovaného klonu poradce, `git worktree add` worktree běhu
     (`run/task.py`), dočasné merge worktree (`providers/git.py`) a worktree kontroly
     a review (`review/sync.py`, `review/flow.py`).
   - Checkout kleslo z 1,2 s na 0,55 s.

## Co zbývá

Návrh parametrů tasku dál trvá hlavně kvůli samotnému agentovi (start CLI a odpověď
modelu). Ten čas určuje zvolený harness a model, ne HAIFA.
