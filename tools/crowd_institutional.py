"""Layer 2 — Institutional Positioning Signals.

Sources:
  - Sector ETF AUM flows (yfinance): proxy for ICI fund flows
  - CFTC COT Report (free FTP CSV): commercial vs non-commercial futures positioning
  - FINRA ATS volume (free): market-level institutional participation (NOT per-stock)
  - SEC EDGAR 13F + FMP API: quarterly hedge fund holdings changes (60-day half-life)
  - FINRA short interest: days-to-cover per ticker (via yfinance info)
  - FRED margin debt (BOGZ1FL663067003Q): market leverage signal

NOTE: FINRA ATS data is venue-aggregate for listed equities, NOT per-security.
Used as a market-level institutional activity signal only.
"""
import sys, io, csv, json, logging, time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import requests
import pandas as pd

from tools.crowd_types import Signal

logger = logging.getLogger(__name__)

SECTOR_ETFS = {
    "XLK": "technology",   "XLF": "financials",     "XLE": "energy",
    "XLV": "healthcare",   "XLI": "industrials",    "XLY": "consumer_discretionary",
    "XLP": "consumer_staples", "XLU": "utilities",  "XLB": "materials",
    "XLRE": "real_estate", "XLC": "communication",
}


def fetch_etf_sector_flows() -> list[Signal]:
    """Compute sector ETF price-based flow proxy via yfinance.

    AUM proxy: recent 5-day avg price change vs prior 15-day avg.
    Standard free substitute for ICI.org (no programmatic API).
    """
    try:
        import yfinance as yf
        signals = []
        for etf, sector in SECTOR_ETFS.items():
            try:
                hist = yf.Ticker(etf).history(period="2mo")
                if hist.empty or len(hist) < 20:
                    continue
                price_now  = float(hist["Close"].iloc[-1])
                price_prev = float(hist["Close"].iloc[-6])
                if price_prev < 0.01:
                    continue
                flow_proxy = (price_now - price_prev) / price_prev
                # Normalize: -5% to +5% weekly move → [0, 1]
                norm = float(min(1.0, max(0.0, (flow_proxy + 0.05) / 0.10)))
                signals.append(Signal(
                    name=f"etf_flow_{sector}",
                    value=flow_proxy * 100,
                    normalized=norm,
                    ic=0.07,
                    half_life=7,
                    age_days=0,
                    layer="institutional",
                    source="etf_flows",
                ))
            except Exception as e:
                logger.debug(f"ETF flow {etf} failed: {e}")
        return signals
    except Exception as e:
        logger.warning(f"fetch_etf_sector_flows failed: {e}")
        return []


def fetch_cot_report() -> list[Signal]:
    """Fetch CFTC Commitments of Traders report (free weekly CSV).

    Speculator net position (non-commercials) as crowding gauge.
    High speculator net long = elevated risk (contrarian at extremes).
    """
    try:
        import zipfile
        year = date.today().year
        for try_year in [year, year - 1]:
            url = f"https://www.cftc.gov/files/dea/history/fut_fin_txt_{try_year}.zip"
            try:
                resp = requests.get(url, timeout=30, headers={"User-Agent": "DruckenmillerAlpha/1.0"})
                if resp.status_code == 200:
                    break
            except Exception:
                continue
        else:
            return []

        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            fname = [f for f in z.namelist() if f.endswith(".txt")][0]
            with z.open(fname) as f:
                df = pd.read_csv(f, encoding="latin1", low_memory=False)

        sp500 = df[df["Market_and_Exchange_Names"].str.contains("S&P 500", na=False, case=False)]
        if sp500.empty:
            return []

        latest = sp500.sort_values("As_of_Date_In_Form_YYMMDD", ascending=False).iloc[0]
        spec_long  = float(latest.get("NonComm_Positions_Long_All", 0) or 0)
        spec_short = float(latest.get("NonComm_Positions_Short_All", 0) or 0)
        comm_long  = float(latest.get("Comm_Positions_Long_All", 0) or 0)
        comm_short = float(latest.get("Comm_Positions_Short_All", 0) or 0)

        spec_net = spec_long - spec_short
        total_oi = spec_long + spec_short + comm_long + comm_short
        spec_pct = (spec_net / total_oi * 100) if total_oi > 0 else 0
        # spec_pct typically -30 to +30; normalize to [0,1]
        spec_norm = float(min(1.0, max(0.0, (spec_pct + 30) / 60)))

        date_str = str(latest.get("As_of_Date_In_Form_YYMMDD", ""))
        age_days = 7
        try:
            cot_date = datetime.strptime(date_str, "%y%m%d")
            age_days = max(0, (datetime.now() - cot_date).days)
        except Exception:
            pass

        return [Signal(
            name="cot_sp500_speculator_net",
            value=spec_pct,
            normalized=spec_norm,
            ic=0.07,
            half_life=14,
            age_days=age_days,
            layer="institutional",
            source="cftc_cot",
        )]
    except Exception as e:
        logger.warning(f"fetch_cot_report failed: {e}")
        return []


