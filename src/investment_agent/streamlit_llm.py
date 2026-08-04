"""Streamlit sidebar: visitor API key for Themes / Stock research runs."""

from __future__ import annotations

import streamlit as st

from investment_agent.ui_settings import resolve_settings


def render_visitor_llm_sidebar() -> None:
    """Collect optional per-session API key (not persisted on the server)."""
    with st.expander("Your LLM API key (optional)", expanded=False):
        st.caption(
            "Paste **your** key to run analysis/research. "
            "Stored only in this browser session — not written to the server. "
            "Leave empty to use the app owner's secrets (if configured)."
        )
        st.selectbox(
            "Provider",
            ["auto", "gemini", "openai"],
            index=0,
            key="visitor_llm_provider",
            help="auto: detect from key prefix (gsk_/sk-or-/sk- → OpenAI-compatible; else Gemini).",
        )
        st.text_input(
            "API key",
            type="password",
            key="visitor_api_key",
            placeholder="AIza… / gsk_… / sk-…",
            autocomplete="off",
        )
        st.text_input(
            "Model (optional)",
            key="visitor_llm_model",
            placeholder="e.g. gemini-2.0-flash or llama-3.3-70b-versatile",
        )
        st.text_input(
            "Base URL (optional)",
            key="visitor_llm_base_url",
            placeholder="Leave blank unless using a custom endpoint",
        )


def settings_from_sidebar(*, market_region: str = "global"):
    """Build Settings from visitor inputs or env secrets."""
    return resolve_settings(
        visitor_api_key=str(st.session_state.get("visitor_api_key") or ""),
        provider=str(st.session_state.get("visitor_llm_provider") or "auto"),
        model=str(st.session_state.get("visitor_llm_model") or ""),
        base_url=str(st.session_state.get("visitor_llm_base_url") or ""),
        market_region=market_region,
    )


def render_active_llm_caption(*, market_region: str = "global") -> None:
    """Show which key source / model will be used."""
    visitor = str(st.session_state.get("visitor_api_key") or "").strip()
    try:
        s = settings_from_sidebar(market_region=market_region)
        source = "your key" if visitor else "app secrets"
        st.caption(f"LLM: **{s.provider}** / `{s.model}` ({source})")
    except ValueError as e:
        st.warning(str(e))
        st.caption(
            "Add your API key above, or ask the app owner to set Streamlit secrets."
        )
