"""Quick end-to-end test of Google Slides generation using live DB data."""
import sys, os, json, sqlite3
from pathlib import Path
from datetime import date

_root = str(Path(__file__).parent)
sys.path.insert(0, _root)

DB_PATH = os.path.join(_root, ".tmp", "druckenmiller.db")

# Google API
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

TOKEN_PATH = os.path.join(_root, "token.json")
SCOPES = [
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/drive.file",
]

def get_creds():
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    return creds

def get_slides():
    return build("slides", "v1", credentials=get_creds())

def get_drive():
    return build("drive", "v3", credentials=get_creds())

# --- Collect data from DB ---
def db_query(sql, params=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(sql, params or [])
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def collect_test_data():
    """Pull energy sector data from DB for test deck."""
    # Get macro regime
    macro_rows = db_query("SELECT * FROM macro_scores ORDER BY date DESC LIMIT 1")
    macro = {
        "regime": macro_rows[0]["regime"] if macro_rows else "NEUTRAL",
        "regime_score": macro_rows[0]["total_score"] if macro_rows else 0,
    }

    # Get energy stocks with convergence signals
    stocks = db_query("""
        SELECT c.symbol, c.convergence_score, c.conviction_level, c.module_count,
               t.total_score as tech_score, f.total_score as fund_score
        FROM convergence_signals c
        LEFT JOIN technical_scores t ON c.symbol = t.symbol
            AND t.date = (SELECT MAX(date) FROM technical_scores WHERE symbol = c.symbol)
        LEFT JOIN fundamental_scores f ON c.symbol = f.symbol
            AND f.date = (SELECT MAX(date) FROM fundamental_scores WHERE symbol = c.symbol)
        INNER JOIN stock_universe su ON c.symbol = su.symbol
        WHERE su.sector = 'Energy'
          AND c.date = (SELECT MAX(date) FROM convergence_signals WHERE symbol = c.symbol)
        ORDER BY c.convergence_score DESC
        LIMIT 15
    """)

    return macro, stocks

# --- EMU helpers ---
EMU = 914400  # 1 inch in EMU
def inches(n): return int(n * EMU)

# Slide dimensions (standard 10" x 7.5")
SLIDE_W = inches(10)
SLIDE_H = inches(7.5)

# Colors
BG_DARK = {"red": 0.08, "green": 0.09, "blue": 0.12}
TEXT_WHITE = {"red": 1.0, "green": 1.0, "blue": 1.0}
TEXT_GRAY = {"red": 0.6, "green": 0.6, "blue": 0.65}
ACCENT_GREEN = {"red": 0.2, "green": 0.8, "blue": 0.4}
ACCENT_GOLD = {"red": 0.9, "green": 0.75, "blue": 0.3}

_slide_counter = 0

def next_slide_id():
    global _slide_counter
    _slide_counter += 1
    return f"slide_{_slide_counter}"

def next_element_id():
    global _slide_counter
    _slide_counter += 1
    return f"elem_{_slide_counter}"

def create_slide_request(slide_id):
    return {"createSlide": {"objectId": slide_id, "slideLayoutReference": {"predefinedLayout": "BLANK"}}}

def set_bg(slide_id, color):
    return {"updatePageProperties": {
        "objectId": slide_id,
        "pageProperties": {"pageBackgroundFill": {"solidFill": {"color": {"rgbColor": color}}}},
        "fields": "pageBackgroundFill.solidFill.color"
    }}

def create_textbox(element_id, page_id, left, top, width, height):
    return {"createShape": {
        "objectId": element_id,
        "shapeType": "TEXT_BOX",
        "elementProperties": {
            "pageObjectId": page_id,
            "size": {"width": {"magnitude": width, "unit": "EMU"},
                     "height": {"magnitude": height, "unit": "EMU"}},
            "transform": {"scaleX": 1, "scaleY": 1,
                          "translateX": left, "translateY": top, "unit": "EMU"}
        }
    }}

def insert_text(element_id, text):
    return {"insertText": {"objectId": element_id, "text": text}}

def style_text(element_id, font_size, color, bold=False, start=0, end=None):
    style = {
        "fontSize": {"magnitude": font_size, "unit": "PT"},
        "foregroundColor": {"opaqueColor": {"rgbColor": color}},
        "bold": bold,
        "fontFamily": "Inter"
    }
    fields = "fontSize,foregroundColor,bold,fontFamily"
    r = {"updateTextStyle": {
        "objectId": element_id,
        "style": style,
        "fields": fields,
        "textRange": {"type": "ALL"} if end is None else {"type": "FIXED_RANGE", "startIndex": start, "endIndex": end}
    }}
    return r

def main():
    print("Collecting data from DB...")
    macro, stocks = collect_test_data()
    print(f"  Macro: {macro['regime']} ({macro['regime_score']})")
    print(f"  Energy stocks: {len(stocks)}")

    if not stocks:
        print("  No energy stocks found — check convergence_signals table")
        return

    # Create presentation
    slides_svc = get_slides()
    pres = slides_svc.presentations().create(
        body={"title": f"Energy Intelligence Brief — {date.today().isoformat()}"}
    ).execute()
    pres_id = pres["presentationId"]
    print(f"  Created: https://docs.google.com/presentation/d/{pres_id}/edit")

    requests = []

    # --- SLIDE 1: Title ---
    sid = next_slide_id()
    requests.append(create_slide_request(sid))
    requests.append(set_bg(sid, BG_DARK))

    # Title text
    eid = next_element_id()
    requests.append(create_textbox(eid, sid, inches(0.8), inches(1.5), inches(8.4), inches(1.5)))
    requests.append(insert_text(eid, "ENERGY SECTOR\nIntelligence Brief"))
    requests.append(style_text(eid, 36, TEXT_WHITE, bold=True, start=0, end=13))
    requests.append(style_text(eid, 24, ACCENT_GOLD, start=14, end=33))

    # Date + regime
    eid2 = next_element_id()
    requests.append(create_textbox(eid2, sid, inches(0.8), inches(3.5), inches(8.4), inches(1)))
    regime_text = f"{date.today().strftime('%B %d, %Y')}  •  Regime: {macro['regime']}"
    requests.append(insert_text(eid2, regime_text))
    requests.append(style_text(eid2, 14, TEXT_GRAY))

    # Footer
    eid3 = next_element_id()
    requests.append(create_textbox(eid3, sid, inches(0.8), inches(6.2), inches(8.4), inches(0.5)))
    requests.append(insert_text(eid3, "Druckenmiller Alpha System  •  Confidential"))
    requests.append(style_text(eid3, 10, TEXT_GRAY))

    # --- SLIDE 2: Conviction Ranking ---
    sid2 = next_slide_id()
    requests.append(create_slide_request(sid2))
    requests.append(set_bg(sid2, BG_DARK))

    # Header
    eid4 = next_element_id()
    requests.append(create_textbox(eid4, sid2, inches(0.5), inches(0.3), inches(9), inches(0.7)))
    requests.append(insert_text(eid4, "CONVICTION RANKING — ENERGY"))
    requests.append(style_text(eid4, 20, ACCENT_GOLD, bold=True))

    # Stock table as text
    header = f"{'Symbol':<8} {'Score':>6} {'Conv':>8} {'Tech':>6} {'Fund':>6} {'Modules':>8}\n"
    header += "─" * 50 + "\n"

    rows_text = ""
    for s in stocks[:12]:
        sym = s["symbol"]
        score = s["convergence_score"] or 0
        conv = s["conviction_level"] or "—"
        tech = f"{s['tech_score']:.0f}" if s.get("tech_score") else "—"
        fund = f"{s['fund_score']:.0f}" if s.get("fund_score") else "—"
        mods = s["module_count"] or 0
        rows_text += f"{sym:<8} {score:>6.1f} {conv:>8} {tech:>6} {fund:>6} {mods:>8}\n"

    eid5 = next_element_id()
    requests.append(create_textbox(eid5, sid2, inches(0.5), inches(1.2), inches(9), inches(5.5)))
    requests.append(insert_text(eid5, header + rows_text))
    requests.append(style_text(eid5, 11, TEXT_WHITE))
    # Bold header
    requests.append(style_text(eid5, 11, ACCENT_GREEN, bold=True, start=0, end=len(header)))

    # --- Send to API ---
    print(f"\n  Sending {len(requests)} API requests...")

    # Batch
    resp = slides_svc.presentations().batchUpdate(
        presentationId=pres_id,
        body={"requests": requests}
    ).execute()

    if "replies" in resp:
        print(f"  OK — {len(resp['replies'])} replies")

    # Delete default blank slide
    pres_data = slides_svc.presentations().get(presentationId=pres_id).execute()
    if pres_data and "slides" in pres_data and len(pres_data["slides"]) > 2:
        default_id = pres_data["slides"][0]["objectId"]
        slides_svc.presentations().batchUpdate(
            presentationId=pres_id,
            body={"requests": [{"deleteObject": {"objectId": default_id}}]}
        ).execute()
        print("  Removed default blank slide")

    url = f"https://docs.google.com/presentation/d/{pres_id}/edit"
    print(f"\n  DECK READY: {url}")
    print(f"  Open it in your browser to review!")

if __name__ == "__main__":
    main()
