# Investment Agent — Multi-Agent Theme Analysis

Four specialist agents plus a CIO layer output **investable themes** with lifecycle stage: **Early / Early-Mid / Mid / Mid-Late / Late**.

| Agent | Role | Focus |
|-------|------|--------|
| **Agent 1** | Macro Economist | Rates, inflation, policy, geopolitics, cross-asset signals |
| **Agent 2** | News / RAG Analyst | Retrieved headlines (Finnhub + TickerTick), cited drivers/risks |
| **Agent 3** | Equity Research Analyst | Valuations, earnings revisions; reads macro + news |
| **Agent 4** | Quant Analyst | Volatility, VIX, sector realized vol, risk timing |

A CIO synthesis layer merges views into final stage, consensus, and investability scores. **All prompts and outputs are in English.**

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

## Workflow

The analysis pipeline is defined in code (not a separate workflow engine). Entry points call `ThemeOrchestrator.run()` in `src/investment_agent/orchestrator.py`:

```
MacroEconomist.analyze()
  → fetch_news_articles() + lexical RAG retrieve
    → NewsAnalyst.analyze(macro)  → NewsReport with citations
      → EquityResearchAnalyst.analyze(macro, news)
        → QuantAnalyst.analyze(macro, equity, vol_snapshot)
          → CIO synthesis (LLM) → InvestmentBrief
            → _enrich_brief() (date, data_sources, news_citations)
```

- **CLI:** `main.py` → `investment_agent/cli.py`
- **Dashboard:** `streamlit_app.py`
- **News RAG:** `src/investment_agent/news/ingest.py`, `news/rag.py`

## Architecture

```
CLI / Streamlit
    └── ThemeOrchestrator
            ├── Agent 1: MacroEconomist
            ├── Agent 2: NewsAnalyst (Finnhub + TickerTick → RAG → LLM)
            ├── Agent 3: EquityResearchAnalyst (reads macro + news)
            ├── Agent 4: QuantAnalyst (reads macro+equity + yfinance vol)
            └── CIO synthesis → InvestmentBrief
```

## Data sources

What each part of the report is based on.

| Output field | Primary source | Notes |
|--------------|----------------|-------|
| `report_date`, `as_of_context` (date prefix) | Local system clock | Set in `dates.py` / `_enrich_brief()` |
| Macro themes, `macro_backdrop`, `dominant_regime` | **LLM** (Agent 1) | No live macro API |
| `news_view`, `news_citations`, `key_drivers_sourced`, `risks_sourced` | **News RAG + LLM** (Agent 2) | Headlines from ingest; claims should cite `citation_ids` |
| Headlines ingested | **Finnhub** (if `FINNHUB_API_KEY`) + **TickerTick** (free) | See `news/ingest.py` |
| RAG retrieval | **Lexical match** (no embedding API) | `news/rag.py` — query from macro themes + region |
| Equity themes, `market_style`, `valuation_notes` | **LLM** (Agent 3) | Reads macro + news JSON; no live quotes API |
| Quant themes, `vol_regime`, `vol_signals` | **LLM** (Agent 4) + **yfinance** | Live vol block in quant prompt |
| VIX level, sector 20d ann. vol | **yfinance** | `market_data.py` |
| `executive_summary`, theme `thesis`, `synthesis` | **LLM** (CIO) | Merges four agent reports |
| `key_drivers` / `risks` (plain strings) | **LLM** (CIO) | Model synthesis |
| `key_drivers_sourced` / `risks_sourced` on themes | **LLM** (CIO) | Should reference news `citation_ids` when supported |
| `agent_stages` | **LLM** (CIO) | `macro`, `news`, `equity`, `quant` |
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
- Macro and equity views do **not** use FRED/Bloomberg-style fundamentals APIs.
- Verify URLs and facts independently before trading.

## Disclaimer

Output is for research only. Not investment advice.
