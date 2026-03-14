"""Founder Vision & Capital Allocation Analyzer.

Identifies Bezos-quality thinking in CEO annual letters before the market prices it in.

The insight: Amazon's 1997 income statement was all red. The only tell was Bezos'
shareholder letter — clarity of thought, long-term orientation, specific theory of value
creation. AI can now systematically apply that lens to hundreds of companies.

Data fetching cascade (in order):
  1. SEC EDGAR EX-13 (Annual Report to Shareholders exhibit)
  2. SEC EDGAR 10-K main document (letter section extracted)
  3. Firecrawl — company IR page scrape
  4. Serper search + Firecrawl fetch

Scoring: 8 dimensions calibrated against Bezos/Buffett/Singleton exemplars.
Each score requires evidence (specific quote from the letter). No black boxes.

YoY trajectory is a standalone alpha signal: improving letters = management quality
rising, deteriorating letters = leading indicator of underperformance.
"""

import sys
import json
import re
import time
import argparse
import requests
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from tools.config import (
    GEMINI_API_KEY, GEMINI_BASE, GEMINI_MODEL,
    FIRECRAWL_API_KEY, SERPER_API_KEY,
)
from tools.db import init_db, upsert_many, query


# ── Constants ─────────────────────────────────────────────────────────

EDGAR_HEADERS = {
    "User-Agent": "Druckemiller Alpha System trading-research@druckemiller.local",
    "Accept-Encoding": "gzip, deflate",
}
EDGAR_BASE = "https://data.sec.gov"
EDGAR_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

LETTERS_DIR = Path(_project_root) / ".tmp" / "letters"
CIK_CACHE_PATH = Path(_project_root) / ".tmp" / "edgar_cik_cache.json"

MIN_LETTER_CHARS = 500
MAX_LETTER_CHARS = 40_000  # ~8000 words — fits Gemini Flash context

TIER_NUMERIC = {
    "bezos_tier": 5,
    "buffett_tier": 4,
    "above_average": 3,
    "average": 2,
    "bureaucratic": 1,
    "red_flags": 0,
}
TRAJECTORY_NUMERIC = {
    "improved": 1,
    "consistent": 0,
    "shifted": -1,
    "concerning_shift": -2,
}

# Dimension weights for composite score
DIMENSION_WEIGHTS = {
    "capital_allocation_score": 0.20,   # Highest — what we're measuring
    "long_term_score":          0.15,
    "failure_attribution_score": 0.15,  # Hardest to fake
    "moat_articulation_score":  0.15,
    "vision_specificity_score": 0.10,
    "customer_value_score":     0.10,
    "intellectual_honesty_score": 0.10,
    "founder_mindset_score":    0.05,
}

# Letter section start patterns
LETTER_HEADER_PATTERNS = [
    r'dear\s+(?:fellow\s+)?shareholders?',
    r'to\s+our\s+shareholders?',
    r'letter\s+to\s+(?:our\s+)?shareholders?',
    r'letter\s+from\s+(?:the\s+)?(?:chairman|ceo|chief\s+executive)',
    r'from\s+(?:the\s+)?(?:chairman|president)\s+and\s+(?:chief\s+executive|ceo)',
    r'to\s+our\s+stockholders',
]
LETTER_END_PATTERNS = [
    r'\bpart\s+i\b',
    r'\bitem\s+1[.\s]',
    r'\bbusiness\s+overview\b',
    r'\bmanagement.s\s+discussion',
    r'\bforward[-\s]looking\s+statements?\b',
    r'\btable\s+of\s+contents\b',
]


# ── HTML Text Extraction ───────────────────────────────────────────────

class _TextExtractor(HTMLParser):
    """Extract visible text from HTML, filtering boilerplate tags."""
    _SKIP_TAGS = {"script", "style", "head", "meta", "link"}

    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self._skip_tag = None
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            self.parts.append(data)


