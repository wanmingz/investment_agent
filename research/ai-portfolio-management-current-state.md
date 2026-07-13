# AI Portfolio Management — Current Codebase State

*Documented from live source as of 2026-07-13. Describes existing behavior only; no recommendations.*

---

## High-Level Summary

The repository today has a **portfolio ledger subsystem** (`src/investment_agent/portfolio/`) that records manual buy/sell trades in SQLite, derives positions with weighted-average cost, marks holdings to market via yfinance, and compares performance to SPY. A **read-only theme alignment overlay** (`theme_alignment.py`) joins the latest `InvestmentBrief` themes with open positions in the Streamlit **Portfolio** view. There is **no LLM call, agent, or automated trade/allocation logic** in the portfolio subsystem; `portfolio/` does not import `llm.py` or `ThemeOrchestrator`. The multi-agent theme pipeline (Regime / Narrative / Markets) runs independently and does not receive portfolio holdings as input. `README.md` contains additional portfolio-related labels (suggested allocation, drift alerts, constraints) under a **Planned** heading; no corresponding implementation exists in source.

---

## 1. Scope Boundary: Portfolio vs Theme Pipeline

### 1.1 Documented separation

`AGENTS.md` states the portfolio subsystem is separate from the theme pipeline:

```94:96:AGENTS.md
## Portfolio subsystem (separate from theme pipeline)

SQLite ledger in `reports/portfolio.db` (default). `portfolio/theme_alignment.py` is **diagnostic only** (overlap/gap vs brief themes) — not rebalance or trade suggestions.
```

### 1.2 Import boundaries (live code)

| Module | Imports from theme pipeline? |
|--------|------------------------------|
| `portfolio/ledger.py`, `db.py`, `cli.py`, `quotes.py`, `theme_alignment.py` | No `llm`, `orchestrator`, or `agents/*/agent.py` |
| `portfolio/performance.py` | Imports `fetch_price_metrics` from `agents/markets/price.py` only |
| `portfolio/theme_alignment.py` | Imports `InvestmentBrief`, `FinalTheme` from `models.py` and universe helpers |

`portfolio/performance.py:9` is the only portfolio file that imports from `agents/`:

```9:9:src/investment_agent/portfolio/performance.py
from investment_agent.agents.markets.price import PriceMetrics, fetch_price_metrics
```

### 1.3 README roadmap text (documented, not implemented in code)

```308:312:README.md
## Roadmap: Portfolio management

**Implemented (ledger):** manual trade recording, weighted-avg positions, mark-to-market P&L, CLI (`invest-portfolio`) and Streamlit **Portfolio** tab. **Theme alignment** overlay compares top brief themes to holdings (ticker + sector match). See `research/portfolio-ledger-design.md`.

**Planned:** suggested allocation from themes, drift alerts, optional constraints.
```

A search of `src/` finds no matches for `allocation`, `drift`, or `rebalance`.

---

## 2. Package Layout (`src/investment_agent/portfolio/`)

| File | Role |
|------|------|
| `__init__.py:1-53` | Re-exports public API (ledger, models, performance) |
| `models.py:1-130` | Pydantic models for trades, positions, snapshots, performance, theme alignment |
| `db.py:1-180` | SQLite schema, migrations, CRUD |
| `ledger.py:1-297` | Position derivation, cash replay, trade validation |
| `performance.py:1-330` | Mark-to-market, SPY benchmark, chain-linked compare series |
| `quotes.py:1-54` | yfinance helpers for close price and symbol name |
| `theme_alignment.py:1-156` | Brief themes vs holdings overlay |
| `cli.py:1-246` | `invest-portfolio` CLI |

Design doc status: `research/portfolio-ledger-design.md:5` marks status **Implemented**.

---

## 3. Data Models (`portfolio/models.py`)

### 3.1 Trade and position models

