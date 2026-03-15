"""Module-specific configuration — convergence weights, regime profiles, per-module settings."""
from datetime import datetime
CONVERGENCE_WEIGHTS = {
    "smartmoney": 0.10, "worldview": 0.10, "variant": 0.07, "foreign_intel": 0.05,
    "research": 0.05, "main_signal": 0.02, "reddit": 0.01, "news_displacement": 0.05,
    "alt_data": 0.03, "sector_expert": 0.04, "pairs": 0.04, "ma": 0.03,
    "energy_intel": 0.04, "prediction_markets": 0.04, "pattern_options": 0.03,
    "estimate_momentum": 0.03, "ai_regulatory": 0.02, "consensus_blindspots": 0.03,
    "earnings_nlp": 0.05, "gov_intel": 0.04, "labor_intel": 0.04,
    "supply_chain": 0.03, "digital_exhaust": 0.03, "pharma_intel": 0.03,
}
CONVICTION_HIGH, CONVICTION_NOTABLE, CONVICTION_WATCH = 3, 2, 1
FOREIGN_INTEL_MAX_ARTICLES_PER_SOURCE = 5
FOREIGN_INTEL_MAX_CHARS_TRANSLATE, FOREIGN_INTEL_FULL_TEXT_THRESHOLD = 2000, 80
FOREIGN_INTEL_FULL_TEXT_MAX_CHARS, FOREIGN_INTEL_LOOKBACK_DAYS = 10000, 14
SENTIMENT_CALIBRATION = {"ja": 1.4, "ko": 1.0, "zh": {"positive": 0.7, "negative": 1.3}, "de": 1.2, "fr": 0.85, "it": 0.85}
FOREIGN_INTEL_SOURCES = {
    "japan": [("Nikkei", "nikkei.com", "株 決算 業績"), ("Kabutan", "kabutan.jp", "決算 業績 株価"), ("Toyo Keizai", "toyokeizai.net", "半導体 AI テクノロジー 企業"), ("Bloomberg JP", "bloomberg.co.jp", "市場 株式 企業")],
    "korea": [("Maeil Business", "mk.co.kr", "삼성 반도체 실적 주식"), ("ETNews", "etnews.com", "반도체 AI 디스플레이"), ("Chosun Biz", "biz.chosun.com", "주식 실적 기업")],
    "china": [("Caixin", "caixin.com", "科技 金融 企业 财报"), ("36Kr", "36kr.com", "AI 芯片 科技 创业"), ("Sina Finance", "finance.sina.com.cn", "股市 行情 公司")],
    "europe_de": [("Handelsblatt", "handelsblatt.com", "Aktie Industrie Unternehmen Rüstung"), ("Boerse.de", "boerse.de", "DAX Aktie Analyse")],
    "europe_fr": [("Les Echos", "lesechos.fr", "LVMH Airbus action entreprise bourse"), ("BFM Business", "bfmbusiness.bfmtv.com", "bourse marché entreprise")],
    "europe_it": [("Il Sole 24 Ore", "ilsole24ore.com", "borsa mercati azienda")],
}
MARKET_LANGUAGE = {"japan": "ja", "korea": "ko", "china": "zh", "europe_de": "de", "europe_fr": "fr", "europe_it": "it"}
MARKET_SERPER_PARAMS = {
    "japan": {"gl": "jp", "hl": "ja"}, "korea": {"gl": "kr", "hl": "ko"}, "china": {"gl": "cn", "hl": "zh-cn"},
    "europe_de": {"gl": "de", "hl": "de"}, "europe_fr": {"gl": "fr", "hl": "fr"}, "europe_it": {"gl": "it", "hl": "it"},
}
_YEAR = datetime.now().year
_YR = f"{_YEAR - 1} {_YEAR}"
_SEMI = ["NVDA", "AMD", "TSM", "ASML", "AMAT", "LRCX", "KLAC", "MU"]
_AI = ["NVDA", "AMD", "GOOGL", "MSFT", "META", "AMZN", "TSM", "ASML"]
_CLOUD = ["NVDA", "MSFT", "GOOGL", "AMZN", "META", "ORCL"]
RESEARCH_SOURCES = [
    {"name": "epoch_ai", "serper_query": f"site:epochai.org AI compute training scaling {_YR}", "relevance_tickers": _AI, "themes": ["ai_capex", "compute_scaling", "training_runs"]},
    {"name": "semianalysis", "serper_query": f"site:semianalysis.com semiconductor GPU HBM AI chip {_YR}", "relevance_tickers": _SEMI, "themes": ["semiconductors", "fab_capacity", "chip_shortage"]},
    {"name": "federal_reserve", "serper_query": f"site:federalreserve.gov monetary policy financial stability report {_YR}", "relevance_tickers": [], "themes": ["monetary_policy", "rate_hike", "rate_cut", "quantitative_tightening", "liquidity"]},
    {"name": "bls", "serper_query": f"site:bls.gov CPI PPI employment situation {_YR}", "relevance_tickers": [], "themes": ["inflation", "cpi", "ppi", "labor_market", "employment"]},
    {"name": "financial_times", "serper_query": f"site:ft.com markets economy central bank policy {_YR}", "relevance_tickers": [], "themes": ["monetary_policy", "geopolitics", "inflation", "liquidity", "central_banks"]},
    {"name": "wsj_markets", "serper_query": f"site:wsj.com markets economy earnings corporate {_YR}", "relevance_tickers": [], "themes": ["monetary_policy", "inflation", "labor_market", "employment", "m_and_a"]},
    {"name": "reuters", "serper_query": f"site:reuters.com markets commodities economy breaking {_YR}", "relevance_tickers": [], "themes": ["geopolitics", "trade_war", "tariffs", "energy", "oil", "commodities_physical"]},
    {"name": "bloomberg", "serper_query": f"site:bloomberg.com markets deals earnings economy {_YR}", "relevance_tickers": [], "themes": ["monetary_policy", "liquidity", "geopolitics", "inflation", "m_and_a"]},
    {"name": "politico", "serper_query": f"site:politico.com regulation trade policy fiscal spending {_YR}", "relevance_tickers": [], "themes": ["regulation", "fiscal_policy", "trade_policy", "tariffs", "geopolitics"]},
    {"name": "the_information", "serper_query": f"site:theinformation.com AI tech startup funding {_YR}", "relevance_tickers": _CLOUD, "themes": ["ai_capex", "cloud_computing", "data_centers", "compute_scaling"]},
    {"name": "energy_intelligence", "serper_query": f"site:energyintel.com OR site:spglobal.com/commodityinsights oil gas OPEC LNG power {_YR}", "relevance_tickers": ["OXY", "COP", "XOM", "CVX", "LNG", "VST", "CEG"], "themes": ["energy", "oil", "natural_gas", "power_demand"]},
    {"name": "morgan_stanley", "serper_query": f"site:morganstanley.com research insights markets outlook {_YR}", "relevance_tickers": _AI[:7], "themes": ["ai_capex", "semiconductors", "monetary_policy", "geopolitics", "m_and_a"]},
    {"name": "goldman_sachs", "serper_query": f"site:goldmansachs.com/insights markets economy outlook strategy {_YR}", "relevance_tickers": ["NVDA", "MSFT", "GOOGL", "AMZN", "META", "AAPL", "JPM"], "themes": ["monetary_policy", "inflation", "liquidity", "geopolitics", "ai_capex"]},
    {"name": "jpmorgan", "serper_query": f"site:jpmorgan.com/insights research markets economy outlook {_YR}", "relevance_tickers": ["NVDA", "MSFT", "GOOGL", "AMZN", "XOM", "JPM"], "themes": ["monetary_policy", "inflation", "credit_markets", "energy", "ai_capex"]},
    {"name": "bofa_research", "serper_query": f"site:business.bofa.com market strategy outlook research {_YR}", "relevance_tickers": [], "themes": ["monetary_policy", "inflation", "liquidity", "credit_markets", "commodities_physical"]},
    {"name": "mckinsey", "serper_query": f"site:mckinsey.com/industries technology energy semiconductors AI financial-services {_YR}", "relevance_tickers": _AI, "themes": ["ai_capex", "compute_scaling", "energy", "semiconductors", "cloud_computing"]},
    {"name": "bcg", "serper_query": f"site:bcg.com/publications technology energy AI semiconductors financial-services {_YR}", "relevance_tickers": _AI[:6], "themes": ["ai_capex", "compute_scaling", "energy", "semiconductors", "cloud_computing"]},
    {"name": "bain", "serper_query": f"site:bain.com/insights technology energy private-equity AI {_YR}", "relevance_tickers": ["NVDA", "MSFT", "GOOGL", "AMZN", "KKR", "BX", "APO"], "themes": ["ai_capex", "m_and_a", "energy", "cloud_computing", "data_centers"]},
]
RESEARCH_MIN_SCRAPE_CHARS, RESEARCH_SNIPPET_FALLBACK = 200, True
PAIRS_MIN_CORRELATION, PAIRS_COINT_PVALUE = 0.60, 0.05
PAIRS_HALF_LIFE_MIN, PAIRS_HALF_LIFE_MAX = 3, 60
PAIRS_ZSCORE_MR_THRESHOLD, PAIRS_ZSCORE_RUNNER_THRESHOLD = 2.0, 1.5
PAIRS_RUNNER_MIN_TECH, PAIRS_RUNNER_MIN_FUND = 60, 40
PAIRS_LOOKBACK_DAYS, PAIRS_REFRESH_DAYS, PAIRS_MIN_PRICE_DAYS = 252, 7, 120
MA_RUMOR_LOOKBACK_DAYS, MA_RUMOR_HALF_LIFE_DAYS, MA_NEWS_BATCH_SIZE = 7, 5, 10
MA_FINNHUB_DELAY, MA_GEMINI_DELAY = 0.15, 1.5
MA_MIN_MARKET_CAP, MA_MAX_MARKET_CAP = 500_000_000, 200_000_000_000
MA_TARGET_WEIGHT_PROFILE, MA_TARGET_WEIGHT_RUMOR, MA_MIN_SCORE_STORE = 0.40, 0.40, 15
ENSO_MODERATE_THRESHOLD, ENSO_STRONG_THRESHOLD = 0.5, 1.5
ENSO_MODERATE_STRENGTH, ENSO_STRONG_STRENGTH = 55, 80
NDVI_ZSCORE_THRESHOLD, NDVI_STRESS_BASE_STRENGTH, NDVI_QUERY_DELAY = 1.5, 60, 1.0
EM_REVISION_VELOCITY_WEIGHT, EM_REVENUE_VELOCITY_WEIGHT = 0.30, 0.10
EM_ACCELERATION_WEIGHT, EM_SURPRISE_MOMENTUM_WEIGHT = 0.15, 0.25
EM_DISPERSION_WEIGHT, EM_CROSS_SECTIONAL_WEIGHT = 0.10, 0.10
EM_STRONG_REVISION_PCT, EM_MODERATE_REVISION_PCT = 5.0, 1.0
EM_SURPRISE_STREAK_BONUS, EM_DISPERSION_TIGHTENING_BONUS = 15, 10
TA_GATE_SKIP, TA_GATE_FULL = 20, 35
TA_GATE_OVERRIDE_WATCHLIST, TA_GATE_OVERRIDE_EXISTING_SIGNALS = True, True
TA_GATE_NEW_IPO_DAYS = 50
# ── Regime-Adaptive Convergence Weights ──
def _build_regime_weights():
    """Build regime weight profiles from neutral base + deltas per regime."""
    base = dict(CONVERGENCE_WEIGHTS)
    _deltas = [
        ("smartmoney", -0.02, -0.01, 0.01, 0.00), ("worldview", -0.04, -0.03, 0.00, 0.02),
        ("variant", 0.03, 0.01, -0.01, -0.03), ("foreign_intel", 0.01, 0.01, -0.01, -0.02),
        ("research", -0.01, 0.00, -0.01, -0.01), ("main_signal", -0.01, 0.00, 0.03, 0.05),
        ("reddit", -0.01, -0.01, 0.01, 0.02), ("news_displacement", 0.01, 0.01, -0.01, -0.02),
        ("alt_data", 0.00, 0.00, -0.01, -0.01), ("sector_expert", 0.00, 0.00, 0.00, 0.00),
        ("pairs", -0.02, -0.01, 0.02, 0.03), ("ma", -0.01, 0.00, 0.01, 0.02),
        ("energy_intel", 0.01, 0.01, 0.00, -0.01), ("prediction_markets", 0.01, 0.01, -0.01, -0.01),
        ("pattern_options", -0.01, -0.01, 0.01, 0.02), ("estimate_momentum", -0.01, 0.00, 0.00, 0.00),
        ("ai_regulatory", 0.02, 0.01, 0.00, 0.00), ("consensus_blindspots", 0.03, 0.02, -0.01, -0.01),
        ("earnings_nlp", 0.01, 0.00, 0.00, -0.01), ("gov_intel", 0.01, 0.00, -0.01, -0.01),
        ("labor_intel", 0.01, 0.00, -0.01, -0.01), ("supply_chain", 0.00, 0.00, 0.00, -0.01),
        ("digital_exhaust", -0.01, -0.01, 0.01, 0.01), ("pharma_intel", 0.00, 0.00, -0.01, -0.01),
    ]
    regimes = {}
    for ri, regime in enumerate(["strong_risk_off", "risk_off", "risk_on", "strong_risk_on"]):
        w = dict(base)
        for mod, *ds in _deltas:
            w[mod] = max(0.0, round(w[mod] + ds[ri], 2))
        total = sum(w.values())
        if abs(total - 1.0) > 0.001:
            scale = 1.0 / total
            w = {k: round(v * scale, 3) for k, v in w.items()}
        regimes[regime] = w
    regimes["neutral"] = dict(base)
    return regimes
