# Investment Agent — Codebase Current State

*Documented from live source as of 2026-07-04. Describes behavior only; no recommendations.*

---

## High-Level Summary

Investment Agent (v2) is a multi-agent pipeline that produces an `InvestmentBrief` by running three domain agents—**Regime**, **Narrative**, and **Markets**—each on disjoint inputs built by a programmatic **Data Plane**, then merging outputs in a programmatic **Brief Assembler** (no LLM). Each full run performs **three LLM structured-JSON calls** (one per agent) via `LLMClient`, using OpenAI-compatible APIs (Gemini, OpenAI, Groq, OpenRouter). External data sources are **yfinance** (market fundamentals and volatility), **Finnhub** (optional news and revision proxy), and **TickerTick** (curated news feed). Entry points are `main.py` / `invest-themes` CLI, `streamlit_app.py` / `invest-dashboard`, and `ThemeOrchestrator.run()`. Checkpoint/resume persists partial runs under `reports/cache/` at pipeline version **6**. All agent LLM outputs are English-only.

---

## 1. Package Layout and Entry Points

### 1.1 Runtime package (`src/investment_agent/`)

| Path | Role |
|------|------|
| `main.py` | Delegates to `investment_agent.cli:main` |
| `orchestrator.py` | `ThemeOrchestrator` — full run lifecycle |
| `data_plane.py` | `build_data_plane()` — wires all agent inputs |
| `brief_assembler.py` | `assemble()` — sector clustering and ranking |
| `checkpoint.py` | Resume cache (`PIPELINE_VERSION = 6`) |
| `llm.py` | `LLMClient.structured()` — JSON schema validation |
| `models.py` | Pydantic report/brief schemas |
| `config.py` | `Settings.from_env()` |
| `storage.py` | `save_brief` / `load_brief` + legacy migration |
| `dates.py` | Analysis date formatting |
| `cli.py` | CLI and `dashboard_main()` |
| `universe/` | Shared sector ETF registry (Markets fetch, Regime, BriefAssembler) |
| `agents/regime/` | Regime agent + input builder |
| `agents/narrative/` | Narrative ingest, RAG, input, agent |
| `agents/markets/` | Markets fetch, snapshot, input, agent |

### 1.2 Entry points

- **CLI:** `src/investment_agent/cli.py:140-208` — `main()` parses `--json`, `--region`, `--output`; constructs `ThemeOrchestrator(settings).run()`; saves via `save_brief`.
- **Streamlit:** `streamlit_app.py:411` — `ThemeOrchestrator(settings).run(resume=resume_ckpt)`; sidebar controls checkpoint resume/clear and load last result from `reports/latest.json`.
- **Console scripts:** `pyproject.toml:17-19` — `invest-themes`, `invest-dashboard`.

### 1.3 Non-runtime paths

- `tests/test_pipeline.py` — unit tests for data plane, regime input, assembler, RAG truncation, brief migration.
- `research/` — empty in working tree at documentation time; git HEAD contains prior design docs (`architecture-and-input-contracts.md`, `codebase-overview.md`, `data-agent-relationship.md`, `three-domain-agents-design.md`) that are deleted locally per git status.
- Legacy `src/investment_agent/data/` and `src/investment_agent/news/` packages are **not present on disk**; no imports reference them.

---

## 2. Configuration (`config.py`)

`Settings.from_env()` (`config.py:79-138`) loads environment via `python-dotenv` (`config.py:4-6`).

