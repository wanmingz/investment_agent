# Design: Portfolio Ledger Subsystem (Proposal 2)

| Field | Value |
|-------|-------|
| Status | Implemented |
| Research basis | `research/codebase-current-state.md`; `README.md:262-283` |
| Approach | Proposal 2 — independent ledger-first subsystem; Brief integration read-only in UI |
| Target location | `research/portfolio-ledger-design.md` |

> **Note:** `design_doc_template.md` was not found in the repository. Structure mirrors `research/shared-universe-design.md`: scope summary, current context, requirements, design decisions, implementation plan; optional sections omitted when not applicable.

---

## Scope Summary (read first)

### In scope

- New package `src/investment_agent/portfolio/` — trade ledger, position derivation, performance marks
- **SQLite** persistence at `reports/portfolio.db` (default path; overridable via env)
- **CLI** entry `invest-portfolio` with subcommands: `add-trade`, `list-trades`, `positions`, `performance`
- **Streamlit tab** in existing `streamlit_app.py` — trade entry form, holdings table, P&L vs SPY (read-only overlay; no pipeline changes)
- Reuse `agents/markets/price.py:36-70` (`fetch_price_metrics`) and `universe/constants.py:145` (`BENCHMARK_SYMBOL`) for mark-to-market
- **Weighted average cost** for cost basis; support buy/sell equity trades in USD
- Pydantic models for `Trade`, `Position`, `PortfolioSnapshot`, `PerformanceSummary`
- Unit tests in `tests/test_portfolio.py` (ledger math, performance with mocked prices)
- Update `README.md` with portfolio CLI + dashboard tab usage

### Out of scope

- Broker API sync, CSV import, dividend/split/corporate-action automation
- Modifying `InvestmentBrief` schema, `ThemeOrchestrator`, or checkpoint (`checkpoint.py:32`, `PIPELINE_VERSION = 6`)
- Feeding holdings into Regime/Narrative/Markets agent inputs (`research/codebase-current-state.md:81`)
- TWR / IRR / daily snapshot job (defer to Phase 2+)
- `theme_alignment_score` vs brief themes (defer to Phase 3; UI join only when implemented)
- Multi-currency, options, fractional-share broker quirks beyond stored decimal qty
- New runtime dependencies (stdlib `sqlite3` only)
- Authentication, multi-user, cloud sync

### Constraints

- **Pipeline isolation:** `portfolio/` must not import `ThemeOrchestrator`, agent modules, or `llm.py`
- **Brief read-only:** Dashboard may load `reports/latest.json` alongside portfolio DB; no writes to brief files from portfolio code
- **Python ≥ 3.11**; existing deps only (`pyproject.toml:7-15`)
- **Existing tests unchanged:** `tests/test_pipeline.py` must pass with zero modifications
- **Symbol normalization:** Uppercase tickers; validate via `universe.symbols.is_likely_ticker` where applicable
- **Local-first:** Single-user SQLite file under `reports/`; no secrets in DB

### Timeline (estimate)

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| 1 — Core ledger | 2–3 days | `portfolio/models.py`, `db.py`, `ledger.py`; SQLite schema + migrations bootstrap |
| 2 — Performance + CLI | 2 days | `performance.py`, `cli.py` portfolio subcommands, `invest-portfolio` script |
| 3 — Streamlit tab | 1–2 days | Trade form, positions table, performance summary in `streamlit_app.py` |
| 4 — Docs + polish | ~1 day | `README.md`, optional `research/codebase-current-state.md` appendix |
| 5 — Theme overlay (optional) | 1 day | Read-only sector weight vs `FinalTheme` ranks in dashboard tab |

**Total (Phases 1–4):** ~1–1.5 weeks for one developer. Phase 5 optional.

---

## Current Context

