"""Build Settings from env and/or a visitor-supplied API key (Streamlit session)."""

from __future__ import annotations

from dataclasses import replace

from investment_agent.config import (
    GEMINI_DEFAULT_MODEL,
    GEMINI_OPENAI_BASE_URL,
    Settings,
    _resolve_openai_compat,
    env_str,
)


def settings_from_api_key(
    api_key: str,
    *,
    provider: str = "auto",
    model: str = "",
    base_url: str = "",
    market_region: str = "global",
) -> Settings:
    """Construct Settings from a pasted key (Gemini / Groq / OpenRouter / OpenAI)."""
    key = api_key.strip()
    if not key:
        raise ValueError("API key is empty.")

    prov = (provider or "auto").strip().lower()
    model = (model or "").strip()
    base_url = (base_url or "").strip()

    if prov in ("", "auto"):
        if key.startswith(("gsk_", "sk-or-", "sk-")):
            inferred_base, inferred_model = _resolve_openai_compat(key)
            return Settings._with_news(
                api_key=key,
                base_url=base_url or inferred_base,
                model=model or inferred_model,
                market_region=market_region,
                provider="openai",
            )
        return Settings._with_news(
            api_key=key,
            base_url=base_url or GEMINI_OPENAI_BASE_URL,
            model=model or env_str("GEMINI_MODEL", GEMINI_DEFAULT_MODEL),
            market_region=market_region,
            provider="gemini",
        )

    if prov in ("gemini", "google"):
        return Settings._with_news(
            api_key=key,
            base_url=base_url or GEMINI_OPENAI_BASE_URL,
            model=model or env_str("GEMINI_MODEL", GEMINI_DEFAULT_MODEL),
            market_region=market_region,
            provider="gemini",
        )

    # openai-compatible (OpenAI, Groq, OpenRouter, …)
    inferred_base, inferred_model = _resolve_openai_compat(key)
    return Settings._with_news(
        api_key=key,
        base_url=base_url or inferred_base,
        model=model or inferred_model,
        market_region=market_region,
        provider="openai",
    )


def resolve_settings(
    *,
    visitor_api_key: str = "",
    provider: str = "auto",
    model: str = "",
    base_url: str = "",
    market_region: str = "global",
) -> Settings:
    """Prefer visitor key; otherwise fall back to server/.env secrets."""
    if visitor_api_key.strip():
        return settings_from_api_key(
            visitor_api_key,
            provider=provider,
            model=model,
            base_url=base_url,
            market_region=market_region,
        )
    settings = Settings.from_env()
    if market_region and market_region != settings.market_region:
        return replace(settings, market_region=market_region)
    return settings