def clean_html(raw):
    """Extract clean text from HTML or plain text."""
    if not raw:
        return ""
    if not raw.strip().startswith("<"):
        # Already plain text — just normalize whitespace
        return re.sub(r'\s+', ' ', raw).strip()

    extractor = _TextExtractor()
    try:
        extractor.feed(raw)
    except Exception:
        # Fall back to simple tag strip
        raw = re.sub(r'<[^>]+>', ' ', raw)
    text = " ".join(extractor.parts)

    # Decode common HTML entities
    replacements = {
        "&amp;": "&", "&nbsp;": " ", "&lt;": "<", "&gt;": ">",
        "&ldquo;": '"', "&rdquo;": '"', "&lsquo;": "'", "&rsquo;": "'",
        "&mdash;": "—", "&ndash;": "–", "&hellip;": "...",
        "&#8220;": '"', "&#8221;": '"', "&#8216;": "'", "&#8217;": "'",
        "&#8212;": "—", "&#8211;": "–", "&#160;": " ",
    }
    for entity, char in replacements.items():
        text = text.replace(entity, char)

    # Normalize whitespace; collapse 3+ newlines to 2
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def extract_letter_section(full_text):
    """Extract the shareholder letter section from a longer 10-K document."""
    text_lower = full_text.lower()

    # Find start of letter
    start_idx = -1
    for pattern in LETTER_HEADER_PATTERNS:
        m = re.search(pattern, text_lower)
        if m:
            start_idx = max(0, m.start() - 20)
            break

    if start_idx == -1:
        return None

    # Find end of letter (stop at next major section)
    search_start = start_idx + 200
    end_idx = len(full_text)
    for pattern in LETTER_END_PATTERNS:
        m = re.search(pattern, text_lower[search_start:])
        if m:
            candidate = search_start + m.start()
            if candidate < end_idx and (candidate - start_idx) > 500:
                end_idx = candidate

    extracted = full_text[start_idx:end_idx].strip()
    return extracted if len(extracted) >= MIN_LETTER_CHARS else None


def truncate_letter(text, max_chars=MAX_LETTER_CHARS):
    """Take first 25k + last 15k chars for Gemini — preserves opening thesis and closing outlook."""
    if len(text) <= max_chars:
        return text
    front = text[:25_000]
    back = text[-15_000:]
    return front + "\n\n[... MIDDLE SECTION TRUNCATED FOR BREVITY ...]\n\n" + back


# ── CIK Lookup ────────────────────────────────────────────────────────

def get_cik_map():
    """Load ticker->CIK map from SEC. Cache for 30 days."""
    import json as _json

    if CIK_CACHE_PATH.exists():
        mtime = CIK_CACHE_PATH.stat().st_mtime
        age_days = (time.time() - mtime) / 86400
        if age_days < 30:
            return _json.loads(CIK_CACHE_PATH.read_text())

    try:
        resp = requests.get(EDGAR_TICKERS_URL, headers=EDGAR_HEADERS, timeout=20)
        resp.raise_for_status()
        raw = resp.json()
        cik_map = {v["ticker"].upper(): str(v["cik_str"]).zfill(10)
                   for v in raw.values()}
        CIK_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CIK_CACHE_PATH.write_text(_json.dumps(cik_map))
        return cik_map
    except Exception as e:
        print(f"  EDGAR CIK map fetch failed: {e}")
        return {}


def get_cik(symbol):
    """Return zero-padded 10-digit CIK string for a ticker, or None."""
    # Handle BRK.B -> BRK-B style variations
    candidates = [symbol.upper(), symbol.upper().replace("-", "."),
                  symbol.upper().replace(".", "-")]
    cik_map = get_cik_map()
    for candidate in candidates:
        if candidate in cik_map:
            return cik_map[candidate]
    return None


# ── EDGAR Fetching ────────────────────────────────────────────────────

def _edgar_get(url, stream=False, timeout=20):
    """GET request to EDGAR with rate-limit courtesy sleep."""
    time.sleep(0.12)
    try:
        resp = requests.get(url, headers=EDGAR_HEADERS, timeout=timeout, stream=stream)
        resp.raise_for_status()
        return resp
    except Exception:
        return None


def get_10k_filings(cik, years):
    """Return list of (year, accession_no, primary_doc) for 10-K filings matching years."""
    url = f"{EDGAR_BASE}/submissions/CIK{cik}.json"
    resp = _edgar_get(url)
    if not resp:
        return []

    data = resp.json()
    results = []

    def _parse_filings_block(block):
        forms = block.get("form", [])
        dates = block.get("filingDate", [])
        accessions = block.get("accessionNumber", [])
        primary_docs = block.get("primaryDocument", [])
        for form, date, acc, doc in zip(forms, dates, accessions, primary_docs):
            if form not in ("10-K", "10-K/A"):
                continue
            try:
                filing_year = int(date[:4])
            except (ValueError, TypeError):
                continue
            if filing_year in years or (filing_year - 1) in years:
                results.append((filing_year, acc, doc))

    recent = data.get("filings", {}).get("recent", {})
    _parse_filings_block(recent)

    # Check paginated filings for large filers
    for extra_file in data.get("filings", {}).get("files", [])[:3]:
        extra_url = f"https://data.sec.gov/{extra_file['name']}"
        extra_resp = _edgar_get(extra_url)
        if extra_resp:
            _parse_filings_block(extra_resp.json())

    return results


