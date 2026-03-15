"""Central configuration for the Druckenmiller Alpha System.

All API keys loaded from .env via python-dotenv.
"""

import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------
FRED_API_KEY = os.getenv("FRED_API_KEY", "")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
FMP_API_KEY = os.getenv("FMP_API_KEY", "")
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")
EIA_API_KEY = os.getenv("EIA_API_KEY", "")
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_MODEL = "gemini-2.5-flash"
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY", "")
NASA_FIRMS_API_KEY = os.getenv("NASA_FIRMS_API_KEY", "")
USDA_API_KEY = os.getenv("USDA_API_KEY", "")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")

# Email
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
EMAIL_TO = os.getenv("EMAIL_TO", "")

# Portfolio
PORTFOLIO_VALUE = float(os.getenv("PORTFOLIO_VALUE", "100000"))

# ---------------------------------------------------------------------------
# Price Fetching
# ---------------------------------------------------------------------------
CRYPTO_TICKERS = {
    "BTC-USD": "Bitcoin", "ETH-USD": "Ethereum", "SOL-USD": "Solana",
    "ADA-USD": "Cardano", "AVAX-USD": "Avalanche", "DOT-USD": "Polkadot",
}
COMMODITIES = {
    "CL=F": "Crude Oil",
    "GC=F": "Gold",
    "SI=F": "Silver",
    "NG=F": "Natural Gas",
    "HG=F": "Copper",
    "ZW=F": "Wheat",
    "ZC=F": "Corn",
}
VIX_TICKER = "^VIX"
VIX3M_TICKER = "^VIX3M"
PRICE_HISTORY_DAYS = 365

# Reddit
REDDIT_USER_AGENT = "DruckenmillerAlpha/1.0"

# ---------------------------------------------------------------------------
# Technical Analysis Parameters
# ---------------------------------------------------------------------------
BENCHMARK_STOCK = "SPY"
BENCHMARK_CRYPTO = "BTC-USD"
BENCHMARK_DOLLAR = "DX-Y.NYB"
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_PERIOD = 20
BB_STD = 2
ADX_PERIOD = 14

# ---------------------------------------------------------------------------
# FRED Series IDs & Macro Regime Classification
# ---------------------------------------------------------------------------
FRED_SERIES = {
    "federal_funds": "FEDFUNDS",
    "m2":            "M2SL",
    "cpi":           "CPIAUCSL",
    "treasury_2y":   "DGS2",
    "treasury_10y":  "DGS10",
    "hy_oas":        "BAMLH0A0HYM2",
}

MACRO_REGIME = {
    "strong_risk_on":  60,   # total >= 60
    "risk_on":         30,   # total >= 30
    "neutral":        -20,   # total >= -20
    "risk_off":       -60,   # total >= -60
    # Below -60 = strong_risk_off
}

# ---------------------------------------------------------------------------
# Economic Indicators (expanded FRED series for macro dashboard)
# ---------------------------------------------------------------------------
ECONOMIC_INDICATORS = {
    # ── Leading (12) ──
    "initial_claims":       "ICSA",
    "continued_claims":     "CCSA",
    "building_permits":     "PERMIT",
    "umich_sentiment":      "UMCSENT",
    "mfg_weekly_hours":     "AWHMAN",
    "core_capex_orders":    "ACOGNO",
    "fed_balance_sheet":    "WALCL",
    "nfci":                 "NFCI",
    "breakeven_10y":        "T10YIE",
    "forward_inflation_5y": "T5YIFR",
    "sahm_rule":            "SAHMREALTIME",
    "yield_curve_10y3m":    "T10Y3M",
    # ── Coincident (4) ──
    "nonfarm_payrolls":        "PAYEMS",
    "industrial_production":   "INDPRO",
    "retail_sales":            "RSAFS",
    "real_income_ex_transfers": "W875RX1",
    # ── Lagging (5) ──
    "unemployment_rate":    "UNRATE",
    "core_cpi":             "CPILFESL",
    "core_pce":             "PCEPILFE",
    "avg_unemployment_dur": "UEMPMEAN",
    "ci_loans":             "BUSLOANS",
    # ── Liquidity & Stress (2) ──
    "reverse_repo":         "RRPONTSYD",
    "stl_fin_stress":       "STLFSI4",
}

