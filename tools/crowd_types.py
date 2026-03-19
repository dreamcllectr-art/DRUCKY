"""Shared types for the Crowd Intelligence System."""
from dataclasses import dataclass, field
import numpy as np


@dataclass
class Signal:
    """A single normalized crowd signal with metadata."""
    name: str           # human-readable label
    value: float        # raw value from source
    normalized: float   # z-score normalized to [0, 1]
    ic: float           # information coefficient (negative = contrarian)
    half_life: int      # signal half-life in days
    age_days: int       # days since signal was collected
    layer: str          # 'retail' | 'institutional' | 'smart'
    source: str         # source identifier (e.g. 'cot', 'reddit')
    low_history: bool = False  # True if <60d history, used cross-sectional rank

    @property
    def decay_weight(self) -> float:
        """Exponential decay: 0.5^(age/half_life). Fresh signal = 1.0."""
        return float(0.5 ** (self.age_days / self.half_life))