def fetch_edgar_ex13(cik, year):
    """Try to fetch EX-13 (Annual Report to Shareholders) exhibit from EDGAR."""
    years_to_check = {year, year + 1}  # 10-K filed in Q1 of year+1 covers year
    filings = get_10k_filings(cik, years_to_check)

    for _filing_year, acc, _doc in filings:
        # Build filing index URL
        acc_clean = acc.replace("-", "")
        cik_int = int(cik)
        index_url = (f"https://www.sec.gov/Archives/edgar/data/{cik_int}/"
                     f"{acc_clean}/{acc}-index.htm")

        # Try JSON index (more reliable)
        json_index_url = (f"https://data.sec.gov/Archives/edgar/data/{cik_int}/"
                          f"{acc_clean}/index.json")
        resp = _edgar_get(json_index_url)
        if not resp:
            continue

        try:
            index_data = resp.json()
        except Exception:
            continue

        # Look for EX-13 document
        for item in index_data.get("directory", {}).get("item", []):
            doc_type = item.get("type", "").upper()
            doc_name = item.get("name", "")
            if doc_type in ("EX-13", "EX-13.1", "EX-13.2") or "EX-13" in doc_type:
                doc_url = (f"https://www.sec.gov/Archives/edgar/data/{cik_int}/"
                           f"{acc_clean}/{doc_name}")
                doc_resp = _edgar_get(doc_url, timeout=30)
                if doc_resp:
                    text = clean_html(doc_resp.text)
                    if len(text) >= MIN_LETTER_CHARS:
                        # Try to isolate the letter section
                        letter = extract_letter_section(text) or text[:MAX_LETTER_CHARS]
                        return letter

    return None


def fetch_edgar_10k_letter(cik, year):
    """Extract letter section from the main 10-K document."""
    years_to_check = {year, year + 1}
    filings = get_10k_filings(cik, years_to_check)

    for _filing_year, acc, primary_doc in filings:
        if not primary_doc:
            continue
        acc_clean = acc.replace("-", "")
        cik_int = int(cik)
        doc_url = (f"https://www.sec.gov/Archives/edgar/data/{cik_int}/"
                   f"{acc_clean}/{primary_doc}")
        resp = _edgar_get(doc_url, timeout=45)
        if not resp:
            continue

        text = clean_html(resp.text)
        letter = extract_letter_section(text)
        if letter and len(letter) >= MIN_LETTER_CHARS:
            return letter

    return None


def fetch_firecrawl(url):
    """Fetch and extract text from a URL using Firecrawl."""
    if not FIRECRAWL_API_KEY:
        return None
    try:
        resp = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers={"Authorization": f"Bearer {FIRECRAWL_API_KEY}",
                     "Content-Type": "application/json"},
            json={"url": url, "formats": ["markdown"]},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("data", {}).get("markdown", "")
        return content if content else None
    except Exception:
        return None


def fetch_ir_page(symbol, company_name):
    """Try to scrape company IR page via Firecrawl."""
    # Common IR URL patterns
    ir_urls = [
        f"https://ir.{company_name.lower().replace(' ', '').replace(',', '')[:15]}.com",
        f"https://investor.{symbol.lower()}.com",
        f"https://investors.{symbol.lower()}.com",
    ]
    for url in ir_urls:
        content = fetch_firecrawl(url)
        if content and len(content) > MIN_LETTER_CHARS:
            letter = extract_letter_section(content)
            if letter:
                return letter
    return None


