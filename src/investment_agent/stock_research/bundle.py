"""Fetch and slice single-ticker data before any stock-research LLM call."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from investment_agent.agents.markets.revisions import fetch_revision_metrics
from investment_agent.agents.markets.valuation import fetch_valuation_metrics
from investment_agent.config import Settings, env_int
from investment_agent.dates import analysis_date, format_date_iso
from investment_agent.stock_research.peers import peers_for


def context_max_chars(settings: Settings | None = None) -> int:
    groq = bool(settings and settings.is_groq)
    return env_int("STOCK_RESEARCH_CONTEXT_MAX_CHARS", 4_000 if groq else 12_000)


def news_max_headlines() -> int:
    return env_int("STOCK_RESEARCH_NEWS_HEADLINES", 12)


def _truncate(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 1)] + "…"


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
        if f != f:
            return None
        return f
    except (TypeError, ValueError):
        return None


def _fmt_num(value: Any) -> str:
    f = _safe_float(value)
    if f is None:
        return "n/a"
    if abs(f) >= 1e9:
        return f"{f / 1e9:.2f}B"
    if abs(f) >= 1e6:
        return f"{f / 1e6:.2f}M"
    if abs(f) >= 100:
        return f"{f:.1f}"
    return f"{f:.2f}"


def _fmt_pct(value: Any) -> str:
    f = _safe_float(value)
    if f is None:
        return "n/a"
    # treat ratios in 0–2 as fractions; larger as already percent
    if abs(f) <= 2.5:
        return f"{f * 100:.1f}%"
    return f"{f:.1f}%"


def _col_label(c: Any) -> str:
    s = str(c)
    return s[:10]


def _find_row(df: Any, row_names: list[str]) -> Any | None:
    if df is None:
        return None
    try:
        import pandas as pd

        if not isinstance(df, pd.DataFrame) or df.empty:
            return None
        for name in row_names:
            if name in df.index:
                return name
            matches = [i for i in df.index if str(i).lower() == name.lower()]
            if matches:
                return matches[0]
            matches = [i for i in df.index if name.lower() in str(i).lower()]
            if matches:
                return matches[0]
    except Exception:  # noqa: BLE001
        return None
    return None


def _df_key_rows(df: Any, row_names: list[str], max_cols: int = 4) -> list[str]:
    lines: list[str] = []
    if df is None:
        return lines
    try:
        import pandas as pd

        if not isinstance(df, pd.DataFrame) or df.empty:
            return lines
        cols = list(df.columns)[:max_cols]
        for want in row_names:
            name = _find_row(df, [want])
            if name is None:
                continue
            vals = [_fmt_num(df.loc[name, c]) for c in cols]
            col_labels = [_col_label(c) for c in cols]
            lines.append(
                f"{name}: " + " | ".join(f"{c}={v}" for c, v in zip(col_labels, vals))
            )
    except Exception:  # noqa: BLE001
        return lines
    return lines


def _yoy_lines(df: Any, row_names: list[str], max_cols: int = 8) -> list[str]:
    """YoY % for each column vs column 4 positions later (quarterly) when available."""
    lines: list[str] = []
    if df is None:
        return lines
    try:
        import pandas as pd

        if not isinstance(df, pd.DataFrame) or df.empty:
            return lines
        cols = list(df.columns)[:max_cols]
        for want in row_names:
            name = _find_row(df, [want])
            if name is None:
                continue
            parts: list[str] = []
            for i, c in enumerate(cols):
                cur = _safe_float(df.loc[name, c])
                # yfinance columns are newest-first; YoY ≈ index i+4
                base = None
                if i + 4 < len(list(df.columns)):
                    base = _safe_float(df.loc[name, list(df.columns)[i + 4]])
                if cur is None or base is None or base == 0:
                    parts.append(f"{_col_label(c)}=n/a")
                else:
                    parts.append(f"{_col_label(c)}={((cur / base) - 1.0) * 100:.1f}%")
            if parts:
                lines.append(f"{name} YoY: " + " | ".join(parts))
    except Exception:  # noqa: BLE001
        return lines
    return lines


def _percentile(series: list[float], value: float) -> float | None:
    clean = [x for x in series if x is not None and x == x]
    if not clean:
        return None
    below = sum(1 for x in clean if x <= value)
    return 100.0 * below / len(clean)


def _history_pe_ps_lines(
    price_hist: Any,
    quarterly_income: Any,
    *,
    shares: float | None,
    current_pe: float | None,
    current_ps: float | None,
) -> list[str]:
    """Build ~5y quarter-end PE/PS series from quarterly income + price history."""
    lines: list[str] = []
    if price_hist is None or quarterly_income is None:
        return ["Historical PE/PS: unavailable (missing price or quarterly income)"]
    try:
        import pandas as pd

        if not isinstance(price_hist, pd.DataFrame) or price_hist.empty:
            return ["Historical PE/PS: unavailable (empty price history)"]
        if not isinstance(quarterly_income, pd.DataFrame) or quarterly_income.empty:
            return ["Historical PE/PS: unavailable (empty quarterly income)"]

        rev_row = _find_row(quarterly_income, ["Total Revenue", "Operating Revenue"])
        eps_row = _find_row(
            quarterly_income,
            ["Diluted EPS", "Basic EPS", "Net Income Common Stockholders", "Net Income"],
        )
        if rev_row is None and eps_row is None:
            return ["Historical PE/PS: unavailable (no revenue/EPS rows)"]

        close = price_hist["Close"] if "Close" in price_hist.columns else price_hist.iloc[:, 0]
        cols = list(quarterly_income.columns)[:20]
        pe_series: list[float] = []
        ps_series: list[float] = []

        for i, c in enumerate(cols):
            # TTM = sum of this quarter + next 3 older columns (newer-first layout)
            window = cols[i : i + 4]
            if len(window) < 4:
                break
            ttm_rev = None
            ttm_eps = None
            if rev_row is not None:
                vals = [_safe_float(quarterly_income.loc[rev_row, w]) for w in window]
                if all(v is not None for v in vals):
                    ttm_rev = sum(vals)  # type: ignore[arg-type]
            if eps_row is not None:
                raw = str(eps_row).lower()
                vals = [_safe_float(quarterly_income.loc[eps_row, w]) for w in window]
                if all(v is not None for v in vals):
                    if "eps" in raw:
                        ttm_eps = sum(vals)  # type: ignore[arg-type]
                    elif shares and shares > 0:
                        ttm_eps = sum(vals) / shares  # type: ignore[operator]

            # price near quarter-end column date
            try:
                ts = pd.Timestamp(c)
                if close.index.tz is not None:
                    ts = ts.tz_localize(close.index.tz) if ts.tzinfo is None else ts
                # nearest prior close
                sub = close.loc[:ts] if len(close.loc[:ts]) else close
                px = _safe_float(sub.iloc[-1])
            except Exception:  # noqa: BLE001
                px = None

            if px is not None and ttm_eps is not None and ttm_eps > 0:
                pe_series.append(px / ttm_eps)
            if px is not None and ttm_rev is not None and ttm_rev > 0 and shares and shares > 0:
                ps_series.append((px * shares) / ttm_rev)

        lines.append(
            f"Historical PE points (quarter TTM, up to 5y): n={len(pe_series)} "
            f"min={_fmt_num(min(pe_series) if pe_series else None)} "
            f"median={_fmt_num(sorted(pe_series)[len(pe_series) // 2] if pe_series else None)} "
            f"max={_fmt_num(max(pe_series) if pe_series else None)}"
        )
        if current_pe is not None and pe_series:
            pct = _percentile(pe_series, current_pe)
            lines.append(f"Current trailing P/E {_fmt_num(current_pe)} percentile vs history: {_fmt_num(pct)}%")
        elif not pe_series:
            lines.append("Current PE percentile: n/a (insufficient history)")

        lines.append(
            f"Historical PS points (quarter TTM, up to 5y): n={len(ps_series)} "
            f"min={_fmt_num(min(ps_series) if ps_series else None)} "
            f"median={_fmt_num(sorted(ps_series)[len(ps_series) // 2] if ps_series else None)} "
            f"max={_fmt_num(max(ps_series) if ps_series else None)}"
        )
        if current_ps is not None and ps_series:
            pct = _percentile(ps_series, current_ps)
            lines.append(f"Current P/S {_fmt_num(current_ps)} percentile vs history: {_fmt_num(pct)}%")
        elif not ps_series:
            lines.append("Current PS percentile: n/a (insufficient history)")
    except Exception as exc:  # noqa: BLE001
        return [f"Historical PE/PS: failed ({type(exc).__name__})"]
    return lines


def _peer_multiple_lines(peers: list[str]) -> list[str]:
    if not peers:
        return ["Peers: none mapped for industry/sector"]
    lines = [f"Peer set: {', '.join(peers)}"]

    def _one(sym: str) -> str:
        vm = fetch_valuation_metrics(sym, label=sym)
        return (
            f"{sym}: PE(ttm)={_fmt_num(vm.trailing_pe)} PE(fwd)={_fmt_num(vm.forward_pe)} "
            f"PB={_fmt_num(vm.price_to_book)} mcap(B)={_fmt_num(vm.market_cap_b)}"
        )

    try:
        with ThreadPoolExecutor(max_workers=min(5, len(peers))) as pool:
            lines.extend(pool.map(_one, peers))
    except Exception:  # noqa: BLE001
        lines.extend(_one(p) for p in peers)
    return lines


def _frame_preview(df: Any, *, max_rows: int = 8, max_cols: int = 6, title: str = "") -> list[str]:
    lines: list[str] = []
    if title:
        lines.append(title)
    if df is None:
        lines.append("(unavailable)")
        return lines
    try:
        import pandas as pd

        if not isinstance(df, pd.DataFrame) or df.empty:
            lines.append("(empty)")
            return lines
        view = df.iloc[:max_rows, :max_cols]
        lines.append(view.to_string(max_cols=max_cols))
    except Exception:  # noqa: BLE001
        lines.append("(format failed)")
    return lines


def _fetch_ticker_news(ticker: str, limit: int) -> tuple[list[str], list[str]]:
    """TickerTick company query; title + short summary. Soft-fail."""
    notes: list[str] = []
    items: list[str] = []
    try:
        import httpx

        q = f"T:{ticker.upper()}"
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                "https://api.tickertick.com/feed",
                params={"q": q, "n": min(limit, 50)},
            )
            resp.raise_for_status()
            data = resp.json()
        stories = data if isinstance(data, list) else data.get("stories", data.get("news", []))
        if not isinstance(stories, list):
            notes.append("tickertick: unexpected payload")
            return items, notes
        for item in stories[:limit]:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            if not title:
                continue
            summary = (
                item.get("description") or item.get("summary") or item.get("snippet") or ""
            ).strip()
            summary = _truncate(summary, 180)
            if summary:
                items.append(f"{title} — {summary}")
            else:
                items.append(title)
        notes.append(f"tickertick:{len(items)} headlines (q={q})")
    except Exception as exc:  # noqa: BLE001
        notes.append(f"tickertick: failed ({type(exc).__name__})")
    return items, notes


@dataclass(frozen=True)
class StockBundle:
    ticker: str
    as_of: date
    company_name: str
    last_price: float | None
    business_block: str
    financial_block: str
    valuation_block: str
    expectation_block: str
    notes: list[str] = field(default_factory=list)


def fetch_stock_bundle(
    ticker: str,
    *,
    settings: Settings | None = None,
    as_of: date | None = None,
) -> StockBundle:
    """Single yfinance-centered fetch; slice into prompt blocks for domain agents."""
    settings = settings or Settings.from_env()
    as_of = as_of or analysis_date()
    sym = ticker.strip().upper()
    max_chars = context_max_chars(settings)
    notes: list[str] = []

    info: dict[str, Any] = {}
    income = cashflow = balance = None
    q_income = q_cashflow = q_balance = None
    price_hist = None
    earnings_history = earnings_dates = earnings_estimate = revenue_estimate = None
    last_price: float | None = None
    t_obj = None

    try:
        import yfinance as yf

        t_obj = yf.Ticker(sym)
        try:
            info = t_obj.info or {}
        except Exception:  # noqa: BLE001
            info = {}
            notes.append("yfinance.info: failed")
        for attr, dest_name in (
            ("income_stmt", "income"),
            ("cashflow", "cashflow"),
            ("balance_sheet", "balance"),
            ("quarterly_income_stmt", "q_income"),
            ("quarterly_cashflow", "q_cashflow"),
            ("quarterly_balance_sheet", "q_balance"),
        ):
            try:
                val = getattr(t_obj, attr)
                if dest_name == "income":
                    income = val
                elif dest_name == "cashflow":
                    cashflow = val
                elif dest_name == "balance":
                    balance = val
                elif dest_name == "q_income":
                    q_income = val
                elif dest_name == "q_cashflow":
                    q_cashflow = val
                else:
                    q_balance = val
            except Exception:  # noqa: BLE001
                notes.append(f"yfinance.{attr}: failed")

        try:
            price_hist = t_obj.history(period="5y", auto_adjust=True)
        except Exception:  # noqa: BLE001
            notes.append("yfinance.history(5y): failed")

        for attr in ("earnings_history", "earnings_dates", "earnings_estimate", "revenue_estimate"):
            try:
                val = getattr(t_obj, attr, None)
                if callable(val):
                    val = val()
                if attr == "earnings_history":
                    earnings_history = val
                elif attr == "earnings_dates":
                    earnings_dates = val
                elif attr == "earnings_estimate":
                    earnings_estimate = val
                else:
                    revenue_estimate = val
            except Exception:  # noqa: BLE001
                notes.append(f"yfinance.{attr}: failed")

        last_price = _safe_float(info.get("currentPrice") or info.get("regularMarketPrice"))
        if last_price is None:
            try:
                hist = t_obj.history(period="5d")
                if hist is not None and not hist.empty:
                    last_price = _safe_float(hist["Close"].iloc[-1])
            except Exception:  # noqa: BLE001
                pass
    except ImportError:
        notes.append("yfinance: not installed")

    company_name = str(info.get("longName") or info.get("shortName") or sym)
    long_biz = str(info.get("longBusinessSummary") or "").strip()
    headlines, news_notes = _fetch_ticker_news(sym, news_max_headlines())
    notes.extend(news_notes)

    biz_lines = [
        f"Ticker: {sym}",
        f"Company: {company_name}",
        f"As of: {format_date_iso(as_of)}",
        f"Sector: {info.get('sector') or 'n/a'}",
        f"Industry: {info.get('industry') or 'n/a'}",
        f"Country: {info.get('country') or 'n/a'}",
        f"Employees: {info.get('fullTimeEmployees') or 'n/a'}",
        f"Website: {info.get('website') or 'n/a'}",
        "",
        "Business summary:",
        long_biz or "(no longBusinessSummary)",
    ]
    if headlines:
        biz_lines.append("")
        biz_lines.append("Recent headlines (title — summary):")
        biz_lines.extend(f"- {h}" for h in headlines)
    business_block = _truncate("\n".join(biz_lines), max_chars)

    fin_lines = [
        f"Ticker: {sym} | As of: {format_date_iso(as_of)}",
        f"Revenue growth: {_fmt_pct(info.get('revenueGrowth'))}",
        f"Earnings growth: {_fmt_pct(info.get('earningsGrowth'))}",
        f"Gross margins: {_fmt_pct(info.get('grossMargins'))}",
        f"Operating margins: {_fmt_pct(info.get('operatingMargins'))}",
        f"Profit margins: {_fmt_pct(info.get('profitMargins'))}",
        f"Return on equity: {_fmt_pct(info.get('returnOnEquity'))}",
        f"Return on assets: {_fmt_pct(info.get('returnOnAssets'))}",
        f"Debt to equity: {_fmt_num(info.get('debtToEquity'))}",
        f"Current ratio: {_fmt_num(info.get('currentRatio'))}",
        f"Free cash flow: {_fmt_num(info.get('freeCashflow'))}",
        f"Operating cash flow: {_fmt_num(info.get('operatingCashflow'))}",
        "",
        "Annual income statement (key rows):",
    ]
    fin_lines.extend(
        _df_key_rows(
            income,
            ["Total Revenue", "Operating Income", "Net Income", "EBITDA", "Diluted EPS"],
            max_cols=4,
        )
        or ["(unavailable)"]
    )
    fin_lines.append("")
    fin_lines.append("Annual cash flow (key rows):")
    fin_lines.extend(
        _df_key_rows(
            cashflow,
            ["Operating Cash Flow", "Free Cash Flow", "Capital Expenditure"],
            max_cols=4,
        )
        or ["(unavailable)"]
    )
    fin_lines.append("")
    fin_lines.append("Annual balance sheet (key rows):")
    fin_lines.extend(
        _df_key_rows(
            balance,
            ["Total Assets", "Total Debt", "Cash And Cash Equivalents", "Stockholders Equity"],
            max_cols=4,
        )
        or ["(unavailable)"]
    )
    fin_lines.append("")
    fin_lines.append("Quarterly income (up to 8 quarters):")
    fin_lines.extend(
        _df_key_rows(
            q_income,
            ["Total Revenue", "Operating Income", "Net Income", "Diluted EPS"],
            max_cols=8,
        )
        or ["(unavailable)"]
    )
    fin_lines.append("Quarterly income YoY:")
    fin_lines.extend(
        _yoy_lines(q_income, ["Total Revenue", "Operating Income", "Net Income", "Diluted EPS"])
        or ["(unavailable)"]
    )
    fin_lines.append("")
    fin_lines.append("Quarterly cash flow (up to 8 quarters):")
    fin_lines.extend(
        _df_key_rows(
            q_cashflow,
            ["Operating Cash Flow", "Free Cash Flow", "Capital Expenditure"],
            max_cols=8,
        )
        or ["(unavailable)"]
    )
    fin_lines.append("Quarterly cash flow YoY:")
    fin_lines.extend(
        _yoy_lines(q_cashflow, ["Operating Cash Flow", "Free Cash Flow"])
        or ["(unavailable)"]
    )
    fin_lines.append("")
    fin_lines.append("Quarterly balance sheet (up to 8 quarters):")
    fin_lines.extend(
        _df_key_rows(
            q_balance,
            ["Total Assets", "Total Debt", "Cash And Cash Equivalents", "Stockholders Equity"],
            max_cols=8,
        )
        or ["(unavailable)"]
    )
    financial_block = _truncate("\n".join(fin_lines), max_chars)

    vm = fetch_valuation_metrics(sym, label=company_name)
    current_ps = _safe_float(info.get("priceToSalesTrailing12Months"))
    shares = _safe_float(info.get("sharesOutstanding"))
    peers = peers_for(
        industry=str(info.get("industry") or ""),
        sector=str(info.get("sector") or ""),
        ticker=sym,
    )
    val_lines = [
        f"Ticker: {sym} | As of: {format_date_iso(as_of)}",
        f"Last price: {_fmt_num(last_price)}",
        f"Market cap (B): {_fmt_num(vm.market_cap_b)}",
        f"Trailing P/E: {_fmt_num(vm.trailing_pe)}",
        f"Forward P/E: {_fmt_num(vm.forward_pe)}",
        f"Price to book: {_fmt_num(vm.price_to_book)}",
        f"PEG ratio: {_fmt_num(info.get('pegRatio'))}",
        f"EV/EBITDA: {_fmt_num(info.get('enterpriseToEbitda'))}",
        f"Price to sales: {_fmt_num(current_ps)}",
        f"52-week high: {_fmt_num(info.get('fiftyTwoWeekHigh'))}",
        f"52-week low: {_fmt_num(info.get('fiftyTwoWeekLow'))}",
        f"50-day average: {_fmt_num(info.get('fiftyDayAverage'))}",
        f"200-day average: {_fmt_num(info.get('twoHundredDayAverage'))}",
        f"Beta: {_fmt_num(info.get('beta'))}",
        f"Shares outstanding: {_fmt_num(shares)}",
        "",
        "Historical valuation percentiles (from quarterly TTM + 5y prices):",
    ]
    val_lines.extend(
        _history_pe_ps_lines(
            price_hist,
            q_income,
            shares=shares,
            current_pe=vm.trailing_pe,
            current_ps=current_ps,
        )
    )
    val_lines.append("")
    val_lines.append("Peer multiples:")
    val_lines.extend(_peer_multiple_lines(peers))
    val_lines.append("")
    val_lines.append("Use ONLY these figures for valuation claims.")
    valuation_block = _truncate("\n".join(val_lines), max_chars)

    rev = fetch_revision_metrics(
        sym,
        label=company_name,
        finnhub_key=settings.finnhub_api_key,
    )
    if settings.finnhub_api_key:
        notes.append(
            f"finnhub recommendation: proxy={rev.revision_proxy} trend={rev.trend_label or 'n/a'}"
        )
    else:
        notes.append("finnhub recommendation: skipped (no key)")

    target_mean = _safe_float(info.get("targetMeanPrice"))
    upside = None
    if target_mean is not None and last_price and last_price > 0:
        upside = (target_mean / last_price - 1.0) * 100.0

    exp_lines = [
        f"Ticker: {sym} | As of: {format_date_iso(as_of)}",
        f"Last price: {_fmt_num(last_price)}",
        f"Target mean: {_fmt_num(target_mean)}",
        f"Target high: {_fmt_num(info.get('targetHighPrice'))}",
        f"Target low: {_fmt_num(info.get('targetLowPrice'))}",
        f"Target median: {_fmt_num(info.get('targetMedianPrice'))}",
        f"Number of analyst opinions: {info.get('numberOfAnalystOpinions') or 'n/a'}",
        f"Upside to mean target %: {_fmt_num(upside)}",
        f"Recommendation key: {info.get('recommendationKey') or 'n/a'}",
        f"Recommendation mean: {_fmt_num(info.get('recommendationMean'))}",
        f"Forward EPS: {_fmt_num(info.get('forwardEps'))}",
        f"Trailing EPS: {_fmt_num(info.get('trailingEps'))}",
        "",
        "Finnhub recommendation trend proxy:",
        f"  revision_proxy: {_fmt_num(rev.revision_proxy)}",
        f"  trend_label: {rev.trend_label or 'n/a'}",
        f"  strongBuy/buy/hold/sell/strongSell: "
        f"{rev.strong_buy}/{rev.buy}/{rev.hold}/{rev.sell}/{rev.strong_sell}",
        "",
    ]
    exp_lines.extend(_frame_preview(earnings_estimate, title="Earnings estimate:", max_rows=10))
    exp_lines.append("")
    exp_lines.extend(_frame_preview(revenue_estimate, title="Revenue estimate:", max_rows=10))
    exp_lines.append("")
    exp_lines.extend(_frame_preview(earnings_history, title="Earnings history / surprises:", max_rows=8))
    exp_lines.append("")
    exp_lines.extend(_frame_preview(earnings_dates, title="Upcoming / recent earnings dates:", max_rows=8))
    exp_lines.append("")
    exp_lines.append("Ground expectation claims in these figures only.")
    expectation_block = _truncate("\n".join(exp_lines), max_chars)

    return StockBundle(
        ticker=sym,
        as_of=as_of,
        company_name=company_name,
        last_price=last_price,
        business_block=business_block,
        financial_block=financial_block,
        valuation_block=valuation_block,
        expectation_block=expectation_block,
        notes=notes,
    )