| Field | Source | Default behavior |
|-------|--------|------------------|
| `provider` | `LLM_PROVIDER`, key presence | `"gemini"` if `GEMINI_API_KEY`; else `"openai"` if `OPENAI_API_KEY` |
| `api_key`, `base_url`, `model` | `GEMINI_*` / `OPENAI_*` | Gemini default model `gemini-2.0-flash` (`config.py:9`) |
| `market_region` | `MARKET_REGION` | `"global"` |
| `finnhub_api_key` | `FINNHUB_API_KEY` | `""` |
| `news_max_articles` | `NEWS_MAX_ARTICLES` | 25 if Groq base URL; else 80 (`config.py:130`) |
| `rag_top_k` | `RAG_TOP_K` | 5 if Groq; else 24 (`config.py:131`) |
| `rag_summary_max_chars` | `RAG_SUMMARY_MAX_CHARS` | 180 if Groq; else 500 (`config.py:132`) |
| `rag_context_max_chars` | `RAG_CONTEXT_MAX_CHARS` | 3000 if Groq; else 10000 (`config.py:133`) |
| `llm_parallel_agents` | `LLM_PARALLEL_AGENTS` or provider heuristics | `False` for Groq and OpenRouter `:free` models (`config.py:39-48`) |
| `llm_agent_delay_seconds` | `LLM_AGENT_DELAY_SECONDS` or OpenRouter free default | 5.0s for OpenRouter `:free` (`config.py:51-60`) |

Groq detection: `"groq.com" in base_url` (`config.py:31-32`). OpenRouter free: `"openrouter.ai"` and `":free" in model` (`config.py:35-36`).

---

## 3. Data Plane (`data_plane.py`)

`build_data_plane(settings, as_of=None)` (`data_plane.py:42-75`):

1. `fetch_market_snapshots(settings, as_of)` → `MarketSnapshots` + notes
2. `build_regime_input(market_snapshots, ...)` → `RegimeInput` + notes
3. `build_narrative_input(settings, ...)` → `NarrativeInput` + notes
4. `build_markets_input(market_snapshots, ...)` → `MarketsInput`

Returns frozen `DataPlaneSnapshot` (`data_plane.py:32-39`) containing all three agent inputs and `data_plane_notes`.

**Design constraint (orchestrator):** agents never receive other agents' `*Report` objects; inputs are built independently in the data plane.

---

## 4. Regime Agent

### 4.1 Input (`agents/regime/input.py`)

- `RegimeInput` (`agents/regime/input.py:13-18`): `as_of`, `region`, `regime_context_block`, `context_notes`.
- `build_regime_input(snapshots, ...)` (`agents/regime/input.py:83-102`) derives `regime_context_block` from shared `MarketSnapshots` via `_build_regime_context_block` (`agents/regime/input.py:21-80`):
  - Volatility section: VIX level, 20d change, sector ann. vol from `VolSnapshot`
  - Sector rotation: SPY 20d return; per-ETF 20d return and vs SPY
  - Rule-based hints from `FundamentalsSnapshot.signals` (up to 8)
  - Data notes from fundamentals (up to 3)

### 4.2 Agent (`agents/regime/agent.py`)

- `RegimeAgent.analyze(inp: RegimeInput) -> RegimeReport` (`agents/regime/agent.py:49-67`)
- System prompt requests 4–6 macro themes with lifecycle stages (`agents/regime/agent.py:6-42`)
- Single `LLMClient.structured(..., schema=RegimeReport)` call

---

## 5. Narrative Agent

### 5.1 Ingest (`agents/narrative/ingest.py`)

- `NewsArticle` dataclass (`agents/narrative/ingest.py:17-29`): `id`, `title`, `summary`, `url`, `source`, `published_at`, `provider`; `text` property joins title + summary.
- **Finnhub:** `GET https://finnhub.io/api/v1/news` with `category` (`general` / `forex` / `crypto` by region) (`agents/narrative/ingest.py:47-85`, `agents/narrative/ingest.py:154-158`)
- **TickerTick:** `GET https://api.tickertick.com/feed` with `q` and `n` params (`agents/narrative/ingest.py:88-127`)
  - Default query `T:curated`; China region uses `(or tt:baba tt:jd tt:china)` (`agents/narrative/ingest.py:167-169`)
