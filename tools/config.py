"""Central configuration for the Druckenmiller Alpha System.

All API keys loaded from .env via python-dotenv.
"""

import os
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
CUSIP_MAP_PATH = ".tmp/cusip_map.json"
FMP_BASE = "https://financialmodelingprep.com/api/v3"

# ---------------------------------------------------------------------------
# Convergence Weights (must sum to 1.0)
# ---------------------------------------------------------------------------
CONVERGENCE_WEIGHTS = {
    "smartmoney":              0.15,   # was 0.16, gave 0.01 to consensus_blindspots
    "worldview":               0.13,   # was 0.14, gave 0.01 to consensus_blindspots
    "variant":                 0.09,
    "foreign_intel":           0.07,
    "research":                0.06,
    "main_signal":             0.03,   # was 0.04, gave 0.01 to consensus_blindspots
    "reddit":                  0.00,   # was 0.01, gave 0.01 to consensus_blindspots
    "news_displacement":       0.06,
    "alt_data":                0.02,
    "sector_expert":           0.05,
    "pairs":                   0.05,
    "ma":                      0.04,
    "energy_intel":            0.05,
    "prediction_markets":      0.05,
    "pattern_options":         0.04,
    "estimate_momentum":       0.04,
    "ai_regulatory":           0.03,
    "consensus_blindspots":    0.04,   # Howard Marks second-level thinking (contrarian edge)
}

# Conviction thresholds (based on module count)
CONVICTION_HIGH = 3       # 3+ modules agree
CONVICTION_NOTABLE = 2    # 2 modules agree
CONVICTION_WATCH = 1      # 1 module
# forensic_blocked overrides all → BLOCKED

# ---------------------------------------------------------------------------
# Foreign Intelligence Configuration
# ---------------------------------------------------------------------------

# Cost controls
FOREIGN_INTEL_MAX_ARTICLES_PER_SOURCE = 5   # per daily run
FOREIGN_INTEL_MAX_CHARS_TRANSLATE = 2000    # Tier 2 limit
FOREIGN_INTEL_FULL_TEXT_THRESHOLD = 80      # relevance score to trigger Tier 3
FOREIGN_INTEL_FULL_TEXT_MAX_CHARS = 10000   # Tier 3 limit
FOREIGN_INTEL_LOOKBACK_DAYS = 14            # for convergence scoring

# Cultural sentiment calibration factors
SENTIMENT_CALIBRATION = {
    "ja": 1.4,    # Japanese media understates
    "ko": 1.0,    # Korean press is direct
    "zh": {"positive": 0.7, "negative": 1.3},  # Chinese state-adjacent bias
    "de": 1.2,    # German press is measured
    "fr": 0.85,   # French press can be dramatic
    "it": 0.85,   # Italian similar to French
}

# Sources per market — each entry: (source_name, site_domain, search_keywords)
FOREIGN_INTEL_SOURCES = {
    "japan": [
        ("Nikkei", "nikkei.com", "株 決算 業績"),
        ("Kabutan", "kabutan.jp", "決算 業績 株価"),
        ("Toyo Keizai", "toyokeizai.net", "半導体 AI テクノロジー 企業"),
        ("Bloomberg JP", "bloomberg.co.jp", "市場 株式 企業"),
    ],
    "korea": [
        ("Maeil Business", "mk.co.kr", "삼성 반도체 실적 주식"),
        ("ETNews", "etnews.com", "반도체 AI 디스플레이"),
        ("Chosun Biz", "biz.chosun.com", "주식 실적 기업"),
    ],
    "china": [
        ("Caixin", "caixin.com", "科技 金融 企业 财报"),
        ("36Kr", "36kr.com", "AI 芯片 科技 创业"),
        ("Sina Finance", "finance.sina.com.cn", "股市 行情 公司"),
    ],
    "europe_de": [
        ("Handelsblatt", "handelsblatt.com", "Aktie Industrie Unternehmen Rüstung"),
        ("Boerse.de", "boerse.de", "DAX Aktie Analyse"),
    ],
    "europe_fr": [
        ("Les Echos", "lesechos.fr", "LVMH Airbus action entreprise bourse"),
        ("BFM Business", "bfmbusiness.bfmtv.com", "bourse marché entreprise"),
    ],
    "europe_it": [
        ("Il Sole 24 Ore", "ilsole24ore.com", "borsa mercati azienda"),
    ],
}

# Language code per market
MARKET_LANGUAGE = {
    "japan": "ja",
    "korea": "ko",
    "china": "zh",
    "europe_de": "de",
    "europe_fr": "fr",
    "europe_it": "it",
}

# Serper language/country params for better results
MARKET_SERPER_PARAMS = {
    "japan":     {"gl": "jp", "hl": "ja"},
    "korea":     {"gl": "kr", "hl": "ko"},
    "china":     {"gl": "cn", "hl": "zh-cn"},
    "europe_de": {"gl": "de", "hl": "de"},
    "europe_fr": {"gl": "fr", "hl": "fr"},
    "europe_it": {"gl": "it", "hl": "it"},
}

# Regime-aware market priority (which markets to scan first)
# ---------------------------------------------------------------------------
# Research Sources Configuration
# ---------------------------------------------------------------------------
_YEAR = datetime.now().year
_YEAR_RANGE = f"{_YEAR - 1} {_YEAR}"

RESEARCH_SOURCES = [
    {
        "name": "epoch_ai",
        "serper_query": f"site:epochai.org AI compute training scaling {_YEAR_RANGE}",
        "relevance_tickers": ["NVDA", "AMD", "GOOGL", "MSFT", "META", "AMZN", "TSM", "ASML"],
        "themes": ["ai_capex", "compute_scaling", "training_runs"],
    },
    {
        "name": "semianalysis",
        "serper_query": f"site:semianalysis.com semiconductor GPU HBM AI chip {_YEAR_RANGE}",
        "relevance_tickers": ["NVDA", "AMD", "TSM", "ASML", "AMAT", "LRCX", "KLAC", "MU"],
        "themes": ["semiconductors", "fab_capacity", "chip_shortage"],
    },
    {
        "name": "federal_reserve",
        "serper_query": f"site:federalreserve.gov monetary policy financial stability report {_YEAR_RANGE}",
        "relevance_tickers": [],
        "themes": ["monetary_policy", "rate_hike", "rate_cut", "quantitative_tightening", "liquidity"],
    },
    {
        "name": "bls",
        "serper_query": f"site:bls.gov CPI PPI employment situation {_YEAR_RANGE}",
        "relevance_tickers": [],
        "themes": ["inflation", "cpi", "ppi", "labor_market", "employment"],
    },
    # --- Top-tier macro sources (Serper search + Firecrawl with snippet fallback) ---
    {
        "name": "financial_times",
        "serper_query": f"site:ft.com markets economy central bank policy {_YEAR_RANGE}",
        "relevance_tickers": [],
        "themes": ["monetary_policy", "geopolitics", "inflation", "liquidity", "central_banks"],
    },
    {
        "name": "wsj_markets",
        "serper_query": f"site:wsj.com markets economy earnings corporate {_YEAR_RANGE}",
        "relevance_tickers": [],
        "themes": ["monetary_policy", "inflation", "labor_market", "employment", "m_and_a"],
    },
    {
        "name": "reuters",
        "serper_query": f"site:reuters.com markets commodities economy breaking {_YEAR_RANGE}",
        "relevance_tickers": [],
        "themes": ["geopolitics", "trade_war", "tariffs", "energy", "oil", "commodities_physical"],
    },
    {
        "name": "bloomberg",
        "serper_query": f"site:bloomberg.com markets deals earnings economy {_YEAR_RANGE}",
        "relevance_tickers": [],
        "themes": ["monetary_policy", "liquidity", "geopolitics", "inflation", "m_and_a"],
    },
    # --- Policy sources ---
    {
        "name": "politico",
        "serper_query": f"site:politico.com regulation trade policy fiscal spending {_YEAR_RANGE}",
        "relevance_tickers": [],
        "themes": ["regulation", "fiscal_policy", "trade_policy", "tariffs", "geopolitics"],
    },
    # --- Sector/alternative sources ---
    {
        "name": "the_information",
        "serper_query": f"site:theinformation.com AI tech startup funding {_YEAR_RANGE}",
        "relevance_tickers": ["NVDA", "MSFT", "GOOGL", "META", "AMZN", "ORCL"],
        "themes": ["ai_capex", "cloud_computing", "data_centers", "compute_scaling"],
    },
    {
        "name": "energy_intelligence",
        "serper_query": f"site:energyintel.com OR site:spglobal.com/commodityinsights oil gas OPEC LNG power {_YEAR_RANGE}",
        "relevance_tickers": ["OXY", "COP", "XOM", "CVX", "LNG", "VST", "CEG"],
        "themes": ["energy", "oil", "natural_gas", "power_demand"],
    },
    # --- Investment Bank Research ---
    {
        "name": "morgan_stanley",
        "serper_query": f"site:morganstanley.com research insights markets outlook {_YEAR_RANGE}",
        "relevance_tickers": ["NVDA", "MSFT", "GOOGL", "AMZN", "META", "AAPL", "TSM"],
        "themes": ["ai_capex", "semiconductors", "monetary_policy", "geopolitics", "m_and_a"],
    },
    {
        "name": "goldman_sachs",
        "serper_query": f"site:goldmansachs.com/insights markets economy outlook strategy {_YEAR_RANGE}",
        "relevance_tickers": ["NVDA", "MSFT", "GOOGL", "AMZN", "META", "AAPL", "JPM"],
        "themes": ["monetary_policy", "inflation", "liquidity", "geopolitics", "ai_capex"],
    },
    {
        "name": "jpmorgan",
        "serper_query": f"site:jpmorgan.com/insights research markets economy outlook {_YEAR_RANGE}",
        "relevance_tickers": ["NVDA", "MSFT", "GOOGL", "AMZN", "XOM", "JPM"],
        "themes": ["monetary_policy", "inflation", "credit_markets", "energy", "ai_capex"],
    },
    {
        "name": "bofa_research",
        "serper_query": f"site:business.bofa.com market strategy outlook research {_YEAR_RANGE}",
        "relevance_tickers": [],
        "themes": ["monetary_policy", "inflation", "liquidity", "credit_markets", "commodities_physical"],
    },
    # --- Strategy Consulting / Industry Reports ---
    {
        "name": "mckinsey",
        "serper_query": f"site:mckinsey.com/industries technology energy semiconductors AI financial-services {_YEAR_RANGE}",
        "relevance_tickers": ["NVDA", "MSFT", "GOOGL", "AMZN", "META", "TSM", "ASML"],
        "themes": ["ai_capex", "compute_scaling", "energy", "semiconductors", "cloud_computing"],
    },
    {
        "name": "bcg",
        "serper_query": f"site:bcg.com/publications technology energy AI semiconductors financial-services {_YEAR_RANGE}",
        "relevance_tickers": ["NVDA", "MSFT", "GOOGL", "AMZN", "META", "TSM"],
        "themes": ["ai_capex", "compute_scaling", "energy", "semiconductors", "cloud_computing"],
    },
    {
        "name": "bain",
        "serper_query": f"site:bain.com/insights technology energy private-equity AI {_YEAR_RANGE}",
        "relevance_tickers": ["NVDA", "MSFT", "GOOGL", "AMZN", "KKR", "BX", "APO"],
        "themes": ["ai_capex", "m_and_a", "energy", "cloud_computing", "data_centers"],
    },
]

