# Design: Shared Market Universe Registry (Proposal 2)

| Field | Value |
|-------|-------|
| Status | Implemented |
| Research basis | `research/codebase-current-state.md` |
| Approach | Proposal 2 — unified sector/ticker registry; eliminate duplicate mappings |
| Target location | `research/shared-universe-design.md` |

> **Note:** `design_doc_template.md` was not found in the repository. Structure mirrors prior project design docs: scope summary, current context, requirements, design decisions, implementation plan; optional sections omitted when not applicable.

---

## Scope Summary (read first)

### In scope

- Replace `agents/markets/universe.py` with shared package `src/investment_agent/universe/`
- **Single source of truth** for:
  - Sector ETF label → symbol map (`SECTOR_ETFS`)
  - Benchmark (`BENCHMARK_SYMBOL`) and VIX proxy (`VIX_SYMBOL`)
  - Symbol → canonical sector key (`TICKER_TO_SECTOR`, replaces `brief_assembler.py:112-122`)
  - Fundamentals fetch symbol list (`symbols_for_fundamentals`)
  - Vol fetch subset (`vol_labeled_symbols()` — replaces inline dict at `snapshot.py:237-244`)
  - Display names for ETF-backed sectors (`SECTOR_DISPLAY` for keys present in `SECTOR_ETFS`)
- Update consumers:
  - `agents/markets/snapshot.py`
  - `agents/regime/input.py`
  - `brief_assembler.py` (`_primary_sector` ticker branch only)
- Add `tests/test_universe.py` + extend assembler regression assertions
- Update `README.md` and `research/codebase-current-state.md`

### Out of scope

- Region-specific universe (`MARKET_REGION` branches in `config.py:56`)
- Narrative ingest/RAG changes (no ticker universe today — research §5)
- Moving `_SECTOR_WORDS` / `_MERGEABLE_SECTORS` / `_SECTOR_PRIORITY` into universe (theme-title NLP + clustering policy stays in assembler)
- Expanding vol snapshot from 5 to 8 sector ETFs (behavior preserved; subset documented explicitly)
- Wiring `extract_tickers_from_themes` into `fetch_fundamentals_snapshot` (still unused — research §6.1)
- Checkpoint `PIPELINE_VERSION` bump (`checkpoint.py:32`)
- New dependencies or env variables

### Constraints

- **Behavior parity:** With unchanged ETF symbols, pytest fixtures in `tests/test_pipeline.py:134-221` must produce same `FinalTheme.name`, `contributing_agents`, and cluster counts
- **Vol subset unchanged:** 5 sectors (Tech, Energy, Healthcare, Financials, AI/Cloud) + `^VIX` — not all 8 fundamentals sectors (research §18)
- **Agent input isolation unchanged** (`research/codebase-current-state.md:80`)
- **No imports from `agents/` inside `universe/`** (avoid circular deps)
- **Python ≥ 3.11**; no new packages (`pyproject.toml:7-15`)
- **`TICKER_TO_SECTOR` must match current `_TICKER_SECTOR` values** for all symbols in `SECTOR_ETFS` + SPY (e.g. `igv → tech`, `spy → benchmark`)

### Timeline (estimate)

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| 1 — Universe package | 2–3 hrs | `universe/constants.py`, `universe/symbols.py`, `universe/__init__.py` |
| 2 — Consumer refactors | 2–3 hrs | `snapshot.py`, `regime/input.py`, `brief_assembler.py`; delete old `agents/markets/universe.py` |
| 3 — Tests | 1–2 hrs | `tests/test_universe.py`; verify existing pipeline tests |
| 4 — Docs | ~1 hr | README, `codebase-current-state.md` |

**Total:** ~1–2 working days for one developer.

---

## Current Context

- **Canonical ETF list (Markets-only path):** `agents/markets/universe.py:11-22` — 8 sector ETFs + `SPY`.
- **Direct importers:**
  - `agents/markets/snapshot.py:12` — fundamentals via `symbols_for_fundamentals`; vol via **hardcoded** `tickers` dict (`snapshot.py:237-244`)
  - `agents/regime/input.py:10` — `BENCHMARK_SYMBOL` only
- **Duplicate ticker→sector map:** `brief_assembler.py:112-122` `_TICKER_SECTOR` — used by `_primary_sector()` (`brief_assembler.py:144-155`) for theme clustering; overlaps with `SECTOR_ETFS` but maintained separately.
- **Display names:** `brief_assembler.py:98-111` `_SECTOR_DISPLAY` includes ETF sectors plus macro buckets (`growth`, `rates`, …) not tied to ETFs.
- **Regime** consumes the same yfinance rows via `MarketSnapshots` (data plane); does not import full `SECTOR_ETFS` today (`research/codebase-current-state.md:89-93`).
- User request: universe should not live under Markets; **one place to change** ETF definitions so fetch, regime context, and brief clustering stay aligned.

