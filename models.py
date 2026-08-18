"""
models.py
---------
SQLAlchemy ORM schemas for the Micro-Doppler Radar Target Classification
system. Backed by PostgreSQL (no JSON-file storage is used anywhere).
"""

from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any, Dict, List, Optional

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import ARRAY, Float, JSON

db = SQLAlchemy()


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EdgeNode(db.Model):
    """A radar sensor node (real or simulated/'edge') that streams telemetry."""

    __tablename__ = "edge_nodes"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    name = db.Column(db.String(120), unique=True, nullable=False)
    location = db.Column(db.String(200), nullable=True)
    is_simulated = db.Column(db.Boolean, default=True, nullable=False)
    status = db.Column(db.String(20), default="offline", nullable=False)  # online|offline|error
    created_at = db.Column(db.DateTime(timezone=True), default=_utcnow, nullable=False)
    last_seen_at = db.Column(db.DateTime(timezone=True), default=_utcnow, nullable=False)

    samples = db.relationship("RadarSample", backref="node", lazy="dynamic",
                               cascade="all, delete-orphan")
    classifications = db.relationship("Classification", backref="node", lazy="dynamic",
                                       cascade="all, delete-orphan")

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "location": self.location,
            "is_simulated": self.is_simulated,
            "status": self.status,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
        }


class RadarSample(db.Model):
    """A single micro-Doppler telemetry sample (one waterfall row)."""

    __tablename__ = "radar_samples"

    id = db.Column(db.Integer, primary_key=True)
    node_id = db.Column(db.String(36), db.ForeignKey("edge_nodes.id"), nullable=False, index=True)

    timestamp = db.Column(db.DateTime(timezone=True), default=_utcnow, nullable=False, index=True)

    # Dominant / characteristic micro-Doppler frequency shift in Hz.
    doppler_freq_hz = db.Column(db.Float, nullable=False)
    # Signal magnitude / return power in dB.
    signal_power_db = db.Column(db.Float, nullable=False)
    # Bulk radial velocity component estimated from the Doppler shift (m/s).
    radial_velocity_mps = db.Column(db.Float, nullable=False)
    # Comma-separated micro-Doppler frequency bin magnitudes (spectrogram row),
    # stored as a Postgres ARRAY of floats — NOT a JSON blob/file.
    spectrum_bins = db.Column(db.ARRAY(db.Float), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=_utcnow, nullable=False)

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    def to_dict(self):
        return {
            "id": self.id,
            "node_id": self.node_id,
            "timestamp": self.timestamp.isoformat(),
            "doppler_freq_hz": round(self.doppler_freq_hz, 2),
            "signal_power_db": round(self.signal_power_db, 2),
            "radial_velocity_mps": round(self.radial_velocity_mps, 2),
            "spectrum_bins": [round(v, 3) for v in (self.spectrum_bins or [])],
        }


class Classification(db.Model):
    """ML model prediction for a given (window of) radar samples."""

    __tablename__ = "classifications"

    TARGET_TYPES = ("Drone", "Bird", "Human", "Vehicle", "Unknown")

    id = db.Column(db.Integer, primary_key=True)
    node_id = db.Column(db.String(36), db.ForeignKey("edge_nodes.id"), nullable=False, index=True)
    sample_id = db.Column(db.Integer, db.ForeignKey("radar_samples.id"), nullable=True, index=True)

    target_type = db.Column(db.String(30), nullable=False, index=True)
    confidence = db.Column(db.Float, nullable=False)  # 0.0 - 1.0
    model_version = db.Column(db.String(30), default="mil-cnn-v2", nullable=False)

    doppler_freq_hz = db.Column(db.Float, nullable=True)
    radial_velocity_mps = db.Column(db.Float, nullable=True)

    timestamp = db.Column(db.DateTime(timezone=True), default=_utcnow, nullable=False, index=True)

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    def to_dict(self):
        threat_map = {
            "Drone": ("CRITICAL", "#ff4d5e", "ALPHA-DRONE-HOSTILE"),
            "Human": ("HIGH", "#ffb020", "BRAVO-FOOT-INFILTRATOR"),
            "Vehicle": ("MEDIUM", "#c98bff", "CHARLIE-ARMORED-VEHICLE"),
            "Bird": ("LOW", "#6fb7c9", "AVIAN-NEUTRAL-FILTERED"),
            "Unknown": ("WARNING", "#8fa8a4", "DELTA-UNIDENTIFIED-ECHO"),
        }
        tl, tc, tcode = threat_map.get(self.target_type, ("LOW", "#6fb7c9", "NEUTRAL"))
        return {
            "id": self.id,
            "node_id": self.node_id,
            "sample_id": self.sample_id,
            "target_type": self.target_type,
            "confidence": round(self.confidence, 4),
            "confidence_pct": round(self.confidence * 100, 1),
            "threat_level": tl,
            "threat_color": tc,
            "threat_code": tcode,
            "model_version": self.model_version,
            "doppler_freq_hz": round(self.doppler_freq_hz, 2) if self.doppler_freq_hz is not None else None,
            "radial_velocity_mps": round(self.radial_velocity_mps, 2) if self.radial_velocity_mps is not None else None,
            "timestamp": self.timestamp.isoformat(),
        }


_sqlite_patched = False


def _patch_sqlite_array():
    """Register SQLite type compiler and descriptor overrides for ARRAY columns."""
    global _sqlite_patched
    if _sqlite_patched:
        return
    try:
        from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler, SQLiteDialect
        from sqlalchemy.types import ARRAY, JSON
        SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "JSON"
        orig_td = SQLiteDialect.type_descriptor
        SQLiteDialect.type_descriptor = lambda self, type_: JSON() if isinstance(type_, ARRAY) else orig_td(self, type_)
        _sqlite_patched = True
    except Exception:
        pass


def init_db(app):
    """Attach SQLAlchemy to the Flask app and create tables if needed."""
    _patch_sqlite_array()
    db.init_app(app)
    with app.app_context():
        db.create_all()
        _ensure_default_node()


def _ensure_default_node():
    """Seed a default simulated edge node on first boot."""
    try:
        existing = EdgeNode.query.filter_by(name="SIM-EDGE-01").first()
        if not existing:
            node = EdgeNode(
                name="SIM-EDGE-01",
                location="Simulated Perimeter Sensor",
                is_simulated=True,
                status="offline",
            )
            db.session.add(node)
            db.session.commit()
    except Exception:
        db.session.rollback()

