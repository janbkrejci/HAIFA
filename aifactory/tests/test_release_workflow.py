"""The retained HAIFA source must never publish from pushes or an unapproved dispatch."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from bundle.release import check_transition


@pytest.fixture
def gate(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    for name, value in {
        "GITHUB_REPOSITORY": "janbkrejci/HAIFA",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/tags/haifa-transition-acl-source",
        "GITHUB_SHA": "a" * 40,
        "HAIFA_TRANSITION_HOTFIX_SHA": "a" * 40,
        "HAIFA_TRANSITION_HOTFIX_PUBLISHED": "false",
        "HAIFA_TRANSITION_SHA": "b" * 40,
        "HAIFA_TRANSITION_PUBLISHED": "true",
        "GITHUB_RUN_NUMBER": "700",
    }.items():
        monkeypatch.setenv(name, value)
    data: dict[str, Any] = {
        "published": "",
        "original": "b" * 40 + "\trefs/tags/haifa-transition-published",
        "ancestor": True,
        "giro": {
            "tag_name": "v1.0.1",
            "assets": [
                {
                    "name": "giro-1.0.1.zip",
                    "browser_download_url": "https://github.com/janbkrejci/GIRO/releases/download/v1.0.1/giro-1.0.1.zip",
                }
            ],
        },
        "haifa": {"tag_name": "v0.1.699"},
    }

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert kwargs["check"] is True
        if argv[0] == "git":
            if argv[1] == "merge-base":
                assert argv[2:] == ["--is-ancestor", "b" * 40, "a" * 40]
                if not data["ancestor"]:
                    raise subprocess.CalledProcessError(1, argv)
                return subprocess.CompletedProcess(argv, 0, "")
            if argv[-1] == "refs/tags/haifa-transition-published":
                return subprocess.CompletedProcess(argv, 0, data["original"])
            assert argv[-1] == "refs/tags/haifa-transition-acl-published"
            return subprocess.CompletedProcess(argv, 0, data["published"])
        return subprocess.CompletedProcess(
            argv, 0, json.dumps(data["giro" if "GIRO" in argv[-1] else "haifa"])
        )

    monkeypatch.setattr(subprocess, "run", run)
    return data


def test_approved_source_with_giro_available(gate: dict[str, Any]) -> None:
    check_transition()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("GITHUB_REPOSITORY", "other/HAIFA"),
        ("GITHUB_REPOSITORY", "janbkrejci/GIRO"),
        ("GITHUB_EVENT_NAME", "push"),
        ("GITHUB_REF", "refs/heads/main"),
        ("HAIFA_TRANSITION_HOTFIX_SHA", ""),
        ("GITHUB_SHA", "b" * 40),
        ("HAIFA_TRANSITION_HOTFIX_PUBLISHED", "true"),
        ("HAIFA_TRANSITION_HOTFIX_PUBLISHED", ""),
        ("HAIFA_TRANSITION_SHA", ""),
        ("HAIFA_TRANSITION_PUBLISHED", "false"),
        ("HAIFA_TRANSITION_PUBLISHED", ""),
        ("GITHUB_REF", "refs/tags/haifa-transition-source"),
    ],
)
def test_rejects_unapproved_dispatch(
    gate: dict[str, Any], monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        check_transition()


@pytest.mark.parametrize(
    "failure", ["published", "draft", "prerelease", "version", "asset", "downgrade"]
)
def test_release_gate_fails_closed(gate: dict[str, Any], failure: str) -> None:
    if failure == "published":
        gate["published"] = "already claimed"
    elif failure in {"draft", "prerelease"}:
        gate["giro"][failure] = True
    elif failure == "version":
        gate["giro"]["tag_name"] = "v0.1.999"
    elif failure == "asset":
        gate["giro"]["assets"] = []
    else:
        gate["haifa"]["tag_name"] = "v0.1.700"
    with pytest.raises(ValueError):
        check_transition()


def test_network_failure_cannot_open_gate(
    gate: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: Any, **kwargs: Any) -> Any:
        raise subprocess.CalledProcessError(1, "gh")

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        check_transition()


@pytest.mark.parametrize("failure", ["missing_original", "changed_original", "unrelated_source"])
def test_hotfix_requires_preserved_original(gate: dict[str, Any], failure: str) -> None:
    if failure == "missing_original":
        gate["original"] = ""
    elif failure == "changed_original":
        gate["original"] = "c" * 40 + "\trefs/tags/haifa-transition-published"
    else:
        gate["ancestor"] = False
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        check_transition()


def test_workflow_only_dispatches_preserved_source_and_claims_once() -> None:
    workflow = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml").read_text()
    )
    assert (workflow.get("on") or workflow[True]) == {"workflow_dispatch": None}
    job = workflow["jobs"]["release"]
    assert "github.repository == 'janbkrejci/HAIFA'" in job["if"]
    assert "refs/tags/haifa-transition-acl-source" in job["if"]
    assert "vars.HAIFA_TRANSITION_HOTFIX_SHA" in job["if"]
    assert "vars.HAIFA_TRANSITION_HOTFIX_PUBLISHED == 'false'" in job["if"]
    assert "vars.HAIFA_TRANSITION_PUBLISHED == 'true'" in job["if"]
    steps = job["steps"]
    assert steps[0]["with"]["ref"] == "${{ vars.HAIFA_TRANSITION_HOTFIX_SHA }}"
    assert sum("--check-transition" in s.get("run", "") for s in steps) == 2
    publish = next(s["run"] for s in steps if s.get("name") == "Publish completed release")
    assert (
        publish.index("--check-transition")
        < publish.index("git push")
        < publish.index("gh release create")
    )
    assert "haifa-$VERSION.zip" in publish and "giro-$VERSION.zip" not in publish
    assert 'git tag haifa-transition-acl-published "$GITHUB_SHA"' in publish
    assert "git tag haifa-transition-published " not in publish