# Paywall handling: when Firecrawl can't get full text, fall back to Serper snippet
RESEARCH_MIN_SCRAPE_CHARS = 200
RESEARCH_SNIPPET_FALLBACK = True

# ---------------------------------------------------------------------------
# Pairs Trading / Statistical Arbitrage Configuration
# ---------------------------------------------------------------------------
PAIRS_MIN_CORRELATION = 0.60          # Min 60d correlation to test cointegration
PAIRS_COINT_PVALUE = 0.05            # Max p-value for cointegration acceptance
PAIRS_HALF_LIFE_MIN = 3              # Min half-life in days (filter noise)
PAIRS_HALF_LIFE_MAX = 60             # Max half-life in days (filter slow-reverting)
PAIRS_ZSCORE_MR_THRESHOLD = 2.0      # Z-score threshold for mean-reversion signal
PAIRS_ZSCORE_RUNNER_THRESHOLD = 1.5   # Z-score threshold for runner detection
PAIRS_RUNNER_MIN_TECH = 60            # Min technical score for runner candidate (avg ~43, so 60 = top quartile)
PAIRS_RUNNER_MIN_FUND = 40            # Min fundamental score for runner candidate (avg ~39, so 40 = above median)
PAIRS_LOOKBACK_DAYS = 252            # 1 year of trading days for spread stats
PAIRS_REFRESH_DAYS = 7               # How often to recompute pair relationships
PAIRS_MIN_PRICE_DAYS = 120           # Min overlapping trading days required

# ---------------------------------------------------------------------------
# M&A Intelligence Configuration
# ---------------------------------------------------------------------------
MA_RUMOR_LOOKBACK_DAYS = 7            # How many days of news to scan for rumors
MA_RUMOR_HALF_LIFE_DAYS = 5           # Decay half-life for stale rumors
MA_NEWS_BATCH_SIZE = 10               # Articles per Gemini classification batch
MA_FINNHUB_DELAY = 0.15              # Rate limit between Finnhub calls
MA_GEMINI_DELAY = 1.5                # Rate limit between Gemini calls
MA_MIN_MARKET_CAP = 500_000_000      # $500M — below this, too illiquid for M&A signal
MA_MAX_MARKET_CAP = 200_000_000_000  # $200B — above this, acquisition near-impossible
MA_TARGET_WEIGHT_PROFILE = 0.40      # Weight of target profile in final ma_score
MA_TARGET_WEIGHT_RUMOR = 0.40        # Weight of rumor signal in final ma_score
# Remaining 0.20 is interaction bonus (profile × rumor convergence)
MA_MIN_SCORE_STORE = 15              # Min ma_score to persist (filter noise)

# ---------------------------------------------------------------------------
# Satellite Data Configuration
# ---------------------------------------------------------------------------
# ENSO / ONI thresholds (Oceanic Niño Index)
ENSO_MODERATE_THRESHOLD = 0.5         # |ONI| >= 0.5 → El Niño/La Niña phase
ENSO_STRONG_THRESHOLD = 1.5           # |ONI| >= 1.5 → Strong phase
ENSO_MODERATE_STRENGTH = 55           # Signal strength for moderate phase
ENSO_STRONG_STRENGTH = 80             # Signal strength for strong phase

# NDVI (Normalized Difference Vegetation Index) — crop health from space
NDVI_ZSCORE_THRESHOLD = 1.5           # |z| >= 1.5 to fire signal
NDVI_STRESS_BASE_STRENGTH = 60        # Base signal strength for crop stress
NDVI_QUERY_DELAY = 1.0                # Seconds between ORNL MODIS queries

# ---------------------------------------------------------------------------
# Estimate Revision Momentum (Jane Street edge)
# ---------------------------------------------------------------------------
# Sub-signal weights (must sum to 1.0)
EM_REVISION_VELOCITY_WEIGHT = 0.30    # EPS revision velocity (primary signal)
EM_REVENUE_VELOCITY_WEIGHT = 0.10     # Revenue revision velocity
EM_ACCELERATION_WEIGHT = 0.15         # Is velocity increasing or decreasing?
EM_SURPRISE_MOMENTUM_WEIGHT = 0.25    # Beat/miss streaks + magnitude
EM_DISPERSION_WEIGHT = 0.10           # Estimate spread tightening/widening
EM_CROSS_SECTIONAL_WEIGHT = 0.10      # Rank vs sector peers

# Thresholds
EM_STRONG_REVISION_PCT = 5.0          # >=5% revision = strong signal
EM_MODERATE_REVISION_PCT = 1.0        # >=1% revision = moderate signal
EM_SURPRISE_STREAK_BONUS = 15         # Extra points for increasing surprise magnitude
EM_DISPERSION_TIGHTENING_BONUS = 10   # Bonus when estimate spread narrows below 10%

# ---------------------------------------------------------------------------
# TA Pre-Screening Gate
# ---------------------------------------------------------------------------
# After Phase 2 technical scoring, gate which assets proceed to expensive
# Phase 2.5+ modules. Saves API costs by skipping broken-chart stocks.
# Tiered: SKIP = skip ALL expensive modules, FULL = threshold for forensics/variant.
TA_GATE_SKIP = 20                    # Below this: skip all expensive per-stock modules
TA_GATE_FULL = 35                    # Below this: skip forensics + variant (most expensive)
TA_GATE_OVERRIDE_WATCHLIST = True    # Watchlist symbols always get full analysis
TA_GATE_OVERRIDE_EXISTING_SIGNALS = True  # Prior BUY/STRONG BUY always get full analysis
TA_GATE_NEW_IPO_DAYS = 50           # Symbols with < N days of price data bypass the gate

# ---------------------------------------------------------------------------
# Regime-Adaptive Convergence Weights
# ---------------------------------------------------------------------------
# Module weights shift based on macro regime. In risk-off, contrarian and
# real-world signals dominate; in risk-on, momentum and trend signals lead.
# All profiles sum to 1.00. Falls back to static CONVERGENCE_WEIGHTS if
# no macro data is available.
REGIME_CONVERGENCE_WEIGHTS = {
    "strong_risk_off": {
        "smartmoney":              0.10,
        "worldview":               0.08,
        "variant":                 0.13,
        "foreign_intel":           0.09,
        "research":                0.05,
        "main_signal":             0.01,
        "reddit":                  0.00,
        "news_displacement":       0.08,
        "alt_data":                0.04,
        "sector_expert":           0.06,
        "pairs":                   0.03,
        "ma":                      0.03,
        "energy_intel":            0.06,
        "prediction_markets":      0.07,
        "pattern_options":         0.02,
        "estimate_momentum":       0.03,
        "ai_regulatory":           0.05,
        "consensus_blindspots":    0.07,   # HIGHEST — contrarian signals peak when fear peaks (Marks)
    },
    "risk_off": {
        "smartmoney":              0.12,
        "worldview":               0.10,
        "variant":                 0.11,
        "foreign_intel":           0.08,
        "research":                0.06,
        "main_signal":             0.02,
        "reddit":                  0.00,
        "news_displacement":       0.07,
        "alt_data":                0.03,
        "sector_expert":           0.05,
        "pairs":                   0.04,
        "ma":                      0.03,
        "energy_intel":            0.06,
        "prediction_markets":      0.06,
        "pattern_options":         0.03,
        "estimate_momentum":       0.04,
        "ai_regulatory":           0.04,
        "consensus_blindspots":    0.06,   # High — contrarian opportunities emerge in fear
    },
    "neutral": {
        "smartmoney":              0.15,
        "worldview":               0.13,
        "variant":                 0.09,
        "foreign_intel":           0.07,
        "research":                0.06,
        "main_signal":             0.03,
        "reddit":                  0.00,
        "news_displacement":       0.06,
        "alt_data":                0.02,
        "sector_expert":           0.05,
        "pairs":                   0.05,
        "ma":                      0.04,
        "energy_intel":            0.05,
        "prediction_markets":      0.05,
        "pattern_options":         0.04,
        "estimate_momentum":       0.04,
        "ai_regulatory":           0.03,
        "consensus_blindspots":    0.04,   # Baseline — mirrors static weights
    },
    "risk_on": {
        "smartmoney":              0.15,
        "worldview":               0.14,   # was 0.15
        "variant":                 0.07,
        "foreign_intel":           0.05,
        "research":                0.05,
        "main_signal":             0.06,
        "reddit":                  0.02,   # was 0.03
        "news_displacement":       0.05,
        "alt_data":                0.02,
        "sector_expert":           0.05,
        "pairs":                   0.07,
        "ma":                      0.05,
        "energy_intel":            0.05,
        "prediction_markets":      0.04,
        "pattern_options":         0.05,
        "estimate_momentum":       0.04,
        "ai_regulatory":           0.02,
        "consensus_blindspots":    0.02,   # Low — momentum dominates, contrarian is early
    },
    "strong_risk_on": {
        "smartmoney":              0.13,
        "worldview":               0.15,   # was 0.16
        "variant":                 0.05,
        "foreign_intel":           0.04,
        "research":                0.05,
        "main_signal":             0.08,
        "reddit":                  0.03,   # was 0.04
        "news_displacement":       0.04,
        "alt_data":                0.02,
        "sector_expert":           0.05,
        "pairs":                   0.09,
        "ma":                      0.06,
        "energy_intel":            0.04,
        "prediction_markets":      0.03,
        "pattern_options":         0.06,
        "estimate_momentum":       0.04,
        "ai_regulatory":           0.02,
        "consensus_blindspots":    0.02,   # Minimal — euphoria overrides contrarian (for now)
    },
}

# ---------------------------------------------------------------------------
# Devil's Advocate Configuration
# ---------------------------------------------------------------------------
DA_MAX_SIGNALS = 10           # Max HIGH signals to analyze per run
DA_WARNING_THRESHOLD = 75     # risk_score above this triggers WARNING flag
DA_GEMINI_TEMPERATURE = 0.7   # Higher temp for creative adversarial thinking