```38:77:src/investment_agent/portfolio/models.py
class TradeSide(str, Enum):
    BUY = "buy"
    SELL = "sell"

class TradeInput(BaseModel):
    symbol: str
    side: TradeSide
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    trade_date: date
    name: str = ""
    fees: float = Field(default=0.0, ge=0)
    notes: str = ""

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, v: str) -> str:
        sym = v.strip().upper().lstrip("$")
        if not is_likely_ticker(sym):
            raise ValueError(f"Invalid ticker symbol: {v!r}")
        return sym

class Trade(TradeInput):
    id: int
    created_at: datetime

class Position(BaseModel):
    symbol: str
    name: str = ""
    quantity: float
    avg_cost: float
    cost_basis: float
    last_price: float | None = None
    market_value: float | None = None
    unrealized_pnl: float | None = None
    unrealized_pnl_pct: float | None = None
```

Symbol validation uses `universe.symbols.is_likely_ticker` (`models.py:10`, `symbols.py:18-24`).

### 3.2 Snapshot and performance models

```79:107:src/investment_agent/portfolio/models.py
class PortfolioSnapshot(BaseModel):
    as_of: date
    positions: list[Position]
    total_cost_basis: float
    total_market_value: float
    cash_balance: float = 0.0
    total_nav: float = 0.0
    total_unrealized_pnl: float
    total_unrealized_pnl_pct: float | None = None

class PerformanceSummary(BaseModel):
    as_of: date
    from_date: date | None = None
    to_date: date | None = None
    snapshot: PortfolioSnapshot
    realized_pnl: float
    total_pnl: float
    gross_invested: float
    total_return_pct: float | None = None
    spy_return_pct: float | None = None
    vs_spy_pct: float | None = None
    first_trade_date: date | None = None

class PerformanceComparePoint(BaseModel):
    date: date
    portfolio_index: float
    spy_index: float
```

### 3.3 Theme alignment models

```110:129:src/investment_agent/portfolio/models.py
class ThemeAlignmentRow(BaseModel):
    theme_name: str
    rank: int
    overlap_symbols: list[str] = Field(default_factory=list)
    overlap_pct: float = 0.0
    status: str  # high | partial | gap
    theme_tickers: list[str] = Field(default_factory=list)

class UncoveredPosition(BaseModel):
    symbol: str
    name: str = ""
    weight_pct: float = 0.0

class ThemeAlignmentReport(BaseModel):
    as_of: date
    rows: list[ThemeAlignmentRow] = Field(default_factory=list)
    uncovered_positions: list[UncoveredPosition] = Field(default_factory=list)
    gap_themes: list[str] = Field(default_factory=list)
    total_nav: float = 0.0
```

### 3.4 Streamlit-safe helpers

```13:35:src/investment_agent/portfolio/models.py
def model_name(obj: object) -> str:
    """Return ``name`` from Trade/Position; safe when field missing (e.g. Streamlit hot reload)."""
    val = getattr(obj, "name", "")
    return val if isinstance(val, str) else ""

def snapshot_cash_balance(snapshot: object) -> float:
    """Cash in portfolio account; safe when schema predates cash_balance field."""
    ...

def snapshot_total_nav(snapshot: object) -> float:
    """Cash + holdings market value; safe when schema predates total_nav field."""
    ...
```

---

## 4. Persistence (`portfolio/db.py`)

### 4.1 Default path and override

```13:22:src/investment_agent/portfolio/db.py
SCHEMA_VERSION = 2

_DEFAULT_DB = Path(__file__).resolve().parents[3] / "reports" / "portfolio.db"

def db_path() -> Path:
    override = os.environ.get("PORTFOLIO_DB_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return _DEFAULT_DB
```

`reports/` is gitignored (`.gitignore:9`). `README.md:113` documents `PORTFOLIO_DB_PATH`.

### 4.2 Schema

```65:85:src/investment_agent/portfolio/db.py
def init_db(path: Path | None = None) -> None:
    with connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
                quantity REAL NOT NULL CHECK (quantity > 0),
                price REAL NOT NULL CHECK (price > 0),
                fees REAL NOT NULL DEFAULT 0 CHECK (fees >= 0),
                trade_date TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
            CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(trade_date);
            """
        )
```