REGIME_CONVERGENCE_WEIGHTS = _build_regime_weights()
# ── Devil's Advocate ──
DA_MAX_SIGNALS, DA_WARNING_THRESHOLD, DA_GEMINI_TEMPERATURE = 10, 75, 0.7
# ── Adaptive Weight Optimizer ──
WO_MIN_WEIGHT, WO_MAX_WEIGHT = 0.01, 0.25
WO_MIN_OBSERVATIONS, WO_MAX_DELTA_PER_CYCLE, WO_LEARNING_RATE = 60, 0.02, 0.10
WO_MIN_TOTAL_SIGNALS, WO_MIN_DAYS_RUNNING = 100, 30
WO_ENABLE_ADAPTIVE, WO_HOLDOUT_MODULES = True, ["reddit"]
# ── Insider Trading ──
INSIDER_CLUSTER_WINDOW_DAYS, INSIDER_CLUSTER_MIN_COUNT = 14, 3
INSIDER_LARGE_BUY_THRESHOLD, INSIDER_UNUSUAL_VOLUME_MULT = 200_000, 3.0
INSIDER_BOOST_HIGH, INSIDER_BOOST_MED, INSIDER_SELL_PENALTY = 15, 8, -10
INSIDER_FMP_BATCH_SIZE, INSIDER_LOOKBACK_DAYS = 30, 90
# ── AI Executive Investment Tracker ──
AI_EXEC_SERPER_QUERIES_PER_EXEC, AI_EXEC_MAX_URLS_PER_EXEC = 2, 3
AI_EXEC_FIRECRAWL_DELAY, AI_EXEC_GEMINI_DELAY, AI_EXEC_MIN_CONFIDENCE = 2.0, 1.5, 3
AI_EXEC_MIN_SCORE_STORE, AI_EXEC_SM_BOOST_HIGH, AI_EXEC_SM_BOOST_MED = 20, 12, 6
AI_EXEC_CONVERGENCE_BONUS, AI_EXEC_LOOKBACK_DAYS, AI_EXEC_SCAN_INTERVAL_DAYS = 10, 180, 7
def _exec(name, role, org, prominence, aliases, vehicles=None):
    d = {"name": name, "role": role, "org": org, "prominence": prominence, "search_aliases": aliases}
    if vehicles: d["known_vehicles"] = vehicles
    return d
