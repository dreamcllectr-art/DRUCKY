"""Tests for crowd intelligence scoring engine."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pytest
from tools.crowd_types import Signal

# Note: crowd_engine imports will be added when that module is created
# from tools.crowd_engine import (
#     normalize_signal_value,
#     apply_decay,
#     score_layer,
#     compute_conviction,
#     run_divergence_detector,
# )

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
