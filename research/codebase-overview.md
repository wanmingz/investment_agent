# Investment Agent — Codebase Research Document

*Generated from live code inspection. Describes behavior as implemented today.*

---

## High-Level Summary

`investment-agent` (v0.1.0) is a Python multi-agent pipeline that produces a structured `InvestmentBrief` JSON report. Four specialist LLM agents (Macro, News/RAG, Equity, Quant) each emit an independent `themes[]` list; a fifth LLM call acts as CIO to merge and rank themes into `FinalTheme` rows. Non-LLM data comes from Finnhub, TickerTick, and yfinance via `httpx` and `yfinance`. Execution is orchestrated sequentially in `ThemeOrchestrator.run()` with optional checkpoint resume under `reports/cache/`. Entry points are `main.py` / `invest-themes` (CLI), `streamlit run streamlit_app.py` / `invest-dashboard` (UI). There is no `tests/` directory in the repository.

---

## Repository Layout

```
investment_agent/
├── main.py                          # CLI entry shim
├── streamlit_app.py                 # Streamlit UI
├── pyproject.toml                   # deps, console scripts
├── .env.example                     # env var template
├── README.md                        # user-facing docs
├── research/                        # research documents (this file)
└── src/investment_agent/
    ├── orchestrator.py              # pipeline + CIO synthesis
    ├── checkpoint.py                # partial-run cache
    ├── storage.py                   # latest.json persistence
    ├── models.py                    # Pydantic schemas
    ├── config.py                    # Settings.from_env()
    ├── llm.py                       # OpenAI-compatible structured JSON client
    ├── dates.py                     # analysis date helpers
    ├── errors.py                    # QuotaExhaustedError
    ├── themes.py                    # theme_key() helper
    ├── brief_compat.py              # backward-compatible brief accessors
    ├── market_data.py               # VolSnapshot for quant agent
    ├── cli.py                       # CLI implementation
    ├── dashboard.py                 # streamlit launcher subprocess
    ├── agents/                      # four specialist agents
    ├── news/                        # ingest + lexical RAG
    └── data/                        # yfinance fundamentals snapshot
```

Runtime artifacts (not in git by default): `reports/latest.json`, `reports/cache/*.json`.

---

## Entry Points

| Path | Role |
|------|------|
| `main.py:1-4` | Imports and calls `investment_agent.cli.main` |
| `src/investment_agent/cli.py:133-201` | `main()` — argparse, `ThemeOrchestrator.run()`, `save_brief()`, Rich print or `--json` |
| `streamlit_app.py:327-424` | `main()` — sidebar controls, run orchestrator, render `InvestmentBrief` |
| `src/investment_agent/dashboard.py:6-9` | `main()` — subprocess `streamlit run streamlit_app.py` |
| `pyproject.toml:17-19` | Console scripts `invest-themes`, `invest-dashboard` |

---

## Configuration (`config.py`)

`Settings` is a frozen dataclass loaded via `Settings.from_env()` (`config.py:22-84`).

| Field | Source |
|-------|--------|
| `api_key`, `base_url`, `model`, `provider` | `GEMINI_*` or `OPENAI_*` env vars |
| `market_region` | `MARKET_REGION` (default `global`) |
| `finnhub_api_key` | `FINNHUB_API_KEY` |
| `news_max_articles` | `NEWS_MAX_ARTICLES` (default 40) |
| `rag_top_k` | `RAG_TOP_K` (default 12) |

Provider resolution order (`config.py:34-75`): explicit `LLM_PROVIDER=gemini` → `OPENAI_API_KEY` → fallback `GEMINI_API_KEY`; raises `ValueError` if no key.

Gemini default base URL: `https://generativelanguage.googleapis.com/v1beta/openai/` (`config.py:8`). Default model: `gemini-2.0-flash` (`config.py:9`).

---

## Data Models (`models.py`)

### Theme lifecycle

`ThemeStage` enum: `early`, `early_mid`, `mid`, `mid_late`, `late` (`models.py:7-21`). Labels in `STAGE_LABELS` (`models.py:23-29`).

### Per-agent theme row

`AgentTheme` (`models.py:49-64`): `name`, `subtitle` (alias `name_zh`), `thesis`, `stage`, `stage_rationale`, `confidence`, `key_drivers`, `risks`, `tickers_or_sectors`.

### Agent reports

