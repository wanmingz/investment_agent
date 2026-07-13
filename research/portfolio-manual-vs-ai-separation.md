# Design: Manual vs AI Portfolio Separation

| Field | Value |
|-------|-------|
| Status | Implemented |
| Research basis | `research/ai-portfolio-management-current-state.md`; `AGENTS.md:94-96` |
| Approach | Dual SQLite ledgers + three Streamlit sub-views; brief target stays stateless |
| Target location | `research/portfolio-manual-vs-ai-separation.md` |

> **Note:** `design_doc_template.md` was not found in the repository. Structure mirrors `research/portfolio-ledger-design.md`.

---

## Scope Summary (read first)

### In scope

- **`portfolio/db.py`** — `LedgerKind = Literal["manual", "model"]`; `db_path(ledger="manual"|"model")`
- **Default paths:** `reports/portfolio.db` (manual, unchanged); `reports/ai_portfolio.db` (model)
- **Env:** `PORTFOLIO_DB_PATH` (existing); `PORTFOLIO_AI_DB_PATH` (new)
- **API pass-through** — `ledger: LedgerKind = "manual"` on `ledger.py`, `performance.py` public functions; explicit `path=` still wins
- **CLI** — global `--ledger {manual,model}` on `invest-portfolio` (`cli.py:178-187`)
- **Streamlit Portfolio tab** — sub-nav: **My portfolio** | **Model portfolio** | **Compare**
- **Compare view** — read-only manual `PortfolioSnapshot` vs brief-derived target weights (requires `allocation.py` + `drift.py` from Proposal 2 MVP; stub message if not yet implemented)
- **Tests** — `tests/test_portfolio_dual_ledger.py`
- **Docs** — `README.md` env table; `AGENTS.md` portfolio subsection

### Out of scope

- Broker sync; auto-copy trades model → manual
- `ledger_id` column in a single DB
- `InvestmentBrief` / `ThemeOrchestrator` / agent input changes
- LLM advisory (Proposal 1)
- Target snapshot persistence (`reports/model_targets/*.json`) — defer
- Model ledger required for Compare (Compare uses manual + brief only)

### Constraints

- **Backward compatible:** default `ledger="manual"` → same path as `db.py:18-22` today
- **Schema parity:** both files use `init_db` / `SCHEMA_VERSION = 2` (`db.py:13`)
- **No cross-writes:** model trades never touch manual path
- **Diagnostic Compare:** no trade posting from Compare (`AGENTS.md:96`)
- **Pipeline isolation:** no new imports of `llm.py` or `ThemeOrchestrator`
- **Python ≥ 3.11**; no new dependencies (`pyproject.toml:7-21`)

### Timeline (estimate)

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| 1 — Dual `db_path` | 0.5 day | `db.py`, `PORTFOLIO_AI_DB_PATH`, unit tests |
| 2 — `ledger` kwarg | 0.5 day | `ledger.py`, `performance.py`, `__init__.py` exports |
| 3 — CLI `--ledger` | 0.25 day | `cli.py` |
| 4 — Streamlit My / Model | 1 day | `_render_portfolio(ledger=…)` refactor |
| 5 — Streamlit Compare | 0.5 day | drift table or “run allocation MVP first” stub |
| 6 — Docs | 0.25 day | README, AGENTS.md |

**Total:** ~3 days for one developer (Phases 1–4 shippable without Compare).

---

## Current Context

- Single SQLite ledger: `reports/portfolio.db` via `db_path()` (`db.py:15-22`)
- Streamlit **Portfolio** tab: one trade form + one `summarize_performance()` (`streamlit_app.py:539-765`)
- Theme alignment joins brief + **same** snapshot (`streamlit_app.py:712-713`, `theme_alignment.py:86-156`)
- No `allocation` / `drift` modules in `src/` (`research/ai-portfolio-management-current-state.md:49`)
- User request: AI portfolio and manual portfolio must not share one trade journal

---

## Requirements

### Functional