AI_EXEC_WATCHLIST = [
    _exec("Sam Altman", "CEO", "OpenAI", 95, ["Sam Altman investment", "Sam Altman board", "Sam Altman angel"], ["Hydrazine Capital"]),
    _exec("Greg Brockman", "President", "OpenAI", 75, ["Greg Brockman investment", "Greg Brockman board"]),
    _exec("Dario Amodei", "CEO", "Anthropic", 85, ["Dario Amodei investment", "Dario Amodei board"]),
    _exec("Daniela Amodei", "President", "Anthropic", 75, ["Daniela Amodei investment", "Daniela Amodei board"]),
    _exec("Demis Hassabis", "CEO DeepMind", "Google DeepMind", 90, ["Demis Hassabis investment", "Demis Hassabis board"]),
    _exec("Jeff Dean", "Chief Scientist", "Google AI", 80, ["Jeff Dean Google investment", "Jeff Dean board"]),
    _exec("Yann LeCun", "Chief AI Scientist", "Meta", 85, ["Yann LeCun investment", "Yann LeCun board"]),
    _exec("Jensen Huang", "CEO", "NVIDIA", 98, ["Jensen Huang personal investment", "Jensen Huang board"]),
    _exec("Satya Nadella", "CEO", "Microsoft", 95, ["Satya Nadella personal investment", "Satya Nadella board"]),
    _exec("Mustafa Suleyman", "CEO Microsoft AI", "Microsoft", 80, ["Mustafa Suleyman investment", "Mustafa Suleyman board"]),
    _exec("Kevin Scott", "CTO", "Microsoft", 70, ["Kevin Scott Microsoft investment"]),
    _exec("Elon Musk", "CEO", "xAI/Tesla", 99, ["Elon Musk AI investment", "Elon Musk startup investment"]),
    _exec("Lisa Su", "CEO", "AMD", 85, ["Lisa Su personal investment", "Lisa Su board"]),
    _exec("Ilya Sutskever", "Co-founder", "Safe Superintelligence", 85, ["Ilya Sutskever investment", "Ilya Sutskever startup"]),
    _exec("Andrej Karpathy", "Founder", "Eureka Labs", 80, ["Andrej Karpathy investment", "Andrej Karpathy startup"]),
    _exec("Fei-Fei Li", "Co-founder", "World Labs", 75, ["Fei-Fei Li investment", "Fei-Fei Li World Labs"]),
    _exec("Alexandr Wang", "CEO", "Scale AI", 70, ["Alexandr Wang investment", "Alexandr Wang Scale AI"]),
    _exec("Arthur Mensch", "CEO", "Mistral AI", 70, ["Arthur Mensch investment", "Arthur Mensch Mistral"]),
    _exec("Vinod Khosla", "Founder", "Khosla Ventures", 85, ["Vinod Khosla AI investment", "Khosla Ventures AI"]),
    _exec("Elad Gil", "Angel Investor", "Independent", 75, ["Elad Gil investment", "Elad Gil AI startup"]),
    _exec("Sarah Guo", "Founder", "Conviction Capital", 70, ["Sarah Guo Conviction investment", "Conviction Capital AI"]),
    _exec("Nat Friedman", "Angel Investor", "Independent", 75, ["Nat Friedman investment", "Nat Friedman AI startup"]),
    _exec("Daniel Gross", "Angel Investor", "Independent", 70, ["Daniel Gross AI investment", "Daniel Gross startup"]),
]
REGIME_MARKET_PRIORITY = {
    "strong_risk_on": ["japan", "korea", "china", "europe_de", "europe_fr", "europe_it"],
    "risk_on": ["japan", "europe_de", "korea", "china", "europe_fr", "europe_it"],
    "neutral": ["japan", "europe_de", "europe_fr", "korea", "china", "europe_it"],
    "risk_off": ["europe_de", "europe_fr", "japan", "europe_it", "korea", "china"],
    "strong_risk_off": ["europe_de", "europe_fr", "europe_it", "japan"],
}
# ── Hyperliquid Weekend Gap Arbitrage ──
HL_API_BASE = "https://api.hyperliquid.xyz"
HL_SNAPSHOT_INTERVAL_HOURS, HL_OPTIMAL_SIGNAL_TIME = 1, "20:00"
HL_CROSS_DEPLOYER_SPREAD_THRESHOLD_BPS, HL_BOOK_THIN_WARNING_PCT = 50, 50
HL_GAP_ALERT_THRESHOLD_PCT, HL_DEPLOYER_ALERT_THRESHOLD_BPS = 1.0, 100
HL_DEPLOYERS = ["xyz", "flx", "km", "vntl", "cash"]
def _hl(ticker, deployer, asset_class, name, gap=True):
    return {"ticker": ticker, "deployer": deployer, "asset_class": asset_class, "name": name, "gap_eligible": gap}
