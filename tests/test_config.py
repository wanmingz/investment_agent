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
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-groq")
    monkeypatch.setenv("OPENAI_MODEL", "")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    s = Settings.from_env()
    assert s.provider == "openai"
    assert s.model == "gpt-4o"
    assert "api.openai.com" in s.base_url


def test_settings_groq_key_infers_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "gsk_test_key")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    s = Settings.from_env()
    assert s.provider == "openai"
    assert "groq.com" in s.base_url
    assert s.model == "llama-3.3-70b-versatile"
    assert s.rag_top_k == 5