- **No portfolio code today:** Theme discovery only; README roadmap (`README.md:262-283`) sketches post-assembler alignment but no trade journal
- **Persistence pattern:** Briefs → JSON at `reports/latest.json` and `reports/runs/` (`storage.py:18-19`, `storage.py:115-137`); checkpoint cache at `reports/cache/` (`checkpoint.py:30-31`)
- **Price data:** yfinance via `fetch_price_metrics` (`agents/markets/price.py:36-70`); SPY benchmark constant in `universe/constants.py:145`
- **Entry points:** `invest-themes`, `invest-dashboard` (`pyproject.toml:17-19`); CLI argparse in `cli.py:140-208`
- **UI:** Single Streamlit app (`streamlit_app.py`); sidebar for checkpoint/resume; theme cards sorted by `investability_score + consensus_score`
- **User request:** 实盘功能 — manually record trades, view portfolio holdings, track performance

---

## Requirements

### Functional

- **R1:** Record a trade with fields: `symbol`, `side` (`buy` | `sell`), `quantity` (> 0), `price` (> 0), `trade_date` (ISO date), optional `fees`, optional `notes`
- **R2:** Derive open positions from trade history using **weighted average cost**; zero out closed positions
- **R3:** On `positions` / `performance`, fetch latest marks via `fetch_price_metrics`; compute per-symbol and portfolio-level:
  - Market value, cost basis, unrealized P&L ($ and %)
  - Realized P&L on sells (avg-cost method)
- **R4:** Portfolio-level benchmark: total return vs SPY over same holding period window (MVP: since first trade date to today)
- **R5:** CLI commands:
  - `invest-portfolio add-trade …`
  - `invest-portfolio list-trades [--symbol SYM]`
  - `invest-portfolio positions`
  - `invest-portfolio performance [--from DATE] [--to DATE]`
- **R6:** Streamlit tab: add trade (calls same ledger API as CLI), show positions + performance summary
- **R7:** Idempotent DB init on first use; schema version table for future migrations

### Non-functional

- **NR1:** Ledger operations complete in < 100 ms excluding yfinance network calls
- **NR2:** `portfolio/` importable without loading LLM or agent code
- **NR3:** Corrupt or missing DB → clear error message; no silent data loss on sell exceeding holdings

---

## Design Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Separate package** `investment_agent/portfolio/` | Decouples ledger from theme pipeline; aligns with Proposal 2 |
| D2 | **SQLite at `reports/portfolio.db`** | Audit trail, queryable history; stdlib only; matches `reports/` convention |
| D3 | **Weighted average cost** (not FIFO) | Simpler MVP; easier trade corrections; sufficient for personal use |
| D4 | **No `InvestmentBrief` extension** | Avoids `storage.py` migration churn; brief and portfolio evolve independently |
| D5 | **Reuse `fetch_price_metrics`** | Same yfinance path as Markets agent; consistent SPY-relative logic |
| D6 | **CLI + shared library API** | Streamlit tab calls `ledger.add_trade()` / `performance.summarize()` — no duplicated business logic |
| D7 | **`PORTFOLIO_DB_PATH` env override** | Optional; default `reports/portfolio.db` relative to project root |
| D8 | **Sell validation** | Reject sell qty > current shares; no short positions in MVP |
| D9 | **Streamlit tab, not new app** | One dashboard for themes + portfolio; minimal user friction |
| D10 | **Theme overlay deferred** | Core ask is trade/portfolio/performance; alignment is optional Phase 5 |

### Proposed package layout

```
src/investment_agent/portfolio/
├── __init__.py       # re-export public API
├── models.py         # Trade, Position, PortfolioSnapshot, PerformanceSummary (Pydantic)
├── db.py             # SQLite connection, schema init, CRUD helpers
├── ledger.py         # add_trade, list_trades, compute_positions
├── performance.py    # mark-to-market, realized/unrealized P&L, vs SPY
└── cli.py            # argparse subcommands; wired from investment_agent.cli or standalone main
```

### SQLite schema (MVP)

| Table | Columns |
|-------|---------|
| `schema_version` | `version INTEGER` |
| `trades` | `id`, `symbol`, `side`, `quantity`, `price`, `fees`, `trade_date`, `notes`, `created_at` |