Migration v1→v2 adds `name` column (`db.py:52-57`). Positions are derived from trades at read time, not stored (`research/portfolio-ledger-design.md:133`).

### 4.3 CRUD surface

- `insert_trade` — `db.py:113-137`
- `fetch_trades` (optional symbol/date filters) — `db.py:140-165`
- `fetch_trade_by_id` — `db.py:168-172`
- `delete_trade_by_id` — `db.py:175-179`

---

## 5. Ledger Logic (`portfolio/ledger.py`)

### 5.1 Cost basis method

Weighted average cost (`ledger.py:1`). `compute_positions` — `ledger.py:114-164`:

- BUY: updates avg cost including fees
- SELL: validates quantity, realizes P&L at avg cost, removes closed symbols

### 5.2 Cash and external capital tracking

```17:51:src/investment_agent/portfolio/ledger.py
@dataclass(frozen=True)
class LedgerState:
    """Cash balance and open share quantities after replaying trades."""
    cash: float
    holdings: dict[str, float]

def replay_ledger_to(trades: list[Trade], on_date: date) -> LedgerState:
    """Replay trades through *on_date* (inclusive): cash + share quantities."""
```

- `external_inflow_on_date` — `ledger.py:54-78`
- `net_external_contributions` — `ledger.py:81-99` (used as `gross_invested` in performance summary)

Buy shortfall is funded via `_buy_shortfall` (`ledger.py:25-28`): when cash is insufficient, external deposit is implied.

### 5.3 Trade operations

- `add_trade` — validates sells against holdings (`ledger.py:222-252`), auto-fetches name via `fetch_symbol_name` when empty (`ledger.py:234-241`)
- `delete_trade` — validates remaining history (`ledger.py:255-281`)
- `list_trades` — `ledger.py:284-291`
- `get_open_positions` — `ledger.py:294-297`

Exceptions: `InsufficientSharesError`, `TradeNotFoundError`, `InvalidDeleteError` — `ledger.py:102-111`.

---

## 6. Performance (`portfolio/performance.py`)

### 6.1 Mark-to-market

`mark_positions` — `performance.py:37-109`:

- Fetches SPY once for 20d context (`performance.py:58-59`)
- Parallel `fetch_price_metrics` per symbol (`performance.py:62-90`)
- Computes `cash_balance` via `replay_ledger_to` (`performance.py:97-98`)
- `total_nav = cash + total_market_value` (`performance.py:98-106`)

Benchmark symbol: `BENCHMARK_SYMBOL = "SPY"` — `universe/constants.py:17`.

### 6.2 Performance summary

`summarize_performance` — `performance.py:283-323`:

- `total_pnl = snapshot.total_nav - invested` where `invested = net_external_contributions`
- `total_return_pct = total_pnl / invested`
- SPY return since first trade via `_spy_return_since` (`performance.py:112-134`)

### 6.3 Chain-linked compare series

`compare_performance_series` — `performance.py:192-280`:

- Default start: `DEFAULT_COMPARE_START = date(2026, 7, 1)` (`performance.py:30`)
- Adjusts daily returns for buy inflows (`performance.py:264-268`)
- Returns `list[PerformanceComparePoint]`

`get_marked_positions` — `performance.py:326-329` loads trades and calls `mark_positions`.

---

## 7. Quotes (`portfolio/quotes.py`)

- `fetch_close_on_date` — historical close for trade form prefill (`quotes.py:8-36`)
- `fetch_symbol_name` — yfinance `shortName` / `longName` (`quotes.py:39-53`)

Separate from `agents/markets/price.fetch_price_metrics` (`price.py:36-70`), which loads 1y history and momentum fields.

---

## 8. Theme Alignment (`portfolio/theme_alignment.py`)

Read-only overlay; module docstring `theme_alignment.py:1`.

### 8.1 Matching logic