# ---------------------------------------------------------------------------
# Adaptive Weight Optimizer Configuration
# ---------------------------------------------------------------------------
WO_MIN_WEIGHT = 0.01             # No module below 1% (except reddit=0)
WO_MAX_WEIGHT = 0.25             # No single module above 25%
WO_MIN_OBSERVATIONS = 60         # Per module before adjusting weights
WO_MAX_DELTA_PER_CYCLE = 0.02    # Max 2% weight change per daily run
WO_LEARNING_RATE = 0.10          # Bayesian update conservatism (lower = slower adaptation)
WO_MIN_TOTAL_SIGNALS = 100       # Minimum total resolved signals before any adjustment
WO_MIN_DAYS_RUNNING = 30         # Minimum days of data collection before adapting
WO_ENABLE_ADAPTIVE = True        # Master switch for adaptive weights
WO_HOLDOUT_MODULES = ["reddit"]  # Modules excluded from optimization (weight stays fixed)

# ---------------------------------------------------------------------------
# Insider Trading Configuration
# ---------------------------------------------------------------------------
INSIDER_CLUSTER_WINDOW_DAYS = 14       # Window for detecting cluster buys
INSIDER_CLUSTER_MIN_COUNT = 3          # Min distinct insiders buying = cluster
INSIDER_LARGE_BUY_THRESHOLD = 200_000  # $200K+ = large purchase
INSIDER_UNUSUAL_VOLUME_MULT = 3.0      # Buy value > 3x avg = unusual
INSIDER_BOOST_HIGH = 15                # Smart money conviction boost when insider_score >= 70
INSIDER_BOOST_MED = 8                  # Boost when insider_score >= 50
INSIDER_SELL_PENALTY = -10             # Penalty when insider_score <= 20
INSIDER_FMP_BATCH_SIZE = 30            # Symbols per FMP batch (rate limit)
INSIDER_LOOKBACK_DAYS = 90             # How far back to fetch transactions

# ---------------------------------------------------------------------------
# AI Executive Investment Tracker
# ---------------------------------------------------------------------------
AI_EXEC_SERPER_QUERIES_PER_EXEC = 2      # Search queries per exec per run
AI_EXEC_MAX_URLS_PER_EXEC = 3            # Max URLs to scrape per exec
AI_EXEC_FIRECRAWL_DELAY = 2.0            # Seconds between Firecrawl calls
AI_EXEC_GEMINI_DELAY = 1.5               # Seconds between Gemini calls
AI_EXEC_MIN_CONFIDENCE = 3               # Filter activities below this
AI_EXEC_MIN_SCORE_STORE = 20             # Min raw_score to persist
AI_EXEC_SM_BOOST_HIGH = 12               # Smart money boost when ai_exec_score >= 70
AI_EXEC_SM_BOOST_MED = 6                 # Boost when ai_exec_score >= 50
AI_EXEC_CONVERGENCE_BONUS = 10           # Bonus when 2+ execs invest in same target
AI_EXEC_LOOKBACK_DAYS = 180              # How far back to consider activities
AI_EXEC_SCAN_INTERVAL_DAYS = 7           # Run weekly, not daily

AI_EXEC_WATCHLIST = [
    # ── OpenAI ──
    {"name": "Sam Altman", "role": "CEO", "org": "OpenAI", "prominence": 95,
     "search_aliases": ["Sam Altman investment", "Sam Altman board", "Sam Altman angel"],
     "known_vehicles": ["Hydrazine Capital"]},
    {"name": "Greg Brockman", "role": "President", "org": "OpenAI", "prominence": 75,
     "search_aliases": ["Greg Brockman investment", "Greg Brockman board"]},
    # ── Anthropic ──
    {"name": "Dario Amodei", "role": "CEO", "org": "Anthropic", "prominence": 85,
     "search_aliases": ["Dario Amodei investment", "Dario Amodei board"]},
    {"name": "Daniela Amodei", "role": "President", "org": "Anthropic", "prominence": 75,
     "search_aliases": ["Daniela Amodei investment", "Daniela Amodei board"]},
    # ── Google / DeepMind ──
    {"name": "Demis Hassabis", "role": "CEO DeepMind", "org": "Google DeepMind", "prominence": 90,
     "search_aliases": ["Demis Hassabis investment", "Demis Hassabis board"]},
    {"name": "Jeff Dean", "role": "Chief Scientist", "org": "Google AI", "prominence": 80,
     "search_aliases": ["Jeff Dean Google investment", "Jeff Dean board"]},
    # ── Meta ──
    {"name": "Yann LeCun", "role": "Chief AI Scientist", "org": "Meta", "prominence": 85,
     "search_aliases": ["Yann LeCun investment", "Yann LeCun board"]},
    # ── NVIDIA ──
    {"name": "Jensen Huang", "role": "CEO", "org": "NVIDIA", "prominence": 98,
     "search_aliases": ["Jensen Huang personal investment", "Jensen Huang board"]},
    # ── Microsoft ──
    {"name": "Satya Nadella", "role": "CEO", "org": "Microsoft", "prominence": 95,
     "search_aliases": ["Satya Nadella personal investment", "Satya Nadella board"]},
    {"name": "Mustafa Suleyman", "role": "CEO Microsoft AI", "org": "Microsoft", "prominence": 80,
     "search_aliases": ["Mustafa Suleyman investment", "Mustafa Suleyman board"]},
    {"name": "Kevin Scott", "role": "CTO", "org": "Microsoft", "prominence": 70,
     "search_aliases": ["Kevin Scott Microsoft investment"]},
    # ── xAI / Tesla ──
    {"name": "Elon Musk", "role": "CEO", "org": "xAI/Tesla", "prominence": 99,
     "search_aliases": ["Elon Musk AI investment", "Elon Musk startup investment"]},
    # ── AMD ──
    {"name": "Lisa Su", "role": "CEO", "org": "AMD", "prominence": 85,
     "search_aliases": ["Lisa Su personal investment", "Lisa Su board"]},
    # ── Independent AI leaders ──
    {"name": "Ilya Sutskever", "role": "Co-founder", "org": "Safe Superintelligence", "prominence": 85,
     "search_aliases": ["Ilya Sutskever investment", "Ilya Sutskever startup"]},
    {"name": "Andrej Karpathy", "role": "Founder", "org": "Eureka Labs", "prominence": 80,
     "search_aliases": ["Andrej Karpathy investment", "Andrej Karpathy startup"]},
    {"name": "Fei-Fei Li", "role": "Co-founder", "org": "World Labs", "prominence": 75,
     "search_aliases": ["Fei-Fei Li investment", "Fei-Fei Li World Labs"]},
    {"name": "Alexandr Wang", "role": "CEO", "org": "Scale AI", "prominence": 70,
     "search_aliases": ["Alexandr Wang investment", "Alexandr Wang Scale AI"]},
    {"name": "Arthur Mensch", "role": "CEO", "org": "Mistral AI", "prominence": 70,
     "search_aliases": ["Arthur Mensch investment", "Arthur Mensch Mistral"]},
    # ── AI-focused VCs ──
    {"name": "Vinod Khosla", "role": "Founder", "org": "Khosla Ventures", "prominence": 85,
     "search_aliases": ["Vinod Khosla AI investment", "Khosla Ventures AI"]},
    {"name": "Elad Gil", "role": "Angel Investor", "org": "Independent", "prominence": 75,
     "search_aliases": ["Elad Gil investment", "Elad Gil AI startup"]},
    {"name": "Sarah Guo", "role": "Founder", "org": "Conviction Capital", "prominence": 70,
     "search_aliases": ["Sarah Guo Conviction investment", "Conviction Capital AI"]},
    {"name": "Nat Friedman", "role": "Angel Investor", "org": "Independent", "prominence": 75,
     "search_aliases": ["Nat Friedman investment", "Nat Friedman AI startup"]},
    {"name": "Daniel Gross", "role": "Angel Investor", "org": "Independent", "prominence": 70,
     "search_aliases": ["Daniel Gross AI investment", "Daniel Gross startup"]},
]

REGIME_MARKET_PRIORITY = {
    "strong_risk_on":  ["japan", "korea", "china", "europe_de", "europe_fr", "europe_it"],
    "risk_on":         ["japan", "europe_de", "korea", "china", "europe_fr", "europe_it"],
    "neutral":         ["japan", "europe_de", "europe_fr", "korea", "china", "europe_it"],
    "risk_off":        ["europe_de", "europe_fr", "japan", "europe_it", "korea", "china"],
    "strong_risk_off": ["europe_de", "europe_fr", "europe_it", "japan"],
}

# ---------------------------------------------------------------------------
# Hyperliquid Weekend Gap Arbitrage
# ---------------------------------------------------------------------------
HL_API_BASE = "https://api.hyperliquid.xyz"
HL_SNAPSHOT_INTERVAL_HOURS = 1
HL_OPTIMAL_SIGNAL_TIME = "20:00"   # UTC — best R² for gap prediction (slope≈1.0)
HL_CROSS_DEPLOYER_SPREAD_THRESHOLD_BPS = 50
HL_BOOK_THIN_WARNING_PCT = 50      # Warn when book drops >50% vs Saturday avg
HL_GAP_ALERT_THRESHOLD_PCT = 1.0   # Email alert if |predicted gap| > 1%
HL_DEPLOYER_ALERT_THRESHOLD_BPS = 100  # Alert if cross-deployer spread > 100bps

# Deployer names (discovered via perpDexs endpoint)
HL_DEPLOYERS = ["xyz", "flx", "km", "vntl", "cash"]