Positions are **derived** (not stored), except optional future `daily_snapshots` table (out of scope MVP).

---

## Implementation Plan

### Step 1 — `portfolio/models.py`

- [ ] Define Pydantic models: `Trade`, `TradeInput`, `Position`, `PortfolioSnapshot`, `PerformanceSummary`
- [ ] Validators: uppercase symbol, positive qty/price, `side` enum

### Step 2 — `portfolio/db.py`

- [ ] Resolve DB path: `PORTFOLIO_DB_PATH` or `reports/portfolio.db`
- [ ] `init_db()` — create tables, `schema_version = 1`
- [ ] `insert_trade`, `fetch_trades(symbol=None, from_date=None, to_date=None)`

### Step 3 — `portfolio/ledger.py`

- [ ] `add_trade(trade: TradeInput) -> Trade` — persist + return
- [ ] `compute_positions(trades) -> list[Position]` — weighted avg cost; handle partial sells
- [ ] `get_open_positions() -> list[Position]` — load trades from DB, compute

### Step 4 — `portfolio/performance.py`

- [ ] `mark_positions(positions) -> PortfolioSnapshot` — batch `fetch_price_metrics` (reuse ThreadPoolExecutor pattern from `snapshot.py:167-186` if >1 symbol)
- [ ] `summarize_performance(from_date?, to_date?) -> PerformanceSummary` — unrealized + realized P&L, vs SPY
- [ ] Fetch SPY once for benchmark comparison

### Step 5 — `portfolio/cli.py` + entry point

- [ ] Implement subcommands per R5
- [ ] Rich tables for CLI output (match `cli.py` style)
- [ ] Add `invest-portfolio = "investment_agent.portfolio.cli:main"` to `pyproject.toml:17-19`

### Step 6 — Streamlit tab (`streamlit_app.py`)

- [ ] Add sidebar or top-level tab selector: **Themes** | **Portfolio**
- [ ] Portfolio tab: `st.form` for trade entry; `st.dataframe` for positions; metrics for total P&L and vs SPY
- [ ] Import only from `investment_agent.portfolio` — not orchestrator

### Step 7 — Tests (`tests/test_portfolio.py`)

- [ ] Ledger: buy → sell partial → sell all; avg cost matches hand calculation
- [ ] Sell exceeding holdings raises error
- [ ] Performance: mock `fetch_price_metrics` → expected P&L
- [ ] DB init idempotent

### Step 8 — Documentation

- [ ] `README.md` — new section: Portfolio ledger CLI + dashboard tab
- [ ] Optional: append § to `research/codebase-current-state.md` when implemented

---

## Testing

### New: `tests/test_portfolio.py`

- [ ] Weighted avg: buy 10 @ $100, buy 10 @ $120 → 20 shares @ $110 cost
- [ ] Partial sell: sell 5 @ $130 → 15 shares @ $110; realized P&L = 5 × ($130 − $110)
- [ ] Full close: sell remaining → empty positions list
- [ ] Invalid sell qty → `ValueError` (or domain exception)
- [ ] Mock yfinance: fixed `last_close` → correct unrealized P&L

### Regression

- [ ] `PYTHONPATH=src python -m pytest tests/test_pipeline.py -v` — unchanged, all pass

---

## Rollout

- New feature; no migration of existing brief or checkpoint data
- First run creates `reports/portfolio.db` automatically
- Recommend documenting in README: portfolio data is local-only; back up `reports/portfolio.db` before schema changes in future releases
- Phase 5 theme overlay: pure UI addition; no DB or pipeline impact

---

## Observability

- Log trade inserts at INFO (symbol, side, qty, date) via stdlib `logging` in `ledger.add_trade`
- CLI errors surfaced to stderr with actionable messages (e.g. insufficient shares)

---

## Security

- Local SQLite only; no network exposure of portfolio data
- No API keys stored in portfolio DB
- Streamlit remains local dev tool; no auth in MVP (same as existing dashboard)
