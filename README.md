# Investment Agent — Multi-Agent Theme Analysis

Four specialist agents each propose **their own investable theme list**; a CIO layer **merges and ranks** them with lifecycle stage: **Early / Early-Mid / Mid / Mid-Late / Late**.

| Agent | Role | Theme lens | External data |
|-------|------|------------|---------------|
| **Agent 1** | Macro Economist | Policy, rates, cross-asset regime | LLM only |
| **Agent 2** | News / RAG Analyst | Headline narrative heat | Finnhub + TickerTick, lexical RAG |
| **Agent 3** | Equity Research Analyst | Valuations, sector structure | yfinance sector ETF fundamentals |
| **Agent 4** | Quant Analyst | Volatility and risk timing | yfinance VIX / sector vol |
| **CIO** | Synthesis | Cluster, rank, final stage | Merges four independent lists |

**All prompts and outputs are in English.** Theme **names may differ** across agents until the CIO merge.

## Stage definitions

| Stage | Code | Meaning |
|-------|------|---------|
| Early | `early` | Theme forming, not fully priced — positioning |
| Early-Mid | `early_mid` | Thesis validating, narrative spreading |
| Mid | `mid` | Trend confirmed, earnings and flows supporting |
| Mid-Late | `mid_late` | Crowded, rich valuations, vol rising |
| Late | `late` | Overheated — exit watch |

## Quick start

```bash
cd investment_agent
python -m venv .venv
source .venv/bin/activate
pip install -e .

cp .env.example .env
# Set GEMINI_API_KEY or OPENAI_API_KEY in .env
```

### Gemini