```75:84:src/investment_agent/portfolio/theme_alignment.py
def _position_matches_theme(pos: Position, theme: FinalTheme) -> bool:
    sym = pos.symbol.upper()
    if sym in _theme_tickers(theme):
        return True
    sectors = _theme_sector_keys(theme)
    if not sectors:
        return False
    pos_sector = sector_key_for_symbol(sym)
    return pos_sector is not None and pos_sector in sectors
```

Uses `extract_tickers_from_themes` (`universe/symbols.py:27-35`) and `sector_key_for_symbol` (`universe/symbols.py:90-91`). Sector label tokens mapped in `theme_alignment.py:21-37`.

### 8.2 Status thresholds

```18:18:src/investment_agent/portfolio/theme_alignment.py
_HIGH_OVERLAP_PCT = 25.0
```

- `overlap_pct >= 25%` → `high`
- `> 0` → `partial`
- `0` → `gap`

`compute_theme_alignment` — `theme_alignment.py:86-156`: top `top_n` themes (default 8) by `theme_rank_score` from `models.py`, produces `ThemeAlignmentReport`.

---

## 9. CLI Entry Point (`invest-portfolio`)

Registered in `pyproject.toml:18-21`:

```18:21:pyproject.toml
[project.scripts]
invest-themes = "investment_agent.cli:main"
invest-dashboard = "investment_agent.cli:dashboard_main"
invest-portfolio = "investment_agent.portfolio.cli:main"
```

Subcommands (`cli.py:178-217`):

| Command | Handler |
|---------|---------|
| `add-trade` | `_cmd_add_trade` — `cli.py:34-51` |
| `delete-trade` | `_cmd_delete_trade` — `cli.py:54-60` |
| `list-trades` | `_cmd_list_trades` — `cli.py:63-96` |
| `positions` | `_cmd_positions` — `cli.py:99-137` |
| `performance` | `_cmd_performance` — `cli.py:140-175` |

Global `--db` flag — `cli.py:182-187`. README documents usage at `README.md:78-87`.

---

## 10. Streamlit Integration (`streamlit_app.py`)

### 10.1 Navigation

Sidebar radio — `streamlit_app.py:776`:

```776:776:streamlit_app.py
        page = st.radio("View", ["Themes", "Portfolio"], index=0, horizontal=True)
```

Portfolio page dispatch — `streamlit_app.py:853-855`:

```853:855:streamlit_app.py
    if page == "Portfolio":
        _render_portfolio(brief=st.session_state.get("brief"))
        return
```

### 10.2 Portfolio view sections (`_render_portfolio`, `streamlit_app.py:539-765`)

| Section | Lines | Behavior |
|---------|-------|----------|
| Trade entry form | `552-631` | Symbol → yfinance close/name; `add_trade()` |
| Performance metrics | `633-675` | `summarize_performance()`; five metrics |
| vs SPY chart | `677`, `429-498` | `compare_performance_series(from_date=DEFAULT_COMPARE_START)` |
| Open positions table + pie | `679-710` | Altair allocation chart |
| Research alignment | `712-718`, `501-536` | `compute_theme_alignment(brief, snapshot)` when brief loaded |
| Trade history + delete | `720-765` | `list_trades()`, `delete_trade()` with confirm |

Theme alignment caption — `streamlit_app.py:504-506`:

```504:506:streamlit_app.py
    st.caption(
        "Top themes from the latest brief vs your open positions (ticker + sector ETF match). "
        "Read-only — does not change analysis or trades."
```

When no brief in session — `streamlit_app.py:714-718` shows info to load brief from Themes view.

### 10.3 Theme pipeline in same app (separate flow)

Theme run — `streamlit_app.py:811-851`: `ThemeOrchestrator(settings).run(resume=resume_ckpt)`; saves via `save_run_reports`. Brief stored in `st.session_state.brief` (`streamlit_app.py:771-772`, `829`).

`dashboard_main` launches this file — `cli.py:216-223`.

---

## 11. Theme Pipeline (No Portfolio Input)

