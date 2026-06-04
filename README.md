# Investment Agent — Multi-Agent Theme Analysis

Three specialist agents collaborate to output **investable themes** with lifecycle stage: **Early / Early-Mid / Mid / Mid-Late / Late**.

| Agent | Role | Focus |
|-------|------|--------|
| **Agent 1** | Macro Economist | Rates, inflation, policy, geopolitics, cross-asset signals |
| **Agent 2** | Equity Research Analyst | Valuations, earnings revisions, style and sector |
| **Agent 3** | Quant Analyst | Volatility, VIX, sector realized vol, risk timing |

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

## Workflow

The analysis pipeline is defined in code (not a separate workflow engine). Entry points call `ThemeOrchestrator.run()` in `src/investment_agent/orchestrator.py`:

```
MacroEconomist.analyze()
  → EquityResearchAnalyst.analyze(macro_report)
    → QuantAnalyst.analyze(macro, equity, vol_snapshot)
      → CIO synthesis (LLM) → InvestmentBrief
        → _enrich_brief() (date prefix, stage labels)
```

- **CLI:** `main.py` → `investment_agent/cli.py`
- **Dashboard:** `streamlit_app.py`

## Architecture

```
CLI / Streamlit
    └── ThemeOrchestrator
            ├── Agent 1: MacroEconomist
            ├── Agent 2: EquityResearchAnalyst (reads macro)
            ├── Agent 3: QuantAnalyst (reads macro+equity + yfinance vol)
            └── CIO synthesis → InvestmentBrief
```

## Data sources

What each part of the report is based on. **Drivers, risks, thesis, and tickers are model-generated** unless noted below—they are not pulled from a live news or fundamentals API.

| Output field | Primary source | Notes |
|--------------|----------------|-------|
| `report_date`, `as_of_context` (date prefix) | Local system clock | Set in `dates.py` / `_enrich_brief()` |
| Macro themes, `macro_backdrop`, `dominant_regime` | **LLM** (Agent 1) | Provider from `.env`: `gemini` (Google AI) or `openai` |
| Equity themes, `market_style`, `valuation_notes` | **LLM** (Agent 2) | Uses Agent 1 JSON as context; no live quotes/estimates API |
| Quant themes, `vol_regime`, `vol_signals` | **LLM** (Agent 3) + optional **yfinance** | Live vol block injected into the quant prompt |
| VIX level, sector 20d ann. vol | **yfinance** | See symbols below; 1-month history, computed in `market_data.py` |
| `executive_summary`, `macro_view`, `equity_view`, `quant_view` | **LLM** (CIO synthesis) | Merges three agent reports |
| Final `themes[]`: `thesis`, `synthesis`, `key_drivers`, `risks` | **LLM** (CIO synthesis) | Drivers/risks are synthesized narratives, not cited filings |
| Final `themes[]`: `agent_stages` | **LLM** (CIO) | Per-agent stage labels: `macro`, `equity`, `quant` |
| `tickers_or_sectors` | **LLM** (agents + CIO) | Illustrative examples only; not screened or validated |
| `investability_score`, `consensus_score` | **LLM** (CIO) | Subjective scores from prompt rules |

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

### Attribution limitations

- There is **no** source tag per driver or risk line in the JSON today; treat them as **model inference** from the multi-agent pipeline.
- Macro and equity views do **not** use real-time economic data APIs (FRED, Bloomberg, etc.).
- For compliance, use the report `disclaimer`; verify tickers and facts independently before trading.

## Disclaimer

Output is for research only. Not investment advice.