_HL_DEFS = [
    ("xyz", "GOLD", "GC=F", "commodity", "Gold", True), ("xyz", "SILVER", "SI=F", "commodity", "Silver", True),
    ("xyz", "CL", "CL=F", "commodity", "WTI Crude", True), ("xyz", "BRENTOIL", "BZ=F", "commodity", "Brent Crude", True),
    ("xyz", "NATGAS", "NG=F", "commodity", "Natural Gas", True), ("xyz", "COPPER", "HG=F", "commodity", "Copper", True),
    ("xyz", "PLATINUM", "PL=F", "commodity", "Platinum", True), ("xyz", "XYZ100", "NQ=F", "index", "Nasdaq 100", True),
    ("xyz", "TSLA", "TSLA", "stock", "Tesla", True), ("xyz", "NVDA", "NVDA", "stock", "NVIDIA", True),
    ("xyz", "AMD", "AMD", "stock", "AMD", True), ("xyz", "AAPL", "AAPL", "stock", "Apple", True),
    ("xyz", "AMZN", "AMZN", "stock", "Amazon", True), ("xyz", "GOOGL", "GOOGL", "stock", "Alphabet", True),
    ("xyz", "META", "META", "stock", "Meta", True), ("xyz", "MSFT", "MSFT", "stock", "Microsoft", True),
    ("xyz", "DXY", "DX-Y.NYB", "fx", "Dollar Index", True),
    ("flx", "GOLD", "GC=F", "commodity", "Gold", True), ("flx", "SILVER", "SI=F", "commodity", "Silver", True),
    ("flx", "CL", "CL=F", "commodity", "WTI Crude", True), ("flx", "NATGAS", "NG=F", "commodity", "Natural Gas", True),
    ("flx", "COPPER", "HG=F", "commodity", "Copper", True), ("flx", "OIL", "CL=F", "commodity", "WTI Crude", True),
    ("flx", "PLATINUM", "PL=F", "commodity", "Platinum", True),
    ("flx", "SPX", "ES=F", "index", "S&P 500", True), ("flx", "NDX", "NQ=F", "index", "Nasdaq 100", True),
    ("flx", "TSLA", "TSLA", "stock", "Tesla", True), ("flx", "NVDA", "NVDA", "stock", "NVIDIA", True),
    ("flx", "AAPL", "AAPL", "stock", "Apple", True),
    ("km", "TSLA", "TSLA", "stock", "Tesla", True), ("km", "NVDA", "NVDA", "stock", "NVIDIA", True),
    ("km", "AAPL", "AAPL", "stock", "Apple", True), ("km", "GOOGL", "GOOGL", "stock", "Alphabet", True),
    ("km", "GOLD", "GC=F", "commodity", "Gold", True), ("km", "SILVER", "SI=F", "commodity", "Silver", True),
    ("km", "US500", "SPY", "etf", "S&P 500", False), ("km", "SEMI", "SMH", "etf", "Semiconductors", False),
    ("km", "SMALL2000", "IWM", "etf", "Russell 2000", False), ("km", "USENERGY", "XLE", "etf", "Energy", False),
    ("km", "USOIL", "CL=F", "commodity", "WTI Crude", False),
    ("vntl", "SEMIS", "SMH", "etf", "Semiconductors", False), ("vntl", "ENERGY", "XLE", "etf", "Energy", False),
    ("vntl", "DEFENSE", "ITA", "etf", "Defense", False),
    ("cash", "TSLA", "TSLA", "stock", "Tesla", True), ("cash", "NVDA", "NVDA", "stock", "NVIDIA", True),
    ("cash", "GOOGL", "GOOGL", "stock", "Alphabet", True), ("cash", "META", "META", "stock", "Meta", True),
    ("cash", "MSFT", "MSFT", "stock", "Microsoft", True), ("cash", "AMZN", "AMZN", "stock", "Amazon", True),
    ("cash", "GOLD", "GC=F", "commodity", "Gold", True), ("cash", "SILVER", "SI=F", "commodity", "Silver", True),
    ("cash", "USA500", "SPY", "etf", "S&P 500", False),
]
HL_INSTRUMENTS = {f"{d}:{s}": _hl(t, d, a, n, g) for d, s, t, a, n, g in _HL_DEFS}
# ── AI Regulatory Intelligence ──
AI_REG_FETCH_LIMIT, AI_REG_CLASSIFICATION_BATCH_SIZE, AI_REG_MAX_WEB_RESULTS = 5, 10, 30
AI_REG_GEMINI_DELAY, AI_REG_SCORE_DECAY_DAYS, AI_REG_MIN_SCORE_STORE, AI_REG_LOOKBACK_DAYS = 1.5, 30, 15, 30
AI_REG_SEVERITY_WEIGHTS = {1: 0.2, 2: 0.4, 3: 0.6, 4: 0.8, 5: 1.0}
AI_REG_SECTOR_EXPOSURE = {"Technology": 0.9, "Financials": 0.8, "Health Care": 0.7, "Energy": 0.6, "Industrials": 0.5, "Consumer Discretionary": 0.5, "Consumer Staples": 0.4, "Materials": 0.4, "Utilities": 0.4, "Real Estate": 0.3, "Communication Services": 0.6}
AI_REG_JURISDICTION_WEIGHTS = {"US": 1.0, "EU": 0.8, "UK": 0.7, "China": 0.6, "Global": 0.9}
# ── Energy Intelligence ──
ENERGY_SECTOR_TICKERS = ["OXY", "COP", "XOM", "CVX", "DVN", "FANG", "EOG", "MPC", "VLO", "PSX", "HAL", "SLB", "LNG", "VST", "CEG", "NEE", "DUK", "SO", "AES", "ENPH"]
# ── Consensus Blindspots ──
CBS_SENTIMENT_CYCLE_WEIGHT, CBS_GAP_WEIGHT, CBS_POSITIONING_WEIGHT = 0.25, 0.30, 0.20
CBS_DIVERGENCE_WEIGHT, CBS_FAT_PITCH_WEIGHT = 0.15, 0.10
CBS_AAII_EXTREME_BULL, CBS_AAII_EXTREME_BEAR = 50.0, 25.0
CBS_VIX_FEAR_THRESHOLD, CBS_VIX_COMPLACENCY_THRESHOLD = 30.0, 12.0
CBS_SHORT_INTEREST_HIGH, CBS_SHORT_INTEREST_LOW = 15.0, 2.0
CBS_INSTITUTIONAL_EXTREME_HIGH, CBS_INSTITUTIONAL_EXTREME_LOW = 95.0, 40.0
CBS_DIVERGENCE_THRESHOLD, CBS_FAT_PITCH_MIN_SIGNALS = 30.0, 3
# ── Pattern Scanner / Options Intel ──
BENCHMARK_STOCK = "SPY"
ROTATION_RS_LOOKBACK, ROTATION_MOMENTUM_LOOKBACK, ROTATION_HISTORY_DAYS = 63, 21, 252
PATTERN_MIN_BARS, PATTERN_SR_KDE_BANDWIDTH_ATR_MULT = 60, 0.5
PATTERN_SR_TOUCH_TOLERANCE, PATTERN_VOLUME_PROFILE_BINS = 0.02, 50
PATTERN_TRIANGLE_MIN_TOUCHES, PATTERN_TRIANGLE_R2_MIN = 3, 0.60
HURST_MIN_OBSERVATIONS, MR_ZSCORE_THRESHOLD = 100, 2.0
MR_HALF_LIFE_MIN, MR_HALF_LIFE_MAX = 3, 60
MOMENTUM_VR_THRESHOLD, COMPRESSION_HV_PERCENTILE_LOW, COMPRESSION_SQUEEZE_MIN_BARS = 1.5, 20, 10
PATTERN_LAYER_WEIGHTS = {"regime": 0.15, "rotation": 0.20, "technical": 0.30, "statistical": 0.25, "cycles": 0.10}
OPTIONS_YFINANCE_DELAY, OPTIONS_MIN_OI, OPTIONS_MIN_VOLUME = 0.5, 10, 5
OPTIONS_FETCH_MAX_SYMBOLS, OPTIONS_MIN_PATTERN_SCORE = 50, 55
PATTERN_OPTIONS_BLEND = {"pattern_weight": 0.60, "options_weight": 0.40}
OPTIONS_UNUSUAL_VOL_OI_MULT, OPTIONS_UNUSUAL_MIN_NOTIONAL = 3.0, 500_000
OPTIONS_SKEW_EXTREME_ZSCORE, OPTIONS_TERM_STRUCTURE_STRESS = 2.0, 1.15
OPTIONS_COMPOSITE_WEIGHTS = {"iv_metrics": 0.25, "pc_ratios": 0.20, "unusual_activity": 0.25, "skew": 0.15, "dealer_exposure": 0.15}
# ── Variant Perception ──
DISCOUNT_RATE_BULL, DISCOUNT_RATE_BASE, DISCOUNT_RATE_BEAR = 0.08, 0.10, 0.14
SCENARIO_WEIGHTS = {
    "strong_risk_on": (0.40, 0.40, 0.20), "risk_on": (0.35, 0.40, 0.25), "neutral": (0.25, 0.50, 0.25),
    "risk_off": (0.20, 0.40, 0.40), "strong_risk_off": (0.15, 0.35, 0.50),
}
TERMINAL_GROWTH_CAP, CONSENSUS_CROWDING_NARROW_PCT, CONSENSUS_CROWDING_WIDE_PCT = 0.04, 0.08, 0.30
CONSENSUS_HERDING_BUY_THRESH, CONSENSUS_HERDING_SELL_THRESH = 80, 60
CONSENSUS_SURPRISE_PERSIST_MIN, CONSENSUS_SURPRISE_PERSIST_BIAS = 5, 0.05
CONSENSUS_TARGET_UPSIDE_CROWDED, CONSENSUS_TARGET_UPSIDE_DEEP = 0.05, 0.30
# ── Prediction Markets ──
POLYMARKET_GAMMA_URL = "https://gamma-api.polymarket.com/events"
POLYMARKET_CLOB_URL = "https://clob.polymarket.com"
PM_MIN_VOLUME, PM_MIN_PROBABILITY_CHANGE, PM_LOOKBACK_DAYS = 10000, 0.05, 30
PM_MIN_LIQUIDITY, PM_CLASSIFICATION_BATCH_SIZE = 5000, 10
PM_GEMINI_DELAY, PM_FETCH_LIMIT = 1.5, 100
PM_CATEGORIES = ["Politics", "Economics", "Science", "Business", "Crypto"]
# Auto-compute reverse maps
HL_TICKER_TO_HL_SYMBOLS: dict[str, list[str]] = {}
for _hl_sym, _meta in HL_INSTRUMENTS.items():
    HL_TICKER_TO_HL_SYMBOLS.setdefault(_meta["ticker"], []).append(_hl_sym)
