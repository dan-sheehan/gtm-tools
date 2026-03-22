/* Pipeline Dashboard - Frontend */
(function () {
  const PREFIX = window.APP_PREFIX || "";

  function apiBase() {
    return PREFIX;
  }

  const STAGE_LABELS = {
    prospecting: "Prospecting",
    discovery: "Discovery",
    proposal: "Proposal",
    negotiation: "Negotiation",
    closed_won: "Closed Won",
    closed_lost: "Closed Lost",
  };

  const STAGE_COLORS = {
    prospecting: "var(--muted)",
    discovery: "var(--accent)",
    proposal: "var(--yellow)",
    negotiation: "var(--orange)",
    closed_won: "var(--green)",
    closed_lost: "var(--red)",
  };

  // -----------------------------------------------------------------------
  // Elements
  // -----------------------------------------------------------------------

  const metricTotal = document.getElementById("metric-total");
  const metricWeighted = document.getElementById("metric-weighted");
  const metricAvg = document.getElementById("metric-avg");
  const metricWinrate = document.getElementById("metric-winrate");
  const funnelArea = document.getElementById("funnel-area");
  const dealsArea = document.getElementById("deals-table-area");
  const dealsEmpty = document.getElementById("deals-empty");
  const stageFilter = document.getElementById("stage-filter");
  const seedBtn = document.getElementById("seed-btn");
  const addDealBtn = document.getElementById("add-deal-btn");
  const modalOverlay = document.getElementById("modal-overlay");
  const modalCancel = document.getElementById("modal-cancel");
  const dealForm = document.getElementById("deal-form");

  // -----------------------------------------------------------------------
  // Load metrics
  // -----------------------------------------------------------------------

  function loadMetrics() {
    fetch(apiBase() + "/api/metrics")
      .then(r => r.json())
      .then(data => {
        metricTotal.textContent = formatCurrency(data.total_pipeline);
        metricWeighted.textContent = formatCurrency(data.weighted_pipeline);
        metricAvg.textContent = formatCurrency(data.avg_deal_size);
        metricWinrate.textContent = data.win_rate + "%";
        renderFunnel(data.stage_summary);
      })
      .catch(() => {});
  }

  // -----------------------------------------------------------------------
  // Render funnel
  // -----------------------------------------------------------------------

  function renderFunnel(stages) {
    if (!stages || stages.length === 0) {
      funnelArea.innerHTML = '<div class="empty-state">No data</div>';
      return;
    }

    const openStages = stages.filter(s => s.stage !== "closed_won" && s.stage !== "closed_lost");
    const maxValue = Math.max(...openStages.map(s => s.value), 1);

    funnelArea.innerHTML = openStages.map(s => {
      const pct = Math.max(5, (s.value / maxValue) * 100);
      const color = STAGE_COLORS[s.stage] || "var(--muted)";
      return `<div class="funnel-row">
        <div class="funnel-label">${esc(STAGE_LABELS[s.stage] || s.stage)}</div>
        <div class="funnel-bar-container">
          <div class="funnel-bar" style="width:${pct}%;background:${color}"></div>
        </div>
        <div class="funnel-stats">
          <span class="funnel-count">${s.count} deals</span>
          <span class="funnel-value">${formatCurrency(s.value)}</span>
        </div>
      </div>`;
    }).join("");
  }

  // -----------------------------------------------------------------------
  // Load deals
  // -----------------------------------------------------------------------

  function loadDeals() {
    const stage = stageFilter.value;
    const url = stage
      ? apiBase() + "/api/deals?stage=" + stage
      : apiBase() + "/api/deals";

    fetch(url)
      .then(r => r.json())
      .then(data => {
        if (data.deals && data.deals.length > 0) {
          dealsEmpty.style.display = "none";
          dealsArea.innerHTML = `<table class="deals-table">
            <thead>
              <tr>
                <th>Company</th>
                <th>Contact</th>
                <th>Value</th>
                <th>Stage</th>
                <th>Days</th>
                <th>Close Date</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              ${data.deals.map(d => {
                const color = STAGE_COLORS[d.stage] || "var(--muted)";
                return `<tr>
                  <td class="deal-company">${esc(d.company)}</td>
                  <td>${esc(d.contact)}</td>
                  <td>${formatCurrency(d.value)}</td>
                  <td><span class="stage-badge" style="background:${color}20;color:${color}">${esc(STAGE_LABELS[d.stage] || d.stage)}</span></td>
                  <td>${d.days_in_stage}</td>
                  <td>${d.close_date || "—"}</td>
                  <td><button class="delete-deal-btn" data-id="${d.id}" title="Delete">×</button></td>
                </tr>`;
              }).join("")}
            </tbody>
          </table>`;

          dealsArea.querySelectorAll(".delete-deal-btn").forEach(btn => {
            btn.addEventListener("click", function () {
              const id = parseInt(this.dataset.id);
              if (!confirm("Delete this deal?")) return;
              fetch(apiBase() + "/api/deals/" + id, { method: "DELETE" })
                .then(() => { loadDeals(); loadMetrics(); });
            });
          });
        } else {
          dealsEmpty.style.display = "block";
          dealsArea.innerHTML = "";
        }
      })
      .catch(() => {});
  }

  // -----------------------------------------------------------------------
  // Init
  // -----------------------------------------------------------------------

  loadMetrics();
  loadDeals();

  stageFilter.addEventListener("change", loadDeals);

  // Seed button
  seedBtn.addEventListener("click", function () {
    seedBtn.disabled = true;
    seedBtn.textContent = "Loading...";
    fetch(apiBase() + "/api/seed", { method: "POST" })
      .then(r => r.json())
      .then(() => {
        seedBtn.textContent = "Load Sample Data";
        seedBtn.disabled = false;
        loadDeals();
        loadMetrics();
      })
      .catch(() => {
        seedBtn.textContent = "Load Sample Data";
        seedBtn.disabled = false;
      });
  });

  // Modal
  addDealBtn.addEventListener("click", () => { modalOverlay.style.display = "flex"; });
  modalCancel.addEventListener("click", () => { modalOverlay.style.display = "none"; });
  modalOverlay.addEventListener("click", function (e) {
    if (e.target === modalOverlay) modalOverlay.style.display = "none";
  });

  dealForm.addEventListener("submit", function (e) {
    e.preventDefault();
    const data = {
      company: document.getElementById("deal-company").value.trim(),
      contact: document.getElementById("deal-contact").value.trim(),
      value: parseFloat(document.getElementById("deal-value").value) || 0,
      stage: document.getElementById("deal-stage").value,
      close_date: document.getElementById("deal-close").value,
    };

    if (!data.company) return;

    fetch(apiBase() + "/api/deals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    })
      .then(r => r.json())
      .then(() => {
        modalOverlay.style.display = "none";
        dealForm.reset();
        loadDeals();
        loadMetrics();
      });
  });

  // -----------------------------------------------------------------------
  // Utilities
  // -----------------------------------------------------------------------

  function formatCurrency(val) {
    if (val >= 1000000) return "$" + (val / 1000000).toFixed(1) + "M";
    if (val >= 1000) return "$" + (val / 1000).toFixed(0) + "K";
    return "$" + Math.round(val);
  }

  function esc(str) {
    if (!str) return "";
    const d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
})();
