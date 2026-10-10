"""`.factory/config.yaml` and `.factory/local.yaml`: defaults and validation with paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from aifactory.config import (
    ConfigError,
    LocalSettings,
    WorktreeSource,
    load_config,
    load_local,
    load_local_checked,
)
from aifactory.config.errors import ConfigIssue
from aifactory.config.settings import CONFIG_FILE, ProjectSettings, parse_project_settings


def _settings(root: Path) -> ProjectSettings:
    source = WorktreeSource(root)
    issues: list[ConfigIssue] = []
    settings = parse_project_settings(
        source.read_text(CONFIG_FILE), source.label(CONFIG_FILE), issues
    )
    if settings is None:
        raise ConfigError(issues)
    return settings


def test_missing_files_give_defaults(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    local = load_local(tmp_path)
    assert settings.base == "main"
    assert settings.levels == ("project", "step", "task")
    assert not hasattr(local, "port")
    assert local.trace_db == ".factory/trace.db"
    assert local.trace_db_path(tmp_path) == (tmp_path / ".factory/trace.db").resolve()


def test_empty_files_give_defaults(tmp_path: Path) -> None:
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory/config.yaml").write_text("", encoding="utf-8", newline="\n")
    (tmp_path / ".factory/local.yaml").write_text("", encoding="utf-8", newline="\n")
    assert _settings(tmp_path) == ProjectSettings()
    assert load_local(tmp_path) == LocalSettings()


def test_custom_values(tmp_path: Path) -> None:
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory/config.yaml").write_text(
        "base: develop\nlevels: [epic, task]\ngit_provider: github\n"
        "merge_strategy: merge\ntest_command: dotnet test --no-build\nworkdir: app\n",
        encoding="utf-8",
        newline="\n",
    )
    elsewhere = tmp_path.parent / "t.db"
    (tmp_path / ".factory/local.yaml").write_text(
        f"trace_db: {elsewhere.as_posix()}\n", encoding="utf-8", newline="\n"
    )
    settings = _settings(tmp_path)
    assert settings.base == "develop"
    assert settings.levels == ("epic", "task")
    assert settings.git_provider == "github"
    assert settings.merge_strategy == "merge"
    assert not hasattr(settings, "test_command")  # obsolete key, dropped silently
    assert settings.workdir == "app"
    local = load_local(tmp_path)
    assert local.trace_db_path(tmp_path) == elsewhere


@pytest.mark.parametrize(
    "text",
    [
        "base: [unclosed\n",
        "- a\n- b\n",
        "levels: [task]\n",
        "backlog_dir: /abs/backlog\n",
        "git_provider: svn\n",
        "bsae: main\n",
        "port: 4700\n",
    ],
)
def test_invalid_config_names_the_file(tmp_path: Path, text: str) -> None:
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory/config.yaml").write_text(text, encoding="utf-8", newline="\n")
    with pytest.raises(ConfigError) as info:
        _settings(tmp_path)
    assert str(tmp_path / ".factory/config.yaml") in str(info.value)


def test_port_in_config_points_to_local(tmp_path: Path) -> None:
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory/config.yaml").write_text(
        "trace_db: x.db\n", encoding="utf-8", newline="\n"
    )
    with pytest.raises(ConfigError, match="machine-local; put it in .factory/local.yaml"):
        _settings(tmp_path)


@pytest.mark.parametrize("text", ["trace_db: ''\n", "trace_db: 5\n", "colour: red\n"])
def test_invalid_local_names_the_file(tmp_path: Path, text: str) -> None:
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory/local.yaml").write_text(text, encoding="utf-8", newline="\n")
    with pytest.raises(ConfigError) as info:
        load_local(tmp_path)
    assert str(tmp_path / ".factory/local.yaml") in str(info.value)


def test_port_in_config_is_the_dashboards(tmp_path: Path) -> None:
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory/config.yaml").write_text("port: 4700\n", encoding="utf-8", newline="\n")
    with pytest.raises(ConfigError, match="'port' is the dashboard's"):
        _settings(tmp_path)


@pytest.mark.parametrize("text", ["port: 4811\n", "port: 0\n", "port: abc\ntrace_db: x.db\n"])
def test_old_local_port_is_ignored_with_a_warning(tmp_path: Path, text: str) -> None:
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory/local.yaml").write_text(text, encoding="utf-8", newline="\n")
    local, warnings = load_local_checked(tmp_path)
    assert load_local(tmp_path) == local
    assert len(warnings) == 1 and warnings[0].startswith("local_port_ignored: ")
    assert load_local_checked(tmp_path / "nowhere")[1] == []


def test_test_timeout_defaults_to_none_and_loads(tmp_path: Path) -> None:
    assert _settings(tmp_path).test_timeout is None
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory/config.yaml").write_text(
        "test_timeout: 1800\n", encoding="utf-8", newline="\n"
    )
    assert _settings(tmp_path).test_timeout == 1800


@pytest.mark.parametrize("value", ["0", "-1", '"1800"', "true", "1.5"])
def test_invalid_test_timeout_is_reported(tmp_path: Path, value: str) -> None:
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory/config.yaml").write_text(
        f"test_timeout: {value}\n", encoding="utf-8", newline="\n"
    )
    with pytest.raises(ConfigError) as info:
        _settings(tmp_path)
    assert "test_timeout" in str(info.value)
    with pytest.raises(ConfigError, match="test_timeout"):
        load_config(WorktreeSource(tmp_path))


def test_max_parallel_runs_defaults_to_one_and_loads(tmp_path: Path) -> None:
    assert _settings(tmp_path).max_parallel_runs == 1
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory/config.yaml").write_text(
        "max_parallel_runs: 3\n", encoding="utf-8", newline="\n"
    )
    assert _settings(tmp_path).max_parallel_runs == 3


@pytest.mark.parametrize("value", ["0", "-1", '"2"', "true", "1.5"])
def test_invalid_max_parallel_runs_is_reported(tmp_path: Path, value: str) -> None:
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory/config.yaml").write_text(
        f"max_parallel_runs: {value}\n", encoding="utf-8", newline="\n"
    )
    with pytest.raises(ConfigError, match="max_parallel_runs"):
        _settings(tmp_path)
