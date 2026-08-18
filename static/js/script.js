/**
 * script.js
 * ---------
 * Unified Single-Page Application (SPA) logic for SIGMA-9 Micro-Doppler Console.
 *
 * Features:
 * 1. Single-Page Navigation Tabs (Live Console, Operations Overview, Mission Log, System Diagnostics).
 * 2. Real-time WebSockets telemetry & DPI-independent HTML5 Canvas Waterfall Spectrogram.
 * 3. Real-time Chart.js Doppler Frequency Trend Line.
 * 4. Streaming AI Target Classification Feed.
 * 5. Database Historical Query & Chart.js Target Distribution Bar Chart.
 * 6. Live System Health Diagnostics & Edge Node Fleet Monitor.
 */

(function () {
  "use strict";

  // ---- Tab Navigation ----------------------------------------------------
  const mainNav = document.getElementById("mainNav");
  const tabPanes = document.querySelectorAll(".tab-pane");

  function switchTab(targetTab) {
    if (!targetTab) return;

    // Update nav button active states
    if (mainNav) {
      mainNav.querySelectorAll(".nav-tab").forEach((btn) => {
        if (btn.dataset.tab === targetTab) {
          btn.classList.add("active");
        } else {
          btn.classList.remove("active");
        }
      });
    }

    // Update tab pane active states
    tabPanes.forEach((pane) => {
      if (pane.id === `tab-${targetTab}`) {
        pane.classList.add("active");
      } else {
        pane.classList.remove("active");
      }
    });

    // Handle tab-specific initializations
    if (targetTab === "console") {
      resizeCanvas();
      resizePPICanvas();
    } else if (targetTab === "history") {
      runQuery(1);
    } else if (targetTab === "diagnostics") {
      loadDiagnostics();
    }

    // Update browser URL hash quietly
    try {
      history.replaceState(null, "", `#${targetTab}`);
    } catch (_) {}
  }

  if (mainNav) {
    mainNav.querySelectorAll(".nav-tab").forEach((btn) => {
      btn.addEventListener("click", () => switchTab(btn.dataset.tab));
    });
  }

  // ---- Device Mode Switcher (Lap, Tab, Mobile) ---------------------------
  const deviceSelector = document.getElementById("deviceModeSelector");
  if (deviceSelector) {
    deviceSelector.querySelectorAll(".device-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const mode = btn.dataset.mode;

        deviceSelector.querySelectorAll(".device-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");

        document.body.classList.remove("mode-lap", "mode-tab", "mode-mobile");
        document.body.classList.add(`mode-${mode}`);

        setTimeout(() => {
          resizeCanvas();
          resizePPICanvas();
        }, 150);
      });
    });
  }

  // Handle in-page buttons with data-target
  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".switch-tab-btn");
    if (btn && btn.dataset.target) {
      switchTab(btn.dataset.target);
    }
  });

  // Check initial URL hash (e.g. #history or #console); default to 'overview' (Start Page)
  const initialHash = window.location.hash.replace("#", "");
  if (["console", "overview", "history", "diagnostics"].includes(initialHash)) {
    switchTab(initialHash);
  } else {
    switchTab("overview");
  }

  // ---- DOM references -----------------------------------------------
  const connDot = document.getElementById("connDot");
  const connLabel = document.getElementById("connLabel");
  const toggleSimBtn = document.getElementById("toggleSimBtn");

  const tDoppler = document.getElementById("tDoppler");
  const tVelocity = document.getElementById("tVelocity");
  const tPower = document.getElementById("tPower");
  const tNode = document.getElementById("tNode");

  const footerNode = document.getElementById("footerNode");
  const footerSamples = document.getElementById("footerSamples");

  const feedEl = document.getElementById("classificationFeed");
  const feedEmpty = document.getElementById("feedEmpty");
  const feedCount = document.getElementById("feedCount");

  const waterfallCanvas = document.getElementById("waterfallCanvas");
  const wfCtx = waterfallCanvas ? waterfallCanvas.getContext("2d") : null;

  // ---- State -----------------------------------------------------------
  let sampleCount = 0;
  let classificationCount = 0;
  let simRunning = true;
  const MAX_TREND_POINTS = 80;
  const trendLabels = [];
  const trendData = [];

  // ---- Waterfall setup ---------------------------------------------------
  function resizeCanvas() {
    if (!waterfallCanvas || !wfCtx) return;
    const rect = waterfallCanvas.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    const dpr = window.devicePixelRatio || 1;
    const targetW = Math.floor(rect.width * dpr);
    const targetH = Math.floor(rect.height * dpr);

    if (waterfallCanvas.width !== targetW || waterfallCanvas.height !== targetH) {
      waterfallCanvas.width = targetW;
      waterfallCanvas.height = targetH;
      wfCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
      wfCtx.fillStyle = "#030607";
      wfCtx.fillRect(0, 0, rect.width, rect.height);
    }
  }

  window.addEventListener("resize", resizeCanvas);

  function magnitudeToColor(mag) {
    const m = Math.max(0, Math.min(1, mag));
    const r = Math.round(20 + m * m * 120);
    const g = Math.round(30 + m * 225);
    const b = Math.round(20 + m * 90);
    return `rgb(${r},${g},${b})`;
  }

  function normalizeBins(bins) {
    if (!bins || bins.length === 0) return [];
    const max = Math.max(...bins, 1e-6);
    return bins.map((b) => b / max);
  }

  function pushWaterfallRow(bins) {
    if (!waterfallCanvas || !wfCtx) return;
    resizeCanvas();
    const rect = waterfallCanvas.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;
    const rowHeight = 3;

    if (width === 0 || height === 0) return;

    // Shift canvas image down by rowHeight (resolution independent)
    wfCtx.drawImage(waterfallCanvas, 0, 0, width, height - rowHeight, 0, rowHeight, width, height - rowHeight);

    const normalized = normalizeBins(bins);
    const n = normalized.length || 1;
    const colWidth = width / n;

    for (let i = 0; i < n; i++) {
      wfCtx.fillStyle = magnitudeToColor(normalized[i]);
      wfCtx.fillRect(i * colWidth, 0, colWidth + 0.5, rowHeight);
    }
  }

  // ---- Trend chart (Chart.js) ---------------------------------------------
  const trendCanvas = document.getElementById("trendChart");
  let trendChart = null;
  if (trendCanvas) {
    trendChart = new Chart(trendCanvas, {
      type: "line",
      data: {
        labels: trendLabels,
        datasets: [{
          label: "Doppler Freq (Hz)",
          data: trendData,
          borderColor: "#39ff9c",
          backgroundColor: "rgba(57,255,156,0.08)",
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.25,
          fill: true,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        scales: {
          x: { display: false },
          y: {
            grid: { color: "rgba(28,46,48,0.6)" },
            ticks: { color: "#4d6663", font: { family: "IBM Plex Mono", size: 10 } },
          },
        },
        plugins: { legend: { display: false } },
      },
    });
  }

  function pushTrendPoint(value) {
    if (!trendChart) return;
    trendLabels.push("");
    trendData.push(value);
    if (trendLabels.length > MAX_TREND_POINTS) {
      trendLabels.shift();
      trendData.shift();
    }
    trendChart.update("none");
  }

  // ---- Classification feed -----------------------------------------------
  function addClassificationCard(payload) {
    if (!feedEl) return;
    if (feedEmpty) feedEmpty.remove();

    const confPct = payload.confidence_pct != null ? payload.confidence_pct : Math.round(payload.confidence * 100);
    const confClass = confPct >= 80 ? "high-conf" : (confPct < 55 ? "low-conf" : "");

    const threatLevel = payload.threat_level || (payload.target_type === "Drone" ? "CRITICAL" : (payload.target_type === "Human" ? "HIGH" : (payload.target_type === "Vehicle" ? "MEDIUM" : "LOW")));
    const threatColor = payload.threat_color || getTargetColor(payload.target_type);
    const threatCode = payload.threat_code || payload.target_type.toUpperCase();

    const tThreatLevel = document.getElementById("tThreatLevel");
    const tThreatCode = document.getElementById("tThreatCode");
    if (tThreatLevel) {
      tThreatLevel.textContent = threatLevel;
      tThreatLevel.style.color = threatColor;
    }
    if (tThreatCode) {
      tThreatCode.textContent = threatCode;
    }

    const card = document.createElement("div");
    card.className = `classification-card ${confClass}`;
    card.innerHTML = `
      <div class="cc-top">
        <span class="cc-target" style="color:${threatColor}">${escapeHtml(payload.target_type)}</span>
        <span class="threat-pill" style="background:${threatColor}22; color:${threatColor}; border:1px solid ${threatColor}66;">${threatLevel}</span>
        <span class="cc-confidence">${confPct}%</span>
      </div>
      <div class="cc-meta">
        <span>${escapeHtml(payload.node_name || "")}</span>
        <span>${formatTime(payload.timestamp)}</span>
      </div>
      <div class="cc-bar"><div class="cc-bar-fill" style="width:${confPct}%; background:${threatColor}"></div></div>
    `;
    feedEl.prepend(card);

    while (feedEl.children.length > 40) {
      feedEl.removeChild(feedEl.lastChild);
    }

    classificationCount += 1;
    if (feedCount) feedCount.textContent = `${classificationCount} events`;
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str == null ? "" : String(str);
    return div.innerHTML;
  }

  function formatTime(ts) {
    let d;
    if (typeof ts === "number") {
      d = new Date(ts * 1000);
    } else {
      d = new Date(ts);
    }
    return d.toLocaleTimeString([], { hour12: false });
  }

  // ---- PPI Target Scope Setup ----------------------------------------------
  const ppiScopeCanvas = document.getElementById("ppiScopeCanvas");
  const ppiCtx = ppiScopeCanvas ? ppiScopeCanvas.getContext("2d") : null;
  const scopeTargetBadge = document.getElementById("scopeTargetBadge");
  let sweepAngle = 0;
  const activeBlips = [];

  function resizePPICanvas() {
    if (!ppiScopeCanvas || !ppiCtx) return;
    const rect = ppiScopeCanvas.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    const dpr = window.devicePixelRatio || 1;
    const targetW = Math.floor(rect.width * dpr);
    const targetH = Math.floor(rect.height * dpr);

    if (ppiScopeCanvas.width !== targetW || ppiScopeCanvas.height !== targetH) {
      ppiScopeCanvas.width = targetW;
      ppiScopeCanvas.height = targetH;
      ppiCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
  }

  window.addEventListener("resize", resizePPICanvas);

  function getTargetColor(targetType) {
    switch (targetType) {
      case "Drone": return "#39ff9c";
      case "Bird": return "#6fb7c9";
      case "Human": return "#ffb020";
      case "Vehicle": return "#c98bff";
      default: return "#8fa8a4";
    }
  }

  function getTargetIcon(targetType) {
    switch (targetType) {
      case "Drone": return "🛸";
      case "Bird": return "🦅";
      case "Human": return "🚶";
      case "Vehicle": return "🚗";
      default: return "❓";
    }
  }

  function addTargetBlip(targetType, confidencePct, velocity = 5, doppler = 100) {
    const angle = ((Math.abs(doppler) * 0.07 + Math.abs(velocity) * 0.13 + (Date.now() % 10000) / 1000) % (2 * Math.PI));
    const distRatio = Math.min(0.85, Math.max(0.2, (Math.abs(velocity) / 25.0)));
    const color = getTargetColor(targetType);
    const icon = getTargetIcon(targetType);

    activeBlips.push({
      targetType: targetType || "Unknown",
      confidencePct: confidencePct || 85,
      angle: angle,
      distRatio: distRatio,
      color: color,
      icon: icon,
      createdAt: Date.now(),
      ttl: 4000,
    });

    while (activeBlips.length > 12) activeBlips.shift();

    if (scopeTargetBadge) {
      scopeTargetBadge.textContent = `${icon} ${targetType || "Unknown"} (${confidencePct || 85}%)`;
    }
  }

  function renderPPIScope() {
    if (ppiScopeCanvas && ppiCtx) {
      resizePPICanvas();

      const rect = ppiScopeCanvas.getBoundingClientRect();
      const w = rect.width;
      const h = rect.height;

      if (w > 0 && h > 0) {
        const cx = w / 2;
        const cy = h / 2;
        const radius = Math.max(10, Math.min(cx, cy) - 14);

        ppiCtx.clearRect(0, 0, w, h);

        // Background circle
        ppiCtx.fillStyle = "#040f0c";
        ppiCtx.beginPath();
        ppiCtx.arc(cx, cy, radius, 0, 2 * Math.PI);
        ppiCtx.fill();

        // Range rings
        ppiCtx.lineWidth = 1;
        ppiCtx.strokeStyle = "rgba(57, 255, 156, 0.25)";
        [0.33, 0.66, 1.0].forEach((rMult) => {
          ppiCtx.beginPath();
          ppiCtx.arc(cx, cy, radius * rMult, 0, 2 * Math.PI);
          ppiCtx.stroke();
        });

        // Crosshairs
        ppiCtx.strokeStyle = "rgba(57, 255, 156, 0.2)";
        ppiCtx.beginPath();
        ppiCtx.moveTo(cx - radius, cy); ppiCtx.lineTo(cx + radius, cy);
        ppiCtx.moveTo(cx, cy - radius); ppiCtx.lineTo(cx, cy + radius);
        ppiCtx.stroke();

        // Cardinal Labels
        ppiCtx.fillStyle = "#8fa8a4";
        ppiCtx.font = "10px IBM Plex Mono";
        ppiCtx.textAlign = "center";
        ppiCtx.textBaseline = "middle";
        ppiCtx.fillText("N", cx, cy - radius + 8);
        ppiCtx.fillText("S", cx, cy + radius - 8);
        ppiCtx.fillText("E", cx + radius - 8, cy);
        ppiCtx.fillText("W", cx - radius + 8, cy);

        // Rotating Sweep Beam
        sweepAngle = (sweepAngle + 0.03) % (2 * Math.PI);
        ppiCtx.save();
        ppiCtx.translate(cx, cy);
        ppiCtx.rotate(sweepAngle);

        const grad = ppiCtx.createConicGradient(0, 0, 0);
        grad.addColorStop(0, "rgba(57, 255, 156, 0.45)");
        grad.addColorStop(0.18, "rgba(57, 255, 156, 0.0)");
        grad.addColorStop(1, "rgba(57, 255, 156, 0.0)");

        ppiCtx.fillStyle = grad;
        ppiCtx.beginPath();
        ppiCtx.arc(0, 0, radius, 0, 2 * Math.PI);
        ppiCtx.fill();

        ppiCtx.strokeStyle = "#39ff9c";
        ppiCtx.lineWidth = 1.5;
        ppiCtx.beginPath();
        ppiCtx.moveTo(0, 0);
        ppiCtx.lineTo(radius, 0);
        ppiCtx.stroke();
        ppiCtx.restore();

        // Draw Active Target Blips
        const now = Date.now();
        for (let i = activeBlips.length - 1; i >= 0; i--) {
          const b = activeBlips[i];
          const age = now - b.createdAt;
          if (age > b.ttl) {
            activeBlips.splice(i, 1);
            continue;
          }
          const alpha = Math.max(0.15, 1.0 - (age / b.ttl));
          const bx = cx + Math.cos(b.angle) * (b.distRatio * radius);
          const by = cy + Math.sin(b.angle) * (b.distRatio * radius);

          // Blip pulse ring
          ppiCtx.save();
          ppiCtx.globalAlpha = alpha;
          ppiCtx.fillStyle = b.color;
          ppiCtx.shadowColor = b.color;
          ppiCtx.shadowBlur = 10;
          ppiCtx.beginPath();
          ppiCtx.arc(bx, by, 5, 0, 2 * Math.PI);
          ppiCtx.fill();

          // Label
          ppiCtx.fillStyle = "#ffffff";
          ppiCtx.font = "10px IBM Plex Mono";
          ppiCtx.textAlign = "left";
          ppiCtx.fillText(`${b.icon} ${b.targetType}`, bx + 8, by + 3);
          ppiCtx.restore();
        }
      }
    }

    requestAnimationFrame(renderPPIScope);
  }

  requestAnimationFrame(renderPPIScope);

  // ---- WebSocket wiring ----------------------------------------------------
  if (typeof io !== "undefined") {
    const socket = io({ transports: ["websocket", "polling"] });

    socket.on("connect", () => {
      if (connDot) connDot.classList.add("connected");
      if (connLabel) connLabel.textContent = "LIVE";
    });

    socket.on("disconnect", () => {
      if (connDot) connDot.classList.remove("connected");
      if (connLabel) connLabel.textContent = "DISCONNECTED";
    });

    socket.on("radar_sample", (data) => {
      sampleCount += 1;
      if (footerSamples) footerSamples.textContent = sampleCount.toLocaleString();

      if (tDoppler) tDoppler.textContent = data.doppler_freq_hz.toFixed(1);
      if (tVelocity) tVelocity.textContent = data.radial_velocity_mps.toFixed(2);
      if (tPower) tPower.textContent = data.signal_power_db.toFixed(1);
      if (tNode) tNode.textContent = data.node_name || "—";
      if (footerNode) footerNode.textContent = data.node_name || "—";

      pushWaterfallRow(data.spectrum_bins);
      pushTrendPoint(data.doppler_freq_hz);
    });

    socket.on("classification", (payload) => {
      addClassificationCard(payload);
      const confPct = payload.confidence_pct != null ? payload.confidence_pct : Math.round(payload.confidence * 100);
      addTargetBlip(payload.target_type, confPct, payload.radial_velocity_mps, payload.doppler_freq_hz);
    });

    if (toggleSimBtn) {
      toggleSimBtn.addEventListener("click", () => {
        if (simRunning) {
          socket.emit("request_simulator_stop");
          toggleSimBtn.textContent = "Resume Feed";
        } else {
          socket.emit("request_simulator_start");
          toggleSimBtn.textContent = "Pause Feed";
        }
        simRunning = !simRunning;
      });
    }
  }

  // ---- Mission Log (History Query) Logic ---------------------------------
  const filterForm = document.getElementById("filterForm");
  const resetFiltersBtn = document.getElementById("resetFiltersBtn");
  const resultsBody = document.getElementById("resultsBody");
  const resultCount = document.getElementById("resultCount");
  const paginationEl = document.getElementById("pagination");

  const summaryCanvas = document.getElementById("summaryChart");
  let summaryChart = null;
  if (summaryCanvas) {
    summaryChart = new Chart(summaryCanvas, {
      type: "bar",
      data: {
        labels: [],
        datasets: [{
          label: "Classifications",
          data: [],
          backgroundColor: ["#39ff9c", "#6fb7c9", "#ffb020", "#c98bff", "#4d6663"],
          borderWidth: 0,
          borderRadius: 3,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: "#8fa8a4", font: { family: "IBM Plex Mono", size: 11 } }, grid: { display: false } },
          y: {
            beginAtZero: true,
            ticks: { color: "#4d6663", font: { family: "IBM Plex Mono", size: 10 } },
            grid: { color: "rgba(28,46,48,0.6)" },
          },
        },
      },
    });
  }

  function buildParams(page) {
    if (!filterForm) return new URLSearchParams();
    const fd = new FormData(filterForm);
    const params = new URLSearchParams();
    for (const [key, value] of fd.entries()) {
      if (value !== "") params.append(key, value);
    }
    params.append("page", page);
    params.append("per_page", 20);
    return params;
  }

  async function runQuery(page = 1) {
    if (!resultsBody) return;
    resultsBody.innerHTML = `<tr><td colspan="7" class="table-empty">Querying database&hellip;</td></tr>`;

    try {
      const params = buildParams(page);
      const summaryParams = new URLSearchParams();
      if (filterForm) {
        const fd = new FormData(filterForm);
        if (fd.get("date_from")) summaryParams.append("date_from", fd.get("date_from"));
        if (fd.get("date_to")) summaryParams.append("date_to", fd.get("date_to"));
      }

      const [resultsRes, summaryRes] = await Promise.all([
        fetch(`/api/classifications?${params.toString()}`),
        fetch(`/api/classifications/summary?${summaryParams.toString()}`),
      ]);
      const resultsJson = await resultsRes.json();
      const summaryJson = await summaryRes.json();

      renderTable(resultsJson);
      renderPagination(resultsJson);
      renderSummary(summaryJson);
    } catch (err) {
      resultsBody.innerHTML = `<tr><td colspan="7" class="table-empty">Query error: ${escapeHtml(err.message)}</td></tr>`;
    }
  }

  function renderTable(json) {
    if (!resultsBody) return;
    const rows = json.results || [];
    if (resultCount) resultCount.textContent = `${json.total ?? rows.length} records`;

    if (rows.length === 0) {
      resultsBody.innerHTML = `<tr><td colspan="7" class="table-empty">No classifications match this query criteria.</td></tr>`;
      return;
    }

    resultsBody.innerHTML = rows.map((r) => `
      <tr>
        <td>${escapeHtml(formatTimestamp(r.timestamp))}</td>
        <td>${escapeHtml(r.node_name || "—")}</td>
        <td><span class="target-pill target-${escapeHtml(r.target_type)}">${escapeHtml(r.target_type)}</span></td>
        <td>${r.confidence_pct}%</td>
        <td>${r.doppler_freq_hz ?? "—"}</td>
        <td>${r.radial_velocity_mps ?? "—"}</td>
        <td>${escapeHtml(r.model_version)}</td>
      </tr>
    `).join("");
  }

  function renderPagination(json) {
    if (!paginationEl) return;
    const pages = json.pages || 1;
    const page = json.page || 1;
    if (pages <= 1) {
      paginationEl.innerHTML = "";
      return;
    }

    let html = `<button class="page-btn" data-page="${page - 1}" ${page <= 1 ? "disabled" : ""}>&larr; Prev</button>`;
    const start = Math.max(1, page - 2);
    const end = Math.min(pages, page + 2);
    for (let p = start; p <= end; p++) {
      html += `<button class="page-btn ${p === page ? "active" : ""}" data-page="${p}">${p}</button>`;
    }
    html += `<button class="page-btn" data-page="${page + 1}" ${page >= pages ? "disabled" : ""}>Next &rarr;</button>`;
    paginationEl.innerHTML = html;

    paginationEl.querySelectorAll(".page-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const p = parseInt(btn.dataset.page, 10);
        if (!Number.isNaN(p) && p >= 1 && p <= pages) runQuery(p);
      });
    });
  }

  function renderSummary(rows) {
    if (!summaryChart) return;
    const order = ["Drone", "Bird", "Human", "Vehicle", "Unknown"];
    const byType = Object.fromEntries((rows || []).map((r) => [r.target_type, r.count]));
    summaryChart.data.labels = order;
    summaryChart.data.datasets[0].data = order.map((t) => byType[t] || 0);
    summaryChart.update();
  }

  function formatTimestamp(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toISOString().replace("T", " ").slice(0, 19);
  }

  if (filterForm) {
    filterForm.addEventListener("submit", (e) => {
      e.preventDefault();
      runQuery(1);
    });
  }

  if (resetFiltersBtn) {
    resetFiltersBtn.addEventListener("click", () => {
      filterForm.reset();
      runQuery(1);
    });
  }

  // ---- System Diagnostics Logic ------------------------------------------
  const diagNodesBody = document.getElementById("diagNodesBody");
  const refreshDiagBtn = document.getElementById("refreshDiagBtn");

  async function loadDiagnostics() {
    try {
      const [healthRes, nodesRes] = await Promise.all([
        fetch("/healthz"),
        fetch("/api/nodes"),
      ]);

      const health = await healthRes.json();
      const nodes = await nodesRes.json();

      const diagAppStatus = document.getElementById("diagAppStatus");
      const diagDbStatus = document.getElementById("diagDbStatus");
      const diagSimStatus = document.getElementById("diagSimStatus");

      if (diagAppStatus) diagAppStatus.textContent = (health.status || "OK").toUpperCase();
      if (diagDbStatus) diagDbStatus.textContent = (health.database || "OK").toUpperCase();
      if (diagSimStatus) diagSimStatus.textContent = health.simulator_running ? "RUNNING" : "STOPPED";

      if (diagNodesBody) {
        if (!nodes || nodes.length === 0) {
          diagNodesBody.innerHTML = `<tr><td colspan="6" class="table-empty">No edge nodes registered.</td></tr>`;
        } else {
          diagNodesBody.innerHTML = nodes.map((n) => `
            <tr>
              <td><code>${escapeHtml(n.id)}</code></td>
              <td><strong>${escapeHtml(n.name)}</strong></td>
              <td>${escapeHtml(n.location || "Simulated Sector")}</td>
              <td><span class="tag">${n.is_simulated ? "Simulated IoT Node" : "Physical Radar HW"}</span></td>
              <td><span class="status-pill status-${escapeHtml(n.status)}">${escapeHtml(n.status.toUpperCase())}</span></td>
              <td>${escapeHtml(formatTimestamp(n.last_seen_at))}</td>
            </tr>
          `).join("");
        }
      }
    } catch (err) {
      if (diagNodesBody) {
        diagNodesBody.innerHTML = `<tr><td colspan="6" class="table-empty">Failed to load diagnostics: ${escapeHtml(err.message)}</td></tr>`;
      }
    }
  }

  if (refreshDiagBtn) {
    refreshDiagBtn.addEventListener("click", loadDiagnostics);
  }
})();
