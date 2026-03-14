"""Google Slides Deck Generator — professional investment presentations.

Converts intelligence report data into polished Google Slides decks using
the Google Slides API via Python client library.

Architecture: Python handles data transformation + slide design logic,
Google API Python client handles Slides API calls (deterministic execution).

Setup:
    1. Go to console.cloud.google.com → Create/select project
    2. Enable "Google Slides API" and "Google Drive API"
    3. Create OAuth 2.0 Desktop credentials → download as credentials.json
    4. Place credentials.json in the project root (same dir as .env)
    5. First run will open browser for OAuth consent → creates token.json

Usage:
    python -m tools.google_slides --topic energy
    python -m tools.google_slides --topic "AI power" --template dark
    python -m tools.google_slides --report-id <id>  # from DB
"""

import sys
import os
import json
import argparse
import re
from datetime import date, datetime
from pathlib import Path

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from tools.db import init_db, query
from tools.config import GEMINI_API_KEY, GEMINI_BASE, GEMINI_MODEL

# Google API imports
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# OAuth scopes — Slides + Drive (for sharing)
SCOPES = [
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/drive.file",
]
CREDS_PATH = os.path.join(_project_root, "credentials.json")
TOKEN_PATH = os.path.join(_project_root, "token.json")

# ═══════════════════════════════════════════════════════════════════
#  DESIGN SYSTEM — Professional Investment Presentation
# ═══════════════════════════════════════════════════════════════════

# Google Slides uses EMU (English Metric Units): 1 inch = 914400 EMU
EMU = 914400
PT = 12700  # 1 point = 12700 EMU

# Slide dimensions (16:9 widescreen)
SLIDE_W = int(10 * EMU)
SLIDE_H = int(5.625 * EMU)

# Design tokens — dark professional theme
THEME = {
    "bg_primary": {"red": 0.055, "green": 0.067, "blue": 0.090},       # #0E1117
    "bg_card": {"red": 0.118, "green": 0.129, "blue": 0.188},          # #1E2130
    "bg_accent": {"red": 0.098, "green": 0.110, "blue": 0.145},        # #191C25
    "text_primary": {"red": 0.878, "green": 0.878, "blue": 0.878},     # #E0E0E0
    "text_secondary": {"red": 0.690, "green": 0.690, "blue": 0.690},   # #B0B0B0
    "text_muted": {"red": 0.533, "green": 0.533, "blue": 0.533},       # #888888
    "accent_green": {"red": 0.0, "green": 0.784, "blue": 0.325},       # #00C853
    "accent_green_soft": {"red": 0.412, "green": 0.941, "blue": 0.682},# #69F0AE
    "accent_red": {"red": 1.0, "green": 0.090, "blue": 0.267},         # #FF1744
    "accent_amber": {"red": 1.0, "green": 0.835, "blue": 0.310},       # #FFD54F
    "accent_orange": {"red": 1.0, "green": 0.541, "blue": 0.396},      # #FF8A65
    "white": {"red": 1.0, "green": 1.0, "blue": 1.0},
    "black": {"red": 0.0, "green": 0.0, "blue": 0.0},
    "divider": {"red": 0.200, "green": 0.200, "blue": 0.200},         # #333333
}

FONTS = {
    "title": "Inter",        # Clean geometric sans (fallback: Arial)
    "heading": "Inter",
    "body": "Inter",
    "mono": "JetBrains Mono",  # For numbers/data (fallback: Courier New)
}


def _score_color(score: float) -> dict:
    """Map 0-100 score to theme color dict."""
    if score is None or score == 0:
        return THEME["text_muted"]
    if score >= 70:
        return THEME["accent_green"]
    elif score >= 50:
        return THEME["accent_green_soft"]
    elif score >= 40:
        return THEME["accent_amber"]
    elif score >= 25:
        return THEME["accent_orange"]
    return THEME["accent_red"]


def _regime_color(regime: str) -> dict:
    """Map macro regime to color."""
    return {
        "strong_risk_on": THEME["accent_green"],
        "risk_on": THEME["accent_green_soft"],
        "neutral": THEME["accent_amber"],
        "risk_off": THEME["accent_orange"],
        "strong_risk_off": THEME["accent_red"],
    }.get(regime, THEME["accent_amber"])


# ═══════════════════════════════════════════════════════════════════
#  GOOGLE API CLIENT — OAuth + Slides service
# ═══════════════════════════════════════════════════════════════════

_slides_service = None
_drive_service = None