INDICATOR_METADATA = {
    "ICSA":          {"name": "Initial Jobless Claims",              "category": "leading",    "unit": "thousands",  "frequency": "weekly",  "bullish_direction": "down"},
    "CCSA":          {"name": "Continued Claims",                    "category": "leading",    "unit": "thousands",  "frequency": "weekly",  "bullish_direction": "down"},
    "PERMIT":        {"name": "Building Permits",                    "category": "leading",    "unit": "thousands",  "frequency": "monthly", "bullish_direction": "up"},
    "UMCSENT":       {"name": "UMich Consumer Sentiment",            "category": "leading",    "unit": "index",      "frequency": "monthly", "bullish_direction": "up"},
    "AWHMAN":        {"name": "Avg Weekly Hours (Manufacturing)",    "category": "leading",    "unit": "hours",      "frequency": "monthly", "bullish_direction": "up"},
    "ACOGNO":        {"name": "Core Capital Goods Orders",           "category": "leading",    "unit": "millions",   "frequency": "monthly", "bullish_direction": "up"},
    "WALCL":         {"name": "Fed Balance Sheet",                   "category": "leading",    "unit": "millions",   "frequency": "weekly",  "bullish_direction": "up"},
    "NFCI":          {"name": "Chicago Fed Financial Conditions",    "category": "leading",    "unit": "index",      "frequency": "weekly",  "bullish_direction": "down"},
    "T10YIE":        {"name": "10Y Breakeven Inflation",             "category": "leading",    "unit": "percent",    "frequency": "daily",   "bullish_direction": "stable"},
    "T5YIFR":        {"name": "5Y Forward Inflation Expectation",    "category": "leading",    "unit": "percent",    "frequency": "daily",   "bullish_direction": "stable"},
    "SAHMREALTIME":  {"name": "Sahm Rule Recession Indicator",       "category": "leading",    "unit": "percent",    "frequency": "monthly", "bullish_direction": "down"},
    "T10Y3M":        {"name": "10Y-3M Yield Curve",                  "category": "leading",    "unit": "percent",    "frequency": "daily",   "bullish_direction": "up"},
    "PAYEMS":        {"name": "Nonfarm Payrolls",                    "category": "coincident", "unit": "thousands",  "frequency": "monthly", "bullish_direction": "up"},
    "INDPRO":        {"name": "Industrial Production",               "category": "coincident", "unit": "index",      "frequency": "monthly", "bullish_direction": "up"},
    "RSAFS":         {"name": "Retail Sales",                        "category": "coincident", "unit": "millions",   "frequency": "monthly", "bullish_direction": "up"},
    "W875RX1":       {"name": "Real Income ex Transfers",            "category": "coincident", "unit": "billions",   "frequency": "monthly", "bullish_direction": "up"},
    "UNRATE":        {"name": "Unemployment Rate",                   "category": "lagging",    "unit": "percent",    "frequency": "monthly", "bullish_direction": "down"},
    "CPILFESL":      {"name": "Core CPI",                            "category": "lagging",    "unit": "index",      "frequency": "monthly", "bullish_direction": "down"},
    "PCEPILFE":      {"name": "Core PCE",                            "category": "lagging",    "unit": "index",      "frequency": "monthly", "bullish_direction": "down"},
    "UEMPMEAN":      {"name": "Avg Duration of Unemployment",        "category": "lagging",    "unit": "weeks",      "frequency": "monthly", "bullish_direction": "down"},
    "BUSLOANS":      {"name": "Commercial & Industrial Loans",       "category": "lagging",    "unit": "billions",   "frequency": "monthly", "bullish_direction": "up"},
    "RRPONTSYD":     {"name": "Reverse Repo Outstanding",            "category": "liquidity",  "unit": "billions",   "frequency": "daily",   "bullish_direction": "down"},
    "STLFSI4":       {"name": "St. Louis Fed Financial Stress",      "category": "liquidity",  "unit": "index",      "frequency": "weekly",  "bullish_direction": "down"},
}