| Model | Key fields | Lines |
|-------|------------|-------|
| `MacroReport` | `macro_backdrop`, `dominant_regime`, `themes`, `cross_asset_signals` | `67-71` |
| `NewsReport` | `news_backdrop`, `narrative_sentiment`, `citations`, `themes`, RAG metadata | `100-110` |
| `EquityReport` | `market_style`, `themes`, `valuation_notes` | `74-77` |
| `QuantReport` | `vol_regime`, `vix_proxy_level`, `themes`, `vol_signals` | `80-84` |

### CIO output

`FinalTheme` (`models.py:113-144`): merged theme with `consensus_score`, `investability_score`, `contributing_agents`, `primary_agent`, `agent_stages`, `synthesis`, sourced drivers/risks.

`InvestmentBrief` (`models.py:147-172`): final report with four agent views, `themes[]`, agent theme snapshots (`macro_themes` … `quant_themes`), `news_citations`, `fundamentals_notes`, `data_sources`, fixed `disclaimer`.

Supporting types: `NewsCitation` (`87-92`), `SourcedItem` (`95-97`).

---

## LLM Client (`llm.py`)

`LLMClient` wraps `openai.OpenAI` with `settings.api_key` and `settings.base_url` (`llm.py:71-77`).

`structured(system, user, schema, temperature=0.3)` (`llm.py:79-157`):

1. Appends JSON schema to system prompt (`llm.py:87-93`).
2. Calls `chat.completions.create` with `response_format=json_object` first, retries without (`llm.py:100-111`).
3. Parses response via `_extract_json` (strips markdown fences, `llm.py:23-28`).
4. Validates with Pydantic `schema.model_validate`.
5. On 429: retries up to `LLM_MAX_RETRIES_ON_429` (default 2, `llm.py:63-68`), then raises `QuotaExhaustedError` (`errors.py:6-40`).

---

## Orchestration (`orchestrator.py`)

### `ThemeOrchestrator`

Constructs one shared `LLMClient` and four agents (`orchestrator.py:91-98`).

### `run(resume=None)` pipeline (`orchestrator.py:100-165`)

| Step | Action | Checkpoint name |
|------|--------|-----------------|
| 0 | `fetch_vol_snapshot()` | — |
| 1 | `MacroEconomist.analyze()` | `macro` |
| 2 | `NewsAnalyst.analyze()` | `news` |
| 3 | `fetch_fundamentals_snapshot([])` | `fundamentals` |
| 4 | `EquityResearchAnalyst.analyze(news, fundamentals)` | `equity` |
| 5 | `QuantAnalyst.analyze(vol, dominant_regime=macro.dominant_regime)` | `quant` |
| 6 | `_synthesize()` — CIO LLM | not checkpointed |
| 7 | `_enrich_brief()` — program metadata | — |
| 8 | `clear_checkpoint()` on success | — |

`as_of` date from `analysis_date()` (`dates.py:14-16`). Resume controlled by `checkpoint.is_resume_enabled()` unless `resume` arg overrides (`orchestrator.py:103`). Mismatched `as_of`/`region` clears cache (`orchestrator.py:106-107`).

### Cross-agent inputs (as wired in `run`)

| Consumer | Receives from upstream |
|----------|------------------------|
| Equity | Full `NewsReport`; only `news_backdrop` + `narrative_sentiment` passed to prompt (`equity_analyst.py:56-59`) |
| Quant | `VolSnapshot` + `macro.dominant_regime` string (`orchestrator.py:143-146`) |
| CIO | All four `*Report.model_dump()` + optional `fundamentals.summary_lines()` (`orchestrator.py:177-184`) |

Agents do not receive each other's `themes[]` lists in their prompts (except CIO).

### `_synthesize()` (`orchestrator.py:167-201`)

- System prompt: `SYNTHESIS_SYSTEM` (`orchestrator.py:35-88`) — merge rules, 4–8 final themes, `investability_score` ranking.
- User payload: JSON of four agent reports.
- `temperature=0.2`.
- Returns `InvestmentBrief` from LLM.

### `_enrich_brief()` (`orchestrator.py:203-272`)

Programmatic updates:

- `report_date`, `as_of_context` via `build_as_of_context` (`dates.py:45-66`)
- Normalizes `FinalTheme.stage` / `stage_label`
- Default `data_sources` list if empty (`orchestrator.py:229-246`)
- `news_view` fallback to `news.news_backdrop` (`orchestrator.py:252`)
- Copies `news_citations`, `macro_themes` … `quant_themes`, `fundamentals_notes`

### `compute_stage_consensus()` (`orchestrator.py:275-294`)

Debug helper: maps `theme_key(name)` → per-agent stages using `themes.py:10-14`.

---

## Agent 1 — Macro (`agents/macro_economist.py`)

