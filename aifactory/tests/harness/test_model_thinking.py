import pytest

from aifactory.harness import codex, thinking


def test_codex_uses_cached_model_capabilities(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        thinking,
        "codex_models",
        lambda: [
            {
                "slug": "custom",
                "supported_reasoning_levels": [{"effort": "low"}, {"effort": "ultra"}],
            }
        ],
    )
    assert thinking.levels("codex", "openai/custom") == ["low", "ultra"]
    assert codex.reasoning_effort("custom", "ultra") == "ultra"
    assert thinking.levels("codex", "gpt-5.5") == ["low", "medium", "high", "xhigh"]


def test_claude_model_specific_levels() -> None:
    assert thinking.levels("claude", "opus") == ["low", "medium", "high", "xhigh", "max"]
    assert thinking.levels("claude", "claude-opus-4-6") == ["low", "medium", "high", "max"]
    assert thinking.levels("claude", "claude-opus-4-5") == ["low", "medium", "high"]
    assert thinking.levels("claude", "claude-haiku-4-5") == []


def test_pi_uses_installed_sdk_levels_and_nonreasoning_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        thinking, "pi_levels", lambda _: {"anthropic/opus": ["low", "medium", "high", "max"]}
    )
    monkeypatch.setattr(
        thinking, "pi_reasoning", lambda _: {"custom/plain": False, "custom/reasoner": True}
    )
    assert thinking.levels("pi", "anthropic/opus") == ["low", "medium", "high", "max"]
    assert thinking.levels("pi", "custom/plain") == ["off"]
    assert thinking.levels("pi", "custom/reasoner") == ["off", "minimal", "low", "medium", "high"]


def test_model_defaults_and_true_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        thinking,
        "codex_models",
        lambda: [
            {
                "slug": "custom",
                "default_reasoning_level": "none",
                "supported_reasoning_levels": [{"effort": "none"}, {"effort": "high"}],
            }
        ],
    )
    assert thinking.default_level("claude", "opus") == "medium"
    assert thinking.default_level("claude", "sonnet") == "high"
    assert thinking.default_level("codex", "custom") == "off"
    assert thinking.levels("codex", "custom") == ["off", "high"]
    assert codex.reasoning_effort("custom", "off") == "none"
    with pytest.raises(ValueError, match="not supported"):
        thinking.validate("claude", "opus", "off")