def _get_creds() -> Credentials:
    """Get or refresh OAuth credentials. Opens browser on first run."""
    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDS_PATH):
                raise FileNotFoundError(
                    f"credentials.json not found at {CREDS_PATH}\n"
                    "Setup: console.cloud.google.com → APIs & Services → "
                    "Credentials → OAuth client ID (Desktop) → Download JSON"
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
        print("    OAuth token saved to token.json")

    return creds


def _get_slides_service():
    """Get or create the Slides API service."""
    global _slides_service
    if _slides_service is None:
        creds = _get_creds()
        _slides_service = build("slides", "v1", credentials=creds)
    return _slides_service


def _get_drive_service():
    """Get or create the Drive API service."""
    global _drive_service
    if _drive_service is None:
        creds = _get_creds()
        _drive_service = build("drive", "v3", credentials=creds)
    return _drive_service


def create_presentation(title: str) -> str:
    """Create a blank presentation, return its ID."""
    service = _get_slides_service()
    body = {"title": title}
    presentation = service.presentations().create(body=body).execute()
    pres_id = presentation.get("presentationId", "")
    print(f"    Created presentation: {pres_id}")
    return pres_id


def batch_update(presentation_id: str, requests: list) -> dict:
    """Send a batch of updates to a presentation."""
    service = _get_slides_service()
    body = {"requests": requests}
    try:
        resp = service.presentations().batchUpdate(
            presentationId=presentation_id, body=body
        ).execute()
        return resp
    except Exception as e:
        print(f"    Batch update error: {e}")
        return {"error": str(e)}


def get_presentation(presentation_id: str) -> dict:
    """Get full presentation object."""
    service = _get_slides_service()
    return service.presentations().get(presentationId=presentation_id).execute()


# ═══════════════════════════════════════════════════════════════════
#  SLIDE BUILDERS — Each returns a list of Slides API requests
# ═══════════════════════════════════════════════════════════════════

def _create_slide_request(layout: str = "BLANK", slide_id: str = None) -> dict:
    """Create a new slide request."""
    req = {
        "createSlide": {
            "slideLayoutReference": {"predefinedLayout": layout},
        }
    }
    if slide_id:
        req["createSlide"]["objectId"] = slide_id
    return req


def _set_bg(slide_id: str, color: dict) -> dict:
    """Set slide background color."""
    return {
        "updatePageProperties": {
            "objectId": slide_id,
            "pageProperties": {
                "pageBackgroundFill": {
                    "solidFill": {"color": {"rgbColor": color}}
                }
            },
            "fields": "pageBackgroundFill"
        }
    }


def _text_box(box_id: str, slide_id: str, left: int, top: int, width: int, height: int) -> dict:
    """Create a text box on a slide."""
    return {
        "createShape": {
            "objectId": box_id,
            "shapeType": "TEXT_BOX",
            "elementProperties": {
                "pageObjectId": slide_id,
                "size": {
                    "width": {"magnitude": width, "unit": "EMU"},
                    "height": {"magnitude": height, "unit": "EMU"},
                },
                "transform": {
                    "scaleX": 1, "scaleY": 1,
                    "translateX": left, "translateY": top,
                    "unit": "EMU",
                },
            },
        }
    }


def _insert_text(box_id: str, text: str, index: int = 0) -> dict:
    """Insert text into a shape."""
    return {
        "insertText": {
            "objectId": box_id,
            "text": text,
            "insertionIndex": index,
        }
    }


def _style_text(box_id: str, start: int, end: int, font_size: int,
                color: dict = None, bold: bool = False, font: str = None,
                italic: bool = False) -> dict:
    """Style a range of text. Returns None if range is empty."""
    if start >= end:
        return None  # Skip empty ranges
    style = {"fontSize": {"magnitude": font_size, "unit": "PT"}}
    fields = "fontSize"

    if color:
        style["foregroundColor"] = {"opaqueColor": {"rgbColor": color}}
        fields += ",foregroundColor"
    if bold:
        style["bold"] = True
        fields += ",bold"
    if italic:
        style["italic"] = True
        fields += ",italic"
    if font:
        style["fontFamily"] = font
        fields += ",fontFamily"

    return {
        "updateTextStyle": {
            "objectId": box_id,
            "textRange": {"type": "FIXED_RANGE", "startIndex": start, "endIndex": end},
            "style": style,
            "fields": fields,
        }
    }


def _paragraph_style(box_id: str, start: int, end: int, alignment: str = "START",
                      spacing_before: float = 0, spacing_after: float = 0,
                      line_spacing: float = 100) -> dict:
    """Set paragraph styling."""
    return {
        "updateParagraphStyle": {
            "objectId": box_id,
            "textRange": {"type": "FIXED_RANGE", "startIndex": start, "endIndex": end},
            "style": {
                "alignment": alignment,
                "spaceAbove": {"magnitude": spacing_before, "unit": "PT"},
                "spaceBelow": {"magnitude": spacing_after, "unit": "PT"},
                "lineSpacing": line_spacing,
            },
            "fields": "alignment,spaceAbove,spaceBelow,lineSpacing",
        }
    }


def _rect(rect_id: str, slide_id: str, left: int, top: int, width: int, height: int,
          fill_color: dict = None, border_color: dict = None, border_weight: float = 0) -> dict:
    """Create a rectangle shape."""
    return {
        "createShape": {
            "objectId": rect_id,
            "shapeType": "RECTANGLE",
            "elementProperties": {
                "pageObjectId": slide_id,
                "size": {
                    "width": {"magnitude": width, "unit": "EMU"},
                    "height": {"magnitude": height, "unit": "EMU"},
                },
                "transform": {
                    "scaleX": 1, "scaleY": 1,
                    "translateX": left, "translateY": top,
                    "unit": "EMU",
                },
            },
        }
    }


def _shape_fill(shape_id: str, color: dict) -> dict:
    """Set shape fill color with no outline."""
    return {
        "updateShapeProperties": {
            "objectId": shape_id,
            "shapeProperties": {
                "shapeBackgroundFill": {
                    "solidFill": {"color": {"rgbColor": color}}
                },
                "outline": {"propertyState": "NOT_RENDERED"},
            },
            "fields": "shapeBackgroundFill,outline",
        }
    }


def _line(line_id: str, slide_id: str, x1: int, y1: int, x2: int, y2: int,
          color: dict = None, weight: float = 1.0) -> dict:
    """Create a line element."""
    return {
        "createLine": {
            "objectId": line_id,
            "lineCategory": "STRAIGHT",
            "elementProperties": {
                "pageObjectId": slide_id,
                "size": {
                    "width": {"magnitude": abs(x2 - x1), "unit": "EMU"},
                    "height": {"magnitude": abs(y2 - y1), "unit": "EMU"},
                },
                "transform": {
                    "scaleX": 1, "scaleY": 1,
                    "translateX": min(x1, x2), "translateY": min(y1, y2),
                    "unit": "EMU",
                },
            },
        }
    }


def _line_style(line_id: str, color: dict, weight: float = 1.0) -> dict:
    """Style a line."""
    return {
        "updateLineProperties": {
            "objectId": line_id,
            "lineProperties": {
                "lineFill": {"solidFill": {"color": {"rgbColor": color}}},
                "weight": {"magnitude": weight, "unit": "PT"},
            },
            "fields": "lineFill,weight",
        }
    }


# ═══════════════════════════════════════════════════════════════════
#  SLIDE TEMPLATES — Professional institutional deck design
# ═══════════════════════════════════════════════════════════════════

_slide_counter = 0


def _uid(prefix: str = "el") -> str:
    """Generate a unique element ID."""
    global _slide_counter
    _slide_counter += 1
    return f"{prefix}_{_slide_counter:04d}"


def build_title_slide(topic_info: dict, macro: dict) -> tuple:
    """Slide 1: Title slide with regime badge and date."""
    sid = _uid("slide")
    reqs = [_create_slide_request("BLANK", sid), _set_bg(sid, THEME["bg_primary"])]

    regime = macro.get("regime", {})
    regime_name = (regime.get("regime", "unknown") or "unknown").replace("_", " ").upper()
    regime_score = regime.get("total_score", 0) or 0

    # Top accent bar
    bar_id = _uid("bar")
    reqs.append(_rect(bar_id, sid, 0, 0, SLIDE_W, int(0.08 * EMU)))
    reqs.append(_shape_fill(bar_id, THEME["accent_green"]))

    # System name
    sys_id = _uid("txt")
    reqs.append(_text_box(sys_id, sid, int(0.8 * EMU), int(0.5 * EMU), int(8.4 * EMU), int(0.4 * EMU)))
    reqs.append(_insert_text(sys_id, "DRUCKENMILLER ALPHA SYSTEM"))
    reqs.append(_style_text(sys_id, 0, 26, 11, THEME["text_muted"], font=FONTS["body"]))
    reqs.append(_paragraph_style(sys_id, 0, 26, "START"))

    # Main title
    title_id = _uid("txt")
    title_text = f"Intelligence Brief: {topic_info['display_name']}"
    reqs.append(_text_box(title_id, sid, int(0.8 * EMU), int(1.2 * EMU), int(8.4 * EMU), int(1.2 * EMU)))
    reqs.append(_insert_text(title_id, title_text))
    reqs.append(_style_text(title_id, 0, len(title_text), 36, THEME["white"], bold=True, font=FONTS["title"]))

    # Date
    date_id = _uid("txt")
    date_text = datetime.now().strftime("%B %d, %Y")
    reqs.append(_text_box(date_id, sid, int(0.8 * EMU), int(2.5 * EMU), int(8.4 * EMU), int(0.4 * EMU)))
    reqs.append(_insert_text(date_id, date_text))
    reqs.append(_style_text(date_id, 0, len(date_text), 14, THEME["text_secondary"], font=FONTS["body"]))

    # Regime badge card
    badge_id = _uid("rect")
    reqs.append(_rect(badge_id, sid, int(0.8 * EMU), int(3.3 * EMU), int(3.2 * EMU), int(0.7 * EMU)))
    reqs.append(_shape_fill(badge_id, THEME["bg_card"]))
    badge_txt = _uid("txt")
    badge_text = f"  {regime_name}  ({regime_score:+.0f})"
    reqs.append(_text_box(badge_txt, sid, int(0.85 * EMU), int(3.4 * EMU), int(3.1 * EMU), int(0.5 * EMU)))
    reqs.append(_insert_text(badge_txt, badge_text))
    reqs.append(_style_text(badge_txt, 0, len(badge_text), 16, _regime_color(regime.get("regime", "")), bold=True, font=FONTS["mono"]))

    # Bottom tagline
    tag_id = _uid("txt")
    tag_text = "14-Module Convergence Engine  |  Institutional-Grade Analysis"
    reqs.append(_text_box(tag_id, sid, int(0.8 * EMU), int(4.6 * EMU), int(8.4 * EMU), int(0.4 * EMU)))
    reqs.append(_insert_text(tag_id, tag_text))
    reqs.append(_style_text(tag_id, 0, len(tag_text), 10, THEME["text_muted"], font=FONTS["body"]))

    return sid, reqs


def build_exec_summary_slide(exec_summary: str, macro: dict) -> tuple:
    """Slide 2: Executive summary with key metrics sidebar."""
    sid = _uid("slide")
    reqs = [_create_slide_request("BLANK", sid), _set_bg(sid, THEME["bg_primary"])]

    # Header
    hdr_id = _uid("txt")
    hdr_text = "EXECUTIVE SUMMARY"
    reqs.append(_text_box(hdr_id, sid, int(0.6 * EMU), int(0.3 * EMU), int(6 * EMU), int(0.5 * EMU)))
    reqs.append(_insert_text(hdr_id, hdr_text))
    reqs.append(_style_text(hdr_id, 0, len(hdr_text), 20, THEME["white"], bold=True, font=FONTS["heading"]))

    # Divider
    div_id = _uid("line")
    reqs.append(_line(div_id, sid, int(0.6 * EMU), int(0.85 * EMU), int(9.4 * EMU), int(0.85 * EMU)))
    reqs.append(_line_style(div_id, THEME["accent_green"], 2.0))

    # Summary text (left 65%)
    # Clean markdown artifacts
    clean_text = re.sub(r'\*\*(.+?)\*\*', r'\1', exec_summary)
    clean_text = re.sub(r'\*(.+?)\*', r'\1', clean_text)
    clean_text = re.sub(r'^[-•]\s*', '  •  ', clean_text, flags=re.MULTILINE)
    clean_text = clean_text[:1200]  # Slides have limited space

    body_id = _uid("txt")
    reqs.append(_text_box(body_id, sid, int(0.6 * EMU), int(1.1 * EMU), int(5.8 * EMU), int(4.0 * EMU)))
    reqs.append(_insert_text(body_id, clean_text))
    reqs.append(_style_text(body_id, 0, len(clean_text), 10, THEME["text_primary"], font=FONTS["body"]))
    reqs.append(_paragraph_style(body_id, 0, len(clean_text), line_spacing=135))

    # Right sidebar — key metrics
    regime = macro.get("regime", {})
    heat = macro.get("heat_index", {})

    sidebar_id = _uid("rect")
    reqs.append(_rect(sidebar_id, sid, int(6.8 * EMU), int(1.1 * EMU), int(2.8 * EMU), int(4.0 * EMU)))
    reqs.append(_shape_fill(sidebar_id, THEME["bg_card"]))

    # Sidebar metrics
    metrics = []
    heat_val = heat.get("heat_index", 0) or 0
    metrics.append(("HEAT INDEX", f"{heat_val:+.1f}"))
    metrics.append(("IMPROVING", f"{heat.get('improving_count', 0)}"))
    metrics.append(("DETERIORATING", f"{heat.get('deteriorating_count', 0)}"))

    for key in ["vix_score", "dxy_score", "credit_spreads_score"]:
        val = regime.get(key, 0) or 0
        label = key.replace("_score", "").replace("_", " ").upper()
        metrics.append((label, f"{val:+.1f}"))

    y_offset = int(1.25 * EMU)
    for label, value in metrics:
        label_id = _uid("txt")
        reqs.append(_text_box(label_id, sid, int(7.0 * EMU), y_offset, int(2.4 * EMU), int(0.2 * EMU)))
        reqs.append(_insert_text(label_id, label))
        reqs.append(_style_text(label_id, 0, len(label), 8, THEME["text_muted"], font=FONTS["body"]))

        val_id = _uid("txt")
        reqs.append(_text_box(val_id, sid, int(7.0 * EMU), y_offset + int(0.2 * EMU), int(2.4 * EMU), int(0.3 * EMU)))
        reqs.append(_insert_text(val_id, value))
        reqs.append(_style_text(val_id, 0, len(value), 16, THEME["white"], bold=True, font=FONTS["mono"]))

        y_offset += int(0.6 * EMU)

    return sid, reqs


def build_conviction_slide(stock_data: list, slide_num: int = 1, stocks_per_slide: int = 12) -> tuple:
    """Conviction ranking table slide. Professional heatmap style."""
    sid = _uid("slide")
    reqs = [_create_slide_request("BLANK", sid), _set_bg(sid, THEME["bg_primary"])]

    # Header
    hdr_id = _uid("txt")
    hdr_text = f"CONVICTION RANKING" + (f" ({slide_num})" if slide_num > 1 else "")
    reqs.append(_text_box(hdr_id, sid, int(0.6 * EMU), int(0.2 * EMU), int(6 * EMU), int(0.4 * EMU)))
    reqs.append(_insert_text(hdr_id, hdr_text))
    reqs.append(_style_text(hdr_id, 0, len(hdr_text), 18, THEME["white"], bold=True, font=FONTS["heading"]))

    # Divider
    div_id = _uid("line")
    reqs.append(_line(div_id, sid, int(0.6 * EMU), int(0.65 * EMU), int(9.4 * EMU), int(0.65 * EMU)))
    reqs.append(_line_style(div_id, THEME["accent_green"], 1.5))

    # Column headers
    cols = [
        ("SYMBOL", 0.6),
        ("CONV", 2.0),
        ("TECH", 3.0),
        ("FUND", 4.0),
        ("SM", 5.0),
        ("PAIRS", 5.8),
        ("SECTOR", 6.7),
        ("SIGNAL", 7.7),
        ("LEVEL", 8.8),
    ]

    y_header = int(0.85 * EMU)
    for col_name, x_inch in cols:
        col_id = _uid("txt")
        reqs.append(_text_box(col_id, sid, int(x_inch * EMU), y_header, int(0.9 * EMU), int(0.25 * EMU)))
        reqs.append(_insert_text(col_id, col_name))
        reqs.append(_style_text(col_id, 0, len(col_name), 7, THEME["text_muted"], bold=True, font=FONTS["body"]))

    # Data rows
    start_idx = (slide_num - 1) * stocks_per_slide
    page_stocks = stock_data[start_idx:start_idx + stocks_per_slide]

    y = int(1.15 * EMU)
    row_h = int(0.32 * EMU)

    for i, s in enumerate(page_stocks):
        # Alternating row background
        if i % 2 == 0:
            row_bg = _uid("rect")
            reqs.append(_rect(row_bg, sid, int(0.4 * EMU), y - int(0.02 * EMU), int(9.2 * EMU), row_h))
            reqs.append(_shape_fill(row_bg, THEME["bg_accent"]))

        sym = s.get("symbol", "?")
        conv = s.get("convergence_score", 0) or 0
        tech = (s.get("technical", {}) or {}).get("total_score", 0) or 0
        fund = (s.get("fundamental", {}) or {}).get("total_score", 0) or 0
        sm = s.get("smartmoney_score", 0) or 0
        pairs = s.get("pairs_score", 0) or 0
        sect = s.get("sector_expert_score", 0) or 0
        sig = (s.get("signal", {}) or {}).get("signal", "—")
        level = s.get("conviction_level", "—") or "—"

        row_data = [
            (sym, 0.6, THEME["white"], True, FONTS["body"]),
            (f"{conv:.1f}", 2.0, _score_color(conv), True, FONTS["mono"]),
            (f"{tech:.0f}", 3.0, _score_color(tech), False, FONTS["mono"]),
            (f"{fund:.0f}", 4.0, _score_color(fund), False, FONTS["mono"]),
            (f"{sm:.0f}", 5.0, _score_color(sm), False, FONTS["mono"]),
            (f"{pairs:.0f}", 5.8, _score_color(pairs), False, FONTS["mono"]),
            (f"{sect:.0f}", 6.7, _score_color(sect), False, FONTS["mono"]),
            (sig[:6], 7.7, THEME["text_secondary"], False, FONTS["body"]),
            (level, 8.8, _score_color(80 if level == "HIGH" else 50 if level == "NOTABLE" else 20), True, FONTS["body"]),
        ]

        for text, x_inch, color, bold, font in row_data:
            cell_id = _uid("txt")
            reqs.append(_text_box(cell_id, sid, int(x_inch * EMU), y, int(0.9 * EMU), int(0.25 * EMU)))
            reqs.append(_insert_text(cell_id, text))
            reqs.append(_style_text(cell_id, 0, len(text), 9, color, bold=bold, font=font))

        y += row_h

    return sid, reqs


def build_macro_slide(macro: dict) -> tuple:
    """Macro context slide with regime breakdown and prediction markets."""
    sid = _uid("slide")
    reqs = [_create_slide_request("BLANK", sid), _set_bg(sid, THEME["bg_primary"])]

    # Header
    hdr_id = _uid("txt")
    hdr_text = "MACRO CONTEXT"
    reqs.append(_text_box(hdr_id, sid, int(0.6 * EMU), int(0.2 * EMU), int(6 * EMU), int(0.4 * EMU)))
    reqs.append(_insert_text(hdr_id, hdr_text))
    reqs.append(_style_text(hdr_id, 0, len(hdr_text), 18, THEME["white"], bold=True, font=FONTS["heading"]))

    div_id = _uid("line")
    reqs.append(_line(div_id, sid, int(0.6 * EMU), int(0.65 * EMU), int(9.4 * EMU), int(0.65 * EMU)))
    reqs.append(_line_style(div_id, THEME["accent_green"], 1.5))

    regime = macro.get("regime", {})

    # Regime sub-scores (left panel)
    panel_id = _uid("rect")
    reqs.append(_rect(panel_id, sid, int(0.6 * EMU), int(0.9 * EMU), int(4.2 * EMU), int(3.8 * EMU)))
    reqs.append(_shape_fill(panel_id, THEME["bg_card"]))

    panel_title = _uid("txt")
    pt_text = "REGIME SUB-SCORES"
    reqs.append(_text_box(panel_title, sid, int(0.9 * EMU), int(1.0 * EMU), int(3.6 * EMU), int(0.3 * EMU)))
    reqs.append(_insert_text(panel_title, pt_text))
    reqs.append(_style_text(panel_title, 0, len(pt_text), 9, THEME["text_muted"], bold=True, font=FONTS["body"]))

    y = int(1.4 * EMU)
    for key in ["fed_funds_score", "yield_curve_score", "credit_spreads_score", "vix_score", "dxy_score", "m2_score"]:
        val = regime.get(key, 0) or 0
        label = key.replace("_score", "").replace("_", " ").title()
        val_text = f"{val:+.1f}"
        val_color = THEME["accent_green"] if val > 5 else THEME["accent_red"] if val < -5 else THEME["accent_amber"]

        lbl_id = _uid("txt")
        reqs.append(_text_box(lbl_id, sid, int(0.9 * EMU), y, int(2.2 * EMU), int(0.25 * EMU)))
        reqs.append(_insert_text(lbl_id, label))
        reqs.append(_style_text(lbl_id, 0, len(label), 10, THEME["text_secondary"], font=FONTS["body"]))

        vid = _uid("txt")
        reqs.append(_text_box(vid, sid, int(3.4 * EMU), y, int(1.2 * EMU), int(0.25 * EMU)))
        reqs.append(_insert_text(vid, val_text))
        reqs.append(_style_text(vid, 0, len(val_text), 12, val_color, bold=True, font=FONTS["mono"]))

        # Score bar visualization
        bar_bg = _uid("rect")
        bar_w = int(1.0 * EMU)
        reqs.append(_rect(bar_bg, sid, int(3.4 * EMU), y + int(0.22 * EMU), bar_w, int(0.04 * EMU)))
        reqs.append(_shape_fill(bar_bg, THEME["bg_primary"]))

        fill_pct = max(0, min(1, (val + 30) / 60))  # normalize -30..+30 to 0..1
        bar_fill = _uid("rect")
        reqs.append(_rect(bar_fill, sid, int(3.4 * EMU), y + int(0.22 * EMU), max(int(bar_w * fill_pct), int(0.02 * EMU)), int(0.04 * EMU)))
        reqs.append(_shape_fill(bar_fill, val_color))

        y += int(0.55 * EMU)

    # Prediction markets (right panel)
    pm = macro.get("prediction_markets", [])
    if pm:
        pm_panel = _uid("rect")
        reqs.append(_rect(pm_panel, sid, int(5.2 * EMU), int(0.9 * EMU), int(4.4 * EMU), int(3.8 * EMU)))
        reqs.append(_shape_fill(pm_panel, THEME["bg_card"]))

        pm_title = _uid("txt")
        pmt_text = "PREDICTION MARKETS (POLYMARKET)"
        reqs.append(_text_box(pm_title, sid, int(5.4 * EMU), int(1.0 * EMU), int(4.0 * EMU), int(0.3 * EMU)))
        reqs.append(_insert_text(pm_title, pmt_text))
        reqs.append(_style_text(pm_title, 0, len(pmt_text), 9, THEME["text_muted"], bold=True, font=FONTS["body"]))

        y = int(1.4 * EMU)
        for p in pm[:6]:
            question = (p.get("question", "") or "")[:55]
            prob = (p.get("yes_probability", 0) or 0) * 100
            direction = p.get("direction", "") or ""
            dir_color = THEME["accent_green"] if "bullish" in direction else THEME["accent_red"] if "bearish" in direction else THEME["text_muted"]

            q_id = _uid("txt")
            reqs.append(_text_box(q_id, sid, int(5.4 * EMU), y, int(3.0 * EMU), int(0.22 * EMU)))
            reqs.append(_insert_text(q_id, question))
            reqs.append(_style_text(q_id, 0, len(question), 8, THEME["text_secondary"], font=FONTS["body"]))

            prob_id = _uid("txt")
            prob_text = f"{prob:.0f}%"
            reqs.append(_text_box(prob_id, sid, int(8.6 * EMU), y, int(0.8 * EMU), int(0.22 * EMU)))
            reqs.append(_insert_text(prob_id, prob_text))
            reqs.append(_style_text(prob_id, 0, len(prob_text), 10, dir_color, bold=True, font=FONTS["mono"]))

            y += int(0.48 * EMU)

    return sid, reqs


def build_pairs_slide(pairs_data: list) -> tuple:
    """Pairs & relative value slide."""
    sid = _uid("slide")
    reqs = [_create_slide_request("BLANK", sid), _set_bg(sid, THEME["bg_primary"])]

    hdr_id = _uid("txt")
    hdr_text = "PAIRS & RELATIVE VALUE"
    reqs.append(_text_box(hdr_id, sid, int(0.6 * EMU), int(0.2 * EMU), int(6 * EMU), int(0.4 * EMU)))
    reqs.append(_insert_text(hdr_id, hdr_text))
    reqs.append(_style_text(hdr_id, 0, len(hdr_text), 18, THEME["white"], bold=True, font=FONTS["heading"]))

    div_id = _uid("line")
    reqs.append(_line(div_id, sid, int(0.6 * EMU), int(0.65 * EMU), int(9.4 * EMU), int(0.65 * EMU)))
    reqs.append(_line_style(div_id, THEME["accent_green"], 1.5))

    if not pairs_data:
        no_id = _uid("txt")
        no_text = "No active pairs signals."
        reqs.append(_text_box(no_id, sid, int(0.6 * EMU), int(2.0 * EMU), int(8 * EMU), int(0.5 * EMU)))
        reqs.append(_insert_text(no_id, no_text))
        reqs.append(_style_text(no_id, 0, len(no_text), 14, THEME["text_muted"], font=FONTS["body"]))
        return sid, reqs

    # Column headers
    cols = [("PAIR", 0.6), ("TYPE", 2.8), ("Z-SCORE", 4.0), ("SCORE", 5.3), ("DIRECTION", 6.5), ("RUNNER", 8.0)]
    for col_name, x in cols:
        cid = _uid("txt")
        reqs.append(_text_box(cid, sid, int(x * EMU), int(0.85 * EMU), int(1.2 * EMU), int(0.25 * EMU)))
        reqs.append(_insert_text(cid, col_name))
        reqs.append(_style_text(cid, 0, len(col_name), 7, THEME["text_muted"], bold=True, font=FONTS["body"]))

    y = int(1.15 * EMU)
    for i, p in enumerate(pairs_data[:12]):
        if i % 2 == 0:
            row_bg = _uid("rect")
            reqs.append(_rect(row_bg, sid, int(0.4 * EMU), y - int(0.02 * EMU), int(9.2 * EMU), int(0.32 * EMU)))
            reqs.append(_shape_fill(row_bg, THEME["bg_accent"]))

        pair_name = f"{p['symbol_a']} / {p['symbol_b']}"
        z = p.get("spread_zscore", 0) or 0
        score = p.get("pairs_score", 0) or 0
        sig_type = p.get("signal_type", "")
        type_color = THEME["accent_green"] if sig_type == "runner" else THEME["accent_green_soft"]

        row = [
            (pair_name, 0.6, THEME["white"], True),
            (sig_type, 2.8, type_color, False),
            (f"{z:+.2f}", 4.0, THEME["accent_red"] if abs(z) > 2.5 else THEME["accent_amber"] if abs(z) > 2 else THEME["text_secondary"], True),
            (f"{score:.0f}", 5.3, _score_color(score), True),
            (p.get("direction", ""), 6.5, THEME["text_secondary"], False),
            (p.get("runner_symbol", "") or "—", 8.0, THEME["white"], False),
        ]

        for text, x, color, bold in row:
            cid = _uid("txt")
            reqs.append(_text_box(cid, sid, int(x * EMU), y, int(1.2 * EMU), int(0.25 * EMU)))
            reqs.append(_insert_text(cid, text[:12]))
            reqs.append(_style_text(cid, 0, min(len(text), 12), 9, color, bold=bold, font=FONTS["mono"] if bold else FONTS["body"]))

        y += int(0.32 * EMU)

    return sid, reqs


def build_smart_money_slide(sm_data: dict) -> tuple:
    """Smart money & insider activity slide."""
    sid = _uid("slide")
    reqs = [_create_slide_request("BLANK", sid), _set_bg(sid, THEME["bg_primary"])]

    hdr_id = _uid("txt")
    hdr_text = "SMART MONEY & INSIDER ACTIVITY"
    reqs.append(_text_box(hdr_id, sid, int(0.6 * EMU), int(0.2 * EMU), int(6 * EMU), int(0.4 * EMU)))
    reqs.append(_insert_text(hdr_id, hdr_text))
    reqs.append(_style_text(hdr_id, 0, len(hdr_text), 18, THEME["white"], bold=True, font=FONTS["heading"]))

    div_id = _uid("line")
    reqs.append(_line(div_id, sid, int(0.6 * EMU), int(0.65 * EMU), int(9.4 * EMU), int(0.65 * EMU)))
    reqs.append(_line_style(div_id, THEME["accent_green"], 1.5))

    # Left panel: 13F
    smart = sm_data.get("smart_money", [])
    if smart:
        panel = _uid("rect")
        reqs.append(_rect(panel, sid, int(0.6 * EMU), int(0.9 * EMU), int(4.2 * EMU), int(4.0 * EMU)))
        reqs.append(_shape_fill(panel, THEME["bg_card"]))

        t = _uid("txt")
        t_text = "13F INSTITUTIONAL POSITIONING"
        reqs.append(_text_box(t, sid, int(0.8 * EMU), int(1.0 * EMU), int(3.8 * EMU), int(0.3 * EMU)))
        reqs.append(_insert_text(t, t_text))
        reqs.append(_style_text(t, 0, len(t_text), 9, THEME["text_muted"], bold=True, font=FONTS["body"]))

        y = int(1.4 * EMU)
        for s in smart[:8]:
            sym = s.get("symbol", "?")
            conv = s.get("conviction_score", 0) or 0
            mgrs = s.get("manager_count", 0)

            sym_id = _uid("txt")
            reqs.append(_text_box(sym_id, sid, int(0.8 * EMU), y, int(1.0 * EMU), int(0.22 * EMU)))
            reqs.append(_insert_text(sym_id, sym))
            reqs.append(_style_text(sym_id, 0, len(sym), 10, THEME["white"], bold=True, font=FONTS["mono"]))

            score_id = _uid("txt")
            score_text = f"{conv:.0f}"
            reqs.append(_text_box(score_id, sid, int(2.0 * EMU), y, int(0.8 * EMU), int(0.22 * EMU)))
            reqs.append(_insert_text(score_id, score_text))
            reqs.append(_style_text(score_id, 0, len(score_text), 10, _score_color(conv), bold=True, font=FONTS["mono"]))

            mgr_id = _uid("txt")
            mgr_text = f"{mgrs} mgrs"
            reqs.append(_text_box(mgr_id, sid, int(3.0 * EMU), y, int(1.5 * EMU), int(0.22 * EMU)))
            reqs.append(_insert_text(mgr_id, mgr_text))
            reqs.append(_style_text(mgr_id, 0, len(mgr_text), 9, THEME["text_secondary"], font=FONTS["body"]))

            y += int(0.38 * EMU)

    # Right panel: Insider
    insider = sm_data.get("insider", [])
    if insider:
        panel2 = _uid("rect")
        reqs.append(_rect(panel2, sid, int(5.2 * EMU), int(0.9 * EMU), int(4.4 * EMU), int(4.0 * EMU)))
        reqs.append(_shape_fill(panel2, THEME["bg_card"]))

        t2 = _uid("txt")
        t2_text = "INSIDER TRADING SIGNALS"
        reqs.append(_text_box(t2, sid, int(5.4 * EMU), int(1.0 * EMU), int(4.0 * EMU), int(0.3 * EMU)))
        reqs.append(_insert_text(t2, t2_text))
        reqs.append(_style_text(t2, 0, len(t2_text), 9, THEME["text_muted"], bold=True, font=FONTS["body"]))

        y = int(1.4 * EMU)
        for ins in insider[:8]:
            sym = ins.get("symbol", "?")
            score = ins.get("insider_score", 0) or 0
            cluster = ins.get("cluster_buy", False)
            buy_val = ins.get("total_buy_value_30d", 0) or 0

            sym_id = _uid("txt")
            reqs.append(_text_box(sym_id, sid, int(5.4 * EMU), y, int(0.8 * EMU), int(0.22 * EMU)))
            reqs.append(_insert_text(sym_id, sym))
            reqs.append(_style_text(sym_id, 0, len(sym), 10, THEME["white"], bold=True, font=FONTS["mono"]))

            sc_id = _uid("txt")
            sc_text = f"{score:.0f}"
            reqs.append(_text_box(sc_id, sid, int(6.4 * EMU), y, int(0.6 * EMU), int(0.22 * EMU)))
            reqs.append(_insert_text(sc_id, sc_text))
            reqs.append(_style_text(sc_id, 0, len(sc_text), 10, _score_color(score), bold=True, font=FONTS["mono"]))

            cluster_id = _uid("txt")
            cl_text = "CLUSTER" if cluster else ""
            reqs.append(_text_box(cluster_id, sid, int(7.1 * EMU), y, int(0.9 * EMU), int(0.22 * EMU)))
            reqs.append(_insert_text(cluster_id, cl_text))
            reqs.append(_style_text(cluster_id, 0, len(cl_text), 8, THEME["accent_green"], bold=True, font=FONTS["body"]))

            val_id = _uid("txt")
            val_text = f"${buy_val:,.0f}" if buy_val > 0 else ""
            reqs.append(_text_box(val_id, sid, int(8.1 * EMU), y, int(1.3 * EMU), int(0.22 * EMU)))
            reqs.append(_insert_text(val_id, val_text))
            reqs.append(_style_text(val_id, 0, len(val_text), 9, THEME["accent_green"], font=FONTS["mono"]))

            y += int(0.38 * EMU)

    return sid, reqs


def build_risk_slide(risk_matrix: str) -> tuple:
    """Risk matrix slide."""
    sid = _uid("slide")
    reqs = [_create_slide_request("BLANK", sid), _set_bg(sid, THEME["bg_primary"])]

    hdr_id = _uid("txt")
    hdr_text = "RISK MATRIX"
    reqs.append(_text_box(hdr_id, sid, int(0.6 * EMU), int(0.2 * EMU), int(6 * EMU), int(0.4 * EMU)))
    reqs.append(_insert_text(hdr_id, hdr_text))
    reqs.append(_style_text(hdr_id, 0, len(hdr_text), 18, THEME["white"], bold=True, font=FONTS["heading"]))

    # Red accent line for risk
    div_id = _uid("line")
    reqs.append(_line(div_id, sid, int(0.6 * EMU), int(0.65 * EMU), int(9.4 * EMU), int(0.65 * EMU)))
    reqs.append(_line_style(div_id, THEME["accent_red"], 2.0))

    clean_text = re.sub(r'\*\*(.+?)\*\*', r'\1', risk_matrix)
    clean_text = re.sub(r'\*(.+?)\*', r'\1', clean_text)
    clean_text = re.sub(r'^[-•]\s*', '  •  ', clean_text, flags=re.MULTILINE)
    clean_text = clean_text[:1800]

    body_id = _uid("txt")
    reqs.append(_text_box(body_id, sid, int(0.6 * EMU), int(0.9 * EMU), int(8.8 * EMU), int(4.2 * EMU)))
    reqs.append(_insert_text(body_id, clean_text))
    reqs.append(_style_text(body_id, 0, len(clean_text), 10, THEME["text_primary"], font=FONTS["body"]))
    reqs.append(_paragraph_style(body_id, 0, len(clean_text), line_spacing=140))

    return sid, reqs


def build_deepdive_slide(deepdive: str, topic_info: dict) -> tuple:
    """Sector deep-dive slide."""
    sid = _uid("slide")
    reqs = [_create_slide_request("BLANK", sid), _set_bg(sid, THEME["bg_primary"])]

    hdr_id = _uid("txt")
    hdr_text = f"SECTOR DEEP-DIVE: {topic_info['display_name'].upper()}"
    reqs.append(_text_box(hdr_id, sid, int(0.6 * EMU), int(0.2 * EMU), int(8 * EMU), int(0.4 * EMU)))
    reqs.append(_insert_text(hdr_id, hdr_text))
    reqs.append(_style_text(hdr_id, 0, len(hdr_text), 18, THEME["white"], bold=True, font=FONTS["heading"]))

    div_id = _uid("line")
    reqs.append(_line(div_id, sid, int(0.6 * EMU), int(0.65 * EMU), int(9.4 * EMU), int(0.65 * EMU)))
    reqs.append(_line_style(div_id, THEME["accent_green"], 1.5))

    clean_text = re.sub(r'\*\*(.+?)\*\*', r'\1', deepdive)
    clean_text = re.sub(r'\*(.+?)\*', r'\1', clean_text)
    clean_text = re.sub(r'^[-•]\s*', '  •  ', clean_text, flags=re.MULTILINE)
    clean_text = clean_text[:1800]

    body_id = _uid("txt")
    reqs.append(_text_box(body_id, sid, int(0.6 * EMU), int(0.9 * EMU), int(8.8 * EMU), int(4.2 * EMU)))
    reqs.append(_insert_text(body_id, clean_text))
    reqs.append(_style_text(body_id, 0, len(clean_text), 10, THEME["text_primary"], font=FONTS["body"]))
    reqs.append(_paragraph_style(body_id, 0, len(clean_text), line_spacing=140))

    return sid, reqs


def build_closing_slide() -> tuple:
    """Closing/disclaimer slide."""
    sid = _uid("slide")
    reqs = [_create_slide_request("BLANK", sid), _set_bg(sid, THEME["bg_primary"])]

    # Bottom accent bar
    bar_id = _uid("bar")
    reqs.append(_rect(bar_id, sid, 0, int(5.3 * EMU), SLIDE_W, int(0.08 * EMU)))
    reqs.append(_shape_fill(bar_id, THEME["accent_green"]))

    # System name large
    name_id = _uid("txt")
    name_text = "DRUCKENMILLER\nALPHA SYSTEM"
    reqs.append(_text_box(name_id, sid, int(0.8 * EMU), int(1.2 * EMU), int(8.4 * EMU), int(1.8 * EMU)))
    reqs.append(_insert_text(name_id, name_text))
    reqs.append(_style_text(name_id, 0, len(name_text), 36, THEME["white"], bold=True, font=FONTS["title"]))
    reqs.append(_paragraph_style(name_id, 0, len(name_text), "CENTER"))

    # Modules line
    mod_id = _uid("txt")
    mod_text = "14 Convergence Modules  •  EIA Weekly  •  JODI International\nPairs Cointegration  •  Polymarket  •  13F Smart Money  •  SEC Insider\nGemini AI Synthesis  •  Satellite Data  •  World Bank/IMF"
    reqs.append(_text_box(mod_id, sid, int(1.5 * EMU), int(3.0 * EMU), int(7.0 * EMU), int(1.0 * EMU)))
    reqs.append(_insert_text(mod_id, mod_text))
    reqs.append(_style_text(mod_id, 0, len(mod_text), 10, THEME["text_muted"], font=FONTS["body"]))
    reqs.append(_paragraph_style(mod_id, 0, len(mod_text), "CENTER"))

    # Disclaimer
    disc_id = _uid("txt")
    disc_text = "For informational purposes only. Not financial advice."
    reqs.append(_text_box(disc_id, sid, int(1.5 * EMU), int(4.4 * EMU), int(7.0 * EMU), int(0.4 * EMU)))
    reqs.append(_insert_text(disc_id, disc_text))
    reqs.append(_style_text(disc_id, 0, len(disc_text), 8, THEME["text_muted"], italic=True, font=FONTS["body"]))
    reqs.append(_paragraph_style(disc_id, 0, len(disc_text), "CENTER"))

    return sid, reqs


# ═══════════════════════════════════════════════════════════════════
#  DATA COLLECTION (reuse from intelligence_report)
# ═══════════════════════════════════════════════════════════════════

def _resolve_topic(topic: str) -> dict:
    """Resolve a topic string to sector info and symbol list."""
    # Map common topic names to GICS sectors
    SECTOR_MAP = {
        "energy": "Energy",
        "tech": "Information Technology",
        "technology": "Information Technology",
        "it": "Information Technology",
        "ai": "Information Technology",
        "financials": "Financials",
        "finance": "Financials",
        "banks": "Financials",
        "healthcare": "Health Care",
        "health": "Health Care",
        "pharma": "Health Care",
        "industrials": "Industrials",
        "materials": "Materials",
        "utilities": "Utilities",
        "realestate": "Real Estate",
        "real estate": "Real Estate",
        "consumer discretionary": "Consumer Discretionary",
        "consumer staples": "Consumer Staples",
        "discretionary": "Consumer Discretionary",
        "staples": "Consumer Staples",
        "telecom": "Communication Services",
        "communication": "Communication Services",
    }
    sector = SECTOR_MAP.get(topic.lower(), topic)

    # Get symbols in this sector
    rows = query("SELECT symbol FROM stock_universe WHERE sector = ?", (sector,))
    symbols = [r["symbol"] for r in rows]

    if not symbols:
        # Try partial match
        rows = query("SELECT symbol FROM stock_universe WHERE sector LIKE ?", (f"%{topic}%",))
        symbols = [r["symbol"] for r in rows]
        if rows:
            sector = query("SELECT DISTINCT sector FROM stock_universe WHERE sector LIKE ?", (f"%{topic}%",))[0]["sector"]

    return {
        "display_name": sector,
        "topic_type": "sector",
        "sector": sector,
        "symbols": symbols,
        "expert_types": [sector.lower().replace(" ", "_")],
    }


def _collect_macro_context() -> dict:
    """Collect macro regime and heat index from DB."""
    regime_rows = query("SELECT * FROM macro_scores ORDER BY date DESC LIMIT 1")
    regime = dict(regime_rows[0]) if regime_rows else {"regime": "neutral", "total_score": 0}

    heat_rows = query("SELECT * FROM economic_heat_index ORDER BY date DESC LIMIT 1")
    heat = {}
    if heat_rows:
        heat = dict(heat_rows[0])
        try:
            details = json.loads(heat.get("details", "{}") or "{}")
            heat.update(details)
        except (json.JSONDecodeError, TypeError):
            pass

    pm_rows = query("""
        SELECT * FROM prediction_market_raw
        WHERE date >= date('now', '-3 days')
        ORDER BY volume DESC LIMIT 8
    """)

    return {"regime": regime, "heat_index": heat, "prediction_markets": pm_rows}


def _collect_stock_data(symbols: list) -> list:
    """Collect convergence + scoring data for symbols."""
    if not symbols:
        return []

    placeholders = ",".join(["?"] * len(symbols))
    rows = query(f"""
        SELECT c.symbol, c.convergence_score, c.conviction_level, c.module_count,
               c.smartmoney_score, c.pairs_score, c.sector_expert_score,
               c.energy_intel_score, c.variant_score, c.estimate_momentum_score,
               c.narrative,
               t.total_score as tech_total,
               f.total_score as fund_total
        FROM convergence_signals c
        LEFT JOIN technical_scores t ON c.symbol = t.symbol
            AND t.date = (SELECT MAX(date) FROM technical_scores WHERE symbol = c.symbol)
        LEFT JOIN fundamental_scores f ON c.symbol = f.symbol
            AND f.date = (SELECT MAX(date) FROM fundamental_scores WHERE symbol = c.symbol)
        WHERE c.symbol IN ({placeholders})
          AND c.date = (SELECT MAX(date) FROM convergence_signals WHERE symbol = c.symbol)
        ORDER BY c.convergence_score DESC
    """, symbols)

    stock_data = []
    for r in rows:
        stock_data.append({
            "symbol": r["symbol"],
            "convergence_score": r["convergence_score"] or 0,
            "conviction_level": r["conviction_level"] or "WATCH",
            "module_count": r["module_count"] or 0,
            "technical": {"total_score": r["tech_total"] or 0},
            "fundamental": {"total_score": r["fund_total"] or 0},
            "smartmoney_score": r["smartmoney_score"] or 0,
            "pairs_score": r["pairs_score"] or 0,
            "sector_expert_score": r["sector_expert_score"] or 0,
            "signal": {"signal": "BUY" if (r["convergence_score"] or 0) >= 60 else "HOLD"},
        })
    return stock_data


def _collect_pairs_data(symbols: list) -> list:
    """Collect pairs trading signals for symbols."""
    if not symbols:
        return []

    placeholders = ",".join(["?"] * len(symbols))
    rows = query(f"""
        SELECT ps.symbol_a, ps.symbol_b, ps.signal_type, ps.spread_zscore,
               ps.direction, ps.pairs_score, ps.runner_symbol
        FROM pair_signals ps
        WHERE ps.date >= date('now', '-7 days')
          AND (ps.symbol_a IN ({placeholders}) OR ps.symbol_b IN ({placeholders}))
        ORDER BY ps.date DESC
    """, symbols + symbols)

    pairs = []
    for r in rows:
        pairs.append({
            "symbol_a": r["symbol_a"],
            "symbol_b": r["symbol_b"],
            "signal_type": r["signal_type"],
            "spread_zscore": r["spread_zscore"] or 0,
            "direction": r["direction"] or "",
            "pairs_score": r["pairs_score"] or 0,
            "runner_symbol": r["runner_symbol"] or "",
        })
    return pairs


def _collect_smart_money_data(symbols: list) -> dict:
    """Collect smart money + insider data for symbols."""
    if not symbols:
        return {"smart_money": [], "insider": []}

    placeholders = ",".join(["?"] * len(symbols))

    sm_rows = query(f"""
        SELECT s.symbol, s.conviction_score, s.manager_count, s.top_holders
        FROM smart_money_scores s
        WHERE s.symbol IN ({placeholders})
          AND s.date = (SELECT MAX(date) FROM smart_money_scores WHERE symbol = s.symbol)
          AND s.conviction_score > 0
        ORDER BY s.conviction_score DESC LIMIT 10
    """, symbols)

    insider_rows = query(f"""
        SELECT i.symbol, i.insider_score, i.cluster_buy, i.total_buy_value_30d
        FROM insider_signals i
        WHERE i.symbol IN ({placeholders})
          AND i.date >= date('now', '-14 days')
          AND i.insider_score > 20
        ORDER BY i.insider_score DESC LIMIT 10
    """, symbols)

    return {"smart_money": [dict(r) for r in sm_rows], "insider": [dict(r) for r in insider_rows]}


def _generate_narrative_gemini(prompt: str) -> str:
    """Call Gemini to generate narrative text."""
    import requests as req
    url = f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        resp = req.post(url, json=body, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"    Gemini error: {e}")
        return "[Narrative generation failed — data-only mode]"


def _collect_all_data(topic: str, skip_gemini: bool = False) -> dict:
    """Collect all data needed for the deck directly from DB + optional Gemini narratives."""
    import time

    init_db()

    print(f"\n  Collecting data for: {topic}")
    topic_info = _resolve_topic(topic)
    print(f"    Topic: {topic_info['display_name']} ({topic_info['topic_type']})")
    print(f"    Symbols: {len(topic_info['symbols'])}")

    macro = _collect_macro_context()
    stock_data = _collect_stock_data(topic_info["symbols"])
    pairs_data = _collect_pairs_data(topic_info["symbols"])
    sm_data = _collect_smart_money_data(topic_info["symbols"])

    # Generate narratives via Gemini (or use placeholders)
    if skip_gemini or not GEMINI_API_KEY:
        exec_summary = _build_data_summary(topic_info, macro, stock_data)
        deepdive = _build_sector_summary(topic_info, stock_data)
        risk_matrix = _build_risk_summary(macro, stock_data)
    else:
        print("    Generating narratives (Gemini)...")
        regime = macro.get("regime", {})
        regime_name = regime.get("regime", "neutral")
        top_stocks = ", ".join(s["symbol"] for s in stock_data[:5])

        exec_summary = _generate_narrative_gemini(
            f"Write a 3-paragraph executive summary for a {topic_info['display_name']} sector intelligence brief. "
            f"Current macro regime: {regime_name}. Top conviction stocks: {top_stocks}. "
            f"Total stocks analyzed: {len(stock_data)}. "
            f"Be concise, data-driven, and institutional in tone. No markdown formatting."
        )
        time.sleep(2)
        deepdive = _generate_narrative_gemini(
            f"Write a 3-paragraph sector deep-dive for {topic_info['display_name']}. "
            f"Cover key drivers, risks, and positioning. Regime: {regime_name}. "
            f"Top picks: {top_stocks}. Institutional tone, no markdown."
        )
        time.sleep(2)
        risk_matrix = _generate_narrative_gemini(
            f"Write a risk matrix for {topic_info['display_name']} sector with 5-6 key risks. "
            f"For each risk: name, probability (HIGH/MED/LOW), impact, and mitigation. "
            f"Macro regime: {regime_name}. Institutional tone, no markdown."
        )

    return {
        "topic_info": topic_info,
        "macro": macro,
        "stock_data": stock_data,
        "sector_data": {},
        "pairs_data": pairs_data,
        "sm_data": sm_data,
        "exec_summary": exec_summary,
        "deepdive": deepdive,
        "risk_matrix": risk_matrix,
    }


def _build_data_summary(topic_info, macro, stock_data):
    """Build a plain-text executive summary from data (no LLM needed)."""
    regime = macro.get("regime", {})
    regime_name = (regime.get("regime", "neutral") or "neutral").replace("_", " ").upper()
    top = stock_data[:5]

    lines = [
        f"The {topic_info['display_name']} sector analysis covers {len(stock_data)} stocks under a {regime_name} macro regime.",
        "",
    ]
    if top:
        lines.append("Top conviction picks:")
        for s in top:
            lines.append(f"  {s['symbol']}: convergence {s['convergence_score']:.1f}, "
                         f"tech {s['technical']['total_score']:.0f}, fund {s['fundamental']['total_score']:.0f} "
                         f"({s['conviction_level']})")
    return "\n".join(lines)


def _build_sector_summary(topic_info, stock_data):
    """Build sector summary from data."""
    if not stock_data:
        return f"No convergence data available for {topic_info['display_name']}."

    avg_conv = sum(s["convergence_score"] for s in stock_data) / len(stock_data)
    high_count = sum(1 for s in stock_data if s["conviction_level"] == "HIGH")

    return (
        f"{topic_info['display_name']} sector: {len(stock_data)} stocks analyzed.\n"
        f"Average convergence score: {avg_conv:.1f}. "
        f"{high_count} HIGH conviction signals.\n"
        f"Strongest: {stock_data[0]['symbol']} ({stock_data[0]['convergence_score']:.1f})" if stock_data else ""
    )


def _build_risk_summary(macro, stock_data):
    """Build risk summary from data."""
    regime = macro.get("regime", {})
    lines = ["Key risks to monitor:", ""]
    if regime.get("vix_score", 0) and regime["vix_score"] < -5:
        lines.append("  Volatility: VIX elevated, risk-off conditions possible")
    if regime.get("credit_spreads_score", 0) and regime["credit_spreads_score"] < -5:
        lines.append("  Credit: Spreads widening, credit stress emerging")
    if regime.get("yield_curve_score", 0) and regime["yield_curve_score"] < -5:
        lines.append("  Rates: Yield curve under pressure")
    lines.append("  Concentration: Conviction concentrated in few names")
    lines.append("  Macro: Regime shifts can rapidly change sector dynamics")
    return "\n".join(lines)


def _load_from_db(topic: str) -> dict:
    """Try to load a recent report from DB to avoid re-running Gemini."""
    rows = query("""
        SELECT topic, report_markdown, metadata, regime, symbols_covered
        FROM intelligence_reports
        WHERE topic = ? AND generated_at >= datetime('now', '-1 day')
        ORDER BY generated_at DESC LIMIT 1
    """, (topic,))

    if not rows:
        return None

    print(f"    Found recent report for '{topic}' in DB")
    return rows[0]


# ═══════════════════════════════════════════════════════════════════
#  MAIN DECK BUILDER
# ═══════════════════════════════════════════════════════════════════

def generate_deck(topic: str, skip_gemini: bool = False) -> dict:
    """Generate a professional Google Slides deck from intelligence data.

    Args:
        topic: Sector, theme, or thesis name
        skip_gemini: If True, use placeholder text instead of LLM calls

    Returns:
        dict with presentation_id, url, slide_count
    """
    global _slide_counter
    _slide_counter = 0

    print(f"\n{'=' * 60}")
    print(f"  GOOGLE SLIDES DECK: {topic.upper()}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}")

    # Collect data
    data = _collect_all_data(topic, skip_gemini=skip_gemini)
    topic_info = data["topic_info"]
    macro = data["macro"]
    stock_data = data["stock_data"]
    pairs_data = data["pairs_data"]
    sm_data = data["sm_data"]
    exec_summary = data["exec_summary"]
    deepdive = data["deepdive"]
    risk_matrix = data["risk_matrix"]

    # Create presentation
    title = f"Intelligence Brief: {topic_info['display_name']} — {date.today().isoformat()}"
    print(f"\n  Creating presentation: {title}")
    pres_id = create_presentation(title)

    # Build all slides
    print("  Building slides...")
    all_requests = []

    # 1. Title slide
    _, reqs = build_title_slide(topic_info, macro)
    all_requests.extend(reqs)
    print("    [1] Title slide")

    # 2. Executive summary
    _, reqs = build_exec_summary_slide(exec_summary, macro)
    all_requests.extend(reqs)
    print("    [2] Executive summary")

    # 3. Macro context
    _, reqs = build_macro_slide(macro)
    all_requests.extend(reqs)
    print("    [3] Macro context")

    # 4. Sector deep-dive
    _, reqs = build_deepdive_slide(deepdive, topic_info)
    all_requests.extend(reqs)
    print("    [4] Sector deep-dive")

    # 5-6. Conviction ranking (paginated)
    stocks_per_slide = 12
    num_conviction_slides = max(1, (len(stock_data) + stocks_per_slide - 1) // stocks_per_slide)
    for i in range(min(num_conviction_slides, 3)):  # Cap at 3 pages
        _, reqs = build_conviction_slide(stock_data, i + 1, stocks_per_slide)
        all_requests.extend(reqs)
        print(f"    [{5 + i}] Conviction ranking (page {i + 1})")

    slide_num = 5 + min(num_conviction_slides, 3)

    # Pairs
    if pairs_data:
        _, reqs = build_pairs_slide(pairs_data)
        all_requests.extend(reqs)
        print(f"    [{slide_num}] Pairs & relative value")
        slide_num += 1

    # Smart money
    if sm_data.get("smart_money") or sm_data.get("insider"):
        _, reqs = build_smart_money_slide(sm_data)
        all_requests.extend(reqs)
        print(f"    [{slide_num}] Smart money & insider")
        slide_num += 1

    # Risk matrix
    _, reqs = build_risk_slide(risk_matrix)
    all_requests.extend(reqs)
    print(f"    [{slide_num}] Risk matrix")
    slide_num += 1

    # Closing
    _, reqs = build_closing_slide()
    all_requests.extend(reqs)
    print(f"    [{slide_num}] Closing")

    # Delete the default blank slide (index 0)
    # First, get the presentation to find the default slide ID
    # Filter out None entries (from skipped empty text styles)
    all_requests = [r for r in all_requests if r is not None]
    print(f"\n  Sending {len(all_requests)} API requests...")

    # Send in batches (API limit is ~500 requests per batch)
    batch_size = 400
    for i in range(0, len(all_requests), batch_size):
        batch = all_requests[i:i + batch_size]
        resp = batch_update(pres_id, batch)
        if "error" in resp:
            print(f"    ERROR in batch {i // batch_size + 1}: {resp['error']}")
            # Try to continue — partial deck is better than nothing
        else:
            print(f"    Batch {i // batch_size + 1}: {len(batch)} requests OK")

    # Delete the default first blank slide
    pres = get_presentation(pres_id)
    if pres and "slides" in pres:
        default_slide_id = pres["slides"][0]["objectId"]
        batch_update(pres_id, [{"deleteObject": {"objectId": default_slide_id}}])
        print("    Removed default blank slide")

    url = f"https://docs.google.com/presentation/d/{pres_id}/edit"
    print(f"\n  {'=' * 60}")
    print(f"  DECK READY: {url}")
    print(f"  Slides: {slide_num}")
    print(f"  {'=' * 60}\n")

    return {
        "presentation_id": pres_id,
        "url": url,
        "slide_count": slide_num,
        "topic": topic_info["display_name"],
    }


# ═══════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════

def run():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Generate professional Google Slides intelligence deck")
    parser.add_argument("--topic", "-t",
                        help="Sector, theme, or thesis (e.g., 'energy', 'AI power')")
    parser.add_argument("--skip-gemini", action="store_true",
                        help="Skip LLM calls (use placeholders for narrative sections)")
    parser.add_argument("--setup", action="store_true",
                        help="Just run OAuth setup and verify credentials work")

    args = parser.parse_args()

    if args.setup:
        print("\n  Google Slides API — OAuth Setup")
        print("  " + "=" * 40)
        try:
            creds = _get_creds()
            service = _get_slides_service()
            # Quick test: create and delete a presentation
            test = service.presentations().create(body={"title": "API Test (delete me)"}).execute()
            test_id = test["presentationId"]
            print(f"    OAuth OK — test presentation created: {test_id}")
            print(f"    Token saved to: {TOKEN_PATH}")
            print(f"    Open: https://docs.google.com/presentation/d/{test_id}/edit")
            print("\n  Setup complete! You can now run:")
            print("    python -m tools.google_slides --topic energy")
        except FileNotFoundError as e:
            print(f"\n    ERROR: {e}")
            print("\n  To fix:")
            print("    1. Go to console.cloud.google.com")
            print("    2. Enable 'Google Slides API' and 'Google Drive API'")
            print("    3. Create OAuth 2.0 Desktop credentials")
            print("    4. Download as credentials.json to project root")
        except Exception as e:
            print(f"\n    ERROR: {e}")
        return

    if not args.topic:
        parser.error("--topic is required (unless using --setup)")

    result = generate_deck(args.topic, skip_gemini=args.skip_gemini)
    print(f"\nOpen your deck: {result['url']}")


if __name__ == "__main__":
    run()
