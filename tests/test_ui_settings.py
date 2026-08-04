"""Tests for visitor API key → Settings."""

import pytest

from investment_agent.config import GEMINI_OPENAI_BASE_URL, GROQ_BASE_URL
from investment_agent.ui_settings import resolve_settings, settings_from_api_key


def test_settings_from_groq_key() -> None:
    s = settings_from_api_key("gsk_testkey123", market_region="US")
    assert s.provider == "openai"
    assert s.base_url == GROQ_BASE_URL
    assert s.market_region == "US"
    assert s.api_key.startswith("gsk_")


def test_settings_from_gemini_key_auto() -> None:
    s = settings_from_api_key("AIzaSyDummyKey", provider="auto")
    assert s.provider == "gemini"
    assert s.base_url == GEMINI_OPENAI_BASE_URL


def test_settings_explicit_openai_model() -> None:
    s = settings_from_api_key(
        "sk-test",
        provider="openai",
        model="gpt-4o-mini",
        base_url="https://api.openai.com/v1",
    )
    assert s.provider == "openai"
    assert s.model == "gpt-4o-mini"


def test_resolve_prefers_visitor_key(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError):
        resolve_settings()
    s = resolve_settings(visitor_api_key="gsk_abc", market_region="global")
    assert s.api_key == "gsk_abc"