- `fetch_news_articles(...)` (`agents/narrative/ingest.py:142-177`): merges providers, dedupes by title prefix (`agents/narrative/ingest.py:130-138`), caps at `NEWS_MAX_ARTICLES` / `max_articles`.

### 5.2 RAG (`agents/narrative/rag.py`)

- `build_news_retrieval_query(region, extra_terms)` (`agents/narrative/rag.py:16-29`): region + fixed macro/market keyword string; no upstream agent theme names.
- `build_retrieval_query(...)` (`agents/narrative/rag.py:32-48`): documented as legacy helper accepting `theme_names` and `macro_backdrop`.
- `retrieve_articles(articles, query, top_k)` (`agents/narrative/rag.py:51-81`): lexical token overlap scoring; title tokens weighted 2×; fallback to first N if no overlap.
- `format_context_block(articles, max_summary_chars, max_total_chars)` (`agents/narrative/rag.py:91-119`): builds markdown context; truncates per-article and total char budget; appends omission note when truncated.

### 5.3 Input (`agents/narrative/input.py`)

- `build_narrative_input(settings, as_of, region)` (`agents/narrative/input.py:29-60`):
  1. Build retrieval query
  2. `fetch_news_articles`
  3. `retrieve_articles` with `settings.rag_top_k`
  4. `format_context_block` with RAG char limits
- Returns `NarrativeInput` (`agents/narrative/input.py:17-26`) including frozen `retrieved` tuple for checkpoint/citation backfill.

### 5.4 Agent (`agents/narrative/agent.py`)

- `NarrativeAgent.analyze(inp) -> NarrativeReport` (`agents/narrative/agent.py:22-64`)
- System prompt:Seat for 3–4 headline-grounded themes with citation rules (`agents/narrative/agent.py:6-15`)
- Post-LLM: backfills `citations` from `inp.retrieved` if LLM returned fewer (`agents/narrative/agent.py:35-55`); always sets `retrieval_query`, `articles_retrieved`, `ingest_notes` on report (`agents/narrative/agent.py:48-63`)

---

## 5.5 Shared Universe (`universe/`)

Cross-agent sector ETF registry; not owned by any single agent package.

### `universe/constants.py`

- `SECTOR_ETFS`: 8 sector label → symbol (Tech→XLK … Utilities→XLU)
- `BENCHMARK_SYMBOL = "SPY"`, `VIX_SYMBOL = "^VIX"`
- `VOL_SECTOR_LABELS`: frozenset of 5 labels used for vol fetch (Tech, Energy, Healthcare, Financials, AI/Cloud)
- `TICKER_TO_SECTOR`: lowercase symbol → canonical sector key (e.g. `igv→tech`, `spy→benchmark`); used by `brief_assembler._primary_sector`
- `SECTOR_DISPLAY_ETF`: display names for ETF-backed sector keys

### `universe/symbols.py`

- `symbols_for_fundamentals(theme_tickers, max_extra=8)` — fundamentals fetch list
- `vol_labeled_symbols()` — VIX + vol subset sectors
- `is_likely_ticker`, `extract_tickers_from_themes`, `sector_key_for_symbol`

### Consumers

- `agents/markets/snapshot.py` — fundamentals + vol yfinance fetches
- `agents/regime/input.py` — `BENCHMARK_SYMBOL` for regime context block
- `brief_assembler.py` — `sector_key_for_symbol`, `SECTOR_DISPLAY_ETF` for theme clustering

---

## 6. Markets Agent

### 6.1 Price metrics (`agents/markets/price.py`)

- `PriceMetrics` (`agents/markets/price.py:12-20`): last close, 20d/60d return %, vs 52w high %, vs SPY 20d pp
- `fetch_price_metrics(symbol, spy_return_20d)` (`agents/markets/price.py:36-70`): `yfinance.Ticker(symbol).history(period="1y")`

### 6.2 Valuation metrics (`agents/markets/valuation.py`)