def fetch_serper_letter(symbol, company_name, year):
    """Search for the letter via Serper, then fetch with Firecrawl."""
    if not SERPER_API_KEY or not FIRECRAWL_API_KEY:
        return None

    queries = [
        f'"{company_name}" annual shareholder letter {year}',
        f'"{company_name}" CEO letter to shareholders {year} annual report',
    ]

    for query in queries:
        try:
            resp = requests.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                json={"q": query, "num": 5},
                timeout=15,
            )
            resp.raise_for_status()
            results = resp.json().get("organic", [])
        except Exception:
            continue

        for result in results:
            link = result.get("link", "")
            if not link:
                continue
            # Skip non-useful sources
            if any(skip in link for skip in ["wikipedia", "linkedin", "twitter", "reddit"]):
                continue
            content = fetch_firecrawl(link)
            if not content or len(content) < MIN_LETTER_CHARS:
                continue
            letter = extract_letter_section(content)
            if letter and len(letter) >= MIN_LETTER_CHARS:
                return letter

    return None


def fetch_letter(symbol, year, company_name=None):
    """Multi-strategy letter fetch. Returns (text, source) or (None, None)."""
    LETTERS_DIR.mkdir(parents=True, exist_ok=True)
    text_cache = LETTERS_DIR / f"{symbol}_{year}.txt"
    src_cache = LETTERS_DIR / f"{symbol}_{year}.source"

    # Return cached version — letters are immutable once published
    if text_cache.exists() and text_cache.stat().st_size >= MIN_LETTER_CHARS:
        source = src_cache.read_text().strip() if src_cache.exists() else "cached"
        return text_cache.read_text(), source

    name = company_name or symbol
    text, source = None, None

    # Strategy 1: EDGAR EX-13 (richest — Bezos' letters live here)
    cik = get_cik(symbol)
    if cik:
        print(f"      Trying EDGAR EX-13 (CIK {cik})...")
        text = fetch_edgar_ex13(cik, year)
        if text:
            source = "edgar_ex13"

    # Strategy 2: EDGAR 10-K letter section
    if not text and cik:
        print(f"      Trying EDGAR 10-K letter section...")
        text = fetch_edgar_10k_letter(cik, year)
        if text:
            source = "edgar_10k"

    # Strategy 3: Firecrawl IR page
    if not text and FIRECRAWL_API_KEY:
        print(f"      Trying Firecrawl IR page...")
        text = fetch_ir_page(symbol, name)
        if text:
            source = "firecrawl"

    # Strategy 4: Serper search + Firecrawl
    if not text and SERPER_API_KEY and FIRECRAWL_API_KEY:
        print(f"      Trying Serper search...")
        text = fetch_serper_letter(symbol, name, year)
        if text:
            source = "serper"

    if text and len(text) >= MIN_LETTER_CHARS:
        text_cache.write_text(text)
        src_cache.write_text(source)
        return text, source

    return None, None


# ── Gemini Analysis ───────────────────────────────────────────────────

