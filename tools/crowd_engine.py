"""Crowd Intelligence Engine — scoring, divergence detection, report generation."""
import sys, json, logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import numpy as np

from tools.crowd_types import Signal

logger = logging.getLogger(__name__)

REGIME_WEIGHTS: dict[str, dict[str, float]] = {
    "strong_risk_on":  {"smart": 0.30, "institutional": 0.50, "retail_penalty": 0.20},
    "risk_on":         {"smart": 0.35, "institutional": 0.45, "retail_penalty": 0.20},
    "neutral":         {"smart": 0.40, "institutional": 0.40, "retail_penalty": 0.20},
    "risk_off":        {"smart": 0.55, "institutional": 0.35, "retail_penalty": 0.10},
    "strong_risk_off": {"smart": 0.60, "institutional": 0.30, "retail_penalty": 0.10},
}
DEFAULT_REGIME = "neutral"


def normalize_signal_value(value: float, history: list[float]) -> float:
    """Z-score normalize value against rolling history, rescale to [0, 1]."""
    arr = np.array(history, dtype=float)
    if len(arr) < 2:
        return 0.5
    mean = float(np.mean(arr))
    std  = float(np.std(arr))
    if std < 1e-9:
        return 0.5
    z = (value - mean) / std
    z_clipped = float(np.clip(z, -3.0, 3.0)) / 3.0
    return float((z_clipped + 1.0) / 2.0)


def apply_decay(signal: Signal) -> float:
    """Return exponential decay weight for signal given its age."""
    return signal.decay_weight


def score_layer(signals: list[Signal], layer_type: str) -> Optional[float]:
    """Combine signals within a layer using IC-weighted, decay-adjusted average.

    For 'retail' layer: values are inverted (1 - normalized) — contrarian.
    Returns None if no signals available.
    """
    if not signals:
        return None
    total_weight = sum(abs(s.ic) * s.decay_weight for s in signals)
    if total_weight < 1e-12:
        return None
    score = 0.0
    for s in signals:
        w = abs(s.ic) * s.decay_weight / total_weight
        value = (1.0 - s.normalized) if layer_type == "retail" else s.normalized
        score += w * value
    return float(np.clip(score, 0.0, 1.0))


def compute_conviction(
    retail: float,
    institutional: float,
    smart: float,
    regime: str = DEFAULT_REGIME,
) -> float:
    """Compute final conviction score [0-100].

    retail is a crowding score — higher retail = more penalty.
    Alignment multiplier: max disagreement → score = 0.
    """
    weights = REGIME_WEIGHTS.get(regime, REGIME_WEIGHTS[DEFAULT_REGIME])
    raw = (
        weights["smart"]          * smart
      + weights["institutional"]  * institutional
      - weights["retail_penalty"] * retail
    )
    aligned_retail = 1.0 - retail
    std = float(np.std([smart, institutional, aligned_retail]))
    alignment = max(0.0, 1.0 - (std / 0.577))
    return float(np.clip(raw * alignment * 100.0, 0.0, 100.0))


def run_divergence_detector(
    retail_score: float,
    institutional_score: float,
    smart_score: float,
    short_dtc: Optional[float],
    has_catalyst: bool,
    insider_cluster: bool = False,
    unusual_calls: bool = False,
) -> Optional[str]:
    """Classify divergence signal type. Priority order matters — most specific first."""
    if retail_score < 20 and insider_cluster and unusual_calls:
        return "HIDDEN_GEM"
    if short_dtc is not None and short_dtc > 10 and institutional_score > 55 and has_catalyst:
        return "SHORT_SQUEEZE"
    if retail_score > 70 and institutional_score < 40 and smart_score < 35:
        return "DISTRIBUTION"
    if retail_score > 75 and (institutional_score < 45 or smart_score < 35):
        return "CROWDED_FADE"
    if retail_score < 30 and institutional_score > 60 and smart_score > 65:
        return "CONTRARIAN_BUY"
    if institutional_score > 65 and smart_score > 60 and retail_score < 40:
        return "STEALTH_ACCUM"
    return None


def detect_regime() -> str:
    """Fetch current macro regime from DB or return DEFAULT_REGIME."""
    try:
        from tools.db import query
        rows = query("SELECT regime FROM macro_scores ORDER BY date DESC LIMIT 1")
        if rows and rows[0].get("regime") in REGIME_WEIGHTS:
            return rows[0]["regime"]
    except Exception:
        pass
    return DEFAULT_REGIME
