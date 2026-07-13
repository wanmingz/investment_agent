"""My portfolio (manual ledger) — real holdings vs theme brief."""

from investment_agent.portfolio.manual.theme_alignment import compute_theme_alignment

LEDGER = "manual"
VIEW_LABEL = "My portfolio"

__all__ = ["LEDGER", "VIEW_LABEL", "compute_theme_alignment"]