def build_gemini_prompt(text, symbol, year, prior_thesis=None):
    """Build the calibrated analysis prompt."""
    prior_context = ""
    if prior_thesis:
        prior_context = (
            f"\nPRIOR YEAR ({year - 1}) THESIS SUMMARY (use for consistency_with_prior):\n"
            f"{prior_thesis}\n"
        )

    truncated = truncate_letter(text)

    return f"""You are a master investor analyzing a CEO annual shareholder letter for capital allocation quality.
Your scoring framework is calibrated against the highest-quality letters ever written.

## CALIBRATION EXEMPLARS

### What a 10/10 looks like (Jeff Bezos, Amazon 1997):
- Long-term: "We believe that a fundamental measure of our success will be the shareholder value we create over the LONG TERM. This value will be a direct result of our ability to extend and solidify our current market leadership position... we will make bold investment decisions in favor of future value creation where we see a sufficient probability of gaining market leadership advantages."
- Capital allocation: "We will continue to make investment decisions in light of long-term market leadership considerations rather than short-term profitability considerations or short-term Wall Street reactions." [Then explains exactly what that means for each investment]
- Honest failure: Names what didn't work, takes personal ownership, extracts the lesson.
- Vision: "Get big fast" — specific, falsifiable, directional. You could prove him wrong in 5 years.

### What a 9/10 looks like (Warren Buffett, Berkshire):
- Honest failure: "I made a number of mistakes last year... I was wrong about [specific thing] because [specific reason]. My mistake cost shareholders approximately $X."
- Moat: Explains the MECHANISM — not "great team" but the specific economic flywheel.
- Capital allocation: Explicit discussion of opportunity cost, ROIC hurdle rates, why buybacks make sense at specific valuations.

### What a 5/10 looks like (average S&P 500 CEO):
- "We remain committed to creating value for all stakeholders as we execute on our strategy."
- Revenue, EPS, "navigated headwinds." Nothing specific. Nothing falsifiable. No failures mentioned.

### What a 2/10 looks like (bureaucratic/red flag):
- Pure financial results with no forward thinking.
- "Despite macro uncertainty and supply chain disruptions..." (always external blame)
- Every result is framed as a win. Nothing went wrong. Ever.
- Dense buzzwords: "leverage synergies," "optimize our portfolio," "unlock value."

---

## COMPANY AND LETTER

Company: {symbol}
Year: {year}{prior_context}

## YOUR TASK

Score 8 dimensions 0-10. For EVERY score, provide:
1. The exact quote from THIS letter (not exemplars) that most influenced your score
2. Brief reasoning

If you cannot find evidence for a dimension, score conservatively (4-5) and note "no evidence found."

---

## LETTER TEXT

{truncated}

---

## REQUIRED OUTPUT FORMAT

Return ONLY a valid JSON object (no markdown, no code fences, no explanation):
{{
  "long_term_score": <0-10>,
  "long_term_evidence": "<direct quote from THIS letter>",
  "long_term_reasoning": "<why this score>",

  "capital_allocation_score": <0-10>,
  "capital_allocation_evidence": "<direct quote>",
  "capital_allocation_reasoning": "<why this score>",

  "customer_value_score": <0-10>,
  "customer_value_evidence": "<direct quote>",
  "customer_value_reasoning": "<why this score>",

  "failure_attribution_score": <0-10>,
  "failure_attribution_evidence": "<direct quote or 'no failure discussion found'>",
  "failure_attribution_reasoning": "<why this score>",

  "vision_specificity_score": <0-10>,
  "vision_specificity_evidence": "<direct quote>",
  "vision_specificity_reasoning": "<why this score>",

  "moat_articulation_score": <0-10>,
  "moat_articulation_evidence": "<direct quote>",
  "moat_articulation_reasoning": "<why this score>",

  "intellectual_honesty_score": <0-10>,
  "intellectual_honesty_evidence": "<direct quote>",
  "intellectual_honesty_reasoning": "<why this score>",

  "founder_mindset_score": <0-10>,
  "founder_mindset_evidence": "<direct quote>",
  "founder_mindset_reasoning": "<why this score>",

  "red_flags": [
    "<specific pattern with quote — e.g. chronic external blame, strategy pivot without explanation>"
  ],

  "exceptional_passages": [
    "<verbatim passage that demonstrates Bezos-level thinking — include only if genuinely exceptional>"
  ],

  "concerning_passages": [
    "<verbatim passage that is generic, bureaucratic, or concerning>"
  ],

  "thesis_summary": "<4-6 sentences: what does this CEO believe? What is their theory of value creation? What makes them distinctive OR undistinctive? Be specific and direct.>",

  "consistency_with_prior": <"improved" | "consistent" | "shifted" | "concerning_shift" | null>,
  "consistency_reasoning": "<explanation of trajectory vs prior year, or null>",

  "investor_verdict": "<2-3 sentences: direct, critical assessment — would a legendary long-term investor be intrigued by this management team based on this letter alone? Why or why not?>"
}}

## SCORING GUIDE (brief)

- **Long-term (0-10):** 9+=explicit multi-year framing + sacrifice current earnings for future value. 5=mixed. 1-2=pure quarterly reporting tone.
- **Capital allocation (0-10):** 9+=every investment explained with expected returns + opportunity cost discussed. 5=some rationale. 1-2=financial summary only.
- **Customer/value (0-10):** 9+=obsessed with end-user outcomes, specific customer metrics. 5=mentioned. 1-2=pure financial framing.
- **Failure attribution (0-10):** 9+=names 2+ specific failures + personal responsibility + learnings. 5=vague acknowledgment. 0-2=zero failures mentioned or pure external blame.
- **Vision specificity (0-10):** 9+=falsifiable 5-year commitments. 5=general direction. 1-2=no discernible strategy beyond "grow."
- **Moat articulation (0-10):** 9+=explains causal mechanism of WHY they win (not "great people"). 5=competitive position mentioned. 1-2=platitudes only.
- **Intellectual honesty (0-10):** 9+=distinguishes know vs. believe, acknowledges genuine uncertainty. 5=mildly hedged. 1-2=everything certain, no risks.
- **Founder mindset (0-10):** 9+=talks like owner, loves the business, decades-long orientation. 5=professional management tone. 1-2=pure bureaucratic language."""


