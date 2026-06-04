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

## Architecture

```
CLI / Streamlit
    └── ThemeOrchestrator
            ├── Agent 1: MacroEconomist
            ├── Agent 2: EquityResearchAnalyst (reads macro)
            ├── Agent 3: QuantAnalyst (reads macro+equity + yfinance vol)
            └── CIO synthesis → InvestmentBrief
```

## Disclaimer

Output is for research only. Not investment advice.