# Instrument mapping: hl_symbol -> {ticker, deployer, asset_class, name}
# Only instruments with a clear traditional market equivalent
HL_INSTRUMENTS = {
    # ── XYZ deployer — commodities ──
    "xyz:GOLD":      {"ticker": "GC=F",   "deployer": "xyz",  "asset_class": "commodity", "name": "Gold",          "gap_eligible": True},
    "xyz:SILVER":    {"ticker": "SI=F",   "deployer": "xyz",  "asset_class": "commodity", "name": "Silver",        "gap_eligible": True},
    "xyz:CL":        {"ticker": "CL=F",   "deployer": "xyz",  "asset_class": "commodity", "name": "WTI Crude",     "gap_eligible": True},
    "xyz:BRENTOIL":  {"ticker": "BZ=F",   "deployer": "xyz",  "asset_class": "commodity", "name": "Brent Crude",   "gap_eligible": True},
    "xyz:NATGAS":    {"ticker": "NG=F",   "deployer": "xyz",  "asset_class": "commodity", "name": "Natural Gas",   "gap_eligible": True},
    "xyz:COPPER":    {"ticker": "HG=F",   "deployer": "xyz",  "asset_class": "commodity", "name": "Copper",        "gap_eligible": True},
    "xyz:PLATINUM":  {"ticker": "PL=F",   "deployer": "xyz",  "asset_class": "commodity", "name": "Platinum",      "gap_eligible": True},
    # ── XYZ deployer — indices ──
    "xyz:XYZ100":    {"ticker": "NQ=F",   "deployer": "xyz",  "asset_class": "index",     "name": "Nasdaq 100",    "gap_eligible": True},
    # ── XYZ deployer — single stocks ──
    "xyz:TSLA":      {"ticker": "TSLA",   "deployer": "xyz",  "asset_class": "stock",     "name": "Tesla",         "gap_eligible": True},
    "xyz:NVDA":      {"ticker": "NVDA",   "deployer": "xyz",  "asset_class": "stock",     "name": "NVIDIA",        "gap_eligible": True},
    "xyz:AMD":       {"ticker": "AMD",    "deployer": "xyz",  "asset_class": "stock",     "name": "AMD",           "gap_eligible": True},
    "xyz:AAPL":      {"ticker": "AAPL",   "deployer": "xyz",  "asset_class": "stock",     "name": "Apple",         "gap_eligible": True},
    "xyz:AMZN":      {"ticker": "AMZN",   "deployer": "xyz",  "asset_class": "stock",     "name": "Amazon",        "gap_eligible": True},
    "xyz:GOOGL":     {"ticker": "GOOGL",  "deployer": "xyz",  "asset_class": "stock",     "name": "Alphabet",      "gap_eligible": True},
    "xyz:META":      {"ticker": "META",   "deployer": "xyz",  "asset_class": "stock",     "name": "Meta",          "gap_eligible": True},
    "xyz:MSFT":      {"ticker": "MSFT",   "deployer": "xyz",  "asset_class": "stock",     "name": "Microsoft",     "gap_eligible": True},
    # ── XYZ deployer — FX/macro ──
    "xyz:DXY":       {"ticker": "DX-Y.NYB", "deployer": "xyz", "asset_class": "fx",       "name": "Dollar Index",  "gap_eligible": True},
    # ── Felix (flx) deployer — 1:1 priced ──
    "flx:GOLD":      {"ticker": "GC=F",   "deployer": "flx",  "asset_class": "commodity", "name": "Gold",          "gap_eligible": True},
    "flx:SILVER":    {"ticker": "SI=F",   "deployer": "flx",  "asset_class": "commodity", "name": "Silver",        "gap_eligible": True},
    "flx:OIL":       {"ticker": "CL=F",   "deployer": "flx",  "asset_class": "commodity", "name": "WTI Crude",     "gap_eligible": True},
    "flx:COPPER":    {"ticker": "HG=F",   "deployer": "flx",  "asset_class": "commodity", "name": "Copper",        "gap_eligible": True},
    "flx:PLATINUM":  {"ticker": "PL=F",   "deployer": "flx",  "asset_class": "commodity", "name": "Platinum",      "gap_eligible": True},
    "flx:TSLA":      {"ticker": "TSLA",   "deployer": "flx",  "asset_class": "stock",     "name": "Tesla",         "gap_eligible": True},
    "flx:NVDA":      {"ticker": "NVDA",   "deployer": "flx",  "asset_class": "stock",     "name": "NVIDIA",        "gap_eligible": True},
    # ── Kinetiq (km) deployer — stocks (1:1 priced) ──
    "km:TSLA":       {"ticker": "TSLA",   "deployer": "km",   "asset_class": "stock",     "name": "Tesla",         "gap_eligible": True},
    "km:NVDA":       {"ticker": "NVDA",   "deployer": "km",   "asset_class": "stock",     "name": "NVIDIA",        "gap_eligible": True},
    "km:AAPL":       {"ticker": "AAPL",   "deployer": "km",   "asset_class": "stock",     "name": "Apple",         "gap_eligible": True},
    "km:GOOGL":      {"ticker": "GOOGL",  "deployer": "km",   "asset_class": "stock",     "name": "Alphabet",      "gap_eligible": True},
    "km:GOLD":       {"ticker": "GC=F",   "deployer": "km",   "asset_class": "commodity", "name": "Gold",          "gap_eligible": True},
    "km:SILVER":     {"ticker": "SI=F",   "deployer": "km",   "asset_class": "commodity", "name": "Silver",        "gap_eligible": True},
    # Kinetiq — different price scale than ETFs (track for cross-deployer only)
    "km:US500":      {"ticker": "SPY",    "deployer": "km",   "asset_class": "etf",       "name": "S&P 500",      "gap_eligible": False},
    "km:SEMI":       {"ticker": "SMH",    "deployer": "km",   "asset_class": "etf",       "name": "Semiconductors","gap_eligible": False},
    "km:SMALL2000":  {"ticker": "IWM",    "deployer": "km",   "asset_class": "etf",       "name": "Russell 2000",  "gap_eligible": False},
    "km:USENERGY":   {"ticker": "XLE",    "deployer": "km",   "asset_class": "etf",       "name": "Energy",        "gap_eligible": False},
    "km:USOIL":      {"ticker": "CL=F",   "deployer": "km",   "asset_class": "commodity", "name": "WTI Crude",     "gap_eligible": False},
    # ── Ventuals (vntl) — different price scale (track for cross-deployer only) ──
    "vntl:SEMIS":    {"ticker": "SMH",    "deployer": "vntl", "asset_class": "etf",       "name": "Semiconductors","gap_eligible": False},
    "vntl:ENERGY":   {"ticker": "XLE",    "deployer": "vntl", "asset_class": "etf",       "name": "Energy",        "gap_eligible": False},
    "vntl:DEFENSE":  {"ticker": "ITA",    "deployer": "vntl", "asset_class": "etf",       "name": "Defense",       "gap_eligible": False},
    # ── Cash (dreamcash) deployer — 1:1 priced ──
    "cash:TSLA":     {"ticker": "TSLA",   "deployer": "cash", "asset_class": "stock",     "name": "Tesla",         "gap_eligible": True},
    "cash:NVDA":     {"ticker": "NVDA",   "deployer": "cash", "asset_class": "stock",     "name": "NVIDIA",        "gap_eligible": True},
    "cash:GOLD":     {"ticker": "GC=F",   "deployer": "cash", "asset_class": "commodity", "name": "Gold",          "gap_eligible": True},
    "cash:SILVER":   {"ticker": "SI=F",   "deployer": "cash", "asset_class": "commodity", "name": "Silver",        "gap_eligible": True},
    "cash:GOOGL":    {"ticker": "GOOGL",  "deployer": "cash", "asset_class": "stock",     "name": "Alphabet",      "gap_eligible": True},
    "cash:META":     {"ticker": "META",   "deployer": "cash", "asset_class": "stock",     "name": "Meta",          "gap_eligible": True},
    "cash:MSFT":     {"ticker": "MSFT",   "deployer": "cash", "asset_class": "stock",     "name": "Microsoft",     "gap_eligible": True},
    "cash:AMZN":     {"ticker": "AMZN",   "deployer": "cash", "asset_class": "stock",     "name": "Amazon",        "gap_eligible": True},
    # Cash — different price scale
    "cash:USA500":   {"ticker": "SPY",    "deployer": "cash", "asset_class": "etf",       "name": "S&P 500",      "gap_eligible": False},
}

# Auto-compute reverse map: traditional ticker -> list of HL symbols
HL_TICKER_TO_HL_SYMBOLS: dict[str, list[str]] = {}
for _hl_sym, _meta in HL_INSTRUMENTS.items():
    HL_TICKER_TO_HL_SYMBOLS.setdefault(_meta["ticker"], []).append(_hl_sym)

# Cross-deployer arbitrage: only compare instruments with 1:1 price mapping
# (gap_eligible=True means same price scale as traditional ticker)
_hl_gap_eligible_by_ticker: dict[str, list[str]] = {}
for _hl_sym, _meta in HL_INSTRUMENTS.items():
    if _meta.get("gap_eligible", True):
        _hl_gap_eligible_by_ticker.setdefault(_meta["ticker"], []).append(_hl_sym)

HL_CROSS_DEPLOYER_TICKERS = {
    k: v for k, v in _hl_gap_eligible_by_ticker.items() if len(v) >= 2
}

# ---------------------------------------------------------------------------
# Energy Intelligence Configuration
# ---------------------------------------------------------------------------

# Scoring sub-signal weights (must sum to 1.0)
ENERGY_SCORE_WEIGHTS = {
    "inventory":      0.30,  # EIA crude+gasoline+distillate draws vs 5yr seasonal
    "production":     0.20,  # US production trend + OPEC compliance proxy
    "demand":         0.20,  # Refinery util + product supplied (implied demand)
    "trade_flows":    0.15,  # PADD flow anomalies, import concentration risk
    "global_balance": 0.15,  # JODI supply-demand, UN Comtrade structural trends
}

# Seasonal analysis
ENERGY_SEASONAL_LOOKBACK_YEARS = 5
ENERGY_CUSHING_PREMIUM = 1.5       # Cushing draw/build weighted 1.5x vs other PADDs

# JODI blending
ENERGY_JODI_MAX_LAG_DAYS = 90      # Staleness discount beyond this
ENERGY_JODI_BLEND_WEIGHT = 0.30    # vs EIA 0.70 when both available

# Comtrade refresh
ENERGY_COMTRADE_REFRESH_DAYS = 90  # Only re-fetch quarterly data after this many days

# Ticker categories — each category gets differentiated scoring
ENERGY_INTEL_TICKERS = {
    "upstream":   ["OXY", "COP", "XOM", "CVX", "DVN", "FANG", "EOG", "PXD", "APA", "MRO"],
    "midstream":  ["ET", "WMB", "KMI", "OKE", "TRGP"],
    "downstream": ["MPC", "VLO", "PSX"],
    "ofs":        ["SLB", "HAL", "BKR"],
    "lng":        ["LNG", "TELL"],
}

# Enhanced EIA series (beyond what fetch_eia_data.py already fetches)
ENERGY_EIA_ENHANCED_SERIES = [
    # PADD district crude stocks
    ("PET.WCESTP11.W",  "PADD 1 Crude Stocks (East Coast)",  "padd"),
    ("PET.WCESTP21.W",  "PADD 2 Crude Stocks (Cushing)",     "padd"),
    ("PET.WCESTP31.W",  "PADD 3 Crude Stocks (Gulf Coast)",  "padd"),
    ("PET.WCESTP41.W",  "PADD 4 Crude Stocks (Rockies)",     "padd"),
    ("PET.WCESTP51.W",  "PADD 5 Crude Stocks (West Coast)",  "padd"),
    # Product supplied = implied demand
    ("PET.WRPUPUS2.W",  "Total Product Supplied (Mb/d)",      "demand"),
    ("PET.WGFUPUS2.W",  "Gasoline Product Supplied (Mb/d)",   "demand"),
    ("PET.WDIUPUS2.W",  "Distillate Product Supplied (Mb/d)", "demand"),
    # Spot prices for crack spread
    ("PET.RWTC.W",      "WTI Spot Price ($/bbl)",             "price"),
    ("PET.EER_EPMRU_PF4_RGC_DPG.W", "Gulf Conv Gasoline ($/gal)", "price"),
]

# JODI key countries for global balance
ENERGY_JODI_COUNTRIES = [
    "Saudi Arabia", "Russia", "United States", "China", "India",
    "Iraq", "UAE", "Brazil", "Canada", "Norway",
]