---

## Requirements

### Functional

- **R1:** `investment_agent.universe` exposes stable public API:
  - Constants: `SECTOR_ETFS`, `BENCHMARK_SYMBOL`, `VIX_SYMBOL`, `TICKER_TO_SECTOR`, `SECTOR_DISPLAY_ETF`
  - Helpers: `symbols_for_fundamentals`, `vol_labeled_symbols`, `is_likely_ticker`, `sector_key_for_symbol(symbol: str) -> str | None`
- **R2:** `fetch_fundamentals_snapshot` resolves the same 9 core symbols (8 ETFs + SPY) when no extra theme tickers (`agents/markets/snapshot.py:148-159`).
- **R3:** `fetch_vol_snapshot` uses `vol_labeled_symbols()`; output keys in `VolSnapshot.sector_vol` unchanged (5 sector labels + VIX level/change).
- **R4:** `brief_assembler._primary_sector` uses `TICKER_TO_SECTOR` from universe for ticker-based sector resolution; theme-title token path (`_SECTOR_WORDS`) unchanged.
- **R5:** Adding a new row label` in fundamentals/vol blocks remains the human labels from `SECTOR_ETFS` keys (e.g. `"AI/Cloud"`, `"Tech"`).

### Non-functional

- **NR1:** Adding/changing one entry in `SECTOR_ETFS` updates fundamentals list, vol list (if in vol subset), and assembler ticker mapping without editing other files.
- **NR2:** `universe/` modules are importable without loading agent or LLM code.

---

## Design Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Subpackage** `investment_agent/universe/` with `constants.py` + `symbols.py` + `__init__.py` | Separates static maps from fetch helpers; room for vol subset config |
| D2 | **`TICKER_TO_SECTOR` derived at import** from `SECTOR_ETFS` + benchmark | Eliminates drift with `brief_assembler.py:112-122`; `IGV → tech` via explicit alias map |
| D3 | **`VOL_SECTOR_LABELS`** frozenset in `constants.py` | Documents intentional 5-sector vol subset; `vol_labeled_symbols()` filters `SECTOR_ETFS` by label |
| D4 | **`SECTOR_DISPLAY_ETF` only for ETF-backed keys** | Macro display names (`growth`, `rates`, …) stay in `brief_assembler.py:98-111`; assembler merges ETF display via import where sector key matches |
| D5 | **`_SECTOR_WORDS` stays in assembler** | Title-token NLP is clustering logic, not market data universe |
| D6 | **Delete `agents/markets/universe.py`**; no re-export shim | Internal-only consumers; grep before merge |
| D7 | **No checkpoint version bump** | Universe not serialized; cached rows use symbol strings already fetched (`checkpoint.py:176-205`) |
| D8 | **IGV → `tech` sector key** (preserve `_TICKER_SECTOR` behavior) | `brief_assembler.py:117` maps `igv` to `tech`, not a separate sector key |

### Proposed package layout

```
src/investment_agent/universe/
├── __init__.py      # re-export public API
├── constants.py     # SECTOR_ETFS, BENCHMARK_SYMBOL, VIX_SYMBOL, VOL_SECTOR_LABELS, TICKER_TO_SECTOR, SECTOR_DISPLAY_ETF
└── symbols.py       # symbols_for_fundamentals, vol_labeled_symbols, is_likely_ticker, extract_tickers_from_themes
```

### `TICKER_TO_SECTOR` derivation (must match today)

| Symbol | Sector key |
|--------|------------|
| XLK, IGV | `tech` |
| XLE | `energy` |
| XLV | `healthcare` |
| XLF | `financials` |
| XLY | `consumer` |
| XLI | `industrials` |
| XLU | `utilities` |
| SPY | `benchmark` |

---

## Implementation Plan

### Step 1 — Create `universe/constants.py`

- [ ] Define `SECTOR_ETFS` (copy from `agents/markets/universe.py:11-20`)
- [ ] Define `BENCHMARK_SYMBOL = "SPY"`, `VIX_SYMBOL = "^VIX"`
- [ ] Define `VOL_SECTOR_LABELS = frozenset({"Tech", "Energy", "Healthcare", "Financials", "AI/Cloud"})`
- [ ] Build `TICKER_TO_SECTOR: dict[str, str]` (lowercase keys) from `SECTOR_ETFS` + alias `{igv: tech}` + `{spy: benchmark}`
- [ ] Define `SECTOR_DISPLAY_ETF: dict[str, str]` for keys `tech`, `energy`, … mapped from ETF sector keys (subset of current `_SECTOR_DISPLAY`)

### Step 2 — Create `universe/symbols.py`

- [ ] Move `is_likely_ticker`, `extract_tickers_from_themes`, `symbols_for_fundamentals` from `agents/markets/universe.py:27-80`
- [ ] Add `vol_labeled_symbols() -> list[tuple[str, str]]` returning `[("VIX", VIX_SYMBOL)] + [(label, sym) for label, sym in SECTOR_ETFS.items() if label in VOL_SECTOR_LABELS]`
- [ ] Add `sector_key_for_symbol(symbol: str) -> str | None` wrapping `TICKER_TO_SECTOR.get(symbol.lower())`

### Step 3 — Create `universe/__init__.py`

- [ ] Re-export public symbols listed in R1

### Step 4 — Refactor `agents/markets/snapshot.py`

- [ ] Replace import at line 12 with `from investment_agent.universe import ...`
- [ ] Replace `tickers = {...}` block (`snapshot.py:237-244`) with `for label, symbol in vol_labeled_symbols():`
- [ ] Keep `label == "VIX"` branch for level/change vs sector vol (`snapshot.py:254-261`)

### Step 5 — Refactor `agents/regime/input.py`

- [ ] `from investment_agent.universe import BENCHMARK_SYMBOL` (line 10)

### Step 6 — Refactor `brief_assembler.py`

- [ ] Remove `_TICKER_SECTOR` (`brief_assembler.py:112-122`)
- [ ] Import `TICKER_TO_SECTOR`, `SECTOR_DISPLAY_ETF` from universe
- [ ] In `_primary_sector` ticker branch (`brief_assembler.py:150-154`): use `TICKER_TO_SECTOR.get(sym)` instead of `_TICKER_SECTOR`
- [ ] In `_group_display_name` (`brief_assembler.py:220-226`): prefer `SECTOR_DISPLAY_ETF.get(sector, ...)` then fall back to existing `_SECTOR_DISPLAY` for macro buckets

### Step 7 — Remove old module

- [ ] Delete `agents/markets/universe.py`
- [ ] Grep for `agents.markets.universe`; update README (~lines 180, 247)

### Step 8 — Tests

- [ ] Add `tests/test_universe.py` (see Testing section)
- [ ] Run `PYTHONPATH=src python -m pytest tests/test_pipeline.py tests/test_universe.py -v`

### Step 9 — Documentation

- [ ] `README.md` — add `universe/` package to layout; remove from `agents/markets/`
- [ ] `research/codebase-current-state.md` — new § for shared universe; update §6.1, §9, §18

---

## Testing

### New: `tests/test_universe.py`

- [ ] `TICKER_TO_SECTOR` matches legacy map for all ETF symbols + SPY
- [ ] `symbols_for_fundamentals([], max_extra=0)` → 9 `(label, symbol)` pairs
- [ ] `vol_labeled_symbols()` → 6 pairs (VIX + 5 sectors); symbols ⊆ `SECTOR_ETFS` values ∪ `{^VIX}`
- [ ] Changing a mock entry in `SECTOR_ETFS` (monkeypatch) propagates to `symbols_for_fundamentals` and `TICKER_TO_SECTOR`

### Regression: existing suite (`tests/test_pipeline.py`)

| Test | Why it matters |
|------|----------------|
| `test_assemble_fuzzy_clusters_sector_themes` | Financials merge across 3 agents |
| `test_assemble_merges_markets_fundamentals_and_vol_same_sector` | Markets vol + fundamentals same sector |
| `test_assemble_clusters_and_maps_views` | Tech cluster name + 3 agents |
| `test_build_regime_input_from_market_snapshots` | SPY/XLK in regime block |

**Acceptance:** All above pass with identical assertions on `FinalTheme.name` and `contributing_agents`.

---

## Rollout

- Refactor-only PR; no env or user migration
- Recommend **Clear checkpoint** after deploy if ETF symbols were changed in the same release (stale `data_plane.json` rows use old symbol labels)
- No `reports/latest.json` schema change
- Document in PR: vol remains 5-sector subset; adding Consumer/Industrials/Utilities to vol requires editing `VOL_SECTOR_LABELS` only

---

## Observability

<!-- Not applicable: no new logging, metrics, or runtime diagnostics. -->

---

## Security

<!-- Not applicable: no secrets, auth, or new network endpoints. -->