- `ValuationMetrics` (`agents/markets/valuation.py:12-19`): trailing/forward P/E, P/B, market cap (billions)
- `fetch_valuation_metrics(symbol)` (`agents/markets/valuation.py:34-53`): `yf.Ticker(symbol).info`

### 6.3 Revision proxy (`agents/markets/revisions.py`)

- `RevisionMetrics` (`agents/markets/revisions.py:16-26`): net recommendation score and trend label
- `fetch_revision_metrics(symbol, finnhub_key)` (`agents/markets/revisions.py:44-95`): `GET https://finnhub.io/api/v1/stock/recommendation`
- Score: `(strongBuy + buy - sell - strongSell) / total` (`agents/markets/revisions.py:29-39`)

### 6.4 Snapshots (`agents/markets/snapshot.py`)

Symbol lists from `universe/` (`symbols_for_fundamentals`, `vol_labeled_symbols` — see §5.5).

**Fundamentals:**

- `SymbolFundamentals`, `FundamentalsSnapshot` (`agents/markets/snapshot.py:18-32`)
- `fetch_fundamentals_snapshot(...)` (`agents/markets/snapshot.py:148-203`):
  - Resolves symbol list via `symbols_for_fundamentals`; `FUNDAMENTALS_MAX_TICKERS` env default 8 (`agents/markets/snapshot.py:156`)
  - Fetches SPY first for benchmark 20d return
  - `ThreadPoolExecutor` (max 6 workers) per symbol via `_fetch_one` (`agents/markets/snapshot.py:124-146`, `agents/markets/snapshot.py:167-186`)
  - Revision fetch only for symbols **not** in sector ETF set when `finnhub_key` present (`agents/markets/snapshot.py:170-171`)
  - `_build_signals(rows)` (`agents/markets/snapshot.py:90-121`): rule-based momentum, 52w high, elevated P/E, SPY outperformance, revision proxy thresholds
  - `to_prompt_block()` (`agents/markets/snapshot.py:34-73`) and `summary_lines()` (`agents/markets/snapshot.py:75-87`)

**Volatility:**

- `VolSnapshot` (`agents/markets/snapshot.py:206-223`): VIX level, VIX 20d change %, `sector_vol` dict, notes
- `fetch_vol_snapshot()` (`agents/markets/snapshot.py:226-265`): uses `vol_labeled_symbols()`; 20d ann. vol from 1mo history

### 6.5 Input (`agents/markets/input.py`)

- `MarketSnapshots` (`agents/markets/input.py:17-22`): `{ fundamentals, vol }`
- `MarketsInput` (`agents/markets/input.py:25-30`): `as_of`, `region`, fundamentals, vol
- `fetch_market_snapshots(settings, as_of)` (`agents/markets/input.py:33-49`): calls both fetch functions; appends row-count notes
- `build_markets_input(snapshots, as_of, region)` (`agents/markets/input.py:52-63`): wraps snapshots into `MarketsInput`

### 6.6 Agent (`agents/markets/agent.py`)

- `MarketsAgent.analyze(inp) -> MarketsReport` (`agents/markets/agent.py:46-63`)
- System prompt requests fundamentals lens (3–5 themes) and vol lens (3–5 themes) in one JSON response (`agents/markets/agent.py:6-39`)
- User prompt includes `fundamentals.to_prompt_block()` and `vol.to_prompt_block()`

---

## 7. LLM Client (`llm.py`)

- `LLMClient` wraps `openai.OpenAI(api_key, base_url)` (`llm.py:199-205`)
- `structured(system, user, schema, temperature=0.3)` (`llm.py:207-296`):
  - Appends JSON schema to system prompt; compact schema strips descriptions when Groq or `LLM_COMPACT_SCHEMA=1` (`llm.py:215-226`, `llm.py:137-159`)
  - Retries on 429 with provider-specific backoff (`llm.py:231-274`, `llm.py:187-196`)
  - Raises `QuotaExhaustedError` on daily/rate limits (`llm.py:15-59`)
  - Raises `RuntimeError` with Groq token hints on 413 / context-too-large (`llm.py:125-134`, `llm.py:162-171`)
  - Parses JSON (strips markdown fences via `_extract_json`, `llm.py:70-75`); validates with Pydantic `schema.model_validate`