### 11.1 Orchestrator flow

Documented in `AGENTS.md:21-24`:

```
data_plane.build_data_plane()  →  Regime / Narrative / Markets *Input
orchestrator                   →  3 × Agent.analyze()  →  brief_assembler.assemble()
```

`research/portfolio-ledger-design.md:32` states holdings are not fed into agent inputs.

### 11.2 Brief storage

- Load: `storage.py:148-154` — default path `reports/latest.json` (`storage.py:18`)
- `InvestmentBrief` schema — `models.py:175+`; themes as `list[FinalTheme]` (`models.py:128+`)

### 11.3 LLM usage

Three structured LLM calls per theme run (`AGENTS.md:7`). Portfolio subsystem has zero LLM calls.

---

## 12. Cross-Component Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ Theme Pipeline (LLM)                                            │
│  data_plane → Regime / Narrative / Markets agents → assembler   │
│  output: reports/latest.json (InvestmentBrief)                  │
└────────────────────────────┬────────────────────────────────────┘
                             │ read-only in Streamlit
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ UI join: theme_alignment.compute_theme_alignment(brief, snap)   │
└────────────────────────────▲────────────────────────────────────┘
                             │ PortfolioSnapshot from performance
┌────────────────────────────┴────────────────────────────────────┐
│ Portfolio Ledger (no LLM)                                       │
│  CLI / Streamlit form → ledger.add_trade → reports/portfolio.db │
│  performance.summarize → yfinance marks + SPY benchmark         │
└─────────────────────────────────────────────────────────────────┘
```

**Data paths:**

1. Trades → SQLite only; never written to brief JSON
2. Brief → JSON only; never written to portfolio DB
3. Join point: `streamlit_app.py:712-713` passes `InvestmentBrief` + `PortfolioSnapshot` to `compute_theme_alignment`

---

## 13. External Dependencies Used by Portfolio

| Dependency | Usage |
|------------|--------|
| `yfinance` | `quotes.py`, `performance._fetch_close_series`, `agents/markets/price.fetch_price_metrics` |
| `sqlite3` (stdlib) | `db.py` |
| `pydantic` | `models.py` |
| `rich` | `cli.py` tables |
| `altair` + `pandas` | Streamlit charts (`streamlit_app.py:387-388`, `431-432`) — imported inside render functions |

No portfolio-specific dependencies beyond `pyproject.toml:7-16`.

---

## 14. Tests

| File | Coverage |
|------|----------|
| `tests/test_portfolio.py` | Weighted avg, sells, mark/summary mocks, delete, cash replay, compare series, migration |
| `tests/test_theme_alignment.py` | Ticker overlap, sector ETF overlap, gap/uncovered, high threshold |

`README.md:319-323` lists both in pytest invocation.

---

## 15. Git History (portfolio-related)

| Commit | Summary |
|--------|---------|
| `55fe0cb` | Initial portfolio feature |
| `f519820` | Cash balance, NAV, performance compare with inflows |
| `1952882` | Theme alignment overlay in Streamlit |

---

## 16. Related Research Docs

| File | Content |
|------|---------|
| `research/portfolio-ledger-design.md` | Design for ledger subsystem; status **Implemented** |
| `research/codebase-current-state.md` | Pipeline state as of 2026-07-04; does not document portfolio |
| `research/shared-universe-design.md` | Universe refactor; sector maps used by theme alignment |

---

## 17. Absent Capabilities (relative to "AI portfolio management")

Based on live source inspection:

| Capability | Present in code? |
|------------|------------------|
| LLM-driven portfolio advice or allocation | No |
| Automated trade execution or suggestions | No (`AGENTS.md:96`) |
| Portfolio agent or `portfolio/agent.py` | No |
| Holdings fed into Regime/Narrative/Markets inputs | No |
| Drift alerts | No |
| Suggested allocation from themes | No |
| Broker API or CSV import | No (`research/portfolio-ledger-design.md:30-31`) |
| Multi-user or auth | No |
