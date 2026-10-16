"""Each harness adapter recognizes an exhausted quota of its own CLI: failure_kind quota."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from harness_fakes import NAMES, agent_phase, fake_popen, make_env, start_run

from aifactory import failure
from aifactory.engine import agent_cc, agent_pi
from aifactory.engine.data_types import AgentRequest
from aifactory.harness import codex


def _jsonl(*events: dict[str, Any]) -> str:
    return "".join(json.dumps(event) + "\n" for event in events)


CLAUDE_LIMIT = "You've hit your limit · resets 3pm (Europe/Prague)"
QUOTA_STREAMS = {
    # claude: the assistant event carries a typed API error, the result is an error
    "claude": _jsonl(
        {"type": "system", "subtype": "init", "session_id": "s"},
        {
            "type": "assistant",
            "message": {"role": "assistant", "content": [{"type": "text", "text": CLAUDE_LIMIT}]},
            "error": "rate_limit",
        },
        {"type": "result", "subtype": "success", "is_error": True, "result": CLAUDE_LIMIT},
    ),
    "codex": _jsonl(
        {"type": "thread.started", "thread_id": "019a0000-0000-7000-8000-000000000003"},
        {"type": "turn.started"},
        {
            "type": "turn.failed",
            "error": {"message": "You've hit your usage limit. Try again in 3 days."},
        },
    ),
    # pi: a 429 that is a quota, not a throttle; it must not be waited out
    "pi": _jsonl(
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [],
                "stopReason": "error",
                "errorMessage": "429 You exceeded your current quota, please check your plan "
                "and billing details.",
            },
        }
    ),
}


@pytest.mark.parametrize("name", NAMES)
def test_quota_fails_the_phase_with_kind_quota(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    env = make_env(tmp_path, monkeypatch, name)
    spawner = fake_popen(monkeypatch, [QUOTA_STREAMS[name]], returncode=1)
    monkeypatch.setattr(
        "aifactory.engine.agent_pi.time.sleep", lambda s: pytest.fail("quota was waited out")
    )

    with pytest.raises(failure.QuotaExhausted) as raised:
        agent_phase(start_run(env), "builder")

    kind, detail = failure.classify(raised.value)
    assert kind == failure.QUOTA
    assert detail["harness"] == name
    assert detail["message"]
    # the engine adds who ran out: the failure card shows the harness and the model
    assert detail["agent"] == "builder"
    assert detail["model"]
    # no JSON correction rounds: one spawn, the quota is not the model's fault
    assert len(spawner.calls) == 1


def test_claude_credit_balance_without_typed_error_is_quota(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_env(tmp_path, monkeypatch, "claude")
    text = "Credit balance is too low"
    fake_popen(
        monkeypatch,
        [
            _jsonl(
                {"type": "system", "subtype": "init", "session_id": "s"},
                {"type": "result", "subtype": "success", "is_error": True, "result": text},
            )
        ],
        returncode=1,
    )
    with pytest.raises(failure.QuotaExhausted, match="Credit balance"):
        agent_cc.run(_claude_request(tmp_path))


def test_claude_other_error_is_not_quota(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    make_env(tmp_path, monkeypatch, "claude")
    text = "API Error: 500 internal server error"
    fake_popen(
        monkeypatch,
        [
            _jsonl(
                {"type": "system", "subtype": "init", "session_id": "s"},
                {"type": "result", "subtype": "success", "is_error": True, "result": text},
            )
        ],
        returncode=1,
    )
    result = agent_cc.run(_claude_request(tmp_path))
    assert result.text == text


def test_quota_text_in_a_successful_turn_is_not_quota(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_env(tmp_path, monkeypatch, "claude")
    answer = json.dumps({"status": "success", "summary": "documented the usage limit"})
    fake_popen(
        monkeypatch,
        [
            _jsonl(
                {"type": "system", "subtype": "init", "session_id": "s"},
                {"type": "result", "subtype": "success", "is_error": False, "result": answer},
            )
        ],
    )
    assert agent_cc.run(_claude_request(tmp_path)).text == answer


@pytest.mark.parametrize(
    ("module", "text", "expected"),
    [
        (agent_cc, "Claude AI usage limit reached|1760000000", True),
        (agent_cc, "API Error: 529 overloaded", False),
        (codex, "ERROR: insufficient_quota", True),
        (codex, "model gpt-5.5 is not available", False),
        (agent_pi, "This request requires more credits", True),
        (agent_pi, "429 rate limit, retry later", False),
    ],
)
def test_adapter_recognizes_its_quota_messages(module: Any, text: str, expected: bool) -> None:
    assert module.quota_exhausted(text) is expected


def _claude_request(tmp_path: Path) -> AgentRequest:
    return AgentRequest(
        prompt="go",
        system_prompt="system",
        model="sonnet",
        thinking="high",
        session_id="sssf-adw1-builder-abc",
        session_dir=str(tmp_path / "sessions"),
        raw_output_path=str(tmp_path / "raw_output.jsonl"),
        cwd=str(tmp_path / "repo"),
    )