---

## 8. Orchestrator (`orchestrator.py`)

`ThemeOrchestrator.run(resume=None)` (`orchestrator.py:32-73`):

1. `as_of = analysis_date()`; region from settings
2. If resume enabled and meta mismatch → `clear_checkpoint()` (`orchestrator.py:37-38`)
3. Load or build `DataPlaneSnapshot`; save if resume (`orchestrator.py:42-46`)
4. Load cached `RegimeReport`, `NarrativeReport`, `MarketsReport` if resume (`orchestrator.py:48-50`)
5. `_run_pending_agents` for missing reports (`orchestrator.py:52-58`)
6. `assemble(regime, narrative, markets, as_of)` → `_enrich_brief(...)` (`orchestrator.py:62-70`)
7. `clear_checkpoint()` on successful completion when resume was used (`orchestrator.py:71-72`)

`_run_pending_agents` (`orchestrator.py:75-130`):

- Builds task list for agents with `None` reports
- Parallel: `ThreadPoolExecutor(max_workers=3)` when `settings.llm_parallel_agents` and >1 task (`orchestrator.py:116-124`)
- Sequential: sleeps `llm_agent_delay_seconds` between calls (`orchestrator.py:126-129`)
- Saves each completed report to checkpoint when resume enabled

`_enrich_brief` (`orchestrator.py:132-188`): sets `report_date`, `as_of_context`, `data_sources`, `fundamentals_notes` from data plane, per-agent theme lists, narrative citations.

`compute_stage_consensus(...)` (`orchestrator.py:191-211`): maps `theme_key(name)` → agent stages across three reports.

---

## 9. Brief Assembler (`brief_assembler.py`)

`assemble(regime, narrative, markets, as_of) -> InvestmentBrief` (`brief_assembler.py:342-428`):

1. `_collect_tagged` (`brief_assembler.py:258-272`): all themes from regime, narrative, markets fundamentals + vol (markets vol themes tagged `AGENT_MARKETS`)
2. `_cluster_tagged` (`brief_assembler.py:205-217`): one cluster per mergeable sector; non-sector themes clustered by title similarity (threshold 0.35)
3. Per cluster → `FinalTheme`:
   - `consensus_score = min(1.0, distinct_agents / 3)` (`brief_assembler.py:358`)
   - `investability_score = mean confidence, clamped 0–1` (`brief_assembler.py:357`, `brief_assembler.py:374`)
   - Display name from sector map or highest-confidence theme name (`brief_assembler.py:220-226`)
4. Sort by `investability_score + consensus_score` descending; keep top **8** (`brief_assembler.py:387-391`)
5. Build executive summary and agent views from report fields (`brief_assembler.py:393-410`)

Sector/ticker mapping for clustering: `TICKER_TO_SECTOR` and `SECTOR_DISPLAY_ETF` from `universe/constants.py`; theme-title tokens via `_SECTOR_WORDS` (`brief_assembler.py:45-70`); macro display via `_SECTOR_DISPLAY` (`brief_assembler.py:98-111`).

Narrative sourced drivers/risks attached to clusters via token overlap with narrative themes in cluster (`brief_assembler.py:317-339`).

---

## 10. Checkpoint (`checkpoint.py`)

- Cache directory: `reports/cache/` relative to project root (`checkpoint.py:30-31`)
- `PIPELINE_VERSION = 6` (`checkpoint.py:32`); mismatch clears resume via `meta_matches` (`checkpoint.py:74-80`)
- `RESUME_CHECKPOINT` env default enabled (`checkpoint.py:35-43`)
- Files: `run_meta.json`, `data_plane.json`, `regime.json`, `narrative.json`, `markets.json`
- `save_data_plane` / `load_data_plane` serialize dataclass snapshots including fundamentals rows and news articles (`checkpoint.py:176-264`)
- `_refresh_narrative_input` on load re-truncates `context_block` to current `RAG_*` settings (`checkpoint.py:152-173`)

