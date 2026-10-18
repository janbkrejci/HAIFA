"""`just validate --remote azure`: sandbox names, git auth, config, preflight, R3 prerequisites."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from validation.context import Cmd, Context
from validation.results import ScenarioResult
from validation.safety import Owned
from validation.sandbox import AzureRepo, Sandbox, SetupError

from aifactory.config.settings import ProjectSettings
from validation import runner, sandbox, scenarios

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "providers"))

from az_fake import install_fake_az, reply  # noqa: E402

SANDBOX = AzureRepo("https://asolcz.visualstudio.com", "NEO_HEF", "HAIFA-Azure-Sandbox")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://asolcz.visualstudio.com/NEO_HEF/_git/HAIFA-Azure-Sandbox", SANDBOX),
        ("https://asolcz@asolcz.visualstudio.com/NEO_HEF/_git/HAIFA-Azure-Sandbox/", SANDBOX),
        (
            "https://contoso@dev.azure.com/contoso/Fab%20Rikam/_git/app",
            AzureRepo("https://dev.azure.com/contoso", "Fab Rikam", "app"),
        ),
        ("contoso/Fabrikam/app", AzureRepo("https://dev.azure.com/contoso", "Fabrikam", "app")),
    ],
)
def test_normalize_azure_repo_accepts(value: str, expected: AzureRepo) -> None:
    assert sandbox.normalize_azure_repo(f"  {value} ") == expected


@pytest.mark.parametrize(
    "value",
    [None, "", "   ", "owner/name", "https://github.com/a/b", "https://dev.azure.com/org/p/r"],
)
def test_normalize_azure_repo_rejects(value: str | None) -> None:
    with pytest.raises(SetupError, match="HAIFA_AZURE_SANDBOX_REPO"):
        sandbox.normalize_azure_repo(value)


def test_web_url_quotes_project_and_repo() -> None:
    repo = AzureRepo("https://dev.azure.com/contoso", "Fab Rikam", "app")
    assert repo.web_url == "https://dev.azure.com/contoso/Fab%20Rikam/_git/app"


def test_git_auth_resets_the_helpers_and_stores_no_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_DEVOPS_EXT_PAT", "secret-token")
    args = sandbox.git_auth_args()
    assert args[:2] == ["-c", "credential.helper="]
    assert args[2] == "-c"
    helper = args[3].removeprefix("credential.helper=")
    assert sandbox.AZURE_DEVOPS_RESOURCE in helper
    assert "$AZURE_DEVOPS_EXT_PAT" in helper or "${AZURE_DEVOPS_EXT_PAT" in helper
    assert "secret-token" not in helper


@pytest.mark.skipif(sys.platform == "win32", reason="the helper runs through sh")
def test_credential_helper_prints_the_pat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_DEVOPS_EXT_PAT", "pat-123")
    helper = sandbox.azure_credential_helper().removeprefix("!")
    out = subprocess.run(
        ["sh", "-c", f"{helper} get"], capture_output=True, text=True, check=True
    ).stdout
    assert out.splitlines() == ["username=haifa", "password=pat-123"]
    other = subprocess.run(["sh", "-c", f"{helper} store"], capture_output=True, text=True)
    assert other.returncode == 0 and other.stdout == ""


def test_azure_without_sandbox_env_is_a_setup_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"subprocess started: {args}")

    monkeypatch.delenv(sandbox.AZURE_SANDBOX_ENV, raising=False)
    monkeypatch.setattr(runner, "_load_env", lambda: None)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    code = runner.main(
        [
            "--remote",
            "azure",
            "--results-dir",
            str(tmp_path / "results"),
            "--workdir",
            str(tmp_path / "work"),
        ]
    )
    assert code == runner.EXIT_SETUP
    assert "HAIFA_AZURE_SANDBOX_REPO" in capsys.readouterr().err
    assert not (tmp_path / "results").exists()
    assert not (tmp_path / "work").exists()


# ── config ───────────────────────────────────────────────────────────────────


def _config(tmp_path: Path, provider: str, azure: AzureRepo | None = None) -> dict[str, Any]:
    sandbox.materialize(tmp_path, "haifa-validate/x", provider, azure=azure)
    loaded = yaml.safe_load((tmp_path / ".factory" / "config.yaml").read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_azure_config_names_the_sandbox(tmp_path: Path) -> None:
    repo = AzureRepo("https://dev.azure.com/contoso", "Fab Rikam: x", "app")
    settings = ProjectSettings.model_validate(_config(tmp_path, "azure", repo))
    assert settings.git_provider == "azure"
    assert settings.azure is not None
    assert settings.azure.organization_url == "https://dev.azure.com/contoso"
    assert (settings.azure.project, settings.azure.repository) == ("Fab Rikam: x", "app")


@pytest.mark.parametrize("provider", ["local", "github"])
def test_other_providers_render_no_azure_section(tmp_path: Path, provider: str) -> None:
    config = _config(tmp_path, provider)
    assert "azure" not in config
    assert ProjectSettings.model_validate(config).git_provider == provider


# ── preflight ────────────────────────────────────────────────────────────────


@pytest.fixture
def no_side_checks(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []
    monkeypatch.setattr(runner, "_require_just", lambda: seen.append("just"))
    monkeypatch.setattr(runner, "_preflight_harnesses", lambda roster: seen.append("harness"))
    return seen


def test_preflight_azure_needs_az_login(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_side_checks: list[str]
) -> None:
    install_fake_az(
        tmp_path,
        monkeypatch,
        {"account show": reply(exit=1, stderr="ERROR: Please run 'az login' to setup account.")},
    )
    with pytest.raises(SetupError, match="az login"):
        runner.preflight_azure(SANDBOX.web_url)
    assert "harness" not in no_side_checks


def test_preflight_azure_needs_the_sandbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_side_checks: list[str]
) -> None:
    log = install_fake_az(
        tmp_path,
        monkeypatch,
        {
            "account show": reply({"user": {"name": "me"}}),
            "repos show": reply(
                exit=1, stderr="ERROR: TF200016: The following project does not exist: NEO_HEF."
            ),
        },
    )
    with pytest.raises(SetupError, match="TF200016"):
        runner.preflight_azure(SANDBOX.web_url)
    shown = [a for a in log.argvs() if a[:2] == ["repos", "show"]]
    assert shown and shown[0][2:8] == SANDBOX.repo_args()
    assert "harness" not in no_side_checks


def test_preflight_azure_checks_git_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_side_checks: list[str]
) -> None:
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    install_fake_az(
        tmp_path,
        monkeypatch,
        {
            "account show": reply({"user": {"name": "me"}}),
            "repos show": reply({"remoteUrl": str(bare), "defaultBranch": "refs/heads/main"}),
        },
    )
    assert runner.preflight_azure(SANDBOX.web_url) == SANDBOX
    assert no_side_checks == ["just", "harness"]

    missing = tmp_path / "missing.git"
    install_fake_az(
        tmp_path,
        monkeypatch,
        {
            "account show": reply({"user": {"name": "me"}}),
            "repos show": reply({"remoteUrl": str(missing)}),
        },
    )
    with pytest.raises(SetupError, match="git cannot authenticate"):
        runner.preflight_azure(SANDBOX.web_url)


# ── R3 prerequisites ─────────────────────────────────────────────────────────


def _cmd(task: str, ok: bool = True) -> Cmd:
    data: dict[str, Any] = {
        "ok": ok,
        "data": {
            "run": {"run_id": f"run-{task}", "state": "succeeded" if ok else "failed"},
            "pr": {"url": f"https://example.invalid/{task}", "pr_id": "1", "branch": "b"}
            if ok
            else {},
        },
    }
    return Cmd(["task", "run", task], 0 if ok else 1, data, Path("x.log"))


def _context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ok: bool
) -> tuple[Context, list[str]]:
    ctx = Context(
        "azure", Sandbox("azure", tmp_path, "base", "url", azure=SANDBOX), tmp_path, Owned()
    )
    ran: list[str] = []

    def run_task(task_id: str, *extra: str, variant: str = "happy", fake: bool = False) -> Cmd:
        ran.append(task_id)
        return _cmd(task_id, ok)

    monkeypatch.setattr(ctx, "run_task", run_task)
    monkeypatch.setattr(ctx, "catch_up_base", lambda: None)
    return ctx, ran


def test_r3_runs_r10_and_r1_when_they_are_not_selected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, ran = _context(tmp_path, monkeypatch, ok=True)
    ctx.selected = ["R2", "RESOLVE", "R3", "F2"]
    st = scenarios.R3Run(ScenarioResult("R3", "azure"))
    assert scenarios._r3_prerequisites(ctx, st) is True
    assert ran == [scenarios.R10_TASK, scenarios.R1_TASK]
    assert ctx.state["R10"]["task"] == scenarios.R10_TASK
    assert ctx.state["R1"]["pr"]["url"].endswith(scenarios.R1_TASK)
    assert ctx.state["R1"]["run"]["run_id"] == f"run-{scenarios.R1_TASK}"
    assert st.res.checks == []


def test_r3_does_not_rerun_selected_scenarios(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, ran = _context(tmp_path, monkeypatch, ok=True)
    ctx.selected = ["R1", "R10", "R3"]  # selected, but failed: nothing in ctx.state
    st = scenarios.R3Run(ScenarioResult("R3", "azure"))
    scenarios._r3_prerequisites(ctx, st)
    assert ran == []
    assert "R1" not in ctx.state and "R10" not in ctx.state


def test_r3_failed_prerequisite_is_a_failed_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, ran = _context(tmp_path, monkeypatch, ok=False)
    ctx.selected = ["R3"]
    st = scenarios.R3Run(ScenarioResult("R3", "azure"))
    scenarios._r3_prerequisites(ctx, st)
    assert ran == [scenarios.R10_TASK, scenarios.R1_TASK]
    assert [c.name for c in st.res.checks] == [
        f"prerequisite_{scenarios.R10_TASK}",
        f"prerequisite_{scenarios.R1_TASK}",
    ]
    assert not any(c.ok for c in st.res.checks)
    assert "R1" not in ctx.state
