# SIGMA-9 — Tactical Micro-Doppler Radar Target Classification Console

A full-stack, cloud-ready web application simulating a real-time **Military-Grade Micro-Doppler Radar Target Classification & Perimeter Defense System**. Powered by 10 Hz WebSocket telemetry streaming, an HTML5 Canvas Waterfall Spectrogram, a 360° Target PPI Radar Scope, a deep ML classification engine (`mil-cnn-v2`), and a responsive multi-device HUD (`Laptop`, `Tablet`, `Mobile`).

> **Note on Data Source & ML Architecture:** 
> - **Physics-Based Data Source ([`edge_node/simulator.py`](file:///d:/Micro%20doppler%20radar%20project/microdoppler-radar-app/microdoppler-radar-app/edge_node/simulator.py)):** Generates 10 Hz micro-Doppler radar telemetry (Doppler shift, radial velocity in m/s, signal return power in dB, and 64 frequency spectrum bins) using physical FMCW radar equations ($f_d = \frac{2 \cdot v \cdot f_c}{c}$ at $24.125 \text{ GHz}$). Serves as a direct **hardware swap-in contract** for physical 24 GHz / 77 GHz FMCW millimeter-wave radar boards.
> - **Military Target Classifier ([`ml/classifier.py`](file:///d:/Micro%20doppler%20radar%20project/microdoppler-radar-app/microdoppler-radar-app/ml/classifier.py)):** An AI classification model (`mil-cnn-v2`) mapping micro-Doppler spectra onto target classes (`Drone`, `Human`, `Vehicle`, `Bird`, `Unknown`) with confidence scores, micro-motion signatures, and military threat level ratings (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW/NEUTRAL`).

---

## 🌟 Key Features

1. **Unified Single-Page Application (SPA)**:
   - Instant zero-reload tab navigation between **Operations Overview** (Welcome Landing Portal), **Live Console**, **Mission Log**, and **System Diagnostics**.
2. **Real-Time Target PPI Radar Scope**:
   - 360° rotating radar sweep beam, range grid rings ($25\text{m}$, $50\text{m}$, $75\text{m}$), cardinal markers (N, S, E, W), and target blips color-coded by threat priority.
3. **Military Threat Priority Engine (`mil-cnn-v2`)**:
   - Categorizes targets into `CRITICAL` (Hostile Drones), `HIGH` (Infiltrating Personnel), `MEDIUM` (Armored Vehicles), and `LOW` (Avian / Neutral) with tactical callsigns (`ALPHA-DRONE-HOSTILE`, `BRAVO-FOOT-INFILTRATOR`).
4. **Header Device Mode Switcher (`💻 Lap`, `📟 Tab`, `📱 Mobile`)**:
   - Embedded right before the `LIVE` status badge in the header to simulate Laptop, Tablet, and Mobile Field HUD viewports dynamically.
5. **Zero-Config Database Fallback**:
   - Automatically falls back to SQLite (`sqlite:///radar.db`) when `DATABASE_URL` is omitted, with dynamic SQLAlchemy `ARRAY` column JSON compilation support.

---

## 🏗️ System Architecture

```mermaid
flowchart TD
    A["📡 Edge Node Simulator (10 Hz)"] -->|Raw Radar Telemetry| B["⚙️ Flask-SocketIO Core Server"]
    B -->|Radial Velocity & 64 Bins| C["🤖 Military ML Classifier (mil-cnn-v2)"]
    C -->|Target Class, Confidence & Threat Level| B
    B -->|WebSocket Stream (10 Hz)| D["💻 Single-Page Dashboard (SPA)"]
    B -->|Throttled Persistence| E["🗄️ Database (PostgreSQL / SQLite)"]

    subgraph Frontend Console HUD
        D --> F["🟩 HTML5 Canvas Waterfall Spectrogram"]
        D --> G["🎯 Live Target PPI Radar Scope (360° Sweep)"]
        D --> H["📈 Chart.js Doppler Trend Line"]
        D --> I["⚡ Military AI Classification Feed"]
        D --> J["🎛️ Header Device Mode Switcher (Lap, Tab, Mobile)"]
    end
```

---

## 🛠️ Stack

| Layer | Technology |
|---|---|
| **Backend Framework** | Python 3.11/3.12, Flask, Flask-SocketIO, gevent / eventlet |
| **Real-Time Transport** | WebSockets (Socket.IO protocol), 10 Hz live streaming |
| **Database ORM** | PostgreSQL / SQLite via SQLAlchemy ORM (zero-config auto-fallback) |
| **Frontend HUD** | HTML5, Vanilla CSS3, Vanilla JavaScript, Chart.js, HTML5 Canvas 2D |
| **Radar Simulation** | Background `threading.Thread` generating 24.125 GHz micro-Doppler spectra |
| **Deployment** | Docker, Gunicorn + eventlet/gevent, Render, Heroku, AWS |

---

## 📁 Directory Structure

```
microdoppler-radar-app/
├── app.py                  # Flask routes, SocketIO events, REST API, wiring
├── config.py                # Database configuration & environment overrides
├── models.py                 # SQLAlchemy models (EdgeNode, RadarSample, Classification)
├── explanation.md            # Comprehensive theoretical micro-Doppler physics & math guide
├── README.md                 # System overview and deployment guide
├── requirements.txt
├── Dockerfile
├── docker-compose.yml        # Docker compose file for local PostgreSQL testing
├── ml/
│   └── classifier.py         # Military target classification & threat evaluation engine
├── edge_node/
│   └── simulator.py           # Physics-based FMCW radar edge sensor simulation thread
├── templates/
│   └── index.html             # Unified SPA HTML template (Overview, Console, History, Diagnostics)
└── static/
    ├── css/style.css          # Tactical dark mode radar styling + responsive device breakpoints
    └── js/script.js           # Single-page tab router + WebSocket client + Waterfall + PPI Scope
```

---

## 🚀 Running Locally

### Option A: Direct Python (Quickest — Zero Config)

1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate      # Linux/macOS: source venv/bin/activate
   pip install -r requirements.txt
   ```
2. Launch the application:
   ```bash
   python app.py
   ```
3. Open **[http://127.0.0.1:5000](http://127.0.0.1:5000)** in your browser. The app runs out-of-the-box with SQLite auto-fallback!

### Option B: Docker Compose (PostgreSQL Production Setup)

```bash
docker compose up --build
```
Visit **[http://localhost:8000](http://localhost:8000)**.

---

## 📱 Device Switcher Usage (`💻 Lap`, `📟 Tab`, `📱 Mobile`)

In the top header bar, located **right before the green `LIVE` connection badge**, click any of the device mode buttons:
- **`💻 Lap` (Laptop / Desktop)**: Displays the full side-by-side console view.
- **`📟 Tab` (Tablet Preview)**: Centers the dashboard in an 840px tablet viewport.
- **`📱 Mobile` (Mobile Field HUD Preview)**: Formats the dashboard into a 414px smartphone layout with touch-optimized controls.

---

## 📡 REST API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/classifications` | GET | Query historical classification logs (`target_type`, `date_from`, `date_to`, `min_confidence`, `page`, `per_page`) |
| `/api/classifications/summary` | GET | Aggregate counts & average confidence breakdown per target type |
| `/api/nodes` | GET | Retrieve edge node sensor status & last heartbeat timestamp |
| `/api/simulator/start` \| `/stop` \| `/status` | POST/GET | Control background radar simulator daemon |
| `/healthz` | GET | Health check endpoint (DB connection status & edge simulator health) |
