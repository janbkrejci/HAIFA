"""Temporary repos for the onboarding tests: HAIFA's own `.factory/`, sssf and plain repos."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
HAIFA_FACTORY = ROOT / ".factory"
SSSF_TEMPLATES = ROOT / "vendor" / "sssf" / "templates"
# the committed configuration of HAIFA's .factory/ (never local.yaml, worktrees or data)
HAIFA_SHARED = ("config.yaml", "agents.yaml", "roles.yaml", "prompts")
# Only these repo workflows are inputs to the extraction tests. Operator workflows
# added to HAIFA must not change the exact items those tests expect to extract.
HAIFA_WORKFLOWS = ("build-test-review", "finish-test-review")


def git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
    )
    return proc.stdout.strip()


def write(root: Path, rel: str, text: str | bytes) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8", newline="\n")
    return path


def commit_all(root: Path, message: str = "commit") -> str:
    git(root, "add", "-A")
    git(root, "commit", "-q", "--allow-empty", "-m", message)
    return git(root, "rev-parse", "HEAD")


def init_repo(path: Path, *, readme: bool = True) -> Path:
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    if readme:
        write(path, "README.md", "readme\n")
        commit_all(path, "readme")
    return path.resolve()


def copy_tree(src: Path, dest: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dest, dirs_exist_ok=True)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def copy_haifa_factory(repo: Path) -> None:
    """HAIFA's committed `.factory/` with historical sssf leftovers from vendor templates."""
    for name in HAIFA_SHARED:
        src = HAIFA_FACTORY / name
        if src.exists():
            copy_tree(src, repo / ".factory" / name)
    for name in HAIFA_WORKFLOWS:
        rel = Path("workflows") / f"{name}.yaml"
        copy_tree(HAIFA_FACTORY / rel, repo / ".factory" / rel)
    # HAIFA no longer ships adws/. Keep the pre-library leftover scenario independent
    # of the current checkout by creating those historical inputs only in the test repo.
    copy_tree(
        SSSF_TEMPLATES / "sssf.config.yaml",
        repo / "adws" / "adw_sssf_config" / "sssf.config.yaml",
    )
    copy_tree(SSSF_TEMPLATES / "adws" / "adw_plan.py", repo / "adws" / "adw_plan.py")


def stamp_sssf(repo: Path) -> None:
    """What sssf's install.py stamps into a repo, from `vendor/sssf/templates/`."""
    copy_tree(SSSF_TEMPLATES / "adws", repo / "adws")
    copy_tree(
        SSSF_TEMPLATES / "prompt_engineering", repo / "adws" / "adw_data" / "prompt_engineering"
    )
    copy_tree(
        SSSF_TEMPLATES / "harness_engineering",
        repo / "adws" / "adw_data" / "harness_engineering",
    )
    copy_tree(
        SSSF_TEMPLATES / "sssf.config.yaml",
        repo / "adws" / "adw_sssf_config" / "sssf.config.yaml",
    )
    copy_tree(SSSF_TEMPLATES / "justfile", repo / "justfile")


def git_state(repo: Path) -> dict[str, Any]:
    """Index (bytes and mtime), index.lock and every ref of `repo`."""
    index = repo / ".git" / "index"
    return {
        "index": index.read_bytes() if index.exists() else None,
        "index_mtime": index.stat().st_mtime_ns if index.exists() else None,
        "lock": (repo / ".git" / "index.lock").exists(),
        "refs": git(repo, "for-each-ref"),
        "head": (repo / ".git" / "HEAD").read_text(encoding="utf-8"),
    }


def snapshot(path: Path) -> list[tuple[str, int, bytes]]:
    """Every file below `path` (including `.git`) with its mode and bytes."""
    return sorted(
        (p.relative_to(path).as_posix(), p.stat().st_mode, p.read_bytes())
        for p in path.rglob("*")
        if p.is_file() and not p.is_symlink()
    )


def worktree_snapshot(path: Path) -> list[tuple[str, int, bytes]]:
    """Every file below `path` outside `.git` with its mode and bytes."""
    return sorted(
        (p.relative_to(path).as_posix(), p.stat().st_mode, p.read_bytes())
        for p in path.rglob("*")
        if p.is_file() and not p.is_symlink() and ".git" not in p.relative_to(path).parts
    )


