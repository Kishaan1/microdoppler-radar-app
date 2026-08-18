/**
 * history.js
 * ----------
 * Historical classification querying UI. Talks to the Flask REST API
 * (/api/classifications, /api/classifications/summary) which in turn queries
 * PostgreSQL through SQLAlchemy on the backend.
 */

(function () {
  "use strict";

  const form = document.getElementById("filterForm");
  const resetBtn = document.getElementById("resetFiltersBtn");
  const resultsBody = document.getElementById("resultsBody");
  const resultCount = document.getElementById("resultCount");
  const paginationEl = document.getElementById("pagination");

  let currentPage = 1;
  const PER_PAGE = 20;

  const summaryChart = new Chart(document.getElementById("summaryChart"), {
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

  function buildParams(page) {
    const fd = new FormData(form);
    const params = new URLSearchParams();
    for (const [key, value] of fd.entries()) {
      if (value !== "") params.append(key, value);
    }
    params.append("page", page);
    params.append("per_page", PER_PAGE);
    return params;
  }

  async function runQuery(page = 1) {
    currentPage = page;
    const params = buildParams(page);

    resultsBody.innerHTML = `<tr><td colspan="7" class="table-empty">Querying&hellip;</td></tr>`;

    try {
      const [resultsRes, summaryRes] = await Promise.all([
        fetch(`/api/classifications?${params.toString()}`),
        fetch(`/api/classifications/summary?${buildSummaryParams().toString()}`),
      ]);
      const resultsJson = await resultsRes.json();
      const summaryJson = await summaryRes.json();

      renderTable(resultsJson);
      renderPagination(resultsJson);
      renderSummary(summaryJson);
    } catch (err) {
      resultsBody.innerHTML = `<tr><td colspan="7" class="table-empty">Query failed: ${escapeHtml(err.message)}</td></tr>`;
    }
  }

  function buildSummaryParams() {
    const fd = new FormData(form);
    const params = new URLSearchParams();
    if (fd.get("date_from")) params.append("date_from", fd.get("date_from"));
    if (fd.get("date_to")) params.append("date_to", fd.get("date_to"));
    return params;
  }

  function renderTable(json) {
    const rows = json.results || [];
    resultCount.textContent = `${json.total ?? rows.length} records`;

    if (rows.length === 0) {
      resultsBody.innerHTML = `<tr><td colspan="7" class="table-empty">No classifications match this query.</td></tr>`;
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
    const pages = json.pages || 1;
    const page = json.page || 1;
    if (pages <= 1) {
      paginationEl.innerHTML = "";
      return;
    }

    let html = "";
    html += `<button class="page-btn" data-page="${page - 1}" ${page <= 1 ? "disabled" : ""}>&larr; Prev</button>`;

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

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str == null ? "" : String(str);
    return div.innerHTML;
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    runQuery(1);
  });

  resetBtn.addEventListener("click", () => {
    form.reset();
    runQuery(1);
  });

  // Initial load
  runQuery(1);
})();