# ---------------------------------------------------------------------------
# Global Energy Markets Configuration
# ---------------------------------------------------------------------------

# Sub-signal weights for gem_score — 10 signals, must sum to 1.0
# Original 6 recalibrated (60%) + 4 new physical flow signals (40%)
GEM_SCORE_WEIGHTS = {
    # ── Original 6 (recalibrated down to make room for physical signals) ──
    "term_structure":   0.12,  # Contango/backwardation → storage/supply dynamics
    "basis_spread":     0.12,  # Brent-WTI, TTF-HH → regional tightness, LNG arb
    "crack_spread":     0.12,  # Refiner margins → downstream profitability
    "carbon":           0.07,  # EU ETS trends → utility/industrial cost pressure
    "momentum":         0.10,  # 1w/1m benchmark returns → trend following
    "cross_market":     0.07,  # Copper/energy divergence → demand validation
    # ── NEW: Physical Flow Signals ────────────────────────────────────────
    "eu_storage":       0.15,  # GIE AGSI+ daily EU fill % vs 5yr seasonal
    "cot_positioning":  0.10,  # CFTC managed money extremes (contrarian)
    "norway_flow":      0.08,  # ENTSO-G Norwegian gas nominations vs norm
    "storage_surprise": 0.07,  # EIA weekly change vs 5yr seasonal consensus
}

# How much gem_score adjusts energy_intel_score (30% blend)
GEM_BLEND_WEIGHT = 0.30

# Utility tickers affected by gas/carbon costs
GEM_UTILITY_TICKERS = [
    "VST", "CEG", "NRG", "NEE", "DUK", "SO", "AEP", "XEL", "D", "EIX",
    "PNW", "ES", "WEC", "CMS", "AES", "PPL", "FE", "ETR", "DTE", "AEE",
]

# Clean energy tickers (carbon tailwind beneficiaries)
GEM_CLEAN_ENERGY_TICKERS = [
    "ENPH", "SEDG", "ARRY", "RUN", "SHLS", "FLNC", "STEM",
    "SMR", "OKLO", "LEU", "NNE", "BWXT",
    "PLUG", "BE", "FSLR", "MAXN",
]

# EUR/USD conversion (updated periodically)
GEM_EUR_USD = 1.08

# MWh to MMBtu conversion factor
GEM_MWH_TO_MMBTU = 3.412

# Spread assessment thresholds
GEM_BRENT_WTI_NORMAL = (2.0, 8.0)    # $/bbl
GEM_TTF_HH_NORMAL = (3.0, 15.0)      # $/MMBtu
GEM_CRACK_THRESHOLDS = {              # $/bbl
    "excellent": 30,
    "strong": 20,
    "normal": 10,
    "weak": 0,
}

# ---------------------------------------------------------------------------
# Energy Physical Flows Configuration (energy_physical_flows.py)
# ---------------------------------------------------------------------------

# GIE AGSI+ EU Gas Storage (free, optional key for higher rate limits)
GIE_REFRESH_HOURS      = 20             # Refresh if data older than this
GIE_COUNTRIES_FOCUS    = ["EU", "DE", "FR", "NL", "IT", "AT", "BE", "ES", "PL", "CZ"]
GIE_CRITICAL_FILL_PCT  = 40.0           # Below = critical shortage risk
GIE_TIGHT_FILL_PCT     = 60.0           # Below = tight storage
GIE_NORMAL_FILL_PCT    = 75.0           # Below = normal; above = comfortable

# ENTSO-G Transparency Platform (free, no auth)
ENTSO_REFRESH_HOURS    = 20             # Daily refresh cadence

# CFTC Commitment of Traders (free, weekly)
COT_REFRESH_DAYS       = 7              # Weekly report cadence
COT_EXTREME_PERCENTILE = 85             # >=85th pctl = crowded long; <=15th = crowded short
COT_CONTRACTS = {
    "WTI_CRUDE":   "067651",   # NYMEX Light Sweet Crude Oil
    "BRENT":       "06765T",   # ICE Brent Crude
    "NAT_GAS_HH":  "023651",   # NYMEX Henry Hub Natural Gas
    "RBOB":        "111659",   # NYMEX RBOB Gasoline
    "HEATING_OIL": "022651",   # NYMEX No. 2 Heating Oil
}

# EIA LNG Terminal Utilization (monthly via EIA API)
LNG_REFRESH_DAYS       = 30             # Monthly data cadence
LNG_TERMINAL_CAPACITIES_BCFD = {        # Nameplate capacity in Bcf/day
    "SABINE_PASS":    5.00,
    "CORPUS_CHRISTI": 2.35,
    "FREEPORT":       2.38,
    "CAMERON":        1.70,
    "ELBA_ISLAND":    0.35,
    "COVE_POINT":     0.82,
}
LNG_HIGH_UTILIZATION_PCT = 90.0         # Above = supply-constrained; bullish HH

# EIA Storage Surprise thresholds
STORAGE_SURPRISE_BULLISH_Z = -1.0       # z < -1 = drew more than seasonal = bullish
STORAGE_SURPRISE_BEARISH_Z =  1.0       # z >  1 = built more than seasonal = bearish

# ---------------------------------------------------------------------------
# Energy Stress Test & Regime Configuration (energy_stress_test.py)
# ---------------------------------------------------------------------------

# Regime scoring weights (must sum to 1.0)
ENERGY_REGIME_WEIGHTS = {
    "seasonal":  0.20,  # Calendar demand seasonality
    "curve":     0.30,  # Futures term structure (most timely)
    "storage":   0.30,  # Physical storage status (most reliable)
    "cot":       0.20,  # Speculator positioning (contrarian)
}

# Score thresholds → regime labels
ENERGY_REGIME_THRESHOLDS = {
    "bullish":        65,
    "mildly_bullish": 55,
    "neutral":        45,
    "mildly_bearish": 35,
    # below 35 = bearish
}

# Stress test: how far back to look for existing stress scores (days)
ENERGY_STRESS_LOOKBACK_DAYS = 7

# ---------------------------------------------------------------------------
# Prediction Markets Configuration (Polymarket)
# ---------------------------------------------------------------------------
PM_MIN_VOLUME = 50_000           # Min $50K volume to filter noise markets
PM_MIN_LIQUIDITY = 10_000        # Min $10K liquidity
PM_FETCH_LIMIT = 500             # Max markets to fetch per run
PM_CLASSIFICATION_BATCH_SIZE = 8 # Markets per Gemini classification call
PM_GEMINI_DELAY = 1.5            # Rate limit between Gemini calls
PM_PROBABILITY_STRONG_THRESHOLD = 0.75  # Prob >= 75% = strong signal
PM_PROBABILITY_MODERATE_THRESHOLD = 0.60  # Prob >= 60% = moderate signal
PM_LOOKBACK_DAYS = 7             # Signal freshness for convergence

# ---------------------------------------------------------------------------
# Pattern Match & Options Intelligence Configuration
# ---------------------------------------------------------------------------

# Layer 2: Sector Relative Rotation (RRG)
ROTATION_RS_LOOKBACK = 63              # Trading days for RS-Ratio calculation
ROTATION_MOMENTUM_LOOKBACK = 10        # ROC period for RS-Momentum
ROTATION_HISTORY_DAYS = 252            # For z-scoring RS-Ratio

# Layer 3: Chart Pattern Detection
PATTERN_MIN_BARS = 20                  # Minimum bars for any pattern detection
PATTERN_SR_KDE_BANDWIDTH_ATR_MULT = 0.5  # KDE bandwidth as multiple of ATR(14)
PATTERN_SR_TOUCH_TOLERANCE = 0.005     # 0.5% tolerance for S/R touch counting
PATTERN_VOLUME_PROFILE_BINS = 50       # Price bins for volume profile
PATTERN_TRIANGLE_MIN_TOUCHES = 3       # Min touches per trendline
PATTERN_TRIANGLE_R2_MIN = 0.80         # Min R² for triangle trendline fit

# Layer 4: Statistical Pattern Detection
HURST_MIN_OBSERVATIONS = 100           # Min bars for reliable Hurst exponent
MR_ZSCORE_THRESHOLD = 2.0             # Z-score threshold for MR signal
MR_HALF_LIFE_MIN = 3                  # Min tradeable half-life (days)
MR_HALF_LIFE_MAX = 30                 # Max tradeable half-life (days)
MOMENTUM_VR_THRESHOLD = 1.1           # Variance ratio > this = momentum
COMPRESSION_HV_PERCENTILE_LOW = 25    # HV percentile below this = compressed
COMPRESSION_SQUEEZE_MIN_BARS = 5      # Min squeeze duration to trigger signal

# Layer 5: Options Intelligence
OPTIONS_FETCH_MAX_SYMBOLS = 100        # Max symbols to fetch options per run
OPTIONS_MIN_PATTERN_SCORE = 55         # Gate: pattern_scan_score >= this for options
OPTIONS_YFINANCE_DELAY = 0.5           # Seconds between yfinance calls (rate limit)
OPTIONS_MIN_OI = 10                    # Min open interest to include a strike
OPTIONS_MIN_VOLUME = 5                 # Min volume to include a strike
OPTIONS_UNUSUAL_VOL_OI_MULT = 3.0     # Volume > 3x OI = unusual activity
OPTIONS_UNUSUAL_MIN_NOTIONAL = 1_000_000  # $1M minimum for size flag
OPTIONS_SKEW_EXTREME_ZSCORE = 2.0     # Skew z-score threshold for signal
OPTIONS_TERM_STRUCTURE_STRESS = 1.5   # Short/long IV ratio > this = acute stress

# Composite Layer Weights (must sum to 1.0)
PATTERN_LAYER_WEIGHTS = {
    "regime":      0.10,   # L1: Market context
    "rotation":    0.15,   # L2: Sector RRG positioning
    "technical":   0.30,   # L3: Chart patterns + S/R + volume profile
    "statistical": 0.30,   # L4: MR + momentum + compression
    "cycles":      0.15,   # L4.5: Wyckoff + earnings + vol cycle
}

# Options Composite Weights (must sum to 1.0)
OPTIONS_COMPOSITE_WEIGHTS = {
    "iv_metrics":        0.20,
    "pc_ratios":         0.15,
    "unusual_activity":  0.25,   # Highest — informed flow is strongest signal
    "skew":              0.20,
    "dealer_exposure":   0.20,   # GEX/vanna — mechanical edge
}

# Final blend when options data is available
PATTERN_OPTIONS_BLEND = {
    "pattern_weight": 0.55,
    "options_weight":  0.45,
}

# Regime-adaptive convergence weight for pattern_options module
PATTERN_OPTIONS_REGIME_WEIGHTS = {
    "strong_risk_off": 0.02,
    "risk_off":        0.03,
    "neutral":         0.04,
    "risk_on":         0.05,
    "strong_risk_on":  0.06,
}

