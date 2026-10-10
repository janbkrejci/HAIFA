"""``.factory/manifest.yaml``: model, read and write, load_config, format gate, D4 (L4)."""

from __future__ import annotations

from pathlib import Path

import pytest
from config_repo import commit_all, git, make_repo, write

from aifactory.config import (
    MANIFEST_FILE,
    CommitSource,
    ConfigError,
    LibraryRef,
    Manifest,
    ManifestEntry,
    ManifestItems,
    Onboarding,
    WorktreeSource,
    config_changes,
    dump_manifest,
    load_config,
    load_run_config,
    parse_manifest,
    read_manifest,
    resolve_commit,
    write_manifest,
)
from aifactory.config.status import is_shared_config_path
from cli_json import run_json

Capsys = pytest.CaptureFixture[str]

VERSION = "sha256:" + "a" * 64


def sample() -> Manifest:
    return Manifest(
        written_by="0.2.0",
        library=LibraryRef(id="2f6c0b1e", name="helios", remote=None),
        onboarding=Onboarding(
            source="init",
            source_commit="78db8bf",
            at="2026-10-02T18:40:12Z",
            by="Jan",
            factory="0.2.0",
            library_commit="1a2b3c4",
        ),
        items=ManifestItems(
            agents={"builder": ManifestEntry(item="builder-jsst", version=VERSION)},
            workflows={"plan-build": ManifestEntry(item="plan-build", version=VERSION)},
        ),
    )


def test_write_and_read_round_trip(tmp_path: Path) -> None:
    manifest = sample()
    path = write_manifest(tmp_path, manifest)
    assert path == tmp_path / MANIFEST_FILE
    assert read_manifest(tmp_path) == manifest
    text = dump_manifest(manifest)
    assert text.splitlines()[0] == "format: 1"
    assert list(parse_manifest(text, "m").to_json()) == [
        "format",
        "written_by",
        "library",
        "onboarding",
        "items",
    ]
    assert manifest.entry("agent", "builder") == ManifestEntry(item="builder-jsst", version=VERSION)
    assert manifest.entry("skill", "x") is None


def test_no_manifest_is_format_zero(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    assert read_manifest(repo) is None
    config = load_config(WorktreeSource(repo))
    assert config.manifest is None
    assert MANIFEST_FILE not in config.files


def test_load_config_reads_manifest_into_digest(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    before = load_config(WorktreeSource(repo)).digest
    write_manifest(repo, sample())
    config = load_config(WorktreeSource(repo))
    assert config.manifest == sample()
    assert config.digest != before
    sha = commit_all(repo, "manifest")
    committed = load_config(CommitSource(repo, "main", sha))
    assert committed.manifest == sample()


def test_newer_format_is_refused(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write(repo, MANIFEST_FILE, "format: 2\nwritten_by: 9.0.0\nfuture: {}\n")
    with pytest.raises(ConfigError) as exc:
        load_config(WorktreeSource(repo))
    assert exc.value.code == "format_unsupported"
    assert "factory upgrade" in str(exc.value)
    assert "aifactory" in str(exc.value)


@pytest.mark.parametrize("source", ["sssf", "pre_library"])
def test_legacy_onboarding_source_still_loads(source: str) -> None:
    text = (
        "format: 1\nwritten_by: 0.1.0\nonboarding:\n"
        f"  source: {source}\n  at: '2026-10-01T10:00:00Z'\n  factory: 0.1.0\n"
    )
    manifest = parse_manifest(text, "m")
    assert manifest.onboarding is not None and manifest.onboarding.source == source


def test_invalid_manifest_is_invalid_config(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write(repo, MANIFEST_FILE, "format: 1\nwritten_by: x\nonboarding: {source: other}\n")
    with pytest.raises(ConfigError) as exc:
        load_config(WorktreeSource(repo))
    assert exc.value.code == "invalid_config"
    assert any("onboarding" in i.message for i in exc.value.issues)


def test_cli_reports_format_unsupported(
    tmp_path: Path, capsys: Capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path / "repo")
    write(repo, MANIFEST_FILE, "format: 2\nwritten_by: 9.0.0\n")
    commit_all(repo, "future manifest")
    monkeypatch.chdir(repo)
    rc, obj = run_json(capsys, ["config", "show", "--json"])
    assert rc == 2
    assert obj["error"]["code"] == "format_unsupported"
    assert "factory upgrade" in obj["error"]["message"]


def test_manifest_is_shared_config_with_d4_warning(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    assert is_shared_config_path(MANIFEST_FILE)
    write_manifest(repo, sample())
    sha = resolve_commit(repo, "main")
    assert [c.path for c in config_changes(repo, sha)] == [MANIFEST_FILE]
    run = load_run_config(repo)
    assert run.config.manifest is None
    assert any(MANIFEST_FILE in w and "untracked" in w for w in run.warnings)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "manifest")
    assert load_run_config(repo).config.manifest == sample()