- **External data:** none; single `LLMClient.structured` call (`macro_economist.py:49-61`).
- **Input:** `as_of` date, `settings.market_region`.
- **Output:** `MacroReport` with 4–6 macro themes.
- **Prompt:** `SYSTEM` (`macro_economist.py:8-41`) defines five lifecycle stages and JSON schema.

---

## Agent 2 — News / RAG (`agents/news_analyst.py`, `news/`)

### `NewsAnalyst.analyze()` (`news_analyst.py:50-112`)

1. `build_news_retrieval_query(region)` — `news/rag.py:16-29`
2. `fetch_news_articles(...)` — `news/ingest.py:142-177`
3. `retrieve_articles(corpus, query, top_k)` — lexical overlap scoring, `news/rag.py:51-81`
4. `format_context_block(retrieved)` — `news/rag.py:84-93`
5. LLM → `NewsReport`
6. Post-process: merge missing `citations` from retrieved articles (`news_analyst.py:81-111`)

### News ingest (`news/ingest.py`)

| Provider | Endpoint | ID prefix | Lines |
|----------|----------|-----------|-------|
| Finnhub | `https://finnhub.io/api/v1/news` | `fh-` | `47-85`, `160-165` |
| TickerTick | `https://api.tickertick.com/feed` | `tt-` | `88-127`, `167-172` |

`NewsArticle` dataclass (`ingest.py:17-29`). Dedup by title prefix (`ingest.py:130-139`). Region affects Finnhub category and TickerTick query (`ingest.py:154-172`).

### Lexical RAG (`news/rag.py`)

- Token regex `[a-z0-9]{3,}` (`rag.py:9-13`).
- Score = token overlap + 2× title overlap (`rag.py:70-72`).
- Fallback: first `k` articles if no overlap (`rag.py:80-81`).
- `build_retrieval_query()` with macro themes exists as legacy (`rag.py:32-48`); not used by `NewsAnalyst`.

---

## Agent 3 — Equity (`agents/equity_analyst.py`)

- **External data:** `FundamentalsSnapshot.to_prompt_block()` when provided (`equity_analyst.py:51-55`).
- **News input:** backdrop + sentiment only (`equity_analyst.py:56-59`).
- **Output:** `EquityReport` with 4–6 equity themes (`equity_analyst.py:70-72`).

---

## Agent 4 — Quant (`agents/quant_analyst.py`)

- **External data:** `VolSnapshot.to_prompt_block()` (`quant_analyst.py:62-63`).
- **Macro input:** optional one-line `dominant_regime` hint (`quant_analyst.py:49-52`).
- **Output:** `QuantReport` with `vol_regime`, themes, `vol_signals` (`quant_analyst.py:65-67`).

---

## Market Data — Volatility (`market_data.py`)

`fetch_vol_snapshot()` (`market_data.py:28-67`):

- Symbols: `^VIX`, `XLK`, `XLE`, `XLV`, `XLF`, `IGV` (`market_data.py:39-46`).
- Computes VIX level, 20d change, 20d annualized vol per sector ETF.
- Returns `VolSnapshot` with `notes` on failures (`market_data.py:8-14`).

---

## Market Data — Fundamentals (`data/`)

### Universe (`data/universe.py`)

- `SECTOR_ETFS` — 8 sector labels → symbols (`universe.py:8-17`).
- `BENCHMARK_SYMBOL = "SPY"` (`universe.py:19`).
- `symbols_for_fundamentals()` — sectors + SPY + optional theme tickers capped by `FUNDAMENTALS_MAX_TICKERS` (`universe.py:44-77`).

### Snapshot fetch (`data/snapshot.py`)

`fetch_fundamentals_snapshot(themes, ...)` (`snapshot.py:155-214`):

- Orchestrator passes `[]` for themes (`orchestrator.py:125-128`) → fixed ETF universe only.
- Parallel fetch via `ThreadPoolExecutor` (`snapshot.py:177-196`).
- Per symbol: `fetch_price_metrics`, `fetch_valuation_metrics`, optional `fetch_revision_metrics` for non-ETF symbols when Finnhub key present (`snapshot.py:131-152`, `180-181`).
- Rule-based `signals` via `_build_signals()` (`snapshot.py:97-128`).

### Price (`data/price.py:32-66`)

yfinance 1y history → `last_close`, 20d/60d returns, vs 52w high, vs SPY 20d.

### Valuation (`data/valuation.py:30-49`)

yfinance `.info` → trailing/forward P/E, P/B, market cap.

### Revisions (`data/revisions.py:40-91`)