# Heat index weights for leading indicators (higher = more predictive historically)
HEAT_INDEX_WEIGHTS = {
    "ICSA":         0.15,   # Initial claims — most timely, very predictive
    "T10Y3M":       0.15,   # Yield curve 10Y-3M — best recession predictor
    "PERMIT":       0.12,   # Building permits — strong lead on GDP
    "AWHMAN":       0.10,   # Avg weekly hours — earliest labor signal
    "UMCSENT":      0.10,   # Consumer sentiment — forward expectations
    "ACOGNO":       0.10,   # Core capex orders — business investment
    "SAHMREALTIME": 0.08,   # Sahm rule — real-time recession detection
    "WALCL":        0.06,   # Fed balance sheet — liquidity
    "NFCI":         0.05,   # Financial conditions — credit availability
    "CCSA":         0.04,   # Continued claims — confirms initial claims
    "T10YIE":       0.03,   # Breakeven inflation — expectations
    "T5YIFR":       0.02,   # Forward inflation — long-term expectations
}

# ---------------------------------------------------------------------------
# Signal Generation
# ---------------------------------------------------------------------------
REGIME_WEIGHTS = {
    "strong_risk_off": (0.45, 0.30, 0.25),  # (macro, tech, fund)
    "risk_off":        (0.40, 0.30, 0.30),
    "neutral":         (0.30, 0.40, 0.30),
    "risk_on":         (0.20, 0.40, 0.40),
    "strong_risk_on":  (0.15, 0.40, 0.45),
}

SIGNAL_THRESHOLDS = {
    "strong_buy": 72,
    "buy":        60,
    "neutral":    40,
    "sell":       25,
}

MIN_RR_RATIO = 2.0
ATR_PERIOD = 14

# ---------------------------------------------------------------------------
# Position Sizing
# ---------------------------------------------------------------------------
RISK_PER_TRADE_BUY = 0.01        # 1% risk per BUY
RISK_PER_TRADE_STRONG = 0.02     # 2% risk per STRONG BUY
MAX_POSITION_PCT = 0.20          # Max 20% of portfolio in one position
LIQUIDITY_CAP_PCT = 0.05         # Max 5% of 20-day ADV
MAX_GROSS_EXPOSURE = 1.50        # Max 150% gross exposure

# ---------------------------------------------------------------------------
# Accounting Forensics Thresholds
# ---------------------------------------------------------------------------
BENEISH_MANIPULATION_THRESHOLD = -1.78  # M-Score above this = likely manipulation
ACCRUALS_RED_FLAG = 0.10                # Accruals ratio above 10% = red flag
CASH_CONVERSION_MIN = 0.80             # OCF/NI below 80% = concern
GROWTH_DIVERGENCE_FLAG = 0.15          # Revenue vs AR growth divergence > 15%
FORENSIC_RED_ALERT = 30                # Score below 30 = CRITICAL red flag
FORENSIC_WARNING = 50                  # Score below 50 = WARNING
PIOTROSKI_WEAK = 3                     # F-Score <= 3 = financially weak
ALTMAN_DISTRESS = 1.81                 # Z-Score below 1.81 = distress zone

# ---------------------------------------------------------------------------
# Variant Perception / DCF Scenario Parameters
# ---------------------------------------------------------------------------
DISCOUNT_RATE_BULL = 0.08
DISCOUNT_RATE_BASE = 0.10
DISCOUNT_RATE_BEAR = 0.13
SCENARIO_WEIGHTS = {"bull": 0.25, "base": 0.50, "bear": 0.25}
TERMINAL_GROWTH_CAP = 0.04  # Max 4% terminal growth

