"""Tests for crowd intelligence scoring engine."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pytest
from tools.crowd_types import Signal

try:
    from tools.crowd_engine import (
        normalize_signal_value,
        apply_decay,
        score_layer,
        compute_conviction,
        run_divergence_detector,
    )
except ImportError:
    normalize_signal_value = None
    apply_decay = None
    score_layer = None
    compute_conviction = None
    run_divergence_detector = None

# ── Signal dataclass ──────────────────────────────────────────────────────────

def test_signal_fields():
    s = Signal(
        name="test", value=50.0, normalized=0.5, ic=0.07,
        half_life=14, age_days=0, layer="institutional", source="cot"
    )
    assert s.decay_weight == 1.0  # age=0 → no decay

def test_signal_decay_half_life():
    s = Signal(
        name="test", value=50.0, normalized=0.5, ic=0.07,
        half_life=14, age_days=14, layer="institutional", source="cot"
    )
    assert abs(s.decay_weight - 0.5) < 1e-9  # exactly half at half-life

def test_signal_decay_zero_age():
    s = Signal(
        name="test", value=50.0, normalized=0.5, ic=0.05,
        half_life=7, age_days=0, layer="retail", source="fear_greed"
    )
    assert s.decay_weight == 1.0

# ── normalize_signal_value ─────────────────────────────────────────────────

def test_normalize_clips_to_unit_interval():
    result = normalize_signal_value(value=104.0, history=[50.0] * 252)
    assert 0.0 <= result <= 1.0

def test_normalize_median_value_near_half():
    history = list(range(1, 253))
    mean = sum(history) / len(history)
    result = normalize_signal_value(value=mean, history=history)
    assert abs(result - 0.5) < 0.05

# ── apply_decay ───────────────────────────────────────────────────────────

def test_apply_decay_formula():
    s = Signal("x", 1.0, 0.5, 0.07, 14, 7, "institutional", "cot")
    assert abs(apply_decay(s) - (0.5 ** (7 / 14))) < 1e-9

# ── score_layer ───────────────────────────────────────────────────────────

def test_score_layer_returns_none_when_empty():
    assert score_layer([], "institutional") is None

def test_score_layer_retail_inverts_value():
    s = Signal("fear_greed", 80.0, 0.9, 0.04, 1, 0, "retail", "fear_greed")
    result = score_layer([s], "retail")
    assert result < 0.2

def test_score_layer_institutional_direct():
    s = Signal("cot", 70.0, 0.8, 0.07, 14, 0, "institutional", "cot")
    result = score_layer([s], "institutional")
    assert abs(result - 0.8) < 1e-6

def test_score_layer_ic_weights_correctly():
    s_high = Signal("high_ic", 1.0, 0.9, 0.08, 90, 0, "smart", "insider")
    s_low  = Signal("low_ic",  1.0, 0.1, 0.02, 5,  0, "smart", "options")
    result = score_layer([s_high, s_low], "smart")
    assert result > 0.7

# ── compute_conviction ────────────────────────────────────────────────────

def test_conviction_in_range():
    score = compute_conviction(retail=0.2, institutional=0.8, smart=0.85, regime="risk_on")
    assert 0.0 <= score <= 100.0

def test_conviction_high_when_all_aligned_bullish():
    score = compute_conviction(retail=0.1, institutional=0.9, smart=0.9, regime="risk_on")
    assert score > 60.0

def test_conviction_low_when_layers_disagree():
    score = compute_conviction(retail=0.9, institutional=0.1, smart=0.1, regime="risk_on")
    assert score < 20.0

def test_conviction_scales_to_100():
    score = compute_conviction(retail=0.0, institutional=1.0, smart=1.0, regime="strong_risk_on")
    assert score <= 100.0

def test_conviction_uses_regime_weights():
    score_on  = compute_conviction(0.2, 0.6, 0.9, regime="risk_on")
    score_off = compute_conviction(0.2, 0.6, 0.9, regime="strong_risk_off")
    assert score_off > score_on

# ── run_divergence_detector ───────────────────────────────────────────────

def test_divergence_distribution():
    result = run_divergence_detector(
        retail_score=75.0, institutional_score=35.0, smart_score=30.0,
        short_dtc=None, has_catalyst=False
    )
    assert result == "DISTRIBUTION"

def test_divergence_contrarian_buy():
    result = run_divergence_detector(
        retail_score=25.0, institutional_score=65.0, smart_score=70.0,
        short_dtc=None, has_catalyst=False
    )
    assert result == "CONTRARIAN_BUY"

def test_divergence_hidden_gem():
    result = run_divergence_detector(
        retail_score=15.0, institutional_score=50.0, smart_score=80.0,
        short_dtc=None, has_catalyst=False,
        insider_cluster=True, unusual_calls=True
    )
    assert result == "HIDDEN_GEM"

def test_divergence_short_squeeze():
    result = run_divergence_detector(
        retail_score=20.0, institutional_score=60.0, smart_score=50.0,
        short_dtc=12.0, has_catalyst=True
    )
    assert result == "SHORT_SQUEEZE"

def test_divergence_none_when_neutral():
    result = run_divergence_detector(
        retail_score=50.0, institutional_score=50.0, smart_score=50.0,
        short_dtc=None, has_catalyst=False
    )
    assert result is None