---

## 11. Storage (`storage.py`)

- Default report path: `reports/latest.json` (`storage.py:20`)
- `save_brief(brief, path)` writes Pydantic JSON (`storage.py:186-193`)
- `load_brief(path)` runs `migrate_brief_dict` then `_normalize_loaded_brief` (`storage.py:196-227`)
- Legacy key mapping: `macro_*` → `regime_*`, `news_*` → `narrative_*`, `equity_*`/`quant_*` → `markets_*` (`storage.py:111-184`)
- Accessor helpers: `brief_narrative_view`, `brief_data_sources`, `brief_agent_themes`, etc. (`storage.py:34-69`)

---

## 12. Models (`models.py`)

| Model | Lines | Purpose |
|-------|-------|---------|
| `ThemeStage` | `models.py:17-22` | `early`, `early_mid`, `mid`, `mid_late`, `late` |
| `AgentTheme` | `models.py:59-74` | Per-agent theme row |
| `RegimeReport` | `models.py:90-96` | Regime LLM output |
| `NarrativeReport` | `models.py:99-111` | Narrative LLM output + citations |
| `MarketsReport` | `models.py:114-125` | Fundamentals + vol themes |
| `FinalTheme` | `models.py:128-167` | Merged ranked theme |
| `InvestmentBrief` | `models.py:175-199` | Final report |

Agent constants: `AGENT_REGIME`, `AGENT_NARRATIVE`, `AGENT_MARKETS` (`models.py:6-8`).

`theme_rank_score(theme)` = `investability_score + consensus_score` (`models.py:170-172`).

---

## 13. CLI and Streamlit UI

### CLI (`cli.py`)

- Rich-formatted tables sorted by `_theme_rank_score` (`cli.py:80-91`, `cli.py:100`)
- Displays narrative-sourced drivers/risks with citation titles (`cli.py:104-117`)
- On `QuotaExhaustedError`, prints `user_hint()` and lists checkpoint steps (`cli.py:195-200`)

### Streamlit (`streamlit_app.py`)

- Injects custom CSS for theme cards and stage badges (`streamlit_app.py:86-133`)
- Theme cards show rank, stage badge, agent pills with per-agent stages (`streamlit_app.py:179-199`, `streamlit_app.py:148-165`)
- Sidebar: resume toggle (default from `checkpoint.is_resume_enabled()`), clear checkpoint, load last result (`streamlit_app.py:371-387`)
- Sorts recommended themes by `investability_score + consensus_score` (`streamlit_app.py:82-83`)

---

## 14. Tests (`tests/test_pipeline.py`)

| Test | Validates |
|------|-----------|
| `test_regime_input_has_context_fields` | `RegimeInput.regime_context_block` field |
| `test_build_regime_input_from_market_snapshots` | VIX and XLK in regime block |
| `test_build_data_plane_wires_three_agent_inputs` | Mocked fetch; three inputs wired |
| `test_assemble_fuzzy_clusters_sector_themes` | Financials themes from 3 agents → 1 cluster |
| `test_assemble_merges_markets_fundamentals_and_vol_same_sector` | Both markets lenses same sector |
| `test_assemble_clusters_and_maps_views` | Tech clustering; narrative sourced drivers |
| `test_format_context_block_truncates_for_token_budget` | RAG char limits |
| `test_combined_theme_score_sort_order` | Rank score ordering |
| `test_migrate_brief_dict_maps_legacy_agent_keys` | v1 → v2 field migration |

Run: `PYTHONPATH=src python -m pytest tests/test_pipeline.py -v` (per `README.md:287-288`).

---

## 15. Cross-Component Data Flow