# Regime-adaptive convergence weights for energy_intel
ENERGY_INTEL_REGIME_WEIGHTS = {
    "strong_risk_off": 0.06,  # Supply shocks matter more
    "risk_off":        0.06,
    "neutral":         0.05,
    "risk_on":         0.05,
    "strong_risk_on":  0.04,  # Less relevant when risk appetite dominates
}

# ---------------------------------------------------------------------------
# Intelligence Report Generator
# ---------------------------------------------------------------------------
REPORT_MAX_SYMBOLS = 25
REPORT_MAX_PAIRS = 15
REPORT_EXEC_SUMMARY_TOKENS = 3072
REPORT_DEEPDIVE_TOKENS = 6144
REPORT_RISK_TOKENS = 3072
REPORT_GAPS_TOKENS = 2048

# ---------------------------------------------------------------------------
# AI Regulatory Intelligence Configuration
# ---------------------------------------------------------------------------
AI_REG_FETCH_LIMIT = 30              # Max events per source per run
AI_REG_CLASSIFICATION_BATCH_SIZE = 8 # Events per Gemini classification call
AI_REG_GEMINI_DELAY = 1.5            # Rate limit between Gemini calls (seconds)
AI_REG_LOOKBACK_DAYS = 14            # How far back to search for regulatory events

# Severity weights for scoring (severity 1-5 → weight multiplier)
AI_REG_SEVERITY_WEIGHTS = {
    1: 0.2,    # Minor guidance or comment request
    2: 0.4,    # Proposed rule or draft framework
    3: 0.7,    # Final rule or significant enforcement action
    4: 0.9,    # Major law enacted or landmark enforcement
    5: 1.0,    # Emergency action or executive order
}

# How much AI regulation exposure each sector has (0-1 scale)
# High = more regulatory surface area for AI-specific rules
AI_REG_SECTOR_EXPOSURE = {
    "Technology":               1.0,   # Maximum — AI is the product
    "Communication Services":   0.85,  # Social media, content, ad targeting
    "Financials":               0.75,  # Algorithmic trading, credit scoring, robo-advisory
    "Health Care":              0.70,  # Clinical AI, diagnostics, drug discovery
    "Consumer Discretionary":   0.50,  # Autonomous vehicles, recommendation engines
    "Industrials":              0.40,  # Autonomous systems, manufacturing AI
    "Consumer Staples":         0.15,  # Supply chain AI, minimal direct exposure
    "Energy":                   0.15,  # Grid optimization AI, minimal
    "Materials":                0.10,  # Process optimization AI, minimal
    "Real Estate":              0.10,  # PropTech AI, minimal
    "Utilities":                0.10,  # Grid AI, minimal direct exposure
}

# Regime-adaptive convergence weights for ai_regulatory
AI_REG_REGIME_WEIGHTS = {
    "strong_risk_off": 0.05,  # Regulation accelerates in crisis — govts act
    "risk_off":        0.04,  # Regulatory risk matters more in defensive posture
    "neutral":         0.03,  # Baseline
    "risk_on":         0.02,  # Less relevant when risk appetite dominates
    "strong_risk_on":  0.02,  # Minimal — regulation rarely drives in euphoria
}

# Jurisdiction weights: how much a jurisdiction's AI regulation impacts US-listed stocks
# US = 1.0 (direct), EU = 0.85 (GDPR/DSA precedent, 25-35% revenue exposure for Big Tech),
# UK = 0.6 (AISI benchmarks, fintech hub), CN = 0.75 (supply chain + export controls),
# Others scale with capital flow importance
AI_REG_JURISDICTION_WEIGHTS = {
    "US":     1.0,    # Direct — US regulations hit all US-listed stocks
    "EU":     0.85,   # EU AI Act is global compliance baseline; Big Tech gets 25-35% EU revenue
    "CN":     0.75,   # China regs drive chip export controls, supply chain restructuring
    "UK":     0.60,   # UK AISI sets safety benchmarks, FCA governs fintech
    "JP":     0.40,   # Japan light-touch approach = tailwind signal; APAC manufacturing
    "KR":     0.40,   # Samsung/SK supply chain; AI Basic Act emerging
    "SG":     0.35,   # AI Verify = voluntary; APAC financial hub
    "CA":     0.45,   # AIDA in progress; most US tech operates in Canada
    "GLOBAL": 0.50,   # G7/OECD/UN = directional signal for all jurisdictions
}

# Cross-sector theme -> expert types mapping
REPORT_THEME_MAP = {
    "ai power":            ["ai_compute", "utilities", "energy"],
    "nuclear renaissance": ["utilities", "energy"],
    "lng exports":         ["energy", "commodities"],
    "rate sensitivity":    ["financials", "realestate", "utilities"],
    "data center":         ["ai_compute", "realestate", "utilities"],
    "glp-1":               ["biotech"],
    "defense spending":    ["defense"],
    "semiconductor cycle": ["semiconductors"],
    "clean energy":        ["utilities", "energy", "commodities"],
    "crypto":              ["fintech"],
}

# ---------------------------------------------------------------------------
# Thematic Alpha Scanner — Small/Mid-Cap Trading Ideas
# ---------------------------------------------------------------------------
TS_MCAP_MIN = 300_000_000       # $300M minimum market cap
TS_MCAP_MAX = 10_000_000_000    # $10B maximum market cap
TS_TOP_N_PER_THEME = 10         # Top ideas per theme for output
TS_YFINANCE_DELAY = 1.0         # Seconds between yfinance batches
TS_SCAN_INTERVAL_DAYS = 1       # Run daily

# Composite score weights (must sum to 1.0)
TS_SCORE_WEIGHTS = {
    "policy":        0.25,   # How directly does policy/legislation benefit this stock?
    "growth":        0.25,   # Revenue/earnings growth + margin trajectory
    "technical":     0.20,   # Price momentum, trend, breakout proximity
    "valuation":     0.15,   # Cheap relative to growth? Not priced in?
    "institutional": 0.15,   # Smart money, insider buying, analyst sentiment
}

# Policy tier scoring (tier 1 = direct beneficiary, tier 3 = moderate exposure)
TS_POLICY_SCORES = {
    1: 90,   # Direct beneficiary of specific legislation/contract
    2: 65,   # Strong indirect exposure
    3: 42,   # Moderate thematic exposure
}

# ── Curated Universe by Theme ──
# Each entry: symbol, name, sub_theme, policy_tier (1-3), catalysts
# policy_tier:
#   1 = Direct beneficiary (specific contract, tax credit, mandate)
#   2 = Strong indirect (supply chain, infrastructure enabler)
#   3 = Moderate exposure (thematic tailwind, not direct)