def call_gemini(prompt):
    """Call Gemini API and return parsed JSON dict."""
    if not GEMINI_API_KEY:
        return {}

    for attempt in range(2):
        try:
            resp = requests.post(
                f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent",
                params={"key": GEMINI_API_KEY},
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"temperature": 0.1}},
                timeout=60,
            )
            resp.raise_for_status()
            content = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

            # Strip markdown fences
            content = re.sub(r'^```(?:json)?\s*', '', content)
            content = re.sub(r'\s*```$', '', content)

            return json.loads(content)
        except json.JSONDecodeError:
            if attempt == 0:
                time.sleep(2)
                continue
            print(f"      Gemini JSON parse failed after 2 attempts")
            return {}
        except Exception as e:
            print(f"      Gemini error: {e}")
            return {}

    return {}


# ── Scoring ───────────────────────────────────────────────────────────

def compute_composite(analysis):
    """Weighted composite 0-100 from 8 dimension scores."""
    total = 0.0
    for dim, weight in DIMENSION_WEIGHTS.items():
        score = analysis.get(dim, 5)
        if score is None:
            score = 5
        total += float(score) * weight * 10  # 0-10 score → 0-100 range
    return round(min(100.0, max(0.0, total)), 1)


def score_to_tier(composite):
    if composite >= 85:
        return "bezos_tier"
    if composite >= 70:
        return "buffett_tier"
    if composite >= 55:
        return "above_average"
    if composite >= 40:
        return "average"
    if composite >= 25:
        return "bureaucratic"
    return "red_flags"


TIER_LABELS = {
    "bezos_tier":    "BEZOS-TIER",
    "buffett_tier":  "BUFFETT-TIER",
    "above_average": "ABOVE AVERAGE",
    "average":       "AVERAGE",
    "bureaucratic":  "BUREAUCRATIC",
    "red_flags":     "RED FLAGS",
}


# ── Persistence ───────────────────────────────────────────────────────

def save_to_db(symbol, year, source, letter_text, analysis, composite, tier):
    """Persist analysis results to letter_analysis and fundamentals tables."""
    # letter_analysis table row
    row = (
        symbol, year, source,
        datetime.now().strftime("%Y-%m-%d"),
        composite,
        analysis.get("long_term_score"),
        analysis.get("capital_allocation_score"),
        analysis.get("customer_value_score"),
        analysis.get("failure_attribution_score"),
        analysis.get("vision_specificity_score"),
        analysis.get("moat_articulation_score"),
        analysis.get("intellectual_honesty_score"),
        analysis.get("founder_mindset_score"),
        tier,
        json.dumps(analysis.get("red_flags", [])),
        json.dumps(analysis.get("exceptional_passages", [])),
        json.dumps(analysis.get("concerning_passages", [])),
        analysis.get("thesis_summary", ""),
        analysis.get("consistency_with_prior"),
        analysis.get("investor_verdict", ""),
        letter_text[:500],
    )

    upsert_many("letter_analysis",
                ["symbol", "year", "source", "letter_date", "composite_score",
                 "long_term_score", "capital_allocation_score", "customer_value_score",
                 "failure_attribution_score", "vision_specificity_score",
                 "moat_articulation_score", "intellectual_honesty_score",
                 "founder_mindset_score", "tier", "red_flags", "exceptional_passages",
                 "concerning_passages", "thesis_summary", "consistency_with_prior",
                 "investor_verdict", "letter_preview"],
                [row])

    # Cross-pipeline fundamentals metrics
    consistency = analysis.get("consistency_with_prior")
    fund_rows = [
        (symbol, "letter_composite_score", composite),
        (symbol, "letter_tier", TIER_NUMERIC.get(tier, 2)),
        (symbol, "letter_yoy_trajectory", TRAJECTORY_NUMERIC.get(consistency, 0)),
    ]
    upsert_many("fundamentals", ["symbol", "metric", "value"], fund_rows)


# ── Main Run ──────────────────────────────────────────────────────────

