# HAIFA-REFINEMENT-T10: Remove onboarding (sssf, pre_library) and `factory adopt`

## What changed

HAIFA no longer converts an existing factory into its own format. A repo gets into HAIFA only through `factory init`. The onboarding tests copied `.factory/` from old HAIFA history and compared against sssf golden output, and they were failing on `main` and blocking other tasks.

1. `factory onboard` (from sssf and from `pre_library`) and `factory adopt` are removed from the CLI, the dashboard API and the dashboard UI.
2. The `aifactory.onboard` package, including `sssf_stock/`, is deleted. `web/sssf_cleanup.py` and `docs/sssf/` are deleted.
3. The repo state moved from `aifactory.onboard.state` to `aifactory/src/aifactory/config/repo_state.py` and is simpler.
4. Code and tests in `aifactory/` no longer read `vendor/sssf/`, so the operator can delete that directory after merge.

## Repo state

`repo_state(root, base=None)` reads the tree of `base`. The first matching row wins.

| state | condition | action |
|---|---|---|
| `installed` | `.factory/manifest.yaml` in base | none |
| `unsupported` | `.factory/config.yaml` or `.factory/agents.yaml` in base without a manifest, or `adws/` in base | none |
| `uncommitted` | manifest or config only in the working tree | `config_commit` |
| `none` | none of these | `init` |

The old states `onboarded`, `pre_library`, `sssf` and `working_tree` are gone, as are the flags `sssf_leftover`, `alternate_rosters` and `rosters`. `RepoState` gained `config_in_base` (true for `installed` and for `unsupported` with `.factory/` config). It replaces the old `state in ("onboarded", "pre_library")` checks in `check/context.py` and `web/overview.py`. It is not part of `to_json()`.

## Where it lives

- `config/repo_state.py`: the new state (renamed from `onboard/state.py`).
- `check/repo_rules.py`, `check/model.py`, `check/context.py`, `check/__init__.py`: finding codes `sssf_not_onboarded`, `pre_library_config`, `sssf_leftover` and `alternate_rosters` are replaced by `repo_unsupported` (`info` for `.factory/` without a manifest, `error` for sssf in `adws/`, fix: HAIFA will not convert it, use `factory init` in a repo without `.factory/`). `repo_onboarded` is renamed to `repo_installed`. Actions `onboard` and `adopt` are removed. An item whose version the library does not know now points to `factory config export` (action `export`) instead of `factory adopt`.
- `config/manifest.py`: `OnboardingSource` is only `init`. `sssf` and `pre_library` stay accepted as `LegacyOnboardingSource`, so older manifests still load.
- `cli.py`: the `onboard` and `adopt` subcommands are removed. `factory check` text output prints `state: <state> (...)` with `next: <action>` when there is one. Help texts no longer mention onboard.
- `library/install.py`, `library/install_commit.py`: `factory init` still refuses existing configuration (`existing_config`) with the message "HAIFA does not take over existing configuration" and no `factory onboard` fix.
- `library/update.py`, `library/config_edit.py`: `not_onboarded` now says `factory init` (or says HAIFA does not take over a config without a manifest).
- `skill/codes.py`, `skill/skill.md`: onboard and adopt error codes, enums and documentation are removed. `repo_state` is `installed, unsupported, uncommitted, none`, and `repo_action` is `config_commit, init`.
- `web/factory.py`, `web/app.py`: actions `onboard` and `adopt`, their options, error statuses, the adopt digest and `onboarding_hint` are removed.
- `web/repos.py`, `web/overview.py`: use the new state. A repo counts as not installed when it is `none` or `unsupported` without `.factory/` config. Inspect no longer returns `sssf_paths`.
- Frontend (`aifactory/web/src/`): `OnboardingPanel.vue`, its test and `lib/onboarding.ts` are deleted. `FactoryView.vue`, `InspectCard.vue`, `lib/api.ts`, `lib/repos.ts`, `lib/overview.ts` and `lib/factory.ts` use the four states with Czech labels (for example `unsupported`: "Nepodporováno: HAIFA tuto konfiguraci nepřevezme"). The built bundle in `web/static/` is regenerated.

## Tests

- New `tests/config/test_repo_state.py` covers installed, installed with a broken manifest, installed winning over `adws/`, uncommitted, none, unsupported `.factory/` without a manifest, unsupported sssf, and that nothing is written.
- `tests/onboard/` (with golden files), `tests/e2e/test_onboarding_browser.py`, `tests/e2e/test_team_onboarding_browser.py` and `tests/e2e/team_flow_e2e.py` are deleted.
- Check, web, library, skill, manifest and vitest tests are updated to the new states and codes, and to a dashboard without onboarding.

## Verify

```
just test
just typecheck
just lint
cd aifactory && uv run pytest tests/config/test_repo_state.py tests/check -n0
```

`factory check` in a repo with `.factory/config.yaml` but no manifest reports `state: unsupported` and a `repo_unsupported` finding without an action.