# Contrarian Consensus Signals
# Philosophy: consensus is the benchmark to beat, not the signal to follow.
# When everyone agrees, they're most likely wrong. When estimates are narrow,
# the market is fragile. When analysts herd into "Buy", it's time to be skeptical.
CONSENSUS_CROWDING_NARROW_PCT = 0.10   # Estimate spread < 10% of avg = crowded
CONSENSUS_CROWDING_WIDE_PCT = 0.30     # Estimate spread > 30% = high uncertainty (good)
CONSENSUS_HERDING_BUY_THRESH = 80.0    # >80% buy ratings = contrarian red flag
CONSENSUS_HERDING_SELL_THRESH = 80.0   # >80% sell ratings = contrarian opportunity
CONSENSUS_SURPRISE_PERSIST_MIN = 5     # 5+ of 8 quarters beating = systematic under-est
CONSENSUS_SURPRISE_PERSIST_BIAS = 0.05 # Avg beat > 5% to count as persistent
CONSENSUS_TARGET_UPSIDE_CROWDED = 0.05 # <5% upside to consensus target = priced in
CONSENSUS_TARGET_UPSIDE_DEEP = 0.30    # >30% below target = either broken or opportunity

# ---------------------------------------------------------------------------
# Consensus Blindspots (Howard Marks Second-Level Thinking)
# ---------------------------------------------------------------------------
# Sub-signal weights (must sum to 1.0)
CBS_SENTIMENT_WEIGHT = 0.25            # Market-wide sentiment cycle position
CBS_CONSENSUS_GAP_WEIGHT = 0.30        # Our view vs Wall Street consensus
CBS_POSITIONING_WEIGHT = 0.20          # Short interest, institutional, analyst skew
CBS_DIVERGENCE_WEIGHT = 0.15           # Internal module disagreement
CBS_FAT_PITCH_WEIGHT = 0.10            # Marks/Buffett extreme dislocation

# Sentiment cycle thresholds
CBS_VIX_EXTREME_HIGH = 85              # VIX percentile above this = extreme fear
CBS_VIX_EXTREME_LOW = 15               # VIX percentile below this = extreme complacency
CBS_AAII_BULL_EXTREME = 55             # AAII bullish% above this = greed extreme
CBS_AAII_BEAR_EXTREME = 55             # AAII bearish% above this = fear extreme

# Positioning extremes
CBS_SHORT_INTEREST_HIGH = 15.0         # SI% of float above this = heavily shorted
CBS_SHORT_INTEREST_LOW = 1.0           # SI% below this = complacent longs
CBS_INST_OWNERSHIP_HIGH = 95.0         # Institutional% above this = crowded
CBS_INST_OWNERSHIP_LOW = 20.0          # Institutional% below this = underfollowed

# Divergence
CBS_DIVERGENCE_THRESHOLD = 20.0        # Module score gap to count as divergent
CBS_FAT_PITCH_MIN_SIGNALS = 3          # Min conditions for fat pitch to fire
CBS_FINNHUB_DELAY = 0.15               # Rate limit for Finnhub calls

# ---------------------------------------------------------------------------
# SEC EDGAR / 13F Configuration
# ---------------------------------------------------------------------------
EDGAR_BASE = "https://data.sec.gov"
EDGAR_HEADERS = {
    "User-Agent": f"DruckenmillerAlpha/1.0 ({os.getenv('EMAIL_TO', 'alpha@example.com')})"
}
TRACKED_13F_MANAGERS = {
    "0001536411": "Duquesne (Druckenmiller)",
    "0001649339": "Scion (Burry)",
    "0000813672": "Appaloosa (Tepper)",
    "0001336920": "Pershing Square (Ackman)",
    "0001167483": "Tiger Global",
    "0001336528": "Coatue",
    "0001103804": "Viking Global",
}
CUSIP_MAP_PATH = Path(".tmp/cusip_map.json")
FMP_BASE = "https://financialmodelingprep.com/api/v3"


# Module-specific configs (convergence weights, regime profiles, per-module settings)
from tools.config_modules import *  # noqa: F401,F403