def run(symbols=None, years=None, force=False, no_llm=False):
    """Run founder letter analysis for specified symbols and years."""
    init_db()

    if not GEMINI_API_KEY and not no_llm:
        print("  WARNING: GEMINI_API_KEY not set. Running in quantitative-only mode.")
        no_llm = True

    # Default symbols: current BUY/STRONG BUY signals
    if symbols is None:
        buy_signals = query(
            "SELECT DISTINCT symbol FROM signals WHERE signal IN ('BUY', 'STRONG BUY') "
            "AND date = (SELECT MAX(date) FROM signals)"
        )
        if buy_signals:
            symbols = [r["symbol"] for r in buy_signals]
            print(f"Analyzing founder letters for {len(symbols)} BUY/STRONG BUY signals...")
        else:
            symbols = [r["symbol"] for r in query(
                "SELECT symbol FROM stock_universe LIMIT 50")]
            print(f"No active signals. Analyzing first 50 universe stocks...")

    # Default years: last completed fiscal year
    if years is None:
        current_year = datetime.now().year
        years = [current_year - 1]
        if datetime.now().month >= 4:  # Letters usually out by April
            years.append(current_year)

    print(f"  Years: {years} | LLM: {'disabled' if no_llm else 'Gemini'}")

    # Fetch company names from universe for Serper queries
    universe = {r["symbol"]: r.get("name", r["symbol"])
                for r in query("SELECT symbol, name FROM stock_universe")}

    # Results tracking
    by_tier = {tier: [] for tier in TIER_NUMERIC}
    by_tier["no_letter"] = []

    for i, symbol in enumerate(symbols):
        company_name = universe.get(symbol, symbol)

        for year in years:
            print(f"\n  [{i+1}/{len(symbols)}] {symbol} ({year})...")

            # Cache check
            if not force:
                existing = query(
                    "SELECT composite_score, tier FROM letter_analysis WHERE symbol=? AND year=?",
                    [symbol, year]
                )
                if existing:
                    score = existing[0]["composite_score"]
                    tier = existing[0]["tier"]
                    label = TIER_LABELS.get(tier, tier.upper())
                    print(f"      Cached: {score:.0f} [{label}] (use --force to re-run)")
                    if score is not None:
                        by_tier.get(tier, by_tier["average"]).append(
                            (symbol, score, None, tier))
                    continue

            # Fetch letter
            letter_text, source = fetch_letter(symbol, year, company_name)

            if not letter_text:
                print(f"      No letter found (all 4 strategies failed)")
                by_tier["no_letter"].append(symbol)
                continue

            print(f"      Found via {source} ({len(letter_text):,} chars)")

            if no_llm:
                print(f"      LLM disabled — letter cached, no scoring")
                continue

            # Get prior year thesis for YoY comparison
            prior_thesis = None
            prior_data = query(
                "SELECT thesis_summary FROM letter_analysis WHERE symbol=? AND year=?",
                [symbol, year - 1]
            )
            if prior_data and prior_data[0].get("thesis_summary"):
                prior_thesis = prior_data[0]["thesis_summary"]

            # Gemini analysis
            print(f"      Running Gemini analysis...")
            prompt = build_gemini_prompt(letter_text, symbol, year, prior_thesis)
            analysis = call_gemini(prompt)
            time.sleep(1.5)  # Rate limit

            if not analysis:
                print(f"      Gemini returned empty — skipping")
                continue

            # Score and save
            composite = compute_composite(analysis)
            tier = score_to_tier(composite)
            save_to_db(symbol, year, source, letter_text, analysis, composite, tier)

            # Extract key scores for display
            cap_alloc = analysis.get("capital_allocation_score", "?")
            failure = analysis.get("failure_attribution_score", "?")
            long_term = analysis.get("long_term_score", "?")
            trajectory = analysis.get("consistency_with_prior", "—")
            verdict = analysis.get("investor_verdict", "")[:120]
            label = TIER_LABELS.get(tier, tier.upper())

            print(f"      Score: {composite:.0f} [{label}]")
            print(f"      CapAlloc: {cap_alloc} | Failure: {failure} | LongTerm: {long_term}")
            if trajectory:
                print(f"      YoY: {trajectory}")
            if verdict:
                print(f"      Verdict: {verdict}...")

            by_tier.get(tier, by_tier["average"]).append(
                (symbol, composite, analysis.get("investor_verdict", ""), tier))

    # ── Summary ──────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("FOUNDER LETTER ANALYSIS COMPLETE")
    print("=" * 70)

    for tier_key in ["bezos_tier", "buffett_tier", "above_average", "average",
                     "bureaucratic", "red_flags"]:
        stocks = by_tier.get(tier_key, [])
        if not stocks:
            continue
        label = TIER_LABELS[tier_key]
        print(f"\n  {label} ({len(stocks)} stocks):")
        for sym, score, verdict, _ in sorted(stocks, key=lambda x: x[1], reverse=True):
            v_short = f'"{verdict[:80]}..."' if verdict else ""
            print(f"    {sym:12s} | {score:5.0f} | {v_short}")

    no_letter = by_tier.get("no_letter", [])
    if no_letter:
        print(f"\n  NO LETTER FOUND ({len(no_letter)} stocks): {', '.join(no_letter[:20])}")

    # The trifecta: top candidates with clean forensics + variant score
    print("\n" + "─" * 70)
    print("  TRIFECTA CANDIDATES (Bezos/Buffett-tier + BUY signal):")
    trifecta = query("""
        SELECT la.symbol, la.tier, la.composite_score as letter_score,
               s.signal, s.composite_score as signal_score,
               f_f.value as forensic_score, f_v.value as variant_score,
               f_u.value as upside_pct
        FROM letter_analysis la
        JOIN signals s ON la.symbol = s.symbol
            AND s.date = (SELECT MAX(date) FROM signals)
        LEFT JOIN fundamentals f_f ON la.symbol = f_f.symbol
            AND f_f.metric = 'forensic_score'
        LEFT JOIN fundamentals f_v ON la.symbol = f_v.symbol
            AND f_v.metric = 'variant_score'
        LEFT JOIN fundamentals f_u ON la.symbol = f_u.symbol
            AND f_u.metric = 'variant_upside_pct'
        WHERE la.tier IN ('bezos_tier', 'buffett_tier', 'above_average')
            AND s.signal IN ('BUY', 'STRONG BUY')
            AND COALESCE(f_f.value, 50) >= 55
        ORDER BY la.composite_score DESC
        LIMIT 15
    """)

    if trifecta:
        print(f"    {'Symbol':12s} | {'Tier':16s} | {'LetterScore':>10s} | "
              f"{'Signal':>11s} | {'Forensics':>9s} | {'Variant':>7s} | {'Upside%':>7s}")
        print(f"    {'-'*12}-+-{'-'*16}-+-{'-'*10}-+-{'-'*11}-+-{'-'*9}-+-{'-'*7}-+-{'-'*7}")
        for r in trifecta:
            fs = f"{r['forensic_score']:.0f}" if r['forensic_score'] else "N/A"
            vs = f"{r['variant_score']:.0f}" if r['variant_score'] else "N/A"
            up = f"{r['upside_pct']:+.1f}%" if r['upside_pct'] else "N/A"
            print(f"    {r['symbol']:12s} | {TIER_LABELS.get(r['tier']):16s} | "
                  f"{r['letter_score']:10.0f} | {r['signal']:>11s} | "
                  f"{fs:>9s} | {vs:>7s} | {up:>7s}")
    else:
        print("    No trifecta candidates yet. Run forensics and variant perception first.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Founder Vision & Capital Allocation Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m tools.founder_letter_analyzer
  python -m tools.founder_letter_analyzer --symbols AMZN,NVR,CSU --years 2022,2023
  python -m tools.founder_letter_analyzer --symbols AMZN --years 2019,2020,2021,2022,2023
  python -m tools.founder_letter_analyzer --symbols TSLA --force
  python -m tools.founder_letter_analyzer --symbols AAPL --no-llm  (fetch only)
""",
    )
    parser.add_argument("--symbols", type=str, help="Comma-separated tickers")
    parser.add_argument("--years", type=str, help="Comma-separated years (e.g. 2022,2023)")
    parser.add_argument("--force", action="store_true", help="Re-analyze cached results")
    parser.add_argument("--no-llm", action="store_true", help="Fetch letters only, skip Gemini")
    args = parser.parse_args()

    sym_list = [s.strip() for s in args.symbols.split(",")] if args.symbols else None
    year_list = [int(y.strip()) for y in args.years.split(",")] if args.years else None
    run(sym_list, year_list, force=args.force, no_llm=args.no_llm)
