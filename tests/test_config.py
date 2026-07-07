"""Config env helpers."""

import os

import pytest

from investment_agent.config import Settings, env_int, env_str


def test_env_int_empty_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWS_MAX_ARTICLES", "")
    assert env_int("NEWS_MAX_ARTICLES", 40) == 40


def test_env_str_empty_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_MODEL", "")
    assert env_str("OPENAI_MODEL", "gpt-4o") == "gpt-4o"


def test_settings_openai_blank_model_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    s = Settings.from_env()
    assert s.provider == "openai"
    assert s.model == "gpt-4o"