1. Create an API key at [Google AI Studio](https://aistudio.google.com/apikey)
2. In `.env`:

```bash
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-key
GEMINI_MODEL=gemini-2.5-flash-lite
```

Run:

```bash
python main.py
invest-themes

python main.py --json
python main.py --region US
python main.py -o reports/latest.json
```

### Streamlit dashboard

```bash
streamlit run streamlit_app.py
# or
invest-dashboard
```

1. Select market region, click **Run analysis**
2. Or **Load last result** for `reports/latest.json`
3. Expand **Independent agent themes (before CIO merge)** to compare each agent’s raw theme list

## Environment variables

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Gemini key (with `LLM_PROVIDER=gemini`) |
| `GEMINI_MODEL` | Default `gemini-2.5-flash-lite` |
| `LLM_PROVIDER` | `gemini` or `openai` |
| `OPENAI_API_KEY` | OpenAI or compatible API key |
| `MARKET_REGION` | `global`, `US`, `China`, etc. |
| `FINNHUB_API_KEY` | Optional; more news via [Finnhub](https://finnhub.io/) |
| `NEWS_MAX_ARTICLES` | Max headlines to ingest (default `40`) |
| `RAG_TOP_K` | Articles passed to News Agent after retrieval (default `12`) |
| `FUNDAMENTALS_MAX_TICKERS` | Max theme tickers for yfinance fundamentals (default `8`) |
| `RESUME_CHECKPOINT` | Save agent outputs under `reports/cache/` for resume (default `1`) |
| `LLM_MAX_RETRIES_ON_429` | Short rate-limit retries in `llm.py` (default `2`) |

## Architecture

Multi-agent **investment theme research** prototype: four agents each output an independent `themes[]`; the CIO clusters similar ideas into ranked `FinalTheme` rows. Orchestrated in Python (no separate workflow engine). Outputs are structured JSON (`InvestmentBrief`) plus Streamlit/CLI views.

### Independent theme model

| Phase | What happens |
|-------|----------------|
| **Discover** | Each agent returns 3–6 themes with its own `name`, `stage`, and rationale |
| **Merge** | CIO clusters related themes (e.g. “AI capex” + “Hyperscaler spend”) |
| **Trace** | `contributing_agents`, `primary_agent`, sparse `agent_stages` (only agents that proposed the cluster) |
| **Rank** | `investability_score` (0–1, CIO-assigned) sorts final themes; `consensus_score` reflects multi-agent overlap |

Agents do **not** share a fixed theme checklist upstream. News RAG uses `build_news_retrieval_query()` (region + market terms only). Equity sees news **backdrop** text, not news theme titles. Quant sees **vol snapshot** + optional one-line macro regime hint only.

### System layers

```
┌─────────────────────────────────────────────────────────────┐
│  Entry: main.py / cli.py  ·  streamlit_app.py                │
└────────────────────────────┬────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  ThemeOrchestrator · checkpoint · storage (latest.json)      │
└────────────────────────────┬────────────────────────────────┘
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
    Macro (LLM)         News+RAG (LLM)     Vol snapshot [yfinance]
    own themes          own themes              │
         │                   │                   ▼
         │              Fundamentals [ETFs]   Quant (LLM)
         │                   │              own themes
         └─────────┬─────────┘                   │
                   ▼                             │
              Equity (LLM)                       │
              own themes                         │
                   └──────────────┬─────────────┘
                                  ▼
                         CIO merge (LLM)
                                  ▼
                    InvestmentBrief + agent theme snapshots
```

| Layer | Components | Role |
|-------|------------|------|
| **Entry** | `main.py`, `cli.py`, `streamlit_app.py` | Run analysis, load cache, display UI |
| **Orchestration** | `ThemeOrchestrator`, `checkpoint.py` | Sequential pipeline, resume on 429 |
| **Agents** | `agents/*.py` | One structured LLM call each (+ shared `LLMClient`) |
| **Data (non-LLM)** | `news/`, `data/`, `market_data.py` | Ingest, RAG, fundamentals, volatility |
| **Core** | `models.py`, `llm.py`, `config.py`, `dates.py`, `storage.py` | Schemas, API, env, persistence |

### Runtime pipeline

Entry points call `ThemeOrchestrator.run()` in `src/investment_agent/orchestrator.py`. A full run uses **~5 LLM requests** (macro → news → equity → quant → CIO).

```
fetch_vol_snapshot()                              [yfinance — no LLM]
MacroEconomist.analyze()                          [LLM → MacroReport.themes[]]
fetch_news_articles() + build_news_retrieval_query()
NewsAnalyst.analyze()                             [LLM → NewsReport.themes[] + citations]
fetch_fundamentals_snapshot([])                   [sector ETFs + SPY — no macro tickers]
EquityResearchAnalyst.analyze(news, fundamentals) [LLM → EquityReport.themes[]]
QuantAnalyst.analyze(vol, dominant_regime hint)   [LLM → QuantReport.themes[]]
CIO synthesis                                     [LLM → merge → InvestmentBrief.themes[]]
_enrich_brief()                                   [dates, data_sources, macro_/news_/equity_/quant_themes snapshots]
```

With `RESUME_CHECKPOINT=1` (default), each completed step is saved under `reports/cache/` (`macro.json`, `news.json`, `fundamentals.json`, `equity.json`, `quant.json`). After a quota error, rerun with **Resume from checkpoint** to skip finished agents.

```mermaid
flowchart TB
    subgraph entry [Entry]
        CLI[CLI]
        ST[Streamlit]
    end
    subgraph orch [Orchestrator]
        ORCH[ThemeOrchestrator]
        LLM[LLMClient]
    end
    subgraph discover [Independent discovery]
        A1[MacroEconomist]
        A2[NewsAnalyst]
        A3[EquityResearchAnalyst]
        A4[QuantAnalyst]
    end
    subgraph data [External data]
        NEWS[news/ingest + build_news_retrieval_query]
        FUND[data/snapshot sector ETFs]
        VOL[market_data VolSnapshot]
    end
    CIO[CIO merge and rank]
    CLI --> ORCH
    ST --> ORCH
    ORCH --> A1
    ORCH --> A2
    A2 --> NEWS
    ORCH --> FUND --> A3
    A2 -->|backdrop only| A3
    ORCH --> VOL --> A4
    A1 -->|regime hint| A4
    A1 & A2 & A3 & A4 --> CIO
    A1 & A2 & A3 & A4 & CIO --> LLM
```

### Agent inputs and external data

| Agent | Input (no shared theme list) | Output `themes[]` | External data |
|-------|-------------------------------|-------------------|---------------|
| **1 Macro** | Region, analysis date | 4–6 macro themes | None |
| **2 News** | Region; retrieved articles | 3–6 headline-driven themes | Finnhub (optional), TickerTick; `build_news_retrieval_query` |
| **3 Equity** | News backdrop + sentiment; fundamentals block | 4–6 equity themes | yfinance sector ETFs + SPY |
| **4 Quant** | `VolSnapshot`; optional `dominant_regime` string | 3–6 vol/risk themes | yfinance VIX, sector realized vol |
| **CIO** | Full JSON of all four reports | 4–8 merged `FinalTheme` | Sets `contributing_agents`, `primary_agent`, `investability_score` |

### Repository layout (`src/investment_agent/`)

| Path | Responsibility |
|------|----------------|
| `orchestrator.py` | Pipeline, CIO merge prompt, `_enrich_brief()` |
| `themes.py` | `theme_key()` for clustering / future history diff |
| `agents/macro_economist.py` | Independent macro theme list |
| `agents/news_analyst.py` | Independent news themes + citations |
| `agents/equity_analyst.py` | Independent equity themes + fundamentals block |
| `agents/quant_analyst.py` | Independent quant themes from vol |
| `news/ingest.py` | Headline fetch (Finnhub + TickerTick) |
| `news/rag.py` | `build_news_retrieval_query`, lexical retrieve, context block |
| `data/universe.py` | Sector ETFs, ticker extraction from themes |
| `data/price.py`, `valuation.py`, `revisions.py` | Per-symbol metrics |
| `data/snapshot.py` | `FundamentalsSnapshot` aggregation |
| `market_data.py` | `VolSnapshot` for quant agent |
| `llm.py` | OpenAI-compatible API, JSON schema output, 429 handling |
| `checkpoint.py` | Partial-run cache for resume |
| `errors.py` | `QuotaExhaustedError` with user hints |
| `models.py` | Pydantic reports and `InvestmentBrief` |
| `config.py`, `dates.py`, `storage.py`, `brief_compat.py` | Env, dates, `reports/latest.json`, schema migration |

Console entry points: `invest-themes` (CLI), `invest-dashboard` (Streamlit).

### Output model

**Per-agent reports** — each includes its **own** `themes[]` (five stages: `early` … `late`):

- `MacroReport`, `NewsReport`, `EquityReport`, `QuantReport`

**Final artifact** — `InvestmentBrief`:

- Narrative: `macro_view`, `news_view`, `equity_view`, `quant_view`, `executive_summary`
- **Agent snapshots** (pre-merge): `macro_themes`, `news_themes`, `equity_themes`, `quant_themes`
- **Merged themes**: `themes[]` → `FinalTheme` with:
  - `contributing_agents`, `primary_agent`
  - `agent_stages` — only agents that proposed the cluster (sparse map)
  - `consensus_score`, `investability_score` (CIO-assigned 0–1; not a coded formula)
  - optional `key_drivers_sourced` / `risks_sourced` (news citation IDs)
- Metadata: `news_citations`, `data_sources`, `fundamentals_notes`, `report_date`, `as_of_context`

### Cross-cutting behavior

| Concern | Implementation |
|---------|----------------|
| **LLM provider** | Gemini (OpenAI-compatible endpoint) or OpenAI via `config.py` / `.env` |
| **Persistence** | `storage.py` → `reports/latest.json` |
| **Quota / 429** | `llm.py` + `errors.py`; see [Gemini free-tier quota](#gemini-free-tier-quota-429) below |
| **Resume** | `checkpoint.py` + `RESUME_CHECKPOINT` |
| **Language** | All agent and CIO prompts/outputs in English |

### Scope (PoC vs production)

**In scope today:** independent multi-agent theme discovery, CIO merge/rank, news RAG with citations, sector-ETF fundamentals, theme lifecycle staging, CLI + Streamlit (including per-agent theme expander).

**Not in scope:** vector embeddings / vector DB, trained ML or forecasting models, CI/CD or model governance, integration with portfolio management or enterprise research platforms.

## Data sources

What each part of the report is based on.

| Output field | Primary source | Notes |
|--------------|----------------|-------|
| `report_date`, `as_of_context` (date prefix) | Local system clock | Set in `dates.py` / `_enrich_brief()` |
| Macro themes, `macro_backdrop`, `dominant_regime` | **LLM** (Agent 1) | Independent theme list; no live macro API |
| News themes, `news_view`, citations, sourced drivers/risks | **News RAG + LLM** (Agent 2) | `build_news_retrieval_query` — not macro theme names |
| Headlines ingested | **Finnhub** (optional) + **TickerTick** | See `news/ingest.py` |
| RAG retrieval | **Lexical match** | `news/rag.py` — region + market keyword query |
| Equity themes, `market_style`, `valuation_notes` | **LLM** (Agent 3) + **yfinance** | Sector ETF + SPY block only (`fetch_fundamentals_snapshot([])`) |
| `fundamentals_notes` | **Program** | Highlights from structured snapshot in `_enrich_brief()` |
| `macro_themes` … `quant_themes` on brief | **Program** | Copied from agent reports in `_enrich_brief()` |
| Quant themes, `vol_regime`, `vol_signals` | **LLM** (Agent 4) + **yfinance** | Vol block only; no equity/macro theme JSON |
| VIX level, sector 20d ann. vol | **yfinance** | `market_data.py` |
| Final `themes[]`, `contributing_agents`, `investability_score` | **LLM** (CIO) | Clusters four independent lists |
| `consensus_score`, sparse `agent_stages` | **LLM** (CIO) | High when multiple agents overlap |
| `key_drivers` / `risks` (plain strings) | **LLM** (CIO) | Model synthesis |
| `key_drivers_sourced` / `risks_sourced` | **LLM** (CIO) | Should use news `citation_ids` when supported |
| `data_sources` | **Program** | Auto-filled in `_enrich_brief()` if omitted |
| `tickers_or_sectors` | **LLM** | Illustrative only |

### News ingest (free tier)

| Provider | Auth | Endpoint / usage |
|----------|------|------------------|
| [Finnhub](https://finnhub.io/) | `FINNHUB_API_KEY` (optional) | `GET /api/v1/news?category=general` |
| [TickerTick](https://github.com/hczhu/TickerTick-API) | None | `GET api.tickertick.com/feed?q=T:curated` (10 req/min/IP) |

Without Finnhub, TickerTick alone still powers the news corpus.

### Live market data (yfinance)

Fetched at run time in `src/investment_agent/market_data.py`:

| Label | Symbol | Use |
|-------|--------|-----|
| VIX proxy | `^VIX` | Level and 20-day change |
| Tech | `XLK` | 20-day annualized realized vol |
| Energy | `XLE` | Same |
| Healthcare | `XLV` | Same |
| Financials | `XLF` | Same |
| AI / Cloud | `IGV` | Same |

If yfinance fails or is unavailable, quant analysis continues with LLM-only context (`notes` in the vol snapshot).

### Structured fundamentals (free tier)

Fetched before the equity agent in `src/investment_agent/data/` (fixed universe — **not** tied to macro theme tickers):

| Data | Source | Symbols |
|------|--------|---------|
| 20d / 60d returns, vs 52w high, vs SPY | **yfinance** | Sector ETFs (XLK, XLE, …), SPY |
| Forward / trailing P/E, P/B | **yfinance** `.info` | Same ETF universe (delayed) |

Optional Finnhub revision proxy applies only when extra tickers are added to the snapshot in future; the default pipeline passes an empty theme list (`[]`).

### Gemini free-tier quota (429)

A full run uses **~5 LLM requests** (macro, news, equity, quant, CIO).  
`gemini-2.5-flash-lite` free tier is often **~20 requests/day per project** — about **4 full runs per day**.

If you see `429 RESOURCE_EXHAUSTED` / daily quota:

1. Wait for quota reset (UTC) or use another API key / `LLM_PROVIDER=openai`
2. Sidebar: **Load last result** for `reports/latest.json`
3. Enable **Resume from checkpoint** — partial steps are saved under `reports/cache/` so a retry only calls agents that did not finish

| Variable | Default | Role |
|----------|---------|------|
| `RESUME_CHECKPOINT` | `1` | Save each agent output; resume on next run |
| `LLM_MAX_RETRIES_ON_429` | `2` | Short rate-limit retries (not daily cap) |

### LLM configuration

| Variable | Role |
|----------|------|
| `LLM_PROVIDER` | `gemini` or `openai` |
| `GEMINI_API_KEY` / `OPENAI_API_KEY` | API authentication |
| `GEMINI_MODEL` / `OPENAI_MODEL` | Model id (e.g. `gemini-2.5-flash-lite`) |
| `OPENAI_BASE_URL` | Optional; Gemini uses Google OpenAI-compatible endpoint by default |
| `MARKET_REGION` | Region hint in agent prompts (`global`, `US`, `China`, …) |

### Attribution

- **News-sourced** bullets use `key_drivers_sourced` / `risks_sourced` with `citation_ids` → `news_citations[]` (title, url, source).
- Plain `key_drivers` / `risks` without citations remain **model synthesis**.
- Equity structured metrics use **yfinance** (free, delayed); not Bloomberg/FactSet.
- Macro agent does **not** use FRED/Bloomberg APIs.
- Verify URLs and facts independently before trading.

## Future roadmap

Planned extensions (not implemented in the current PoC):

### Bloomberg as a news and market data backbone

- **News ingest:** Replace or augment TickerTick/Finnhub with **Bloomberg News** (e.g. `BN` feed or equivalent API) for licensed, timestamped headlines aligned with portfolio systems.
- **Cross-asset context:** Pull macro and security-level fields (rates, FX, indices, corporate actions) from Bloomberg where available, so Agent 1 (Macro) and Agent 4 (Quant) can ground narratives in the same data vendor as production research desks.
- **Requirements:** Firm Bloomberg entitlement, API credentials (e.g. B-PIPE / BQL / server API per deployment), compliance logging, and rate/cost controls in the orchestrator.

### Sell-side research agent (replacing or complementing News RAG)

- **Research Agent:** Add a dedicated **equity research report** agent that ingests authorized sell-side PDFs/HTML (broker, date, sector, rating, target price) via Bloomberg Document Search, internal research library, or approved file drop.
- **RAG:** Chunk reports by section (summary, thesis, risks, valuation); retrieval with embeddings + **citation to document id / page** (same pattern as today’s `citation_ids`, extended to `report_id` and page ranges).
- **Pipeline:** `Macro → Research (RAG) → Equity → Quant → CIO`, with Equity using structured yfinance/BBG fundamentals to **validate** stages against cited research—not duplicate broker numbers without a source.
- **Governance:** Entitlement checks per user/team, no storage of reports outside licensed systems, audit trail on retrieved chunks.

### Other enhancements (backlog)

- Vector RAG for news and research with offline evaluation (citation accuracy, faithfulness).
- Production deployment: API service, scheduled ingest, monitoring, model versioning.
- Optional retention of a **fast news** path (Bloomberg headlines) alongside a **deep research** path (sell-side reports) for a six-agent or dual-track workflow.

*Until Bloomberg and research feeds are connected, the repo uses free-tier news APIs, lexical RAG, and yfinance/Finnhub proxies as documented above.*

## Disclaimer

Output is for research only. Not investment advice.
