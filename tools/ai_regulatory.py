"""AI Regulatory Intelligence Module — global AI regulation → stock impact signals.

Tracks significant AI regulatory developments globally and translates them
into per-stock regulatory risk/opportunity scores for the convergence engine.

Signal pipeline:
  1. Fetch recent regulatory developments from 13+ global sources:
     US: Federal Register API, SEC EDGAR EFTS, FTC, state legislatures, sector regs
     EU: EU AI Act, GDPR AI enforcement, Digital Services Act
     UK: AI Safety Institute, FCA, ICO pro-innovation framework
     China: CAC generative AI rules, MIIT, chip/export restrictions
     Asia-Pacific: Japan METI, Korea PIPC, Singapore IMDA, Australia eSafety
     Canada: AIDA (AI and Data Act), privacy law AI provisions
     Global: G7 Hiroshima Process, OECD AI Principles, UN AI governance
  2. Classify developments by severity, scope, jurisdiction, and stock impact (Gemini LLM)
  3. Map regulatory events → sector/stock impacts with jurisdiction + timeline weighting
  4. Score each symbol 0-100 (50=neutral, >50=regulatory tailwind, <50=headwind)
  5. Store in regulatory_signals + regulatory_events tables

Weight: 3-5% regime-adaptive (higher in risk-off when regulatory risk accelerates)

Usage: python -m tools.ai_regulatory
"""

import sys
import json
import time
import logging
import re
from datetime import date, datetime, timedelta
from pathlib import Path

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import requests

from tools.config import (
    GEMINI_API_KEY, GEMINI_BASE, GEMINI_MODEL,
    SERPER_API_KEY, EDGAR_HEADERS,
    AI_REG_FETCH_LIMIT, AI_REG_CLASSIFICATION_BATCH_SIZE,
    AI_REG_GEMINI_DELAY, AI_REG_LOOKBACK_DAYS,
    AI_REG_SEVERITY_WEIGHTS, AI_REG_SECTOR_EXPOSURE,
    AI_REG_JURISDICTION_WEIGHTS,
)
from tools.db import init_db, upsert_many, query, get_conn

logger = logging.getLogger(__name__)

# ── Regulatory Source APIs (all free, no auth required except EDGAR User-Agent) ──

FEDERAL_REGISTER_BASE = "https://www.federalregister.gov/api/v1"
SEC_EFTS_BASE = "https://efts.sec.gov/LATEST"
FTC_PRESS_RSS = "https://www.ftc.gov/feeds/press-releases.xml"
EUR_LEX_SEARCH = "https://eur-lex.europa.eu/search.html"

# ── Regulatory Body Definitions ──────────────────────────────────────────

REGULATORY_BODIES = {
    # ── US Federal ──
    "federal_register": {
        "name": "Federal Register (US)",
        "scope": "federal",
        "jurisdiction": "US",
    },
    "sec": {
        "name": "SEC",
        "scope": "federal",
        "jurisdiction": "US",
    },
    "ftc": {
        "name": "FTC",
        "scope": "federal",
        "jurisdiction": "US",
    },
    "state_us": {
        "name": "US State Legislatures",
        "scope": "state",
        "jurisdiction": "US",
    },
    # ── US Sector ──
    "sector_banking": {
        "name": "Banking Regulators (OCC/Fed/FDIC)",
        "scope": "sector",
        "jurisdiction": "US",
    },
    "sector_healthcare": {
        "name": "Healthcare Regulators (HHS/FDA)",
        "scope": "sector",
        "jurisdiction": "US",
    },
    "sector_employment": {
        "name": "Employment Regulators (EEOC/DOL)",
        "scope": "sector",
        "jurisdiction": "US",
    },
    # ── European Union ──
    "eu_commission": {
        "name": "EU Commission / AI Act",
        "scope": "supranational",
        "jurisdiction": "EU",
    },
    "eu_dsa_dma": {
        "name": "EU Digital Services / Markets Act",
        "scope": "supranational",
        "jurisdiction": "EU",
    },
    # ── United Kingdom ──
    "uk_aisi": {
        "name": "UK AI Safety Institute / DSIT",
        "scope": "federal",
        "jurisdiction": "UK",
    },
    "uk_fca_ico": {
        "name": "UK FCA / ICO",
        "scope": "sector",
        "jurisdiction": "UK",
    },
    # ── China ──
    "china_cac": {
        "name": "China CAC / MIIT",
        "scope": "federal",
        "jurisdiction": "CN",
    },
    # ── Asia-Pacific ──
    "japan_meti": {
        "name": "Japan METI / PPC",
        "scope": "federal",
        "jurisdiction": "JP",
    },
    "korea_pipc": {
        "name": "South Korea PIPC / AI Basic Act",
        "scope": "federal",
        "jurisdiction": "KR",
    },
    "singapore_imda": {
        "name": "Singapore IMDA / AI Verify",
        "scope": "federal",
        "jurisdiction": "SG",
    },
    # ── Canada ──
    "canada_aida": {
        "name": "Canada AIDA / Privacy Commissioner",
        "scope": "federal",
        "jurisdiction": "CA",
    },
    # ── Global Coordination ──
    "global_coordination": {
        "name": "G7 / OECD / UN AI Governance",
        "scope": "multilateral",
        "jurisdiction": "GLOBAL",
    },
}

# ── Category → Sector Impact Mapping ────────────────────────────────────