def haifa_backlog(repo: Path) -> None:
    """A small backlog in HAIFA's format whose tasks name simple-sdlc, plan-build-test and
    (through the project) build-test-review."""
    write(
        repo,
        "backlog/P/index.md",
        "---\nid: P\ntitle: Project\nworkflow: build-test-review\n---\n\nThe project.\n",
    )
    write(repo, "backlog/P/S01/index.md", "---\nid: P-S01\ntitle: Step\n---\n\nThe step.\n")
    for n, workflow in ((1, "simple-sdlc"), (2, "plan-build-test"), (3, None)):
        line = f"workflow: {workflow}\n" if workflow else ""
        write(
            repo,
            f"backlog/P/S01/T0{n}.md",
            f"---\nid: P-S01-T0{n}\ntitle: Task {n}\nstatus: todo\n{line}---\n\n"
            "## Zadání\nDo it.\n",
        )


def bare_origin(repo: Path, tmp: Path, name: str = "origin.git") -> Path:
    """A bare remote `origin` of `repo` with `main` pushed."""
    path = tmp / name
    git(tmp, "init", "-q", "--bare", "-b", "main", str(path))
    git(repo, "remote", "add", "origin", str(path))
    git(repo, "push", "-q", "origin", "main")
    return path


def reject_pushes(bare: Path) -> Path:
    """Make every push to the bare repo fail (an executable ``hooks/pre-receive``)."""
    hook = bare / "hooks" / "pre-receive"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    return hook


def sandbox_factory(repo: Path) -> None:
    """HAIFA's `.factory/` as haifa-sandbox has it: every agent prompt changed and a changed
    simple-sdlc in `.factory/workflows/`."""
    from aifactory.library.store import packaged_seed

    copy_haifa_factory(repo)
    for agent in ("planner", "builder", "reviewer", "documenter"):
        path = repo / ".factory" / "prompts" / agent / "system.md"
        path.write_text(
            path.read_text(encoding="utf-8") + "\nThis is the sandbox.\n",
            encoding="utf-8",
            newline="\n",
        )
    seed = next(s for s in packaged_seed() if s.key == "workflow/simple-sdlc")
    write(repo, ".factory/workflows/simple-sdlc.yaml", seed.files[0].data + b"# sandbox\n")


def library_with_versions(repo: Path) -> list[str]:
    """Put the versions of the repo copies the seed lacks into the library's history, then
    restore the seed versions at the head; returns the ``type/name`` imported."""
    from aifactory.library.load import check_repo_item
    from aifactory.library.model import ItemType
    from aifactory.library.state import repo_item_names
    from aifactory.library.store import SeedItem, import_items, packaged_seed
    from aifactory.onboard.adopt import _library_files, _roster, _settings

    seed = {s.key: s for s in packaged_seed()}
    roster, settings = _roster(repo), _settings(repo)
    copies: list[SeedItem] = []
    restore: list[SeedItem] = []
    names = repo_item_names(repo)
    kinds: tuple[ItemType, ...] = ("agent", "workflow")
    for kind in kinds:
        for name in names.get(kind, []):
            item, issues = check_repo_item(repo, kind, name)
            assert item is not None and not issues, (kind, name, issues)
            known = seed.get(f"{kind}/{name}")
            if known is not None and known.version == item.version:
                continue
            files = _library_files(item, name, roster, settings, name)
            copies.append(SeedItem(item.type, name, item.version, files))
            if known is not None:
                restore.append(known)
    if copies:
        import_items(copies, "test", "library: the repo versions")
    if restore:
        import_items(restore, "test", "library: back to the seed")
    return [c.key for c in copies]


# ── sssf installations (factory onboard of adws/, O4) ─────────────────────────

SSSF_ROSTER = "adws/adw_sssf_config/sssf.config.yaml"
SSSF_PROMPTS = "adws/adw_data/prompt_engineering"
SSSF_QUALITY = "adws/adw_modules/quality.py"
# rules a repo adds to its prompts; the patch positions are checked in test_sssf_parts.py
JSST_BUILDER_RULES = (
    "- JSST: run `bun test` for the package you touched before you report.\n"
    "- JSST: never edit generated files under `dist/`.\n"
)
JSST_REVIEWER_RULE = "- JSST: a change without a test for it is blocking.\n"
AMBER_BUILDER_RULE = "- Amber: every clock change keeps the Swiss time zone.\n"
PLANNER_CHANGED_LINE = "- Name the plan `specs/<slug>.md` (amended for this repo).\n"


def sssf_repo(tmp: Path, name: str, *, origin: bool) -> Path:
    """A repo with stock sssf stamped in and committed (and a bare `origin` when asked)."""
    repo = init_repo(tmp / name)
    git(repo, "config", "user.name", "Ada Tester")
    git(repo, "config", "user.email", "ada@example.com")
    stamp_sssf(repo)
    copy_tree(SSSF_TEMPLATES / "env.sample", repo / ".env.sample")
    commit_all(repo, "sssf")
    if origin:
        bare_origin(repo, tmp, f"{name}.git")
    return repo