Finnhub `GET /stock/recommendation` → `revision_proxy` = (strongBuy+buy−sell−strongSell)/total.

---

## Checkpoint (`checkpoint.py`)

- Directory: `reports/cache/` relative to repo root (`checkpoint.py:21-22`).
- Enabled when `RESUME_CHECKPOINT` is `1`/`true`/`yes`/`on` (`checkpoint.py:25-33`).
- `run_meta.json` stores `{as_of, region}` (`checkpoint.py:41-63`).
- Per-step JSON: `macro`, `news`, `equity`, `quant` via Pydantic; `fundamentals` via custom dataclass serialization (`checkpoint.py:86-117`, `138-167`).
- `clear_checkpoint()` deletes all `*.json` in cache dir (`checkpoint.py:131-135`).
- Successful full run clears checkpoint (`orchestrator.py:163-164`).

---

## Persistence (`storage.py`)

- Default path: `reports/latest.json` (`storage.py:8`).
- `save_brief()` — `model_dump_json(by_alias=True)` (`storage.py:11-18`).
- `load_brief()` — validates via `migrate_brief_dict()` from `brief_compat.py` (`storage.py:21-27`, `brief_compat.py:49-66`).

---

## UI Layer

### Streamlit (`streamlit_app.py`)

- Inserts `src/` on `sys.path` (`streamlit_app.py:9-12`).
- Sidebar: region select, run, resume checkbox, checkpoint clear, load cache (`streamlit_app.py:333-366`).
- Run: `ThemeOrchestrator(settings).run(resume=resume_ckpt)` + `save_brief()` (`streamlit_app.py:385-389`).
- Renders agent tabs, pre-merge themes, news citations, theme cards sorted by `investability_score` (`streamlit_app.py:241-324`).

### CLI (`cli.py`)

- `print_brief()` — Rich panels and theme table (`cli.py:40-130`).
- Handles `QuotaExhaustedError` with checkpoint step listing (`cli.py:184-189`).

---

## End-to-End Data Flow

```
Settings.from_env()
       │
       ▼
ThemeOrchestrator.run()
       │
       ├─► MacroReport          (LLM only)
       ├─► NewsReport            (Finnhub + TickerTick → RAG → LLM)
       ├─► FundamentalsSnapshot  (yfinance [+ Finnhub revisions])
       ├─► EquityReport          (LLM + news backdrop + fundamentals)
       ├─► QuantReport           (LLM + VolSnapshot + regime hint)
       │
       ├─► InvestmentBrief       (CIO LLM merge)
       └─► _enrich_brief()       (program: dates, citations, snapshots)
                │
                ▼
         save_brief() → reports/latest.json
```

**LLM calls per full run:** 5 (macro, news, equity, quant, CIO).

**HTTP external services:**

| Service | Used by | Library |
|---------|---------|---------|
| Gemini/OpenAI compatible API | All agents + CIO | `openai` |
| Finnhub news | `news/ingest.py` | `httpx` |
| Finnhub recommendations | `data/revisions.py` | `httpx` |
| TickerTick feed | `news/ingest.py` | `httpx` |
| Yahoo Finance | `market_data.py`, `data/price.py`, `data/valuation.py` | `yfinance` |

---

## Python Dependencies (`pyproject.toml:7-15`)

`openai`, `pydantic`, `python-dotenv`, `rich`, `yfinance`, `streamlit`, `httpx`. Requires Python `>=3.11`.

---

## Tests and Fixtures

No `tests/`, `test_*.py`, or fixture directories exist in the repository as of this inspection.

---

## Cross-Component Connections Summary

| From | To | What flows |
|------|-----|------------|
| `config.Settings` | All agents, `LLMClient` | API keys, region, news/RAG limits |
| `MacroReport.dominant_regime` | `QuantAnalyst` | One-line regime hint |
| `NewsReport` | `EquityResearchAnalyst` | `news_backdrop`, `narrative_sentiment` |
| `FundamentalsSnapshot` | `EquityResearchAnalyst`, CIO payload | Prompt block, `summary_lines` |
| `VolSnapshot` | `QuantAnalyst` | `to_prompt_block()` |
| Four `*Report` | CIO `_synthesize` | Full JSON dumps |
| `NewsReport.citations` | `InvestmentBrief.news_citations` | Via `_enrich_brief` |
| Agent `themes[]` | `InvestmentBrief.*_themes` | Snapshot copies in `_enrich_brief` |
| `brief_compat` | `storage.load_brief`, CLI, Streamlit | Safe field access, schema migration |