TS_THEMES = {
    # =============================================
    # THEME 1: AI INFRASTRUCTURE
    # =============================================
    "ai_infrastructure": [
        # ── Data Center / Cooling ──
        {"symbol": "VRT",  "name": "Vertiv Holdings",        "theme": "ai_infrastructure", "sub_theme": "data_center_power",   "policy_tier": 2, "catalysts": ["AI capex cycle", "data center buildout", "power density increase"]},
        {"symbol": "AAON", "name": "AAON Inc",               "theme": "ai_infrastructure", "sub_theme": "data_center_cooling", "policy_tier": 2, "catalysts": ["data center HVAC demand", "liquid cooling adoption"]},
        {"symbol": "POWL", "name": "Powell Industries",      "theme": "ai_infrastructure", "sub_theme": "data_center_power",   "policy_tier": 2, "catalysts": ["switchgear demand", "data center electrical buildout", "grid interconnection"]},
        {"symbol": "AEIS", "name": "Advanced Energy",        "theme": "ai_infrastructure", "sub_theme": "power_solutions",     "policy_tier": 2, "catalysts": ["precision power for semis/data centers", "AI compute scaling"]},
        {"symbol": "CLS",  "name": "Celestica",              "theme": "ai_infrastructure", "sub_theme": "hardware_mfg",        "policy_tier": 2, "catalysts": ["AI server assembly", "HPC infrastructure", "networking hardware"]},
        {"symbol": "IREN", "name": "Iris Energy",            "theme": "ai_infrastructure", "sub_theme": "ai_data_center",      "policy_tier": 2, "catalysts": ["GPU-as-a-service", "AI/HPC hosting", "renewable powered"]},
        {"symbol": "APLD", "name": "Applied Digital",        "theme": "ai_infrastructure", "sub_theme": "ai_cloud",            "policy_tier": 2, "catalysts": ["AI cloud compute", "next-gen data centers", "NVIDIA partnership"]},

        # ── AI Chips / Semiconductor Equipment ──
        {"symbol": "AMBA", "name": "Ambarella",              "theme": "ai_infrastructure", "sub_theme": "ai_edge_chips",       "policy_tier": 2, "catalysts": ["edge AI inference", "autonomous vehicle vision", "CHIPS Act"]},
        {"symbol": "CAMT", "name": "Camtek",                 "theme": "ai_infrastructure", "sub_theme": "chip_inspection",     "policy_tier": 2, "catalysts": ["advanced packaging inspection", "HBM/CoWoS demand", "CHIPS Act"]},
        {"symbol": "ACLS", "name": "Axcelis Technologies",   "theme": "ai_infrastructure", "sub_theme": "chip_equipment",      "policy_tier": 1, "catalysts": ["ion implantation", "SiC power chips", "CHIPS Act funding"]},
        {"symbol": "ONTO", "name": "Onto Innovation",        "theme": "ai_infrastructure", "sub_theme": "chip_equipment",      "policy_tier": 1, "catalysts": ["process control", "advanced lithography support", "CHIPS Act"]},
        {"symbol": "COHU", "name": "Cohu Inc",               "theme": "ai_infrastructure", "sub_theme": "chip_testing",        "policy_tier": 1, "catalysts": ["chip test & handling", "automotive/AI chip testing", "CHIPS Act"]},
        {"symbol": "AEHR", "name": "Aehr Test Systems",      "theme": "ai_infrastructure", "sub_theme": "chip_testing",        "policy_tier": 1, "catalysts": ["wafer-level burn-in", "SiC/GaN testing", "CHIPS Act"]},

        # ── AI Software / Platforms ──
        {"symbol": "AI",   "name": "C3.ai",                  "theme": "ai_infrastructure", "sub_theme": "enterprise_ai",       "policy_tier": 3, "catalysts": ["enterprise AI adoption", "federal contracts", "generative AI platform"]},
        {"symbol": "SOUN", "name": "SoundHound AI",          "theme": "ai_infrastructure", "sub_theme": "conversational_ai",   "policy_tier": 3, "catalysts": ["voice AI adoption", "automotive integration", "restaurant/IoT"]},
        {"symbol": "BBAI", "name": "BigBear.ai",             "theme": "ai_infrastructure", "sub_theme": "defense_ai",          "policy_tier": 2, "catalysts": ["federal AI contracts", "DoD analytics", "autonomous systems"]},
        {"symbol": "PRST", "name": "Presto Automation",      "theme": "ai_infrastructure", "sub_theme": "ai_automation",       "policy_tier": 3, "catalysts": ["restaurant AI", "voice ordering automation"]},

        # ── Networking for AI ──
        {"symbol": "CALX", "name": "Calix",                  "theme": "ai_infrastructure", "sub_theme": "broadband_infra",     "policy_tier": 2, "catalysts": ["BEAD broadband funding", "rural connectivity", "cloud platform"]},
        {"symbol": "LITE", "name": "Lumentum Holdings",      "theme": "ai_infrastructure", "sub_theme": "optical_networking",  "policy_tier": 2, "catalysts": ["AI data center interconnect", "800G/1.6T optics", "coherent networking"]},
    ],

    # =============================================
    # THEME 2: ENERGY BUILDOUT
    # =============================================
    "energy_buildout": [
        # ── Solar ──
        {"symbol": "ENPH", "name": "Enphase Energy",         "theme": "energy_buildout", "sub_theme": "solar",              "policy_tier": 1, "catalysts": ["IRA 30% solar ITC", "residential solar mandate", "battery integration"]},
        {"symbol": "SEDG", "name": "SolarEdge Technologies", "theme": "energy_buildout", "sub_theme": "solar",              "policy_tier": 1, "catalysts": ["IRA solar ITC", "EU solar mandate", "grid-tied inverters"]},
        {"symbol": "ARRY", "name": "Array Technologies",     "theme": "energy_buildout", "sub_theme": "solar",              "policy_tier": 1, "catalysts": ["IRA utility solar PTC", "solar tracker demand", "domestic manufacturing bonus"]},
        {"symbol": "RUN",  "name": "Sunrun",                 "theme": "energy_buildout", "sub_theme": "solar",              "policy_tier": 1, "catalysts": ["IRA residential solar/storage ITC", "virtual power plants", "NEM 3.0 adaptation"]},
        {"symbol": "SHLS", "name": "Shoals Technologies",    "theme": "energy_buildout", "sub_theme": "solar",              "policy_tier": 1, "catalysts": ["IRA domestic content bonus", "solar EBOS", "utility-scale connectors"]},
        {"symbol": "MAXN", "name": "Maxeon Solar",           "theme": "energy_buildout", "sub_theme": "solar",              "policy_tier": 1, "catalysts": ["IRA manufacturing credit", "high-efficiency panels", "IBC technology"]},

        # ── Nuclear / SMR ──
        {"symbol": "SMR",  "name": "NuScale Power",          "theme": "energy_buildout", "sub_theme": "nuclear_smr",        "policy_tier": 1, "catalysts": ["NRC SMR approval", "IRA nuclear PTC", "data center baseload", "DOE funding"]},
        {"symbol": "OKLO", "name": "Oklo Inc",               "theme": "energy_buildout", "sub_theme": "nuclear_smr",        "policy_tier": 1, "catalysts": ["advanced reactor design", "DOE site access", "Sam Altman backed", "AI baseload"]},
        {"symbol": "LEU",  "name": "Centrus Energy",         "theme": "energy_buildout", "sub_theme": "nuclear_fuel",       "policy_tier": 1, "catalysts": ["HALEU fuel production", "DOE contract", "nuclear renaissance", "Russia supply risk"]},
        {"symbol": "NNE",  "name": "Nano Nuclear Energy",    "theme": "energy_buildout", "sub_theme": "micro_reactor",      "policy_tier": 1, "catalysts": ["portable micro reactor", "DoD applications", "remote power"]},
        {"symbol": "BWXT", "name": "BWX Technologies",       "theme": "energy_buildout", "sub_theme": "nuclear",            "policy_tier": 1, "catalysts": ["naval nuclear propulsion", "TRISO fuel", "micro reactor components"]},

        # ── Grid / Transmission ──
        {"symbol": "PWR",  "name": "Quanta Services",        "theme": "energy_buildout", "sub_theme": "grid_construction",  "policy_tier": 1, "catalysts": ["FERC transmission reform", "IRA grid modernization", "data center interconnection"]},
        {"symbol": "PRIM", "name": "Primoris Services",      "theme": "energy_buildout", "sub_theme": "utility_construction","policy_tier": 1, "catalysts": ["transmission buildout", "renewable interconnection", "IRA infrastructure"]},
        {"symbol": "MTZ",  "name": "MasTec",                 "theme": "energy_buildout", "sub_theme": "infrastructure",     "policy_tier": 1, "catalysts": ["clean energy construction", "transmission lines", "5G tower buildout"]},
        {"symbol": "GEV",  "name": "GE Vernova",             "theme": "energy_buildout", "sub_theme": "grid_equipment",     "policy_tier": 1, "catalysts": ["grid electrification", "gas turbines for AI baseload", "offshore wind"]},

        # ── Battery / Storage ──
        {"symbol": "FLNC", "name": "Fluence Energy",         "theme": "energy_buildout", "sub_theme": "battery_storage",    "policy_tier": 1, "catalysts": ["IRA storage ITC", "grid-scale batteries", "utility demand"]},
        {"symbol": "STEM", "name": "Stem Inc",               "theme": "energy_buildout", "sub_theme": "energy_storage",     "policy_tier": 1, "catalysts": ["IRA storage ITC", "AI-driven optimization", "virtual power plants"]},
        {"symbol": "BE",   "name": "Bloom Energy",           "theme": "energy_buildout", "sub_theme": "fuel_cells",         "policy_tier": 1, "catalysts": ["IRA clean hydrogen PTC", "solid oxide fuel cells", "data center power"]},
        {"symbol": "PLUG", "name": "Plug Power",             "theme": "energy_buildout", "sub_theme": "hydrogen",           "policy_tier": 1, "catalysts": ["IRA hydrogen PTC $3/kg", "green hydrogen hubs", "DOE funding"]},

        # ── EV Charging ──
        {"symbol": "CHPT", "name": "ChargePoint Holdings",   "theme": "energy_buildout", "sub_theme": "ev_charging",        "policy_tier": 1, "catalysts": ["NEVI EV charging program", "fleet electrification", "IRA 30C tax credit"]},
        {"symbol": "BLNK", "name": "Blink Charging",         "theme": "energy_buildout", "sub_theme": "ev_charging",        "policy_tier": 1, "catalysts": ["NEVI program", "owner-operator model", "Level 2/DC fast"]},
        {"symbol": "EVGO", "name": "EVgo Inc",               "theme": "energy_buildout", "sub_theme": "ev_charging",        "policy_tier": 1, "catalysts": ["NEVI funding", "DC fast charging network", "eXtend platform"]},

        # ── Efficiency / Smart Grid ──
        {"symbol": "AMRC", "name": "Ameresco",               "theme": "energy_buildout", "sub_theme": "energy_efficiency",  "policy_tier": 1, "catalysts": ["federal ESPC contracts", "IRA efficiency incentives", "distributed energy"]},
        {"symbol": "GNRC", "name": "Generac Holdings",       "theme": "energy_buildout", "sub_theme": "power_generation",   "policy_tier": 2, "catalysts": ["grid resilience", "home battery/solar", "grid services platform"]},
    ],

    # =============================================
    # THEME 3: FINTECH & STABLECOINS
    # =============================================
    "fintech_stablecoins": [
        # ── Digital Banking / Lending ──
        {"symbol": "SOFI", "name": "SoFi Technologies",      "theme": "fintech_stablecoins", "sub_theme": "digital_banking",   "policy_tier": 2, "catalysts": ["bank charter", "student loan refinancing", "Galileo platform"]},
        {"symbol": "UPST", "name": "Upstart Holdings",       "theme": "fintech_stablecoins", "sub_theme": "ai_lending",        "policy_tier": 2, "catalysts": ["AI underwriting", "auto lending expansion", "rate cut beneficiary"]},
        {"symbol": "AFRM", "name": "Affirm Holdings",        "theme": "fintech_stablecoins", "sub_theme": "bnpl",              "policy_tier": 2, "catalysts": ["BNPL regulation clarity", "Debit+ card", "Amazon/Shopify integration"]},
        {"symbol": "LPRO", "name": "Open Lending",            "theme": "fintech_stablecoins", "sub_theme": "lending_tech",      "policy_tier": 3, "catalysts": ["auto lending insurance", "credit union partnerships"]},
        {"symbol": "LC",   "name": "LendingClub",             "theme": "fintech_stablecoins", "sub_theme": "marketplace_lending","policy_tier": 2, "catalysts": ["bank charter monetization", "structured certificates", "rate cut tailwind"]},

        # ── Payments / Processing ──
        {"symbol": "MQ",   "name": "Marqeta",                "theme": "fintech_stablecoins", "sub_theme": "card_issuing",      "policy_tier": 2, "catalysts": ["modern card issuing", "embedded finance", "crypto card programs"]},
        {"symbol": "TOST", "name": "Toast Inc",              "theme": "fintech_stablecoins", "sub_theme": "restaurant_fintech","policy_tier": 3, "catalysts": ["restaurant digitization", "fintech add-ons", "POS expansion"]},
        {"symbol": "RELY", "name": "Remitly Global",         "theme": "fintech_stablecoins", "sub_theme": "remittances",       "policy_tier": 2, "catalysts": ["digital remittance growth", "stablecoin settlement potential"]},
        {"symbol": "DLO",  "name": "DLocal",                 "theme": "fintech_stablecoins", "sub_theme": "em_payments",       "policy_tier": 2, "catalysts": ["emerging market digital payments", "cross-border settlement"]},
        {"symbol": "PAYO", "name": "Payoneer Global",        "theme": "fintech_stablecoins", "sub_theme": "cross_border",      "policy_tier": 2, "catalysts": ["cross-border B2B payments", "emerging market expansion", "working capital"]},
        {"symbol": "PSFE", "name": "Paysafe",                "theme": "fintech_stablecoins", "sub_theme": "payments",          "policy_tier": 2, "catalysts": ["iGaming payments", "digital wallet", "crypto on/off ramp"]},

        # ── Crypto Infrastructure ──
        {"symbol": "COIN", "name": "Coinbase Global",        "theme": "fintech_stablecoins", "sub_theme": "crypto_exchange",   "policy_tier": 1, "catalysts": ["stablecoin legislation", "ETF custody", "Base L2 chain", "USDC issuer (Circle partnership)"]},
        {"symbol": "HOOD", "name": "Robinhood Markets",      "theme": "fintech_stablecoins", "sub_theme": "retail_trading",    "policy_tier": 2, "catalysts": ["crypto trading expansion", "retirement accounts", "prediction markets"]},
        {"symbol": "MARA", "name": "Marathon Digital",        "theme": "fintech_stablecoins", "sub_theme": "crypto_mining",     "policy_tier": 2, "catalysts": ["BTC halving cycle", "mining efficiency", "energy arbitrage"]},
        {"symbol": "RIOT", "name": "Riot Platforms",          "theme": "fintech_stablecoins", "sub_theme": "crypto_mining",     "policy_tier": 2, "catalysts": ["BTC mining scale", "Corsicana facility", "power curtailment revenue"]},
        {"symbol": "CIFR", "name": "Cipher Mining",          "theme": "fintech_stablecoins", "sub_theme": "crypto_mining",     "policy_tier": 2, "catalysts": ["low-cost mining", "HPC/AI pivot potential", "Texas power"]},
        {"symbol": "CLSK", "name": "CleanSpark",             "theme": "fintech_stablecoins", "sub_theme": "crypto_mining",     "policy_tier": 2, "catalysts": ["efficient BTC mining", "infrastructure expansion"]},

        # ── Capital Markets Tech ──
        {"symbol": "DKNG", "name": "DraftKings",             "theme": "fintech_stablecoins", "sub_theme": "igaming",           "policy_tier": 2, "catalysts": ["sports betting legalization", "iGaming expansion", "prediction markets regulation"]},
        {"symbol": "FLUT", "name": "Flutter Entertainment",  "theme": "fintech_stablecoins", "sub_theme": "igaming",           "policy_tier": 2, "catalysts": ["FanDuel scale", "state-by-state legalization", "US listing"]},
    ],

    # =============================================
    # THEME 4: DEFENSE TECH
    # =============================================
    "defense_tech": [
        # ── Drones / Autonomous ──
        {"symbol": "AVAV", "name": "AeroVironment",          "theme": "defense_tech", "sub_theme": "drones",             "policy_tier": 1, "catalysts": ["Switchblade/Puma demand", "Ukraine lessons", "DoD drone autonomy program"]},
        {"symbol": "KTOS", "name": "Kratos Defense",         "theme": "defense_tech", "sub_theme": "autonomous_systems", "policy_tier": 1, "catalysts": ["UTAP-22 drone wingman", "CCA program", "hypersonic targets"]},
        {"symbol": "RCAT", "name": "Red Cat Holdings",       "theme": "defense_tech", "sub_theme": "small_drones",       "policy_tier": 1, "catalysts": ["SRR program", "DJI ban beneficiary", "Teal drones"]},
        {"symbol": "JOBY", "name": "Joby Aviation",          "theme": "defense_tech", "sub_theme": "evtol",              "policy_tier": 2, "catalysts": ["FAA eVTOL certification", "DoD contract", "air taxi market"]},
        {"symbol": "ACHR", "name": "Archer Aviation",        "theme": "defense_tech", "sub_theme": "evtol",              "policy_tier": 2, "catalysts": ["FAA certification", "United Airlines partnership", "defense applications"]},

        # ── Space ──
        {"symbol": "RKLB", "name": "Rocket Lab USA",         "theme": "defense_tech", "sub_theme": "space_launch",       "policy_tier": 1, "catalysts": ["Neutron rocket", "NRO/DoD launches", "space systems vertical integration"]},
        {"symbol": "PL",   "name": "Planet Labs",            "theme": "defense_tech", "sub_theme": "satellite_imagery",  "policy_tier": 1, "catalysts": ["defense/intel imagery contracts", "daily Earth scanning", "NGA contract"]},
        {"symbol": "ASTS", "name": "AST SpaceMobile",        "theme": "defense_tech", "sub_theme": "satellite_comms",    "policy_tier": 2, "catalysts": ["direct-to-cell satellite", "AT&T/Verizon partnerships", "DoD spectrum"]},
        {"symbol": "LUNR", "name": "Intuitive Machines",     "theme": "defense_tech", "sub_theme": "lunar",              "policy_tier": 1, "catalysts": ["NASA CLPS contracts", "lunar landing services", "Artemis program"]},
        {"symbol": "IRDM", "name": "Iridium Communications", "theme": "defense_tech", "sub_theme": "satellite_comms",    "policy_tier": 2, "catalysts": ["DoD SATCOM", "IoT connectivity", "GPS backup"]},

        # ── Cybersecurity ──
        {"symbol": "S",    "name": "SentinelOne",            "theme": "defense_tech", "sub_theme": "cybersecurity",      "policy_tier": 2, "catalysts": ["AI-native security", "FedRAMP authorization", "CISA directives"]},
        {"symbol": "RPD",  "name": "Rapid7",                 "theme": "defense_tech", "sub_theme": "cybersecurity",      "policy_tier": 2, "catalysts": ["threat detection", "federal cybersecurity mandates", "SEC disclosure rules"]},
        {"symbol": "TENB", "name": "Tenable Holdings",       "theme": "defense_tech", "sub_theme": "cybersecurity",      "policy_tier": 2, "catalysts": ["exposure management", "federal contracts", "BOD compliance"]},
        {"symbol": "VRNS", "name": "Varonis Systems",        "theme": "defense_tech", "sub_theme": "data_security",      "policy_tier": 2, "catalysts": ["data governance mandates", "AI data security", "cloud DSPM"]},

        # ── Defense Electronics / Primes ──
        {"symbol": "MRCY", "name": "Mercury Systems",        "theme": "defense_tech", "sub_theme": "defense_electronics","policy_tier": 1, "catalysts": ["radar/EW processing", "JADC2 modernization", "defense budget growth"]},
        {"symbol": "AXON", "name": "Axon Enterprise",         "theme": "defense_tech", "sub_theme": "law_enforcement_tech","policy_tier": 2, "catalysts": ["AI-powered policing", "body cameras", "drone-as-first-responder"]},
        {"symbol": "CACI", "name": "CACI International",     "theme": "defense_tech", "sub_theme": "defense_it",         "policy_tier": 1, "catalysts": ["DoD IT modernization", "signals intelligence", "cyber operations"]},
    ],

    # =============================================
    # THEME 5: RESHORING & CHIPS ACT
    # =============================================
    "reshoring_chips": [
        # ── Semiconductor Fabs ──
        {"symbol": "GFS",  "name": "GlobalFoundries",        "theme": "reshoring_chips", "sub_theme": "foundry",            "policy_tier": 1, "catalysts": ["CHIPS Act $1.5B grant", "Malta NY fab", "automotive chips", "defense supply chain"]},
        {"symbol": "WOLF", "name": "Wolfspeed",              "theme": "reshoring_chips", "sub_theme": "sic_chips",           "policy_tier": 1, "catalysts": ["CHIPS Act funding", "SiC fab Siler City NC", "EV power semis", "200mm SiC wafers"]},
        {"symbol": "NVTS", "name": "Navitas Semiconductor",  "theme": "reshoring_chips", "sub_theme": "gan_chips",           "policy_tier": 1, "catalysts": ["GaN power ICs", "data center power efficiency", "EV onboard chargers", "CHIPS Act"]},
        {"symbol": "MKSI", "name": "MKS Instruments",        "theme": "reshoring_chips", "sub_theme": "process_equipment",  "policy_tier": 2, "catalysts": ["laser/vacuum for fabs", "advanced packaging tools", "CHIPS Act capex"]},
        {"symbol": "FORM", "name": "FormFactor",             "theme": "reshoring_chips", "sub_theme": "probe_cards",         "policy_tier": 2, "catalysts": ["wafer probe technology", "HBM testing", "advanced node ramp"]},
        {"symbol": "UCTT", "name": "Ultra Clean Holdings",   "theme": "reshoring_chips", "sub_theme": "fab_services",        "policy_tier": 1, "catalysts": ["critical parts/gas delivery for fabs", "CHIPS Act greenfield builds"]},

        # ── Industrial Automation ──
        {"symbol": "AZTA", "name": "Azenta (fka Brooks)",     "theme": "reshoring_chips", "sub_theme": "automation",          "policy_tier": 2, "catalysts": ["semiconductor automation", "life sciences automation", "reshoring labor gap"]},
        {"symbol": "TER",  "name": "Teradyne",               "theme": "reshoring_chips", "sub_theme": "test_automation",     "policy_tier": 2, "catalysts": ["ATE for chip testing", "collaborative robots", "reshoring manufacturing"]},
        {"symbol": "NOVT", "name": "Novanta",                "theme": "reshoring_chips", "sub_theme": "precision_motion",    "policy_tier": 2, "catalysts": ["precision motion for semis", "medical robotics", "US manufacturing"]},

        # ── Supply Chain / Logistics ──
        {"symbol": "GXO",  "name": "GXO Logistics",          "theme": "reshoring_chips", "sub_theme": "logistics",           "policy_tier": 3, "catalysts": ["reshoring logistics demand", "warehouse automation", "nearshoring"]},
        {"symbol": "KNX",  "name": "Knight-Swift Transport", "theme": "reshoring_chips", "sub_theme": "trucking",            "policy_tier": 3, "catalysts": ["domestic freight volume", "reshoring shipping", "capacity tightening"]},

        # ── Critical Minerals / Materials ──
        {"symbol": "MP",   "name": "MP Materials",           "theme": "reshoring_chips", "sub_theme": "rare_earths",         "policy_tier": 1, "catalysts": ["DoD rare earth supply chain", "China derisking", "EV magnet materials", "IRA critical minerals"]},
        {"symbol": "LAC",  "name": "Lithium Americas",       "theme": "reshoring_chips", "sub_theme": "lithium",             "policy_tier": 1, "catalysts": ["Thacker Pass mine", "DOE loan guarantee", "IRA critical minerals 30D credit"]},
        {"symbol": "ALB",  "name": "Albemarle Corp",         "theme": "reshoring_chips", "sub_theme": "lithium",             "policy_tier": 1, "catalysts": ["US lithium production", "IRA 45X manufacturing credit", "EV battery supply"]},
        {"symbol": "SQM",  "name": "Sociedad Quimica Minera", "theme": "reshoring_chips", "sub_theme": "lithium",             "policy_tier": 2, "catalysts": ["lithium brine production", "Chile supply", "EV battery supply chain"]},
        {"symbol": "UUUU", "name": "Energy Fuels",           "theme": "reshoring_chips", "sub_theme": "uranium_ree",         "policy_tier": 1, "catalysts": ["uranium mining", "rare earth processing", "Russia uranium ban"]},
        {"symbol": "CCJ",  "name": "Cameco Corp",            "theme": "reshoring_chips", "sub_theme": "uranium",             "policy_tier": 1, "catalysts": ["uranium supply constraints", "nuclear renaissance", "Russia supply risk"]},

        # ── Steel / Infrastructure Materials ──
        {"symbol": "STLD", "name": "Steel Dynamics",         "theme": "reshoring_chips", "sub_theme": "steel",               "policy_tier": 2, "catalysts": ["EAF steel for reshoring", "IIJA infrastructure", "data center construction"]},
        {"symbol": "CMC",  "name": "Commercial Metals",      "theme": "reshoring_chips", "sub_theme": "steel",               "policy_tier": 2, "catalysts": ["rebar for construction", "reshoring construction boom", "fab buildout steel"]},
    ],
}
