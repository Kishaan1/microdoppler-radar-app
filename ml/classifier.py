"""
ml/classifier.py
-----------------
A lightweight, deterministic-ish SIMULATED classifier standing in for a real
trained micro-Doppler CNN/LSTM model. It maps the physical characteristics of
a generated radar sample (dominant Doppler frequency, micro-Doppler modulation
"texture" from the spectrum bins, and radial velocity) onto a target class and
a plausible confidence score.

Swap-in point: replace `SimulatedMicroDopplerClassifier.predict()` with a call
to a real model (e.g. `model.predict(spectrogram_tensor)` from a TensorFlow /
PyTorch model loaded at startup) — the rest of the pipeline (DB persistence,
WebSocket broadcast) does not need to change.
"""

import random
from dataclasses import dataclass

TARGET_PROFILES = {
    "Drone": {
        "velocity_range": (0.0, 20.0),
        "signature": "periodic rotor-blade flutter, high micro-Doppler bandwidth",
        "confidence_range": (0.85, 0.99),
        "threat_level": "CRITICAL",
        "threat_color": "#ff4d5e",
        "threat_code": "ALPHA-DRONE-HOSTILE",
    },
    "Bird": {
        "velocity_range": (2.0, 15.0),
        "signature": "irregular wingbeat modulation, low harmonic content",
        "confidence_range": (0.60, 0.92),
        "threat_level": "LOW",
        "threat_color": "#6fb7c9",
        "threat_code": "AVIAN-NEUTRAL-FILTERED",
    },
    "Human": {
        "velocity_range": (0.5, 3.5),
        "signature": "gait-cycle limb swing, torso micro-motion",
        "confidence_range": (0.75, 0.98),
        "threat_level": "HIGH",
        "threat_color": "#ffb020",
        "threat_code": "BRAVO-FOOT-INFILTRATOR",
    },
    "Vehicle": {
        "velocity_range": (5.0, 35.0),
        "signature": "engine vibration harmonic, low micro-Doppler spread",
        "confidence_range": (0.88, 0.99),
        "threat_level": "MEDIUM",
        "threat_color": "#c98bff",
        "threat_code": "CHARLIE-ARMORED-VEHICLE",
    },
    "Unknown": {
        "velocity_range": (0.0, 40.0),
        "signature": "unclassified / ambiguous signature",
        "confidence_range": (0.35, 0.60),
        "threat_level": "WARNING",
        "threat_color": "#8fa8a4",
        "threat_code": "DELTA-UNIDENTIFIED-ECHO",
    },
}

_TARGET_WEIGHTS = {
    "Drone": 0.35,
    "Bird": 0.20,
    "Human": 0.25,
    "Vehicle": 0.15,
    "Unknown": 0.05,
}


@dataclass
class ClassificationResult:
    target_type: str
    confidence: float
    signature: str
    threat_level: str = "LOW"
    threat_color: str = "#6fb7c9"
    threat_code: str = "NEUTRAL"
    model_version: str = "mil-cnn-v2"


class SimulatedMicroDopplerClassifier:
    """Stand-in for a military-trained micro-Doppler target classification model."""

    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)
        self.model_version = "mil-cnn-v2"

    def predict(self, doppler_freq_hz: float, radial_velocity_mps: float,
                spectrum_bins: list[float]) -> ClassificationResult:
        candidates = []
        weights = []
        for name, profile in TARGET_PROFILES.items():
            lo, hi = profile["velocity_range"]
            in_band = lo <= abs(radial_velocity_mps) <= hi
            w = _TARGET_WEIGHTS[name] * (3.5 if in_band else 0.3)
            candidates.append(name)
            weights.append(w)

        target_type = self._rng.choices(candidates, weights=weights, k=1)[0]
        profile = TARGET_PROFILES[target_type]

        conf_lo, conf_hi = profile["confidence_range"]
        confidence = self._rng.uniform(conf_lo, conf_hi)

        if spectrum_bins:
            mean_val = sum(spectrum_bins) / len(spectrum_bins)
            variance = sum((b - mean_val) ** 2 for b in spectrum_bins) / len(spectrum_bins)
            texture_bonus = max(-0.04, min(0.04, 0.02 - variance * 0.001))
            confidence = max(0.10, min(0.99, confidence + texture_bonus))

        return ClassificationResult(
            target_type=target_type,
            confidence=round(confidence, 4),
            signature=profile["signature"],
            threat_level=profile["threat_level"],
            threat_color=profile["threat_color"],
            threat_code=profile["threat_code"],
            model_version=self.model_version,
        )


# Module-level singleton so app.py / edge simulator share one instance.
classifier = SimulatedMicroDopplerClassifier()