def fetch_finra_ats_activity() -> list[Signal]:
    """Fetch FINRA ATS weekly volume as market-level institutional activity proxy.

    IMPORTANT: This is venue-aggregate data, NOT per-security for listed equities.
    Used as a market-level signal only. Falls back to neutral estimate if API unavailable.
    """
    try:
        url = "https://api.finra.org/data/group/otcmarket/name/weeklySummary"
        resp = requests.get(
            url, timeout=15,
            headers={"Accept": "application/json", "User-Agent": "DruckenmillerAlpha/1.0"},
        )
        if resp.status_code == 200:
            data = resp.json()
            if data and isinstance(data, list):
                latest = data[0]
                ats_vol   = float(latest.get("totalWeeklyShareQuantity", 0) or 0)
                total_vol = float(latest.get("totalWeeklyTradeCount", 1) or 1)
                ats_frac  = min(1.0, ats_vol / max(total_vol * 1000, 1))
                return [Signal(
                    name="finra_ats_activity",
                    value=ats_frac * 100,
                    normalized=ats_frac,
                    ic=0.05,
                    half_life=5,
                    age_days=0,
                    layer="institutional",
                    source="finra_ats",
                )]
    except Exception as e:
        logger.debug(f"FINRA ATS API failed (expected): {e}")

    # Fallback: neutral estimate
    return [Signal(
        name="finra_ats_activity",
        value=50.0,
        normalized=0.5,
        ic=0.05,
        half_life=5,
        age_days=7,
        layer="institutional",
        source="finra_ats_estimate",
        low_history=True,
    )]


def fetch_13f_flows(tickers: list[str]) -> list[Signal]:
    """Fetch 13F institutional flow direction from existing filings_13f DB table.

    13F half-life is 60 days (NOT 180). Academic consensus: signal degrades sharply
    after 60 days (Grinblatt & Titman 1993, Wermers 1999). Filings are 45 days
    stale at publication.
    """
    try:
        from tools.db import query
        signals = []
        cutoff = (date.today() - timedelta(days=180)).isoformat()

        for ticker in tickers[:200]:
            try:
                rows = query(
                    "SELECT change_pct, date FROM filings_13f WHERE symbol=? AND date>=? ORDER BY date DESC LIMIT 1",
                    [ticker, cutoff]
                )
                if rows and rows[0].get("change_pct") is not None:
                    change = float(rows[0]["change_pct"])
                    norm = float(min(1.0, max(0.0, (change + 50) / 100)))
                    age_days = (date.today() - date.fromisoformat(rows[0]["date"])).days
                    signals.append(Signal(
                        name=f"13f_flow_{ticker}",
                        value=change,
                        normalized=norm,
                        ic=0.06,
                        half_life=60,
                        age_days=age_days,
                        layer="institutional",
                        source="sec_13f",
                    ))
            except Exception:
                continue
        return signals
    except Exception as e:
        logger.warning(f"fetch_13f_flows failed: {e}")
        return []


def fetch_short_interest(tickers: list[str]) -> list[Signal]:
    """Fetch short interest days-to-cover per ticker via yfinance.

    High DTC = potential squeeze pressure = institutional conviction signal.
    Only returns signals where DTC > 1 (non-trivial short interest).
    """
    try:
        import yfinance as yf
        signals = []
        for ticker in tickers[:300]:
            try:
                info = yf.Ticker(ticker).info or {}
                short_ratio = float(info.get("shortRatio", 0) or 0)
                if short_ratio < 1:
                    continue
                norm = min(1.0, short_ratio / 30.0)
                signals.append(Signal(
                    name=f"short_dtc_{ticker}",
                    value=short_ratio,
                    normalized=norm,
                    ic=0.05,
                    half_life=14,
                    age_days=0,
                    layer="institutional",
                    source="finra_short",
                ))
            except Exception:
                continue
        return signals
    except Exception as e:
        logger.warning(f"fetch_short_interest failed: {e}")
        return []


def fetch_margin_debt() -> list[Signal]:
    """Fetch FINRA margin debt via FRED series BOGZ1FL663067003Q.

    YoY growth > 0 = leverage expanding = mild crowding signal.
    """
    try:
        from tools.config import FRED_API_KEY
        if not FRED_API_KEY:
            return []
        import fredapi
        fred = fredapi.Fred(api_key=FRED_API_KEY)
        series = fred.get_series("BOGZ1FL663067003Q", observation_start="2020-01-01")
        if series is None or len(series) < 4:
            return []
        current  = float(series.iloc[-1])
        year_ago = float(series.iloc[-5]) if len(series) >= 5 else float(series.iloc[0])
        yoy_growth = (current - year_ago) / max(abs(year_ago), 1)
        norm = float(min(1.0, max(0.0, (yoy_growth + 0.20) / 0.40)))
        return [Signal(
            name="margin_debt_yoy",
            value=yoy_growth * 100,
            normalized=norm,
            ic=0.04,
            half_life=90,
            age_days=0,
            layer="institutional",
            source="fred_margin_debt",
        )]
    except Exception as e:
        logger.warning(f"fetch_margin_debt failed: {e}")
        return []


def fetch_all_institutional(tickers: list[str]) -> list[Signal]:
    """Fetch all Layer 2 institutional signals. Gracefully handles source failures."""
    signals: list[Signal] = []
    signals.extend(fetch_etf_sector_flows())
    signals.extend(fetch_cot_report())
    signals.extend(fetch_finra_ats_activity())
    signals.extend(fetch_13f_flows(tickers))
    signals.extend(fetch_short_interest(tickers))
    signals.extend(fetch_margin_debt())
    logger.info(f"Institutional layer: {len(signals)} signals collected")
    return signals
