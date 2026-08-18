"""
app.py
------
Micro-Doppler Radar Target Classification — Flask backend.
"""

from __future__ import annotations

import os
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
from sqlalchemy import func, select

from config import get_config
from models import db, init_db, EdgeNode, RadarSample, Classification
from ml.classifier import classifier
from edge_node.simulator import EdgeNodeSimulator, RadarSampleData

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("radar_app")

# ---------------------------------------------------------------------------
# App / extensions setup
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config.from_object(get_config())

init_db(app)

socketio = SocketIO(
    app,
    async_mode=app.config.get("SOCKETIO_ASYNC_MODE", "threading"),
    cors_allowed_origins="*",
    message_queue=app.config.get("SOCKETIO_MESSAGE_QUEUE"),  # Redis URL in multi-worker prod, else None
)

_simulator: Optional[EdgeNodeSimulator] = None
_simulator_lock = threading.Lock()
_sample_counter = {"count": 0}

DEFAULT_NODE_NAME = "SIM-EDGE-01"


# ---------------------------------------------------------------------------
# Edge node -> DB -> WebSocket pipeline
# ---------------------------------------------------------------------------
def handle_incoming_sample(sample: RadarSampleData):
    """
    Callback invoked by the EdgeNodeSimulator background thread for every
    generated radar sample (10Hz). Runs the simulated ML classifier, persists
    to PostgreSQL (throttled), and broadcasts both the raw telemetry and any
    new classification over WebSocket to all connected dashboards.
    """
    with app.app_context():
        try:
            node = db.session.get(EdgeNode, sample.node_id)
            if node is None:
                logger.warning("Sample received for unknown node_id=%s", sample.node_id)
                return

            node.last_seen_at = datetime.now(timezone.utc)
            node.status = "online"

            _sample_counter["count"] += 1
            persist_every_n = app.config.get("CLASSIFICATION_PERSIST_EVERY_N", 10)
            should_persist_sample = (_sample_counter["count"] % max(1, persist_every_n // 2)) == 0
            should_classify = (_sample_counter["count"] % persist_every_n) == 0

            db_sample = None
            if should_persist_sample:
                db_sample = RadarSample(
                    node_id=node.id,
                    timestamp=datetime.fromtimestamp(sample.timestamp, tz=timezone.utc),
                    doppler_freq_hz=sample.doppler_freq_hz,
                    signal_power_db=sample.signal_power_db,
                    radial_velocity_mps=sample.radial_velocity_mps,
                    spectrum_bins=sample.spectrum_bins,
                )
                db.session.add(db_sample)
                db.session.flush()  # get db_sample.id without full commit yet

            classification_payload = None
            if should_classify:
                result = classifier.predict(
                    doppler_freq_hz=sample.doppler_freq_hz,
                    radial_velocity_mps=sample.radial_velocity_mps,
                    spectrum_bins=sample.spectrum_bins,
                )
                db_classification = Classification(
                    node_id=node.id,
                    sample_id=db_sample.id if db_sample else None,
                    target_type=result.target_type,
                    confidence=result.confidence,
                    model_version=result.model_version,
                    doppler_freq_hz=sample.doppler_freq_hz,
                    radial_velocity_mps=sample.radial_velocity_mps,
                    timestamp=datetime.fromtimestamp(sample.timestamp, tz=timezone.utc),
                )
                db.session.add(db_classification)
                db.session.flush()
                classification_payload = db_classification.to_dict()
                classification_payload["signature"] = result.signature
                classification_payload["threat_level"] = result.threat_level
                classification_payload["threat_color"] = result.threat_color
                classification_payload["threat_code"] = result.threat_code

            db.session.commit()

            # --- broadcast over WebSocket (always, regardless of persistence) ---
            socketio.emit("radar_sample", {
                "node_id": node.id,
                "node_name": node.name,
                "timestamp": sample.timestamp,
                "doppler_freq_hz": round(sample.doppler_freq_hz, 2),
                "signal_power_db": round(sample.signal_power_db, 2),
                "radial_velocity_mps": round(sample.radial_velocity_mps, 2),
                "spectrum_bins": sample.spectrum_bins,
                "scenario": sample.scenario,
            })

            if classification_payload:
                classification_payload["node_name"] = node.name
                socketio.emit("classification", classification_payload)

        except Exception:
            db.session.rollback()
            logger.exception("Error while handling incoming radar sample")


def start_edge_simulator():
    """Start (or restart) the background edge-node simulator thread."""
    global _simulator
    with _simulator_lock:
        if _simulator and _simulator.is_running:
            return _simulator

        with app.app_context():
            node = EdgeNode.query.filter_by(name=DEFAULT_NODE_NAME).first()
            if node is None:
                node = EdgeNode(name=DEFAULT_NODE_NAME, location="Simulated Perimeter Sensor",
                                 is_simulated=True, status="online")
                db.session.add(node)
                db.session.commit()
            node_id = node.id

        rate_hz = app.config.get("RADAR_STREAM_HZ", 10.0)
        _simulator = EdgeNodeSimulator(node_id=node_id, on_sample=handle_incoming_sample, rate_hz=rate_hz)
        _simulator.start()
        logger.info("Edge node simulator started at %.1f Hz (node_id=%s)", rate_hz, node_id)
        return _simulator


def stop_edge_simulator():
    global _simulator
    with _simulator_lock:
        if _simulator:
            _simulator.stop()
            with app.app_context():
                node = db.session.get(EdgeNode, _simulator.node_id)
                if node:
                    node.status = "offline"
                    db.session.commit()
            logger.info("Edge node simulator stopped")


# ---------------------------------------------------------------------------
# Page routes (Unified Single-Page Application)
# ---------------------------------------------------------------------------
@app.route("/")
@app.route("/console")
@app.route("/console.html")
@app.route("/history")
@app.route("/history.html")
@app.route("/overview")
@app.route("/start")
@app.route("/start.html")
@app.route("/diagnostics")
def main_app():
    return render_template("index.html")


@app.route("/start_alias", endpoint="start_page")
def start_page():
    return render_template("index.html")


@app.route("/console_alias", endpoint="console_page")
def console_page():
    return render_template("index.html")


@app.route("/history_alias", endpoint="history_page")
def history_page():
    return render_template("index.html")


@app.route("/overview_alias", endpoint="overview_page")
def overview_page():
    return render_template("index.html")


@app.route("/diagnostics_alias", endpoint="diagnostics_page")
def diagnostics_page():
    return render_template("index.html")




# ---------------------------------------------------------------------------
# REST API — simulator control
# ---------------------------------------------------------------------------
@app.route("/api/simulator/start", methods=["POST"])
def api_start_simulator():
    sim = start_edge_simulator()
    return jsonify({"status": "started", "running": sim.is_running, "rate_hz": sim.rate_hz})


@app.route("/api/simulator/stop", methods=["POST"])
def api_stop_simulator():
    stop_edge_simulator()
    return jsonify({"status": "stopped"})


@app.route("/api/simulator/status")
def api_simulator_status():
    running = bool(_simulator and _simulator.is_running)
    return jsonify({"running": running, "rate_hz": app.config.get("RADAR_STREAM_HZ")})


# ---------------------------------------------------------------------------
# REST API — nodes
# ---------------------------------------------------------------------------
@app.route("/api/nodes")
def api_nodes():
    nodes = EdgeNode.query.order_by(EdgeNode.name).all()
    return jsonify([n.to_dict() for n in nodes])


# ---------------------------------------------------------------------------
# REST API — historical querying
# ---------------------------------------------------------------------------
@app.route("/api/classifications")
def api_classifications():
    """
    Query historical classifications.

    Query params:
      target_type: filter by exact target type (Drone, Bird, Human, Vehicle, Unknown)
      date_from:   ISO date/datetime, inclusive lower bound
      date_to:     ISO date/datetime, inclusive upper bound
      min_confidence: float 0-1
      node_id:     filter by edge node id
      page, per_page: pagination (defaults 1 / 25, max per_page 200)
    """
    query = Classification.query

    target_type = request.args.get("target_type")
    if target_type and target_type != "All":
        query = query.filter(Classification.target_type == target_type)

    node_id = request.args.get("node_id")
    if node_id:
        query = query.filter(Classification.node_id == node_id)

    min_confidence = request.args.get("min_confidence", type=float)
    if min_confidence is not None:
        query = query.filter(Classification.confidence >= min_confidence)

    date_from = _parse_date(request.args.get("date_from"))
    if date_from:
        query = query.filter(Classification.timestamp >= date_from)

    date_to = _parse_date(request.args.get("date_to"), end_of_day=True)
    if date_to:
        query = query.filter(Classification.timestamp <= date_to)

    try:
        raw_page = request.args.get("page", 1)
        page = max(1, int(raw_page))
    except (ValueError, TypeError):
        page = 1

    try:
        raw_per_page = request.args.get("per_page", 25)
        per_page = max(1, min(int(raw_per_page), 200))
    except (ValueError, TypeError):
        per_page = 25

    query = query.order_by(Classification.timestamp.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    results = [c.to_dict() for c in pagination.items]
    for c, row in zip(pagination.items, results):
        row["node_name"] = c.node.name if (c and c.node) else None

    return jsonify({
        "results": results,
        "page": pagination.page,
        "per_page": pagination.per_page,
        "total": pagination.total,
        "pages": pagination.pages,
    })


@app.route("/api/classifications/summary")
def api_classifications_summary():
    """Aggregate counts by target_type for the current filter window (for charts)."""
    date_from = _parse_date(request.args.get("date_from"))
    date_to = _parse_date(request.args.get("date_to"), end_of_day=True)

    query = db.session.query(
        Classification.target_type, func.count(Classification.id), func.avg(Classification.confidence)
    ).group_by(Classification.target_type)

    if date_from:
        query = query.filter(Classification.timestamp >= date_from)
    if date_to:
        query = query.filter(Classification.timestamp <= date_to)

    rows = query.all()
    return jsonify([
        {"target_type": t, "count": c, "avg_confidence": round(float(a), 3) if a is not None else 0}
        for t, c, a in rows
    ])


def _parse_date(value: Optional[str], end_of_day: bool = False):
    if not value:
        return None
    try:
        if len(value) == 10:  # YYYY-MM-DD
            dt = datetime.strptime(value, "%Y-%m-%d")
            if end_of_day:
                dt = dt + timedelta(hours=23, minutes=59, seconds=59)
        else:
            dt = datetime.fromisoformat(value)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Health check (useful for cloud load balancers / Render / AWS)
# ---------------------------------------------------------------------------
@app.route("/healthz")
def healthz():
    try:
        db.session.execute(select(func.count()).select_from(EdgeNode))
        db_ok = True
    except Exception:
        db_ok = False
    return jsonify({
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else "unreachable",
        "simulator_running": bool(_simulator and _simulator.is_running),
    }), (200 if db_ok else 503)


# ---------------------------------------------------------------------------
# SocketIO event handlers
# ---------------------------------------------------------------------------
@socketio.on("connect")
def on_connect():
    logger.info("Client connected: %s", request.sid)
    start_edge_simulator()
    socketio.emit("status", {"message": "Connected to radar telemetry stream"}, to=request.sid)


@socketio.on("disconnect")
def on_disconnect():
    logger.info("Client disconnected: %s", request.sid)


@socketio.on("request_simulator_start")
def on_request_start():
    start_edge_simulator()


@socketio.on("request_simulator_stop")
def on_request_stop():
    stop_edge_simulator()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    with app.app_context():
        start_edge_simulator()
    socketio.run(app, host="0.0.0.0", port=port, debug=app.config.get("DEBUG", False), allow_unsafe_werkzeug=True)
