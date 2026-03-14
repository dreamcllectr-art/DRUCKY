"""Foreign ticker mapping — resolves local tickers and company names to ADR symbols.

Maintains a static map of ~80 major foreign stocks with their ADR equivalents,
plus fuzzy matching via Gemini for unknown company names found in articles.
"""

import json
import logging
from tools.db import get_conn, query

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static ADR Map: (local_ticker, adr_ticker, company_name_local,
#                   company_name_english, market, sector)
# ---------------------------------------------------------------------------
_STATIC_MAP = [
    # ── Japan (20) ──
    ("7203.T", "TM", "トヨタ自動車", "Toyota Motor", "japan", "Auto"),
    ("6758.T", "SONY", "ソニーグループ", "Sony Group", "japan", "Tech"),
    ("9432.T", "NTT", "日本電信電話", "NTT", "japan", "Telecom"),
    ("8306.T", "MUFG", "三菱UFJフィナンシャル", "Mitsubishi UFJ", "japan", "Banks"),
    ("8316.T", "SMFG", "三井住友フィナンシャル", "Sumitomo Mitsui", "japan", "Banks"),
    ("8411.T", "MFG", "みずほフィナンシャル", "Mizuho Financial", "japan", "Banks"),
    ("7267.T", "HMC", "本田技研工業", "Honda Motor", "japan", "Auto"),
    ("7974.T", "NTDOY", "任天堂", "Nintendo", "japan", "Gaming"),
    ("6861.T", "KYOCY", "キーエンス", "Keyence", "japan", "Industrials"),
    ("8001.T", "ITOCY", "伊藤忠商事", "Itochu", "japan", "Trading"),
    ("6902.T", "DNZOF", "デンソー", "Denso", "japan", "Auto Parts"),
    ("6501.T", "HTHIY", "日立製作所", "Hitachi", "japan", "Industrials"),
    ("8035.T", "TOELY", "東京エレクトロン", "Tokyo Electron", "japan", "Semis"),
    ("6723.T", "RNECY", "ルネサスエレクトロニクス", "Renesas Electronics", "japan", "Semis"),
    ("6857.T", "APTS", "アドバンテスト", "Advantest", "japan", "Semis"),
    ("9984.T", "SFTBY", "ソフトバンクグループ", "SoftBank Group", "japan", "Tech"),
    ("4063.T", "SHECY", "信越化学工業", "Shin-Etsu Chemical", "japan", "Materials"),
    ("7741.T", "HOCPY", "HOYA", "Hoya", "japan", "Healthcare"),
    ("6367.T", "DKILY", "ダイキン工業", "Daikin Industries", "japan", "Industrials"),
    ("6981.T", "MRAAY", "村田製作所", "Murata Manufacturing", "japan", "Electronics"),

    # ── Korea (8) ──
    ("005930.KS", "SSNLF", "삼성전자", "Samsung Electronics", "korea", "Semis"),
    ("000660.KS", "SKLKF", "SK하이닉스", "SK Hynix", "korea", "Semis"),
    ("005380.KS", "HYMTF", "현대자동차", "Hyundai Motor", "korea", "Auto"),
    ("051910.KS", "LGCLF", "LG화학", "LG Chem", "korea", "Chemicals"),
    ("035420.KS", "NAVER", "네이버", "Naver", "korea", "Tech"),
    ("035720.KS", "KAKOF", "카카오", "Kakao", "korea", "Tech"),
    ("006400.KS", "SSDSF", "삼성SDI", "Samsung SDI", "korea", "Batteries"),
    ("003550.KS", "LGGNF", "LG전자", "LG Electronics", "korea", "Electronics"),

    # ── China / Hong Kong (20) ──
    ("9988.HK", "BABA", "阿里巴巴", "Alibaba", "china", "Tech"),
    ("9618.HK", "JD", "京东", "JD.com", "china", "Tech"),
    ("PDD", "PDD", "拼多多", "PDD Holdings", "china", "Tech"),
    ("9888.HK", "BIDU", "百度", "Baidu", "china", "Tech"),
    ("NIO", "NIO", "蔚来", "NIO", "china", "EV"),
    ("LI", "LI", "理想汽车", "Li Auto", "china", "EV"),
    ("XPEV", "XPEV", "小鹏汽车", "XPeng", "china", "EV"),
    ("0700.HK", "TCEHY", "腾讯", "Tencent", "china", "Tech"),
    ("3690.HK", "MPNGY", "美团", "Meituan", "china", "Tech"),
    ("9999.HK", "NTES", "网易", "NetEase", "china", "Gaming"),
    ("9626.HK", "BILI", "哔哩哔哩", "Bilibili", "china", "Tech"),
    ("1810.HK", "XIACY", "小米", "Xiaomi", "china", "Tech"),
    ("2269.HK", "WXXWY", "药明生物", "WuXi Biologics", "china", "Biotech"),
    ("9961.HK", "TME", "腾讯音乐", "Tencent Music", "china", "Tech"),
    ("2057.HK", "ZTO", "中通快递", "ZTO Express", "china", "Logistics"),
    ("YUMC", "YUMC", "百胜中国", "Yum China", "china", "Consumer"),
    ("TAL", "TAL", "好未来", "TAL Education", "china", "Education"),
    ("BEKE", "BEKE", "贝壳找房", "KE Holdings", "china", "Real Estate"),
    ("WB", "WB", "微博", "Weibo", "china", "Tech"),
    ("MNSO", "MNSO", "名创优品", "Miniso", "china", "Retail"),

    # ── Europe — Germany (10) ──
    ("SAP.DE", "SAP", "SAP", "SAP SE", "europe_de", "Tech"),
    ("SIE.DE", "SIEGY", "Siemens", "Siemens AG", "europe_de", "Industrials"),
    ("DTE.DE", "DTEGY", "Deutsche Telekom", "Deutsche Telekom", "europe_de", "Telecom"),
    ("BAS.DE", "BASFY", "BASF", "BASF SE", "europe_de", "Chemicals"),
    ("BAYN.DE", "BAYRY", "Bayer", "Bayer AG", "europe_de", "Pharma"),
    ("IFX.DE", "IFNNY", "Infineon", "Infineon Technologies", "europe_de", "Semis"),
    ("MBG.DE", "MBGYY", "Mercedes-Benz", "Mercedes-Benz Group", "europe_de", "Auto"),
    ("ALV.DE", "ALIZY", "Allianz", "Allianz SE", "europe_de", "Insurance"),
    ("AIR.PA", "EADSF", "Airbus", "Airbus SE", "europe_de", "Aerospace"),
    ("RHM.DE", "RNMBY", "Rheinmetall", "Rheinmetall AG", "europe_de", "Defense"),

    # ── Europe — France (10) ──
    ("MC.PA", "LVMHF", "LVMH", "LVMH", "europe_fr", "Luxury"),
    ("OR.PA", "LRLCF", "L'Oréal", "L'Oréal", "europe_fr", "Consumer"),
    ("SAN.PA", "SNY", "Sanofi", "Sanofi", "europe_fr", "Pharma"),
    ("TTE.PA", "TTE", "TotalEnergies", "TotalEnergies", "europe_fr", "Energy"),
    ("SU.PA", "SCMWY", "Schneider Electric", "Schneider Electric", "europe_fr", "Industrials"),
    ("KER.PA", "PPRUY", "Kering", "Kering", "europe_fr", "Luxury"),
    ("BNP.PA", "BNPQY", "BNP Paribas", "BNP Paribas", "europe_fr", "Banks"),
    ("DSY.PA", "DASTY", "Dassault Systèmes", "Dassault Systèmes", "europe_fr", "Tech"),
    ("HO.PA", "THLLY", "Thales", "Thales SA", "europe_fr", "Defense"),
    ("DG.PA", "DGEAF", "Vinci", "Vinci SA", "europe_fr", "Industrials"),

    # ── Europe — Other (10) ──
    ("ASML.AS", "ASML", "ASML", "ASML Holding", "europe_de", "Semis"),
    ("NOVN.SW", "NVO", "Novo Nordisk", "Novo Nordisk", "europe_de", "Pharma"),
    ("AZN.L", "AZN", "AstraZeneca", "AstraZeneca", "europe_de", "Pharma"),
    ("ROG.SW", "RHHBY", "Roche", "Roche Holding", "europe_de", "Pharma"),
    ("GSK.L", "GSK", "GSK", "GSK plc", "europe_de", "Pharma"),
    ("NESN.SW", "NSRGF", "Nestlé", "Nestlé", "europe_de", "Consumer"),
    ("SHEL.L", "SHEL", "Shell", "Shell plc", "europe_de", "Energy"),
    ("ISP.MI", "ISNPY", "Intesa Sanpaolo", "Intesa Sanpaolo", "europe_it", "Banks"),
    ("UCG.MI", "UNCRY", "UniCredit", "UniCredit", "europe_it", "Banks"),
    ("LDO.MI", "FINMY", "Leonardo", "Leonardo SpA", "europe_it", "Defense"),
]


def init_ticker_map():
    """Populate the foreign_ticker_map table with static ADR mappings."""
    with get_conn() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO foreign_ticker_map
               (local_ticker, adr_ticker, company_name_local,
                company_name_english, market, sector, in_universe)
               VALUES (?, ?, ?, ?, ?, ?, 1)""",
            _STATIC_MAP,
        )
    logger.info(f"Loaded {len(_STATIC_MAP)} foreign ticker mappings.")


def get_ticker_map(market: str = None) -> dict:
    """Return mapping dict: {company_name_local: adr_ticker, local_ticker: adr_ticker, ...}

    Used by foreign_intel.py to resolve mentions in articles.
    """
    where = "WHERE in_universe = 1"
    params = []
    if market:
        where += " AND market = ?"
        params.append(market)

    rows = query(f"SELECT * FROM foreign_ticker_map {where}", params)

    mapping = {}
    for r in rows:
        # Map by local ticker
        if r["local_ticker"]:
            mapping[r["local_ticker"]] = r["adr_ticker"]
        # Map by local company name
        if r["company_name_local"]:
            mapping[r["company_name_local"]] = r["adr_ticker"]
        # Map by English company name
        if r["company_name_english"]:
            mapping[r["company_name_english"]] = r["adr_ticker"]
    return mapping


def get_adr_universe() -> list[str]:
    """Return list of all ADR tickers in the universe."""
    rows = query("SELECT DISTINCT adr_ticker FROM foreign_ticker_map WHERE in_universe = 1 AND adr_ticker IS NOT NULL")
    return [r["adr_ticker"] for r in rows]


def resolve_ticker(name_or_ticker: str, market: str = None) -> str | None:
    """Resolve a company name or local ticker to an ADR ticker.

    Returns the ADR symbol or None if no match found.
    """
    mapping = get_ticker_map(market)

    # Exact match
    if name_or_ticker in mapping:
        return mapping[name_or_ticker]

    # Case-insensitive match
    lower = name_or_ticker.lower()
    for key, adr in mapping.items():
        if key.lower() == lower:
            return adr

    # Partial match (company name contains search term)
    for key, adr in mapping.items():
        if lower in key.lower() or key.lower() in lower:
            return adr

    return None
