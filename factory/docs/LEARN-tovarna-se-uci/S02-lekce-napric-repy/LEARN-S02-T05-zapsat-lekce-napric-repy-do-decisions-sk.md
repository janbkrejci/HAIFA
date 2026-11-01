# LEARN-S02-T05: Lekce napříč repy v decisions, skillu factory a příručce

## Co se změnilo

- `docs/decisions.md` má oddíl **Lekce napříč repy (LEARN-S02)**. Popisuje zdroje lekcí (registr dashboardu), cílové repo lekce (`repo`, `origin`), jak se pozná repo factory (`HAIFA_FACTORY_REPO`, jinak `aifactory/pyproject.toml` s projektem `aifactory`), uložení lekce do trace DB cílového repa, klíče výtek s předponou `<repo_id>:` a cíl `seed`, povolený jen pro repo factory.
- Skill `factory` (oddíl *Lessons from runs*) popisuje `factory learn scan --all`, pole `repo`, `origin`, `origin_repos`, `data.all`, `data.repos` a cíl `seed`. Dál uvádí, že `factory learn accept` se spouští v cílovém repu (`--repo PATH`) a že sekce Lekce v dashboardu má přepínač Ze všech rep.
- Příručka, kapitola *Konfigurace*, oddíl *Záložka Factory*, má odrážku **Lekce**: Najít lekce, přepínač Ze všech rep a kam se lekce uloží (lekce o factory do repa HAIFA). Hláška po hledání odkáže na sekci Lekce cílového repa.
- Test `test_guide_stays_short` hlídá limit 4100 slov a příručka byla na 4099. Aby se nová odrážka vešla, zkrátil jsem formulace v kapitolách *Co je HAIFA*, *Běhy a review* a *Aktualizace a řešení problémů*. Vypadly jen podrobnosti: JSON klíče úklidu a detaily čipu System info.

## Ověření

- `cd aifactory && uv run pytest tests/test_guide_consistency.py tests/test_guide.py tests/test_skill.py tests/web/test_web_guide.py -n0`