REGULATORY_IMPACT_MAP = {
    "ai_model_regulation": {
        "description": "Rules governing AI model training, deployment, or capabilities",
        "headwind_sectors": ["Technology", "Communication Services"],
        "tailwind_sectors": [],
        "headwind_symbols": ["GOOGL", "META", "MSFT", "AMZN", "NVDA", "CRM", "PLTR", "AI", "SAP", "BABA"],
        "tailwind_symbols": [],
    },
    "ai_transparency_disclosure": {
        "description": "Mandatory disclosure of AI use, model cards, impact assessments",
        "headwind_sectors": ["Technology", "Communication Services", "Financials"],
        "tailwind_sectors": [],
        "headwind_symbols": ["GOOGL", "META", "MSFT", "CRM", "NOW", "PLTR", "SAP"],
        "tailwind_symbols": ["MSFT", "IBM", "SAP"],  # compliance tooling providers
    },
    "ai_copyright_ip": {
        "description": "AI training data copyright, IP ownership of AI outputs",
        "headwind_sectors": ["Technology", "Communication Services"],
        "tailwind_sectors": [],
        "headwind_symbols": ["GOOGL", "META", "MSFT", "ADBE", "AI"],
        "tailwind_symbols": ["DIS", "NFLX", "WBD", "SPOT"],  # content owners benefit from protection
    },
    "ai_liability_safety": {
        "description": "AI product liability, safety requirements, incident reporting",
        "headwind_sectors": ["Technology", "Industrials"],
        "tailwind_sectors": ["Insurance"],
        "headwind_symbols": ["TSLA", "GOOGL", "MSFT", "AMZN"],
        "tailwind_symbols": [],
    },
    "ai_employment_hr": {
        "description": "AI in hiring, performance evaluation, workplace monitoring",
        "headwind_sectors": ["Technology"],
        "tailwind_sectors": [],
        "headwind_symbols": ["WDAY", "NOW", "CRM", "HIMS"],
        "tailwind_symbols": [],
    },
    "ai_healthcare": {
        "description": "AI in clinical decision support, drug discovery, diagnostics",
        "headwind_sectors": ["Health Care"],
        "tailwind_sectors": [],
        "headwind_symbols": ["ISRG", "VEEV", "DXCM", "TDOC"],
        "tailwind_symbols": [],
    },
    "ai_financial_services": {
        "description": "AI in lending, trading, credit scoring, robo-advisory",
        "headwind_sectors": ["Financials"],
        "tailwind_sectors": [],
        "headwind_symbols": ["GS", "JPM", "MS", "SCHW", "HOOD", "UPST", "SOFI"],
        "tailwind_symbols": [],
    },
    "ai_autonomous_vehicles": {
        "description": "Self-driving regulation, ADAS requirements",
        "headwind_sectors": ["Consumer Discretionary", "Industrials"],
        "tailwind_sectors": [],
        "headwind_symbols": ["TSLA", "GM", "F", "UBER", "LYFT"],
        "tailwind_symbols": [],
    },
    "ai_data_privacy": {
        "description": "AI-specific data privacy rules, biometric data, facial recognition bans",
        "headwind_sectors": ["Technology", "Communication Services"],
        "tailwind_sectors": [],
        "headwind_symbols": ["META", "GOOGL", "AMZN", "CRM", "PLTR"],
        "tailwind_symbols": ["CRWD", "ZS", "PANW"],  # cybersecurity/compliance beneficiaries
    },
    "ai_export_controls": {
        "description": "Chip export restrictions, AI technology transfer controls, cross-border AI",
        "headwind_sectors": ["Technology"],
        "tailwind_sectors": [],
        "headwind_symbols": ["NVDA", "AMD", "INTC", "AVGO", "ASML", "AMAT", "LRCX", "TSM"],
        "tailwind_symbols": [],
    },
    "ai_antitrust": {
        "description": "AI market concentration, compute monopoly, platform dominance — US, EU DMA, UK CMA",
        "headwind_sectors": ["Technology"],
        "tailwind_sectors": [],
        "headwind_symbols": ["GOOGL", "META", "MSFT", "AMZN", "AAPL", "NVDA"],
        "tailwind_symbols": ["AMD", "INTC"],  # competitors benefit from forced openness
    },
    "ai_government_adoption": {
        "description": "Government AI procurement, mandates, or bans (all jurisdictions)",
        "headwind_sectors": [],
        "tailwind_sectors": ["Technology", "Industrials"],
        "headwind_symbols": [],
        "tailwind_symbols": ["PLTR", "AI", "GOOG", "MSFT", "AMZN", "IBM", "SAP", "ACN"],
    },
    "ai_infrastructure_investment": {
        "description": "Government AI R&D funding, compute subsidies, CHIPS Act, EU Chips Act, sovereign AI",
        "headwind_sectors": [],
        "tailwind_sectors": ["Technology", "Industrials"],
        "headwind_symbols": [],
        "tailwind_symbols": ["NVDA", "AMD", "INTC", "AVGO", "AMAT", "MSFT", "GOOGL", "AMZN", "ASML", "TSM", "ARM"],
    },
    # ── NEW: International-specific categories ──
    "ai_cross_border_data": {
        "description": "Data localization mandates, cross-border AI data transfer rules, adequacy decisions",
        "headwind_sectors": ["Technology", "Communication Services", "Financials"],
        "tailwind_sectors": [],
        "headwind_symbols": ["GOOGL", "META", "AMZN", "MSFT", "CRM", "SNOW", "DDOG", "PLTR"],
        "tailwind_symbols": ["SAP", "IBM"],  # local/hybrid cloud providers
    },
    "ai_international_standards": {
        "description": "ISO/IEC AI standards, mutual recognition frameworks, interoperability requirements",
        "headwind_sectors": [],
        "tailwind_sectors": ["Technology"],
        "headwind_symbols": [],
        "tailwind_symbols": ["MSFT", "IBM", "SAP", "ACN", "GOOGL"],  # compliance frameworks = moat
    },
    "ai_sovereign_compute": {
        "description": "National AI compute initiatives, sovereign cloud mandates, domestic chip programs",
        "headwind_sectors": [],
        "tailwind_sectors": ["Technology", "Industrials"],
        "headwind_symbols": ["AMZN", "MSFT", "GOOGL"],  # may lose sovereign cloud deals
        "tailwind_symbols": ["NVDA", "AMD", "INTC", "ASML", "TSM", "ARM", "AMAT"],  # hardware demand
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# DATA FETCHING — All free APIs, no auth keys needed (except Serper for state)
# ═══════════════════════════════════════════════════════════════════════════


def _fetch_federal_register() -> list[dict]:
    """Fetch AI-related rules and proposed rules from Federal Register API.

    Free API, no auth. Returns rules published in last N days mentioning AI.
    """
    events = []
    cutoff = (date.today() - timedelta(days=AI_REG_LOOKBACK_DAYS)).isoformat()

    search_terms = [
        "artificial intelligence",
        "machine learning",
        "automated decision",
        "algorithmic",
    ]

    for term in search_terms:
        try:
            resp = requests.get(
                f"{FEDERAL_REGISTER_BASE}/documents.json",
                params={
                    "conditions[term]": term,
                    "conditions[publication_date][gte]": cutoff,
                    "conditions[type][]": ["RULE", "PRORULE", "NOTICE"],
                    "per_page": 20,
                    "order": "newest",
                    "fields[]": [
                        "title", "abstract", "publication_date",
                        "type", "agencies", "document_number", "html_url",
                    ],
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            for doc in data.get("results", []):
                agencies = doc.get("agencies", [])
                agency_names = [a.get("name", "") for a in agencies] if agencies else []

                events.append({
                    "source": "federal_register",
                    "title": doc.get("title", ""),
                    "abstract": (doc.get("abstract") or "")[:500],
                    "date": doc.get("publication_date", ""),
                    "doc_type": doc.get("type", ""),
                    "agencies": ", ".join(agency_names),
                    "url": doc.get("html_url", ""),
                    "doc_id": doc.get("document_number", ""),
                    "jurisdiction": "US",
                })

            time.sleep(0.5)

        except requests.RequestException as e:
            logger.warning(f"Federal Register search '{term}' failed: {e}")

    # Deduplicate by doc_id
    seen = set()
    unique = []
    for ev in events:
        if ev["doc_id"] not in seen:
            seen.add(ev["doc_id"])
            unique.append(ev)

    logger.info(f"Federal Register: {len(unique)} AI-related documents")
    return unique[:AI_REG_FETCH_LIMIT]


def _fetch_sec_ai_guidance() -> list[dict]:
    """Fetch AI-related SEC guidance and enforcement from EDGAR EFTS search.

    Free API, requires User-Agent header per SEC policy.
    """
    events = []
    cutoff = (date.today() - timedelta(days=AI_REG_LOOKBACK_DAYS)).isoformat()

    search_terms = ["artificial intelligence", "AI risk", "algorithmic trading"]

    for term in search_terms:
        try:
            resp = requests.get(
                f"{SEC_EFTS_BASE}/search-index",
                params={
                    "q": f'"{term}"',
                    "dateRange": "custom",
                    "startdt": cutoff,
                    "enddt": date.today().isoformat(),
                    "forms": "RULE,NOTICE,PRESS,LITIGATION",
                },
                headers=EDGAR_HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            for hit in data.get("hits", {}).get("hits", [])[:10]:
                src = hit.get("_source", {})
                events.append({
                    "source": "sec",
                    "title": src.get("display_name_t", src.get("file_description", "")),
                    "abstract": (src.get("file_description", "") or "")[:500],
                    "date": (src.get("file_date", "") or "")[:10],
                    "doc_type": src.get("form_type", ""),
                    "agencies": "SEC",
                    "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&filenum={src.get('file_num', '')}",
                    "doc_id": src.get("_id", hit.get("_id", "")),
                    "jurisdiction": "US",
                })

            time.sleep(0.5)

        except requests.RequestException as e:
            logger.warning(f"SEC EFTS search '{term}' failed: {e}")

    # Deduplicate
    seen = set()
    unique = []
    for ev in events:
        if ev["doc_id"] and ev["doc_id"] not in seen:
            seen.add(ev["doc_id"])
            unique.append(ev)

    logger.info(f"SEC EDGAR: {len(unique)} AI-related documents")
    return unique[:AI_REG_FETCH_LIMIT]


def _fetch_ftc_ai_enforcement() -> list[dict]:
    """Fetch FTC AI enforcement actions via press release search.

    Uses Serper to search FTC.gov for recent AI enforcement.
    """
    if not SERPER_API_KEY:
        logger.warning("No Serper API key — skipping FTC enforcement search")
        return []

    events = []
    try:
        resp = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={
                "q": "site:ftc.gov artificial intelligence AI enforcement action 2025 2026",
                "num": 15,
            },
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json().get("organic", [])

        for r in results:
            events.append({
                "source": "ftc",
                "title": r.get("title", ""),
                "abstract": (r.get("snippet", "") or "")[:500],
                "date": _extract_date_from_snippet(r.get("snippet", "")),
                "doc_type": "enforcement",
                "agencies": "FTC",
                "url": r.get("link", ""),
                "doc_id": r.get("link", ""),
                "jurisdiction": "US",
            })

    except requests.RequestException as e:
        logger.warning(f"FTC Serper search failed: {e}")

    logger.info(f"FTC: {len(events)} AI enforcement results")
    return events[:AI_REG_FETCH_LIMIT]


def _fetch_eu_ai_act() -> list[dict]:
    """Fetch EU AI Act developments via news search.

    Uses Serper to find recent EU AI Act implementation updates.
    """
    if not SERPER_API_KEY:
        logger.warning("No Serper API key — skipping EU AI Act search")
        return []

    events = []
    queries = [
        "EU AI Act implementation enforcement 2025 2026",
        "European Commission artificial intelligence regulation compliance",
    ]

    for q in queries:
        try:
            resp = requests.post(
                "https://google.serper.dev/news",
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                json={"q": q, "num": 10},
                timeout=15,
            )
            resp.raise_for_status()
            results = resp.json().get("news", [])

            for r in results:
                events.append({
                    "source": "eu_commission",
                    "title": r.get("title", ""),
                    "abstract": (r.get("snippet", "") or "")[:500],
                    "date": (r.get("date", "") or "")[:10],
                    "doc_type": "news",
                    "agencies": "EU Commission",
                    "url": r.get("link", ""),
                    "doc_id": r.get("link", ""),
                    "jurisdiction": "EU",
                })

            time.sleep(0.5)

        except requests.RequestException as e:
            logger.warning(f"EU AI Act search failed: {e}")

    logger.info(f"EU AI Act: {len(events)} developments")
    return events[:AI_REG_FETCH_LIMIT]


def _fetch_state_level_ai_laws() -> list[dict]:
    """Fetch US state-level AI legislation via news search.

    Covers key states: California, Colorado, Texas, Illinois, New York, Connecticut.
    """
    if not SERPER_API_KEY:
        logger.warning("No Serper API key — skipping state-level search")
        return []

    events = []
    key_states = ["California", "Colorado", "Texas", "Illinois", "New York", "Connecticut"]

    try:
        state_str = " OR ".join(key_states)
        resp = requests.post(
            "https://google.serper.dev/news",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={
                "q": f"({state_str}) AI artificial intelligence law bill regulation 2025 2026",
                "num": 15,
            },
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json().get("news", [])

        for r in results:
            events.append({
                "source": "state_us",
                "title": r.get("title", ""),
                "abstract": (r.get("snippet", "") or "")[:500],
                "date": (r.get("date", "") or "")[:10],
                "doc_type": "legislation",
                "agencies": "US State Legislature",
                "url": r.get("link", ""),
                "doc_id": r.get("link", ""),
                "jurisdiction": "US",
            })

    except requests.RequestException as e:
        logger.warning(f"State-level AI law search failed: {e}")

    logger.info(f"State-level: {len(events)} AI law developments")
    return events[:AI_REG_FETCH_LIMIT]


def _fetch_sector_regulatory_news() -> list[dict]:
    """Fetch sector-specific AI regulatory developments (banking, healthcare, employment)."""
    if not SERPER_API_KEY:
        logger.warning("No Serper API key — skipping sector regulatory search")
        return []

    events = []
    sector_queries = [
        ("sector_banking", "OCC Fed FDIC artificial intelligence AI banking regulation guidance 2025 2026"),
        ("sector_healthcare", "FDA HHS artificial intelligence AI healthcare medical device regulation 2025 2026"),
        ("sector_employment", "EEOC DOL artificial intelligence AI hiring employment discrimination regulation 2025 2026"),
    ]

    for source, q in sector_queries:
        try:
            resp = requests.post(
                "https://google.serper.dev/news",
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                json={"q": q, "num": 8},
                timeout=15,
            )
            resp.raise_for_status()
            results = resp.json().get("news", [])

            for r in results:
                events.append({
                    "source": source,
                    "title": r.get("title", ""),
                    "abstract": (r.get("snippet", "") or "")[:500],
                    "date": (r.get("date", "") or "")[:10],
                    "doc_type": "sector_regulation",
                    "agencies": REGULATORY_BODIES[source]["name"],
                    "url": r.get("link", ""),
                    "doc_id": r.get("link", ""),
                    "jurisdiction": "US",
                })

            time.sleep(0.5)

        except requests.RequestException as e:
            logger.warning(f"Sector regulatory search ({source}) failed: {e}")

    logger.info(f"Sector-specific: {len(events)} AI regulatory developments")
    return events[:AI_REG_FETCH_LIMIT]


# ═══════════════════════════════════════════════════════════════════════════
# INTERNATIONAL DATA FETCHING
# ═══════════════════════════════════════════════════════════════════════════


def _fetch_uk_ai_regulation() -> list[dict]:
    """Fetch UK AI regulation: AI Safety Institute, FCA, ICO, DSIT pro-innovation framework.

    UK is the #1 non-US jurisdiction for AI policy — AISI sets global safety
    benchmarks, FCA regulates AI in financial services, ICO enforces data/AI rules.
    """
    if not SERPER_API_KEY:
        logger.warning("No Serper API key — skipping UK AI regulation search")
        return []

    events = []
    queries = [
        ("uk_aisi", "UK AI Safety Institute DSIT artificial intelligence regulation safety 2025 2026"),
        ("uk_aisi", "UK AI regulation pro-innovation framework Bletchley 2025 2026"),
        ("uk_fca_ico", "UK FCA artificial intelligence AI financial services regulation guidance 2025 2026"),
        ("uk_fca_ico", "UK ICO AI data protection enforcement automated decision 2025 2026"),
    ]

    for source, q in queries:
        try:
            resp = requests.post(
                "https://google.serper.dev/news",
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                json={"q": q, "num": 8},
                timeout=15,
            )
            resp.raise_for_status()
            results = resp.json().get("news", [])

            for r in results:
                events.append({
                    "source": source,
                    "title": r.get("title", ""),
                    "abstract": (r.get("snippet", "") or "")[:500],
                    "date": (r.get("date", "") or "")[:10],
                    "doc_type": "regulation",
                    "agencies": REGULATORY_BODIES[source]["name"],
                    "url": r.get("link", ""),
                    "doc_id": r.get("link", ""),
                    "jurisdiction": "UK",
                })

            time.sleep(0.5)

        except requests.RequestException as e:
            logger.warning(f"UK AI regulation search failed: {e}")

    # Deduplicate by URL
    seen = set()
    unique = [ev for ev in events if ev["doc_id"] not in seen and not seen.add(ev["doc_id"])]

    logger.info(f"UK AI regulation: {len(unique)} developments")
    return unique[:AI_REG_FETCH_LIMIT]


def _fetch_china_ai_regulation() -> list[dict]:
    """Fetch China AI regulation: CAC generative AI measures, MIIT, export controls.

    China's regulatory moves directly impact NVDA (chip export bans), BABA, PDD,
    and any company with China revenue exposure. CAC's interim measures on
    generative AI are the strictest in the world.
    """
    if not SERPER_API_KEY:
        logger.warning("No Serper API key — skipping China AI regulation search")
        return []

    events = []
    queries = [
        ("china_cac", "China CAC artificial intelligence generative AI regulation 2025 2026"),
        ("china_cac", "China MIIT AI regulation algorithm recommendation deep synthesis 2025 2026"),
        ("china_cac", "China AI chip export restriction semiconductor ban 2025 2026"),
        ("china_cac", "China AI data security cross-border data transfer 2025 2026"),
    ]

    for source, q in queries:
        try:
            resp = requests.post(
                "https://google.serper.dev/news",
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                json={"q": q, "num": 8},
                timeout=15,
            )
            resp.raise_for_status()
            results = resp.json().get("news", [])

            for r in results:
                events.append({
                    "source": source,
                    "title": r.get("title", ""),
                    "abstract": (r.get("snippet", "") or "")[:500],
                    "date": (r.get("date", "") or "")[:10],
                    "doc_type": "regulation",
                    "agencies": REGULATORY_BODIES[source]["name"],
                    "url": r.get("link", ""),
                    "doc_id": r.get("link", ""),
                    "jurisdiction": "CN",
                })

            time.sleep(0.5)

        except requests.RequestException as e:
            logger.warning(f"China AI regulation search failed: {e}")

    seen = set()
    unique = [ev for ev in events if ev["doc_id"] not in seen and not seen.add(ev["doc_id"])]

    logger.info(f"China AI regulation: {len(unique)} developments")
    return unique[:AI_REG_FETCH_LIMIT]


def _fetch_asia_pacific_ai_regulation() -> list[dict]:
    """Fetch Japan, Korea, Singapore, Australia AI regulatory developments.

    Japan: Hiroshima AI Process, METI voluntary guidelines (AI-friendly approach)
    Korea: AI Basic Act (mandatory risk assessments for high-risk AI)
    Singapore: AI Verify framework (model governance), IMDA guidelines
    Australia: Mandatory AI guardrails consultation, eSafety Commissioner
    """
    if not SERPER_API_KEY:
        logger.warning("No Serper API key — skipping Asia-Pacific AI regulation search")
        return []

    events = []
    queries = [
        ("japan_meti", "Japan artificial intelligence AI regulation METI Hiroshima AI Process 2025 2026"),
        ("korea_pipc", "South Korea AI Basic Act artificial intelligence regulation PIPC 2025 2026"),
        ("singapore_imda", "Singapore AI Verify IMDA artificial intelligence governance framework 2025 2026"),
        ("singapore_imda", "Australia AI regulation mandatory guardrails eSafety 2025 2026"),  # bundled with SG
    ]

    for source, q in queries:
        try:
            resp = requests.post(
                "https://google.serper.dev/news",
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                json={"q": q, "num": 6},
                timeout=15,
            )
            resp.raise_for_status()
            results = resp.json().get("news", [])

            for r in results:
                events.append({
                    "source": source,
                    "title": r.get("title", ""),
                    "abstract": (r.get("snippet", "") or "")[:500],
                    "date": (r.get("date", "") or "")[:10],
                    "doc_type": "regulation",
                    "agencies": REGULATORY_BODIES[source]["name"],
                    "url": r.get("link", ""),
                    "doc_id": r.get("link", ""),
                    "jurisdiction": REGULATORY_BODIES[source]["jurisdiction"],
                })

            time.sleep(0.5)

        except requests.RequestException as e:
            logger.warning(f"Asia-Pacific AI regulation search failed: {e}")

    seen = set()
    unique = [ev for ev in events if ev["doc_id"] not in seen and not seen.add(ev["doc_id"])]

    logger.info(f"Asia-Pacific AI regulation: {len(unique)} developments")
    return unique[:AI_REG_FETCH_LIMIT]


def _fetch_canada_ai_regulation() -> list[dict]:
    """Fetch Canada AIDA (Artificial Intelligence and Data Act) + privacy AI provisions.

    AIDA is part of Bill C-27, would create mandatory AI registration for
    high-impact systems. Canada also has strong privacy framework (PIPEDA)
    with AI-specific provisions being added.
    """
    if not SERPER_API_KEY:
        logger.warning("No Serper API key — skipping Canada AI regulation search")
        return []

    events = []
    queries = [
        ("canada_aida", "Canada AIDA Artificial Intelligence Data Act Bill C-27 regulation 2025 2026"),
        ("canada_aida", "Canada AI regulation privacy PIPEDA artificial intelligence 2025 2026"),
    ]

    for source, q in queries:
        try:
            resp = requests.post(
                "https://google.serper.dev/news",
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                json={"q": q, "num": 8},
                timeout=15,
            )
            resp.raise_for_status()
            results = resp.json().get("news", [])

            for r in results:
                events.append({
                    "source": source,
                    "title": r.get("title", ""),
                    "abstract": (r.get("snippet", "") or "")[:500],
                    "date": (r.get("date", "") or "")[:10],
                    "doc_type": "legislation",
                    "agencies": REGULATORY_BODIES[source]["name"],
                    "url": r.get("link", ""),
                    "doc_id": r.get("link", ""),
                    "jurisdiction": "CA",
                })

            time.sleep(0.5)

        except requests.RequestException as e:
            logger.warning(f"Canada AI regulation search failed: {e}")

    seen = set()
    unique = [ev for ev in events if ev["doc_id"] not in seen and not seen.add(ev["doc_id"])]

    logger.info(f"Canada AI regulation: {len(unique)} developments")
    return unique[:AI_REG_FETCH_LIMIT]


def _fetch_global_ai_coordination() -> list[dict]:
    """Fetch G7, OECD, UN multilateral AI governance developments.

    These shape the direction ALL jurisdictions move. The Hiroshima AI Process
    and OECD AI Principles are the baseline that national laws build on.
    When G7 agrees on compute governance, it flows into every member's policy.
    """
    if not SERPER_API_KEY:
        logger.warning("No Serper API key — skipping global AI coordination search")
        return []

    events = []
    queries = [
        ("global_coordination", "G7 artificial intelligence AI governance Hiroshima Process 2025 2026"),
        ("global_coordination", "OECD AI principles governance regulation international 2025 2026"),
        ("global_coordination", "United Nations AI governance global regulation summit 2025 2026"),
        ("global_coordination", "EU US AI trade agreement technology alliance regulation 2025 2026"),
    ]

    for source, q in queries:
        try:
            resp = requests.post(
                "https://google.serper.dev/news",
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                json={"q": q, "num": 6},
                timeout=15,
            )
            resp.raise_for_status()
            results = resp.json().get("news", [])

            for r in results:
                events.append({
                    "source": source,
                    "title": r.get("title", ""),
                    "abstract": (r.get("snippet", "") or "")[:500],
                    "date": (r.get("date", "") or "")[:10],
                    "doc_type": "multilateral",
                    "agencies": REGULATORY_BODIES[source]["name"],
                    "url": r.get("link", ""),
                    "doc_id": r.get("link", ""),
                    "jurisdiction": "GLOBAL",
                })

            time.sleep(0.5)

        except requests.RequestException as e:
            logger.warning(f"Global AI coordination search failed: {e}")

    seen = set()
    unique = [ev for ev in events if ev["doc_id"] not in seen and not seen.add(ev["doc_id"])]

    logger.info(f"Global AI coordination: {len(unique)} developments")
    return unique[:AI_REG_FETCH_LIMIT]


# ═══════════════════════════════════════════════════════════════════════════
# EU DSA/DMA AI ENFORCEMENT
# ═══════════════════════════════════════════════════════════════════════════


def _fetch_eu_dsa_dma() -> list[dict]:
    """Fetch EU Digital Services Act / Digital Markets Act AI enforcement.

    DSA/DMA are now in enforcement — fines up to 6% of global revenue.
    These directly hit GOOGL, META, AMZN, AAPL, MSFT. Capital is flowing
    to Europe partly BECAUSE the regulatory framework creates predictability.
    """
    if not SERPER_API_KEY:
        logger.warning("No Serper API key — skipping EU DSA/DMA search")
        return []

    events = []
    queries = [
        ("eu_dsa_dma", "EU Digital Services Act AI enforcement algorithm compliance 2025 2026"),
        ("eu_dsa_dma", "EU Digital Markets Act gatekeeper AI interoperability 2025 2026"),
    ]

    for source, q in queries:
        try:
            resp = requests.post(
                "https://google.serper.dev/news",
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                json={"q": q, "num": 8},
                timeout=15,
            )
            resp.raise_for_status()
            results = resp.json().get("news", [])

            for r in results:
                events.append({
                    "source": source,
                    "title": r.get("title", ""),
                    "abstract": (r.get("snippet", "") or "")[:500],
                    "date": (r.get("date", "") or "")[:10],
                    "doc_type": "enforcement",
                    "agencies": REGULATORY_BODIES[source]["name"],
                    "url": r.get("link", ""),
                    "doc_id": r.get("link", ""),
                    "jurisdiction": "EU",
                })

            time.sleep(0.5)

        except requests.RequestException as e:
            logger.warning(f"EU DSA/DMA search failed: {e}")

    seen = set()
    unique = [ev for ev in events if ev["doc_id"] not in seen and not seen.add(ev["doc_id"])]

    logger.info(f"EU DSA/DMA: {len(unique)} AI enforcement developments")
    return unique[:AI_REG_FETCH_LIMIT]


# ═══════════════════════════════════════════════════════════════════════════
# LLM CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════


def _classify_events_batch(events: list[dict]) -> list[dict]:
    """Use Gemini to classify regulatory events by financial impact.

    For each event, determines:
      - is_significant: bool (does this have material stock market impact?)
      - impact_category: str (key from REGULATORY_IMPACT_MAP)
      - severity: 1-5 (1=minor guidance, 5=binding enforcement/law enacted)
      - stage: proposed | final_rule | enforcement | enacted | guidance
      - direction: headwind | tailwind | mixed (net effect on affected companies)
      - timeline: immediate | 6_months | 1_year | 2_plus_years
      - specific_symbols: list of directly impacted tickers
      - rationale: one-line explanation
    """
    if not GEMINI_API_KEY:
        logger.warning("No Gemini API key — skipping classification")
        return []

    categories_list = list(REGULATORY_IMPACT_MAP.keys())
    classified = []

    for i in range(0, len(events), AI_REG_CLASSIFICATION_BATCH_SIZE):
        batch = events[i:i + AI_REG_CLASSIFICATION_BATCH_SIZE]

        event_texts = []
        for idx, ev in enumerate(batch):
            jurisdiction = ev.get("jurisdiction", "US")
            event_texts.append(
                f"{idx+1}. [{ev['source'].upper()}] [{jurisdiction}] \"{ev['title']}\" | "
                f"Date: {ev['date']} | Agency: {ev['agencies']} | "
                f"Type: {ev['doc_type']} | "
                f"Abstract: {ev['abstract'][:200]}"
            )

        prompt = f"""You are a global regulatory analyst assessing how AI-related regulatory developments impact US-listed stocks.

Events come from multiple jurisdictions: US, EU, UK, China, Japan, South Korea, Singapore, Canada, and multilateral bodies (G7, OECD, UN).

KEY JURISDICTION LOGIC for impact on US-listed stocks:
- US regulations: Direct impact on all US companies in scope
- EU regulations: Impact US companies with European revenue (GOOGL, META, MSFT, AMZN get 25-35% of revenue from Europe). EU AI Act = most comprehensive AI law globally, sets compliance baseline
- UK regulations: Impact US companies with UK operations. UK AI Safety Institute sets global safety benchmarks
- China regulations: Impact companies with China revenue/supply chain exposure (AAPL, NVDA, TSLA, QCOM). Also drives chip export control dynamics
- Japan/Korea/Singapore: Impact companies with APAC revenue. Japan's light-touch approach is a TAILWIND vs EU's heavy approach
- Canada: Impact companies with North American operations (most US tech)
- G7/OECD/UN: Signals direction ALL jurisdictions will move — early warning of coordinated action

Focus on MATERIAL developments — skip minor procedural notices, comment period extensions, or generic press releases.

Available impact categories: {json.dumps(categories_list)}

Severity scale:
  1 = Minor guidance or comment request (minimal market impact)
  2 = Proposed rule or draft framework (signals regulatory direction)
  3 = Final rule or significant enforcement action (compliance required)
  4 = Major law enacted or landmark enforcement (industry restructuring)
  5 = Emergency action or executive order with immediate effect

Stage: proposed | final_rule | enforcement | enacted | guidance

Direction: "headwind" (increases cost/risk), "tailwind" (creates opportunity), "mixed"

Timeline: "immediate" | "6_months" | "1_year" | "2_plus_years"

For each event, respond with a JSON array:
{{
  "index": <1-based>,
  "is_significant": true/false,
  "impact_category": "<category or null>",
  "severity": <1-5>,
  "stage": "<stage>",
  "direction": "headwind" or "tailwind" or "mixed",
  "timeline": "<timeline>",
  "specific_symbols": ["TICKER1", "TICKER2"],
  "jurisdiction": "<US|EU|UK|CN|JP|KR|SG|CA|GLOBAL>",
  "rationale": "<one sentence explaining impact on US-listed stocks>"
}}

Events:
{chr(10).join(event_texts)}

Respond ONLY with the JSON array, no other text."""

        try:
            resp = requests.post(
                f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent",
                headers={"Content-Type": "application/json"},
                params={"key": GEMINI_API_KEY},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.2,
                        "maxOutputTokens": 2048,
                    },
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()

            # Parse JSON (handle markdown code blocks)
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            classifications = json.loads(text)

            for cls in classifications:
                idx = cls.get("index", 0) - 1
                if 0 <= idx < len(batch) and cls.get("is_significant"):
                    event = batch[idx].copy()
                    event["impact_category"] = cls.get("impact_category")
                    event["severity"] = cls.get("severity", 1)
                    event["stage"] = cls.get("stage", "guidance")
                    event["direction"] = cls.get("direction", "mixed")
                    event["timeline"] = cls.get("timeline", "1_year")
                    event["specific_symbols"] = cls.get("specific_symbols", [])
                    event["rationale"] = cls.get("rationale", "")
                    # Jurisdiction: prefer LLM classification, fall back to fetcher tag
                    event["jurisdiction"] = cls.get("jurisdiction") or event.get("jurisdiction", "US")
                    classified.append(event)

        except Exception as e:
            logger.warning(f"Gemini classification batch error: {e}")

        time.sleep(AI_REG_GEMINI_DELAY)

    logger.info(f"Classified {len(classified)} significant events from {len(events)} total")
    return classified


# ═══════════════════════════════════════════════════════════════════════════
# SCORING ENGINE
# ═══════════════════════════════════════════════════════════════════════════


def _compute_symbol_scores(classified_events: list[dict]) -> dict[str, dict]:
    """Translate classified regulatory events into per-symbol scores.

    Scoring logic:
      - Severity weight: 1→0.2, 2→0.4, 3→0.7, 4→0.9, 5→1.0
      - Stage weight: guidance→0.3, proposed→0.5, final_rule→0.8, enforcement→0.9, enacted→1.0
      - Timeline discount: immediate→1.0, 6_months→0.8, 1_year→0.5, 2_plus_years→0.3
      - Direction: headwind→negative impact, tailwind→positive, mixed→half
      - Sector exposure multiplier from config (how much AI regulation matters to this sector)

    Returns: {symbol: {"score": 0-100, "events": [...], "event_count": N, "net_impact": float}}
    """
    # Load stock universe with sectors
    stocks = query("""
        SELECT symbol, sector FROM stock_universe
        WHERE symbol IS NOT NULL AND sector IS NOT NULL
    """)
    sector_map = {r["symbol"]: r["sector"] for r in stocks}

    # Stage weights
    stage_weights = {
        "guidance": 0.3, "proposed": 0.5, "final_rule": 0.8,
        "enforcement": 0.9, "enacted": 1.0,
    }

    # Timeline discount
    timeline_discount = {
        "immediate": 1.0, "6_months": 0.8, "1_year": 0.5, "2_plus_years": 0.3,
    }

    symbol_signals: dict[str, list[dict]] = {}

    for event in classified_events:
        cat = event.get("impact_category")
        if not cat or cat not in REGULATORY_IMPACT_MAP:
            continue

        impacts = REGULATORY_IMPACT_MAP[cat]
        severity = event.get("severity", 1)
        severity_w = AI_REG_SEVERITY_WEIGHTS.get(severity, 0.2)
        stage_w = stage_weights.get(event.get("stage", "guidance"), 0.3)
        timeline_w = timeline_discount.get(event.get("timeline", "1_year"), 0.5)
        direction = event.get("direction", "mixed")

        # Jurisdiction weight: how much this jurisdiction's regulation impacts US-listed stocks
        jurisdiction = event.get("jurisdiction", "US")
        jurisdiction_w = AI_REG_JURISDICTION_WEIGHTS.get(jurisdiction, 0.3)

        # Combined event weight — jurisdiction modulates international event importance
        event_weight = severity_w * stage_w * timeline_w * jurisdiction_w

        signal_info = {
            "title": event.get("title", "")[:100],
            "category": cat,
            "severity": severity,
            "stage": event.get("stage", ""),
            "direction": direction,
            "source": event.get("source", ""),
            "weight": round(event_weight, 3),
        }

        # Apply to all symbols in universe
        for symbol, sector in sector_map.items():
            impact = 0.0

            # Sector-level exposure
            sector_exposure = AI_REG_SECTOR_EXPOSURE.get(sector, 0.1)

            if sector in impacts.get("headwind_sectors", []):
                impact = -event_weight * sector_exposure * 0.6
            elif sector in impacts.get("tailwind_sectors", []):
                impact = event_weight * sector_exposure * 0.6

            # Direct symbol impact (stronger)
            if symbol in impacts.get("headwind_symbols", []):
                impact -= event_weight * 0.9
            if symbol in impacts.get("tailwind_symbols", []):
                impact += event_weight * 0.9

            # LLM-identified specific symbols
            if symbol in event.get("specific_symbols", []):
                if direction == "headwind":
                    impact -= event_weight * 0.8
                elif direction == "tailwind":
                    impact += event_weight * 0.8
                else:  # mixed
                    impact -= event_weight * 0.4

            # Flip for direction
            if direction == "tailwind":
                impact = abs(impact)
            elif direction == "mixed":
                impact *= 0.5

            if abs(impact) > 0.005:
                symbol_signals.setdefault(symbol, []).append({
                    **signal_info,
                    "impact": impact,
                })

    # Aggregate into 0-100 scores
    results = {}
    for symbol, signals in symbol_signals.items():
        net_impact = sum(s["impact"] for s in signals)
        event_count = len(set(s["title"] for s in signals))

        # Multiple regulatory events converging amplifies signal
        agreement_mult = min(1.5, 1.0 + (event_count - 1) * 0.1)

        # Convert net impact to 0-100 score
        # net_impact typically ranges from -2 to +2
        # Map: -1.5 → 0 (severe headwind), 0 → 50 (neutral), +1.5 → 100 (strong tailwind)
        raw_score = (net_impact / 1.5 + 1.0) / 2.0 * 100.0
        raw_score *= agreement_mult
        score = max(0.0, min(100.0, raw_score))

        # Only store if meaningfully different from neutral
        if abs(score - 50.0) > 3.0:
            results[symbol] = {
                "score": round(score, 2),
                "events": sorted(signals, key=lambda s: abs(s["impact"]), reverse=True)[:5],
                "event_count": event_count,
                "net_impact": round(net_impact, 4),
            }

    return results


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════


def _extract_date_from_snippet(snippet: str) -> str:
    """Try to extract a date from a news snippet. Returns today if none found."""
    # Try common date patterns
    patterns = [
        r"(\d{4}-\d{2}-\d{2})",
        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s+\d{4})",
    ]
    for pat in patterns:
        match = re.search(pat, snippet)
        if match:
            try:
                raw = match.group(1)
                if "-" in raw:
                    return raw
                for fmt in ("%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y"):
                    try:
                        return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
                    except ValueError:
                        continue
            except Exception:
                pass
    return date.today().isoformat()


# ═══════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════


def run():
    """Main entry: fetch regulatory data, classify, score, persist."""
    init_db()
    today = date.today().isoformat()

    print("\n" + "=" * 60)
    print("  AI REGULATORY INTELLIGENCE MODULE (GLOBAL)")
    print("=" * 60)

    # ── Step 1: Fetch from all global sources ──
    print("\n  Step 1: Fetching global regulatory developments...")

    all_events = []

    # ── US Sources (direct API + Serper) ──
    print("\n    ── US SOURCES ──")
    fr_events = _fetch_federal_register()
    all_events.extend(fr_events)
    print(f"    Federal Register: {len(fr_events)} documents")

    sec_events = _fetch_sec_ai_guidance()
    all_events.extend(sec_events)
    print(f"    SEC EDGAR: {len(sec_events)} documents")

    ftc_events = _fetch_ftc_ai_enforcement()
    all_events.extend(ftc_events)
    print(f"    FTC: {len(ftc_events)} results")

    state_events = _fetch_state_level_ai_laws()
    all_events.extend(state_events)
    print(f"    State-level: {len(state_events)} developments")

    sector_events = _fetch_sector_regulatory_news()
    all_events.extend(sector_events)
    print(f"    Sector-specific: {len(sector_events)} developments")

    # ── European Sources ──
    print("\n    ── EUROPEAN SOURCES ──")
    eu_events = _fetch_eu_ai_act()
    all_events.extend(eu_events)
    print(f"    EU AI Act: {len(eu_events)} developments")

    eu_dsa_events = _fetch_eu_dsa_dma()
    all_events.extend(eu_dsa_events)
    print(f"    EU DSA/DMA: {len(eu_dsa_events)} developments")

    uk_events = _fetch_uk_ai_regulation()
    all_events.extend(uk_events)
    print(f"    UK (AISI/FCA/ICO): {len(uk_events)} developments")

    # ── Asia-Pacific Sources ──
    print("\n    ── ASIA-PACIFIC SOURCES ──")
    china_events = _fetch_china_ai_regulation()
    all_events.extend(china_events)
    print(f"    China (CAC/MIIT): {len(china_events)} developments")

    apac_events = _fetch_asia_pacific_ai_regulation()
    all_events.extend(apac_events)
    print(f"    Japan/Korea/SG/AU: {len(apac_events)} developments")

    # ── Americas Sources ──
    print("\n    ── AMERICAS SOURCES ──")
    canada_events = _fetch_canada_ai_regulation()
    all_events.extend(canada_events)
    print(f"    Canada (AIDA): {len(canada_events)} developments")

    # ── Global Coordination ──
    print("\n    ── GLOBAL COORDINATION ──")
    global_events = _fetch_global_ai_coordination()
    all_events.extend(global_events)
    print(f"    G7/OECD/UN: {len(global_events)} developments")

    # Jurisdiction summary
    jurisdictions = {}
    for ev in all_events:
        j = ev.get("jurisdiction", "US")
        jurisdictions[j] = jurisdictions.get(j, 0) + 1
    jurisdiction_str = ", ".join(f"{k}={v}" for k, v in sorted(jurisdictions.items(), key=lambda x: -x[1]))
    print(f"\n  Total raw events: {len(all_events)} ({jurisdiction_str})")

    if not all_events:
        print("  No regulatory events found — sources may be down")
        return

    # ── Step 2: Classify via Gemini ──
    print("\n  Step 2: Classifying events for financial significance...")
    classified = _classify_events_batch(all_events)
    if not classified:
        print("  No significant AI regulatory events found")
        return

    # Print classified events with jurisdiction
    print(f"\n  SIGNIFICANT EVENTS ({len(classified)}):")
    print(f"  {'Source':<12} {'Jur':>4} {'Sev':>3} {'Stage':<12} {'Category':<28} {'Title':<45}")
    print(f"  {'-'*108}")
    for ev in sorted(classified, key=lambda x: x.get("severity", 0), reverse=True)[:15]:
        title = ev["title"][:44]
        cat = ev.get("impact_category", "")[:27]
        jur = ev.get("jurisdiction", "US")[:4]
        print(f"  {ev['source']:<12} {jur:>4} {ev.get('severity',0):>3} {ev.get('stage',''):<12} {cat:<28} {title}")

    # Jurisdiction breakdown of classified events
    classified_jurisdictions = {}
    for ev in classified:
        j = ev.get("jurisdiction", "US")
        classified_jurisdictions[j] = classified_jurisdictions.get(j, 0) + 1
    jur_str = ", ".join(f"{k}={v}" for k, v in sorted(classified_jurisdictions.items(), key=lambda x: -x[1]))
    print(f"\n  Classified by jurisdiction: {jur_str}")

    # ── Step 3: Compute per-symbol scores ──
    print("\n  Step 3: Computing symbol-level regulatory scores...")
    symbol_scores = _compute_symbol_scores(classified)
    if not symbol_scores:
        print("  No symbol scores generated")
        return

    # ── Step 4: Persist signals ──
    signal_rows = []
    for symbol, data in symbol_scores.items():
        # Build narrative from top events
        top_events = data["events"][:3]
        narrative_parts = []
        for ev in top_events:
            dir_word = "headwind" if ev["impact"] < 0 else "tailwind"
            narrative_parts.append(
                f"[{ev['source'].upper()}] {ev['title'][:60]} (sev={ev['severity']}, {dir_word})"
            )
        narrative = "; ".join(narrative_parts)

        signal_rows.append((
            symbol, today, round(data["score"], 2),
            data["event_count"], round(data["net_impact"], 4),
            "active", narrative[:500],
        ))

    if signal_rows:
        upsert_many(
            "regulatory_signals",
            ["symbol", "date", "reg_score", "event_count",
             "net_impact", "status", "narrative"],
            signal_rows,
        )

    # Persist classified events for audit trail
    event_rows = []
    for ev in classified:
        event_rows.append((
            ev.get("doc_id", ev.get("url", ""))[:128],
            today,
            ev.get("source", ""),
            ev.get("title", "")[:300],
            ev.get("abstract", "")[:500],
            ev.get("date", today),
            ev.get("doc_type", ""),
            ev.get("agencies", ""),
            ev.get("impact_category", ""),
            ev.get("severity", 1),
            ev.get("stage", "guidance"),
            ev.get("direction", "mixed"),
            ev.get("timeline", "1_year"),
            json.dumps(ev.get("specific_symbols", [])),
            ev.get("rationale", "")[:300],
            ev.get("url", ""),
            ev.get("jurisdiction", "US"),
        ))

    if event_rows:
        upsert_many(
            "regulatory_events",
            ["event_id", "date", "source", "title", "abstract",
             "event_date", "doc_type", "agencies", "impact_category",
             "severity", "stage", "direction", "timeline",
             "specific_symbols", "rationale", "url", "jurisdiction"],
            event_rows,
        )

    # ── Summary ──
    headwind = sum(1 for d in symbol_scores.values() if d["score"] < 45)
    tailwind = sum(1 for d in symbol_scores.values() if d["score"] > 55)
    neutral = len(symbol_scores) - headwind - tailwind

    print(f"\n  Results: {len(symbol_scores)} symbols scored from {len(classified)} events")
    print(f"  Headwind: {headwind} | Neutral: {neutral} | Tailwind: {tailwind}")

    # Top headwinds
    top_headwind = sorted(
        [(s, d) for s, d in symbol_scores.items() if d["score"] < 45],
        key=lambda x: x[1]["score"]
    )[:10]
    top_tailwind = sorted(
        [(s, d) for s, d in symbol_scores.items() if d["score"] > 55],
        key=lambda x: x[1]["score"], reverse=True
    )[:10]

    if top_headwind:
        print(f"\n  TOP REGULATORY HEADWINDS:")
        print(f"  {'Symbol':<8} {'Score':>6} {'Events':>7} {'Net Impact':>11}")
        for sym, data in top_headwind:
            print(f"  {sym:<8} {data['score']:>6.1f} {data['event_count']:>7} {data['net_impact']:>+11.3f}")

    if top_tailwind:
        print(f"\n  TOP REGULATORY TAILWINDS:")
        print(f"  {'Symbol':<8} {'Score':>6} {'Events':>7} {'Net Impact':>11}")
        for sym, data in top_tailwind:
            print(f"  {sym:<8} {data['score']:>6.1f} {data['event_count']:>7} {data['net_impact']:>+11.3f}")

    print(f"\n  Regulatory Intelligence complete: {len(signal_rows)} signals, {len(event_rows)} events persisted")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