def _roster(repo: Path) -> dict[str, Any]:
    import yaml

    data: dict[str, Any] = yaml.safe_load((repo / SSSF_ROSTER).read_text(encoding="utf-8"))
    return data


def _write_roster(repo: Path, data: dict[str, Any]) -> None:
    import yaml

    write(repo, SSSF_ROSTER, yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def _replace(repo: Path, rel: str, old: str, new: str) -> None:
    path = repo / rel
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, (rel, old)
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")


def _insert_after(repo: Path, rel: str, line_start: str, added: str) -> None:
    path = repo / rel
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    index = next(i for i, line in enumerate(lines) if line.startswith(line_start))
    lines.insert(index + 1, added)
    path.write_text("".join(lines), encoding="utf-8", newline="\n")


def patch_omnibus(repo: Path) -> None:
    """Every agent on claude (opus) without extensions; `thinking: auto` by default;
    quality.py with a 1800 s test and `just lint`."""
    data = _roster(repo)
    data["defaults"]["thinking"] = "auto"
    data["defaults"].pop("harness_engineering", None)
    for agent in data["agents"]:
        agent["coding_agent"] = "claude_code"
        agent["model"] = "opus"
        agent.pop("harness_engineering", None)
        agent["tools"] = [t for t in agent.get("tools", []) if not t.startswith("subagent_")]
    _write_roster(repo, data)
    _replace(repo, SSSF_QUALITY, "timeout_seconds=600,", "timeout_seconds=1800,")
    _replace(repo, SSSF_QUALITY, 'argv=_placeholder("lint"),', 'argv=["just", "lint"],')


def patch_jsst(repo: Path) -> None:
    """Rules appended to the builder (union with the library) and one inserted into the
    reviewer where it merges cleanly; the pi roster stays."""
    path = repo / SSSF_PROMPTS / "builder" / "system.md"
    path.write_text(
        path.read_text(encoding="utf-8") + JSST_BUILDER_RULES, encoding="utf-8", newline="\n"
    )
    _insert_after(
        repo, f"{SSSF_PROMPTS}/reviewer/system.md", "- `approved` is true ONLY", JSST_REVIEWER_RULE
    )


def patch_amber(repo: Path) -> None:
    """A builder rule near the top: a clean merge with the library."""
    _insert_after(repo, f"{SSSF_PROMPTS}/builder/system.md", "## Instructions", AMBER_BUILDER_RULE)


def patch_modified_chain(repo: Path) -> None:
    """A changed chain, a recipe, a pi agent without a stock template bound to subagents.ts,
    a planner system.md changing the line the library changes too (a conflict), an edited
    planner user.md, a changed adw_modules file and a second roster."""
    _replace(repo, "adws/adw_plan.py", "import sys", "import sys  # amended")
    write(repo, "adws/adw_recipes/demo.json", '{"name": "demo", "steps": []}\n')
    data = _roster(repo)
    data["agents"].append(
        {
            "name": "tester",
            "purpose": "Write the missing tests for the change.",
            "prompt_engineering": {
                "system": f"{SSSF_PROMPTS}/tester/system.md",
                "user": f"{SSSF_PROMPTS}/tester/user.md",
            },
            "harness_engineering": ["adws/adw_data/harness_engineering/subagents.ts"],
            "writes": ["tests/"],
        }
    )
    _write_roster(repo, data)
    write(repo, f"{SSSF_PROMPTS}/tester/system.md", "# Tester\n\nWrite tests.\n")
    write(repo, f"{SSSF_PROMPTS}/tester/user.md", "# Task\n\n{{prompt}}\n")
    _replace(
        repo,
        f"{SSSF_PROMPTS}/planner/system.md",
        "- List `specs/` before naming that copy and pick a name nothing else holds. Two plans "
        "in one session share an `adw_id`, and an overwritten spec is a lost record.\n",
        PLANNER_CHANGED_LINE,
    )
    path = repo / SSSF_PROMPTS / "planner" / "user.md"
    path.write_text(
        path.read_text(encoding="utf-8") + "\nAlso list the open questions.\n",
        encoding="utf-8",
        newline="\n",
    )
    path = repo / "adws" / "adw_modules" / "utils.py"
    path.write_text(path.read_text(encoding="utf-8") + "\n# amended\n", encoding="utf-8")
    copy_tree(repo / SSSF_ROSTER, repo / "adws" / "adw_sssf_config" / "alt.yaml")