```
main.py / streamlit_app.py / cli.py
        │
        ▼
ThemeOrchestrator.run()                          [orchestrator.py:32-73]
        │
        ├─ build_data_plane()                      [data_plane.py:42-75]
        │     ├─ fetch_market_snapshots()          [agents/markets/input.py:33-49]
        │     │     ├─ fetch_fundamentals_snapshot [agents/markets/snapshot.py:148-203]
        │     │     └─ fetch_vol_snapshot          [agents/markets/snapshot.py:226-265]
        │     ├─ build_regime_input()              [agents/regime/input.py:83-102]
        │     ├─ build_narrative_input()           [agents/narrative/input.py:29-60]
        │     │     ├─ fetch_news_articles         [agents/narrative/ingest.py:142-177]
        │     │     ├─ retrieve_articles           [agents/narrative/rag.py:51-81]
        │     │     └─ format_context_block        [agents/narrative/rag.py:91-119]
        │     └─ build_markets_input()             [agents/markets/input.py:52-63]
        │
        ├─ RegimeAgent.analyze(RegimeInput)        [agents/regime/agent.py:49-67]
        ├─ NarrativeAgent.analyze(NarrativeInput)  [agents/narrative/agent.py:22-64]
        ├─ MarketsAgent.analyze(MarketsInput)      [agents/markets/agent.py:46-63]
        │     └─ LLMClient.structured × 3          [llm.py:207-296]
        │
        ├─ assemble() → InvestmentBrief            [brief_assembler.py:342-428]
        └─ _enrich_brief()                         [orchestrator.py:132-188]
              └─ save_brief → reports/latest.json  [storage.py:186-193]
```

### External services

| Service | Used by | Protocol |
|---------|---------|----------|
| OpenAI-compatible LLM API | `llm.py` | Chat completions + JSON |
| yfinance | `price.py`, `valuation.py`, `snapshot.py` | Python library |
| Finnhub news | `ingest.py` | REST `GET /api/v1/news` |
| Finnhub recommendations | `revisions.py` | REST `GET /api/v1/stock/recommendation` |
| TickerTick | `ingest.py` | REST `GET /feed` |

### Side effects and persistence

| Action | Location | Output |
|--------|----------|--------|
| HTTP fetches | ingest, revisions, yfinance | In-memory only during run |
| Checkpoint save | `checkpoint.py` | `reports/cache/*.json` during run |
| Brief save | CLI `--output` or Streamlit | `reports/latest.json` (or custom path) |
| Checkpoint clear | Successful run or manual | Deletes cache JSON files |

---

## 16. Dependencies (`pyproject.toml`)

Python `>=3.11`. Runtime deps: `openai`, `pydantic`, `python-dotenv`, `rich`, `yfinance`, `streamlit`, `httpx` (`pyproject.toml:7-15`).

---

## 17. Theme Lifecycle Stages (shared vocabulary)

All three agents use the same five stage values in prompts and `ThemeStage` enum (`models.py:17-22`):

| Code | Label (`STAGE_LABELS`) |
|------|------------------------|
| `early` | Early |
| `early_mid` | Early-Mid |
| `mid` | Mid |
| `mid_late` | Mid-Late |
| `late` | Late |

---

## 18. Symbols and Universe Reference

Sector ETF map (`universe/constants.py` — `SECTOR_ETFS`):

| Label | Symbol |
|-------|--------|
| Tech | XLK |
| Energy | XLE |
| Healthcare | XLV |
| Financials | XLF |
| AI/Cloud | IGV |
| Consumer | XLY |
| Industrials | XLI |
| Utilities | XLU |
| Benchmark | SPY |

Vol snapshot additionally uses `^VIX` (`agents/markets/snapshot.py:237-244`). Vol sector subset: Tech, Energy, Healthcare, Financials, AI/Cloud only (`agents/markets/snapshot.py:237-244`); Consumer, Industrials, Utilities are in fundamentals fetch but not vol ann. vol block.
