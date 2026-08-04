"""Single-stock research standalone entry (optional).

Prefer the unified dashboard: ``streamlit run streamlit_app.py`` → View → Stock.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from investment_agent.stock_research.streamlit_ui import standalone_main

if __name__ == "__main__":
    standalone_main()