_hl_gap_eligible: dict[str, list[str]] = {}
for _hl_sym, _meta in HL_INSTRUMENTS.items():
    if _meta.get("gap_eligible", True):
        _hl_gap_eligible.setdefault(_meta["ticker"], []).append(_hl_sym)
HL_CROSS_DEPLOYER_TICKERS = {k: v for k, v in _hl_gap_eligible.items() if len(v) >= 2}
# ── Energy Intelligence Config ──
ENERGY_SCORE_WEIGHTS = {"inventory": 0.30, "production": 0.20, "demand": 0.20, "trade_flows": 0.15, "global_balance": 0.15}
ENERGY_SEASONAL_LOOKBACK_YEARS, ENERGY_CUSHING_PREMIUM = 5, 1.5
ENERGY_JODI_MAX_LAG_DAYS, ENERGY_JODI_BLEND_WEIGHT, ENERGY_COMTRADE_REFRESH_DAYS = 90, 0.30, 90
GEM_BLEND_WEIGHT = 0.20
ENERGY_INTEL_TICKERS = {
    "upstream": ["OXY", "COP", "XOM", "CVX", "DVN", "FANG", "EOG", "PXD", "APA", "MRO"],
    "midstream": ["ET", "WMB", "KMI", "OKE", "TRGP"], "downstream": ["MPC", "VLO", "PSX"],
    "ofs": ["SLB", "HAL", "BKR"], "lng": ["LNG", "TELL"],
}
ENERGY_EIA_ENHANCED_SERIES = [
    ("PET.WCESTP11.W", "PADD 1 Crude Stocks", "padd"), ("PET.WCESTP21.W", "PADD 2 Crude Stocks (Cushing)", "padd"),
    ("PET.WCESTP31.W", "PADD 3 Crude Stocks", "padd"), ("PET.WCESTP41.W", "PADD 4 Crude Stocks", "padd"),
    ("PET.WCESTP51.W", "PADD 5 Crude Stocks", "padd"),
    ("PET.WRPUPUS2.W", "Total Product Supplied", "demand"), ("PET.WGFUPUS2.W", "Gasoline Product Supplied", "demand"),
    ("PET.WDIUPUS2.W", "Distillate Product Supplied", "demand"),
    ("PET.RWTC.W", "WTI Spot Price", "price"), ("PET.EER_EPMRU_PF4_RGC_DPG.W", "Gulf Conv Gasoline", "price"),
]
ENERGY_JODI_COUNTRIES = ["Saudi Arabia", "Russia", "United States", "China", "India", "Iraq", "UAE", "Brazil", "Canada", "Norway"]
# ── Global Energy Markets ──
GEM_REFRESH_HOURS = 18
GEM_OIL_TICKERS = ["OXY", "COP", "XOM", "CVX", "DVN", "FANG", "EOG", "MPC", "VLO", "PSX", "SLB", "HAL", "BKR"]
GEM_GAS_TICKERS = ["LNG", "AR", "EQT", "RRC", "SWN", "CTRA", "NFG"]
GEM_UTILITY_TICKERS = ["VST", "CEG", "NRG", "NEE", "DUK", "SO", "AEP", "XEL", "D", "EIX", "PNW", "ES", "WEC", "CMS", "AES", "PPL", "FE", "ETR", "DTE", "AEE"]
GEM_CLEAN_ENERGY_TICKERS = ["ENPH", "SEDG", "ARRY", "RUN", "SHLS", "FLNC", "STEM", "SMR", "OKLO", "LEU", "NNE", "BWXT", "PLUG", "BE", "FSLR", "MAXN"]
GEM_EUR_USD, GEM_MWH_TO_MMBTU = 1.08, 3.412
GEM_BRENT_WTI_NORMAL, GEM_TTF_HH_NORMAL = (2.0, 8.0), (3.0, 15.0)
GEM_CRACK_THRESHOLDS = {"excellent": 30, "strong": 20, "normal": 10, "weak": 0}
GEM_SCORE_WEIGHTS = {"term_structure": 0.15, "basis_spread": 0.10, "crack_spread": 0.10, "carbon": 0.08, "momentum": 0.12, "cross_market": 0.10, "eu_storage": 0.10, "cot_positioning": 0.10, "norway_flow": 0.08, "storage_surprise": 0.07}
# ── Energy Physical Flows ──
GIE_REFRESH_HOURS = 20
GIE_COUNTRIES_FOCUS = ["EU", "DE", "FR", "NL", "IT", "AT", "BE", "ES", "PL", "CZ"]
GIE_CRITICAL_FILL_PCT, GIE_TIGHT_FILL_PCT, GIE_NORMAL_FILL_PCT = 40.0, 60.0, 75.0
ENTSO_REFRESH_HOURS, COT_REFRESH_DAYS = 20, 3
COT_CONTRACTS = {"WTI_CRUDE": "067651", "BRENT_CRUDE": "06765T", "NAT_GAS_HH": "023651", "RBOB_GAS": "111659", "HEATING_OIL": "022651"}
COT_EXTREME_PERCENTILE, LNG_REFRESH_DAYS = 85, 14
LNG_TERMINAL_CAPACITIES_BCFD = {"SABINE_PASS": 4.5, "CORPUS_CHRISTI": 2.6, "FREEPORT": 2.14, "CAMERON": 2.1, "ELBA_ISLAND": 0.35, "COVE_POINT": 0.82}
# ── Energy Infrastructure ──
ENERGY_INFRA_QUEUE_REFRESH_DAYS, ENERGY_INFRA_COST_REFRESH_DAYS, ENERGY_INFRA_REG_REFRESH_DAYS = 30, 90, 7
# ── Economic Dashboard ──
_econ = [
    ("GDP", "GDP", "Real GDP", "growth", "Q"), ("UNRATE", "UNRATE", "Unemployment Rate", "labor", "M"),
    ("CPI", "CPIAUCSL", "CPI All Urban", "inflation", "M"), ("FEDFUNDS", "FEDFUNDS", "Fed Funds Rate", "rates", "M"),
    ("T10Y2Y", "T10Y2Y", "10Y-2Y Spread", "rates", "D"), ("INDPRO", "INDPRO", "Industrial Production", "growth", "M"),
    ("UMCSENT", "UMCSENT", "Consumer Sentiment", "sentiment", "M"), ("PERMIT", "PERMIT", "Building Permits", "housing", "M"),
    ("JTSJOL", "JTSJOL", "Job Openings (JOLTS)", "labor", "M"), ("RETAILSL", "RSAFS", "Retail Sales", "consumer", "M"),
]
ECONOMIC_INDICATORS = [{"id": i, "fred": f, "name": n, "cat": c, "freq": q} for i, f, n, c, q in _econ]
INDICATOR_METADATA = {i["id"]: i for i in ECONOMIC_INDICATORS}
HEAT_INDEX_WEIGHTS = {"growth": 0.25, "labor": 0.20, "inflation": 0.20, "rates": 0.15, "sentiment": 0.10, "housing": 0.05, "consumer": 0.05}