- **R1:** `db_path("manual")` → `PORTFOLIO_DB_PATH` or `reports/portfolio.db`
- **R2:** `db_path("model")` → `PORTFOLIO_AI_DB_PATH` or `reports/ai_portfolio.db`
- **R3:** `add_trade`, `delete_trade`, `list_trades`, `get_open_positions`, `summarize_performance`, `get_marked_positions`, `compare_performance_series` accept `ledger: LedgerKind = "manual"` (resolve to path internally)
- **R4:** `invest-portfolio --ledger model positions` reads model file only
- **R5:** Streamlit **My portfolio** — identical to today; caption shows manual DB path
- **R6:** Streamlit **Model portfolio** — same widgets; `ledger="model"`; caption “Paper / model ledger”
- **R7:** Streamlit **Compare** — manual snapshot + loaded brief → drift table; no trade form; disclaimer
- **R8:** Theme alignment renders on **My portfolio** only (not Model or Compare)

### Non-functional

- **NR1:** Trade inserted with `ledger="model"` not visible in `ledger="manual"` queries
- **NR2:** Existing `tests/test_portfolio.py` passes without edits (uses explicit `path=` fixture)

---

## Design Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Two SQLite files, one codepath | Reuse `ledger.py`; wipe model DB without touching manual |
| D2 | Reject single-DB `ledger_id` | Physical separation matches user intent |
| D3 | **Target** (brief weights) ≠ **model ledger** (paper trades) | Target is computed stateless; model DB is optional practice book |
| D4 | Compare = manual actual vs brief target | Does not require model ledger population |
| D5 | Default ledger `manual` | Zero migration for existing users |
| D6 | Compare depends on allocation MVP | Avoid duplicating weight logic in Streamlit |

### Files touched

| File | Change |
|------|--------|
| `portfolio/db.py` | `LedgerKind`, `db_path(ledger)` |
| `portfolio/ledger.py` | `ledger` kwarg on CRUD wrappers |
| `portfolio/performance.py` | `ledger` kwarg |
| `portfolio/__init__.py` | export `LedgerKind` |
| `portfolio/cli.py` | `--ledger` flag |
| `streamlit_app.py` | sub-nav; pass `ledger` |
| `tests/test_portfolio_dual_ledger.py` | new |
| `README.md`, `AGENTS.md` | env + UX notes |

### Data flow

```
Manual trades  →  reports/portfolio.db     →  My portfolio UI
Model trades   →  reports/ai_portfolio.db  →  Model portfolio UI

InvestmentBrief  →  compute_target_allocation()  →  Compare UI
Manual snapshot  ─────────────────────────────────┘
```

---

## Implementation Plan

### Step 1 — `portfolio/db.py`

- [ ] `LedgerKind = Literal["manual", "model"]`
- [ ] `_DEFAULT_AI_DB = parents[3] / "reports" / "ai_portfolio.db"`
- [ ] `db_path(ledger: LedgerKind = "manual") -> Path`
- [ ] `connect(path=None, ledger="manual")` resolves path when `path` is None

### Step 2 — `ledger.py` + `performance.py`

- [ ] Add `ledger: LedgerKind = "manual"` to all functions that take `path: Path | None`
- [ ] Resolve: `target = path or db_path(ledger)`

### Step 3 — `portfolio/cli.py`

- [ ] `parser.add_argument("--ledger", choices=["manual", "model"], default="manual")`
- [ ] Pass `ledger=args.ledger` into command handlers

### Step 4 — `streamlit_app.py`

- [ ] Extract `_render_portfolio_ledger(brief, ledger: LedgerKind)` from `_render_portfolio`
- [ ] Top sub-radio: My | Model | Compare
- [ ] My → `ledger="manual"` + `_render_theme_alignment`
- [ ] Model → `ledger="model"`, no theme alignment
- [ ] Compare → `summarize_performance(ledger="manual")` + `compute_drift_report` when allocation exists; else `st.info(...)`

### Step 5 — Tests + docs

- [ ] `tests/test_portfolio_dual_ledger.py`
- [ ] README `PORTFOLIO_AI_DB_PATH`; AGENTS.md dual-ledger note

---

## Testing

- [ ] Manual and model DBs in `tmp_path`; trades isolated
- [ ] `db_path("manual")` ≠ `db_path("model")` with defaults
- [ ] Regression: `pytest tests/test_portfolio.py tests/test_theme_alignment.py -v`

---

## Rollout

- Additive; `reports/ai_portfolio.db` created on first model trade
- Default Streamlit sub-view: **My portfolio**
- No changes to `portfolio.db` schema or existing rows

---

## Security

- Both DBs under gitignored `reports/`; local-only; no new secrets
