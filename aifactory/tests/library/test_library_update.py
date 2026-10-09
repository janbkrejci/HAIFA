"""``factory update`` with bare remotes of the library and the repo.

No network and no model: the remotes are local bare repositories, the harness CLI a stub.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from aifactory import __version__
from aifactory.config.manifest import MANIFEST_FILE
from aifactory.library import migrations, store
from aifactory.library.update import merge_text, unit_rule
from cli_json import run_json
from fake_exe import make_executable

Capsys = pytest.CaptureFixture[str]
SYSTEM = ".factory/prompts/builder/system.md"
USER = ".factory/prompts/builder/user.md"
LIB_SYSTEM = "agents/builder/system.md"
SKILL_MD = "---\nname: lint\ndescription: Lint the code.\n---\n\nRun the linter.\n"


def git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return proc.stdout.strip()


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """``$HAIFA_HOME`` in tmp, a git identity, and only claude on this machine."""
    path = tmp_path / "haifa-home"
    monkeypatch.setenv("HAIFA_HOME", str(path))
    monkeypatch.delenv("HAIFA_LIBRARY", raising=False)
    for kind in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{kind}_NAME", "Ada Tester")
        monkeypatch.setenv(f"GIT_{kind}_EMAIL", "ada@example.com")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "commit.gpgsign")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")
    claude = tmp_path / "bin" / "claude"
    claude.parent.mkdir()
    claude.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8", newline="\n")
    claude = make_executable(claude)
    monkeypatch.setenv("CLAUDE_CODE_PATH", str(claude))
    monkeypatch.setenv("CODEX_PATH", "codex-not-installed-anywhere")
    monkeypatch.setenv("PI_PATH", "pi-not-installed-anywhere")
    return path


def make_repo(tmp_path: Path, name: str = "repo") -> Path:
    path = tmp_path / name
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    (path / "README.md").write_text("readme\n", encoding="utf-8", newline="\n")
    (path / "justfile").write_text("test:\n    echo ok\n", encoding="utf-8", newline="\n")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "init")
    bare = tmp_path / f"{name}-origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    git(path, "remote", "add", "origin", str(bare))
    git(path, "push", "-q", "-u", "origin", "main")
    git(path, "remote", "set-head", "origin", "main")
    return path.resolve()


@pytest.fixture
def repo(tmp_path: Path, capsys: Capsys) -> Path:
    """A shared library (bare remote) from the seed and a repo installed from it."""
    bare = tmp_path / "library-origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    store.init_library("team", remote=str(bare))
    path = make_repo(tmp_path)
    rc, env = run_json(capsys, ["init", "--repo", str(path), "--commit", "--json"])
    assert rc == 0, env
    return path


def upd(capsys: Capsys, repo: Path, *args: str) -> tuple[int, Any]:
    return run_json(capsys, ["update", *args, "--repo", str(repo), "--json"])


def ok(capsys: Capsys, repo: Path, *args: str) -> dict[str, Any]:
    rc, env = upd(capsys, repo, *args)
    assert rc == 0, env
    data: dict[str, Any] = env["data"]
    data["_warnings"] = env.get("warnings", [])
    return data


def fail(capsys: Capsys, repo: Path, code: str, *args: str) -> dict[str, Any]:
    rc, env = upd(capsys, repo, *args)
    assert rc == 2 and env["error"]["code"] == code, env
    error: dict[str, Any] = {**env["error"], "data": env["data"]}
    return error


def lib() -> Path:
    return store.library_root()


def read(repo: Path, rel: str) -> str:
    return (repo / rel).read_text(encoding="utf-8")


def manifest(repo: Path) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(read(repo, MANIFEST_FILE))
    return data


def snapshot(repo: Path) -> dict[str, bytes]:
    return {
        p.relative_to(repo).as_posix(): p.read_bytes()
        for p in repo.rglob("*")
        if p.is_file() and ".git" not in p.relative_to(repo).parts
    }


def write(base: Path, rel: str, text: str) -> None:
    path = base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def commit_all(repo: Path, message: str) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    git(repo, "push", "-q", "origin", "main")


def advance_library(rel: str, text: str | None) -> None:
    """Another machine changed the library: a commit pushed to its remote."""
    if text is None:
        (lib() / rel).unlink()
    else:
        write(lib(), rel, text)
    git(lib(), "add", "-A")
    git(lib(), "commit", "-q", "-m", f"change {rel}")
    git(lib(), "push", "-q", "origin", "main")


def states(capsys: Capsys, repo: Path) -> dict[tuple[str, str], str]:
    rc, env = run_json(capsys, ["config", "items", "--repo", str(repo), "--json"])
    assert rc == 0, env
    return {(i["type"], i["name"]): i["state"] for i in env["data"]["items"]}


def item(data: dict[str, Any], kind: str, name: str) -> dict[str, Any]:
    found: dict[str, Any] = next(
        i for i in data["update"]["items"] if (i["type"], i["name"]) == (kind, name)
    )
    return found


def unit(data: dict[str, Any], kind: str, name: str, file: str) -> dict[str, Any]:
    found: dict[str, Any] = next(f for f in item(data, kind, name)["files"] if f["file"] == file)
    return found


LINES = "".join(f"line {i}\n" for i in range(1, 21))


def multi_line(repo: Path) -> None:
    """The library and the repo both have a 20-line system.md of builder, in sync."""
    advance_library(LIB_SYSTEM, LINES)
    write(repo, SYSTEM, LINES)
    commit_all(repo, "repo takes the multi-line prompt")
    lib_version = manifest_version_of_library()
    _set_manifest_version(repo, lib_version)


def manifest_version_of_library() -> str:
    from aifactory.library.state import library_side

    version = library_side().heads([("agent", "builder")])[("agent", "builder")]
    assert version is not None
    return version


def _set_manifest_version(repo: Path, version: str) -> None:
    data = manifest(repo)
    data["items"]["agents"]["builder"]["version"] = version
    write(repo, MANIFEST_FILE, yaml.safe_dump(data, sort_keys=False))
    commit_all(repo, "manifest at the library version")


# ── the rule (pure) ───────────────────────────────────────────────────────────

A, B, C = (b"a", False), (b"b", False), (b"c", False)


@pytest.mark.parametrize(
    ("b", "o", "t", "options", "expected"),
    [
        (A, A, B, {}, "take"),
        (A, B, A, {}, "keep"),
        (A, B, B, {}, "same"),
        (A, B, C, {}, "conflict"),
        (A, B, C, {"take": True}, "taken"),
        (A, B, C, {"merge": True}, "merged"),
        (A, B, A, {"take": True}, "taken"),
        (None, None, A, {"missing": True}, "restore"),
        (A, None, A, {"missing": True}, "restore"),
        (A, None, A, {}, "keep"),
        (None, A, None, {}, "keep"),
        (None, B, C, {"has_base": False}, "unknown"),
        (None, B, C, {"has_base": False, "take": True}, "taken"),
        (None, B, B, {"has_base": False}, "same"),
    ],
)
def test_unit_rule(b: Any, o: Any, t: Any, options: dict[str, bool], expected: str) -> None:
    has_base = options.pop("has_base", True)
    assert unit_rule(b, o, t, has_base=has_base, **options) == expected


def test_merge_text() -> None:
    merged, conflicts = merge_text("x\nb\nc\n", "a\nb\nc\n", "a\nb\nz\n")
    assert (merged, conflicts) == ("x\nb\nz\n", 0)
    _, conflicts = merge_text("x\n", "a\n", "y\n")
    assert conflicts == 1


def test_m001_detect_apply_idempotent() -> None:
    text = "# levels comment\nlevels: [module, step, task]  # inline\nbase: main\n"
    found = migrations.detected({".factory/config.yaml": text.encode()})
    assert [m.id for m in found] == ["m001"]
    after = found[0].apply(text)
    assert after.startswith("# levels comment\nlevels: [project, step, task]")
    assert "# inline\nbase: main\n" in after
    assert migrations.detected({".factory/config.yaml": after.encode()}) == []
    assert migrations.detected({".factory/config.yaml": b"levels: [project, step, task]\n"}) == []


# ── update ────────────────────────────────────────────────────────────────────


def test_outdated_is_replaced(repo: Path, capsys: Capsys) -> None:
    text = "You build. Always run the tests.\n"
    advance_library(LIB_SYSTEM, text)
    assert states(capsys, repo)[("agent", "builder")] == "outdated"
    data = ok(capsys, repo)
    assert data["written"] and SYSTEM in data["paths"] and MANIFEST_FILE in data["paths"]
    assert unit(data, "agent", "builder", "system.md")["status"] == "take"
    assert item(data, "agent", "builder")["action"] == "update"
    assert read(repo, SYSTEM) == text
    entry = manifest(repo)["items"]["agents"]["builder"]
    assert entry["version"] == manifest_version_of_library()
    assert manifest(repo)["written_by"] == __version__
    assert states(capsys, repo)[("agent", "builder")] == "synced"


def test_repo_change_is_kept(repo: Path, capsys: Capsys) -> None:
    text = read(repo, SYSTEM) + "Repo rule.\n"
    write(repo, SYSTEM, text)
    commit_all(repo, "repo change")
    data = ok(capsys, repo)
    assert unit(data, "agent", "builder", "system.md")["status"] == "keep"
    assert item(data, "agent", "builder")["action"] == "keep"
    assert data["update"]["conflicts"] == []
    assert read(repo, SYSTEM) == text


def test_conflict_kept_then_take(repo: Path, capsys: Capsys) -> None:
    write(repo, SYSTEM, "repo text\n")
    commit_all(repo, "repo change")
    advance_library(LIB_SYSTEM, "library text\n")
    dry = ok(capsys, repo, "--dry-run")
    row = unit(dry, "agent", "builder", "system.md")
    assert row["status"] == "conflict"
    assert not next(i for i in dry["update"]["items"] if i["name"] == "builder")["merge_available"]
    assert "+repo text" in row["ours_diff"] and "+library text" in row["theirs_diff"]
    assert dry["update"]["conflicts"] == ["agent/builder:system.md"]
    assert any(w.startswith("update_conflict:") for w in dry["_warnings"])
    data = ok(capsys, repo)
    assert read(repo, SYSTEM) == "repo text\n"
    assert manifest(repo)["items"]["agents"]["builder"]["version"] == (
        manifest_version_of_library()
    )
    assert states(capsys, repo)[("agent", "builder")] == "modified"
    assert data["written"]
    commit_all(repo, "update")
    # the library moves on again: a new conflict, now taken
    advance_library(LIB_SYSTEM, "library text 2\n")
    taken = ok(capsys, repo, "--take", "agent/builder:system.md")
    assert unit(taken, "agent", "builder", "system.md")["status"] == "taken"
    assert read(repo, SYSTEM) == "library text 2\n"
    assert states(capsys, repo)[("agent", "builder")] == "synced"


def test_merge_clean_and_conflict(repo: Path, capsys: Capsys) -> None:
    multi_line(repo)
    advance_library(LIB_SYSTEM, LINES.replace("line 1\n", "library line 1\n"))
    write(repo, SYSTEM, LINES.replace("line 20\n", "repo line 20\n"))
    commit_all(repo, "repo change")
    preview = ok(capsys, repo, "--dry-run")
    assert next(i for i in preview["update"]["items"] if i["name"] == "builder")["merge_available"]
    data = ok(capsys, repo, "--merge", "agent/builder")
    assert unit(data, "agent", "builder", "system.md")["status"] == "merged"
    text = read(repo, SYSTEM)
    assert "library line 1\n" in text and "repo line 20\n" in text
    commit_all(repo, "merged")
    # both sides edit the same line
    advance_library(LIB_SYSTEM, text.replace("line 10\n", "library line 10\n"))
    write(repo, SYSTEM, text.replace("line 10\n", "repo line 10\n"))
    commit_all(repo, "repo change 2")
    before = snapshot(repo)
    error = fail(capsys, repo, "merge_conflict", "--merge", "agent/builder")
    assert error["data"]["file"] == "system.md" and error["data"]["conflicts"] == 1
    assert snapshot(repo) == before


def test_unknown_item(repo: Path, capsys: Capsys) -> None:
    _set_manifest_version(repo, "sha256:" + "0" * 64)
    advance_library(LIB_SYSTEM, "library text\n")
    data = ok(capsys, repo, "--dry-run")
    assert item(data, "agent", "builder")["state"] == "unknown"
    assert item(data, "agent", "builder")["merge_available"] is False
    row = unit(data, "agent", "builder", "system.md")
    assert row["status"] == "unknown" and "+library text" in row["diff"]
    assert any(w.startswith("update_unknown:") for w in data["_warnings"])
    fail(capsys, repo, "invalid_value", "--merge", "agent/builder")
    before = read(repo, SYSTEM)
    ok(capsys, repo)
    assert read(repo, SYSTEM) == before
    ok(capsys, repo, "--take", "agent/builder")
    assert read(repo, SYSTEM) == "library text\n"


def test_binary_conflict_has_no_merge(repo: Path, capsys: Capsys) -> None:
    # Skills may contain binary assets; both sides change the same unit.
    asset = "skills/lint/asset.bin"
    write(lib(), "skills/lint/SKILL.md", SKILL_MD)
    (lib() / asset).write_bytes(b"\xffbase")
    commit_all(lib(), "binary base")
    rc, env = run_json(
        capsys, ["config", "add", "skill", "lint", "--commit", "--repo", str(repo), "--json"]
    )
    assert rc == 0, env
    for folder in (".claude/skills", ".agents/skills"):
        (repo / folder / "lint/asset.bin").write_bytes(b"\xffours")
    commit_all(repo, "binary repo edit")
    (lib() / asset).write_bytes(b"\xfftheirs")
    commit_all(lib(), "binary library edit")
    data = ok(capsys, repo, "--dry-run")
    assert item(data, "skill", "lint")["merge_available"] is False
    row = unit(data, "skill", "lint", "asset.bin")
    assert row["status"] == "conflict" and row["binary"]


def test_missing_prompt_restored(repo: Path, capsys: Capsys) -> None:
    text = read(repo, USER)
    (repo / USER).unlink()
    commit_all(repo, "lose user.md")
    data = ok(capsys, repo)
    assert unit(data, "agent", "builder", "user.md")["status"] == "restore"
    assert item(data, "agent", "builder")["action"] == "restore"
    assert read(repo, USER) == text


def test_declared_agent_prompt_restored(repo: Path, capsys: Capsys) -> None:
    """A roster agent that is not in the manifest gets its missing prompt back."""
    data = manifest(repo)
    del data["items"]["agents"]["builder"]
    write(repo, MANIFEST_FILE, yaml.safe_dump(data, sort_keys=False))
    text = read(repo, USER)
    (repo / USER).unlink()
    commit_all(repo, "builder is local and lost user.md")
    result = ok(capsys, repo)
    assert result["update"]["restored"] == [
        {"type": "agent", "name": "builder", "files": ["user.md"]}
    ]
    assert read(repo, USER) == text


def test_skill_added_and_deleted_files(repo: Path, capsys: Capsys) -> None:
    write(lib(), "skills/lint/SKILL.md", SKILL_MD)
    write(lib(), "skills/lint/bin/run.sh", "#!/bin/sh\nruff .\n")
    (lib() / "skills/lint/bin/run.sh").chmod(0o755)
    git(lib(), "add", "-A")
    git(lib(), "commit", "-q", "-m", "add lint")
    rc, env = run_json(
        capsys, ["config", "add", "skill", "lint", "--commit", "--repo", str(repo), "--json"]
    )
    assert rc == 0, env
    assert os.access(repo / ".claude/skills/lint/bin/run.sh", os.X_OK)  # materialized as 755
    assert git(repo, "status", "--porcelain") == ""
    write(lib(), "skills/lint/docs/extra.md", "More.\n")
    advance_library("skills/lint/bin/run.sh", None)
    data = ok(capsys, repo)
    assert unit(data, "skill", "lint", "docs/extra.md")["status"] == "take"
    assert unit(data, "skill", "lint", "bin/run.sh")["status"] == "take"
    for top in (".claude/skills", ".agents/skills"):
        assert read(repo, f"{top}/lint/docs/extra.md") == "More.\n"
        assert not (repo / f"{top}/lint/bin/run.sh").exists()
        assert read(repo, f"{top}/lint/SKILL.md") == SKILL_MD
        # Windows reports every existing file executable; verify the planned Git mode there.
        assert (
            next(f for f in data["files"] if f["path"] == f"{top}/lint/docs/extra.md")["mode"]
            == "100644"
        )
        if os.name != "nt":
            assert not os.access(repo / f"{top}/lint/docs/extra.md", os.X_OK)
    assert states(capsys, repo)[("skill", "lint")] == "synced"


def test_m001_keeps_comments(repo: Path, capsys: Capsys) -> None:
    config = repo / ".factory/config.yaml"
    old = config.read_text(encoding="utf-8")
    assert "levels" not in old
    text = old + "# levels comment\nlevels: [module, step, task]  # inline\n"
    write(repo, ".factory/config.yaml", text)
    commit_all(repo, "old levels")
    dry = ok(capsys, repo, "--dry-run")
    [found] = dry["update"]["migrations"]
    assert found["id"] == "m001" and not found["applied"]
    assert "+levels: [project, step, task]" in found["diff"]
    assert any(w.startswith("migration_available: m001") for w in dry["_warnings"])
    ok(capsys, repo)
    assert read(repo, ".factory/config.yaml") == text
    data = ok(capsys, repo, "--migrate", "m001")
    assert data["update"]["migrations"][0]["applied"]
    after = read(repo, ".factory/config.yaml")
    assert after.startswith(old + "# levels comment\nlevels: [project, step, task]")
    assert after.endswith("# inline\n")
    again = ok(capsys, repo, "--dry-run", "--migrate", "m001")
    assert again["update"]["migrations"] == []
    assert any(w.startswith("migration_not_needed: m001") for w in again["_warnings"])
    fail(capsys, repo, "invalid_value", "--migrate", "m999")


def test_second_update_no_change(repo: Path, capsys: Capsys) -> None:
    advance_library(LIB_SYSTEM, "library text\n")
    ok(capsys, repo)
    dry = ok(capsys, repo, "--dry-run")
    assert dry["changed"] is False and dry["paths"] == []
    before = snapshot(repo)
    data = ok(capsys, repo)
    assert data["changed"] is False and not data["written"]
    assert snapshot(repo) == before


def test_commit_with_bare_remote(repo: Path, tmp_path: Path, capsys: Capsys) -> None:
    advance_library(LIB_SYSTEM, "library text\n")
    dry = ok(capsys, repo, "--dry-run", "--commit")
    assert dry["target"] == "direct" and SYSTEM in dry["paths"]
    fail(capsys, repo, "plan_changed", "--commit", "--expect", "0" * 64)
    data = ok(capsys, repo, "--commit", "--expect", dry["digest"])
    assert data["committed"] and data["pushed"]
    bare = tmp_path / "repo-origin.git"
    assert git(bare, "rev-parse", "main") == data["commit"] == git(repo, "rev-parse", "main")
    assert git(bare, "log", "-1", "--format=%s", "main").startswith("factory: update 1 item(s)")
    assert read(repo, SYSTEM) == "library text\n"
    assert git(repo, "status", "--porcelain") == ""


def test_refusals(repo: Path, tmp_path: Path, capsys: Capsys) -> None:
    plain = make_repo(tmp_path, "plain")
    error = fail(capsys, plain, "not_onboarded")
    assert error["data"]["fix"] == "factory init"
    worktree_only = make_repo(tmp_path, "wt")
    rc, env = run_json(capsys, ["init", "--repo", str(worktree_only), "--json"])
    assert rc == 0, env
    fail(capsys, worktree_only, "config_not_committed")
    data = manifest(repo)
    data["format"] = 99
    write(repo, MANIFEST_FILE, yaml.safe_dump(data, sort_keys=False))
    commit_all(repo, "future format")
    fail(capsys, repo, "format_unsupported")


def test_selectors(repo: Path, capsys: Capsys) -> None:
    fail(capsys, repo, "invalid_value", "--take", "agent")
    fail(capsys, repo, "invalid_value", "--merge", "agent/builder:system.md")
    fail(capsys, repo, "unknown_item", "--take", "agent/nobody")
    fail(capsys, repo, "invalid_value", "--take", "agent/builder:nope.md")
    fail(capsys, repo, "conflicting_options", "--take", "agent/builder", "--merge", "agent/builder")


def test_gitignore_lines_added(repo: Path, capsys: Capsys) -> None:
    text = read(repo, ".gitignore")
    assert ".factory/local.yaml" in text
    write(repo, ".gitignore", text.replace(".factory/local.yaml\n", ""))
    commit_all(repo, "drop a line")
    data = ok(capsys, repo)
    assert data["update"]["gitignore"]["added"] == [".factory/local.yaml"]
    assert ".factory/local.yaml" in read(repo, ".gitignore").splitlines()
    assert next(f for f in data["files"] if f["path"] == ".gitignore")["action"] == "modify"


def test_check_reports_update_available(repo: Path, capsys: Capsys) -> None:
    def findings() -> list[dict[str, Any]]:
        rc, env = run_json(capsys, ["check", "--repo", str(repo), "--offline", "--json"])
        found: list[dict[str, Any]] = env["data"]["findings"]
        return [f for f in found if f["code"] == "update_available"]

    assert findings() == []
    advance_library(LIB_SYSTEM, "library text\n")
    [finding] = findings()
    assert finding["action"] == "update" and "agent/builder" in finding["message"]
    ok(capsys, repo, "--commit")
    assert findings() == []


def test_text_output(repo: Path, capsys: Capsys) -> None:
    from aifactory.cli import main

    write(repo, SYSTEM, "repo text\n")
    commit_all(repo, "repo change")
    advance_library(LIB_SYSTEM, "library text\n")
    capsys.readouterr()
    assert main(["update", "--dry-run", "--repo", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "conflict agent/builder" in out and "+library text" in out and "digest" in out
