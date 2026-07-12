const $ = (id) => document.getElementById(id);

const els = {
  scanStatus: $("scan-status"),
  btnCached: $("btn-scan-cached"),
  btnFresh: $("btn-scan-fresh"),
  metricOpps: $("metric-opps"),
  metricPairs: $("metric-pairs"),
  metricKalshi: $("metric-kalshi"),
  metricKalshiHint: $("metric-kalshi-hint"),
  metricPoly: $("metric-poly"),
  configBody: $("config-body"),
  statusBody: $("status-body"),
  oppBadge: $("opp-count-badge"),
  pairsBadge: $("pairs-count-badge"),
  oppBody: $("opportunities-body"),
  pairsBody: $("pairs-body"),
};

let pollTimer = null;
let expandedOppIndex = null;

function fmtPct(value) {
  if (value == null || Number.isNaN(value)) return "—";
  return `${(value * (value <= 1 ? 100 : 1)).toFixed(1)}%`;
}

function fmtMoney(value) {
  if (value == null) return "—";
  return `$${Number(value).toFixed(4)}`;
}

function fmtDays(value) {
  if (value == null) return "—";
  return `${Number(value).toFixed(1)}d`;
}

function fmtSize(value) {
  if (value == null || Number.isNaN(value)) return "—";
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function setScanUi(running, error) {
  els.btnCached.disabled = running;
  els.btnFresh.disabled = running;
  els.scanStatus.className = "status-pill";
  if (running) {
    els.scanStatus.textContent = "Scanning…";
    els.scanStatus.classList.add("running");
  } else if (error) {
    els.scanStatus.textContent = "Error";
    els.scanStatus.classList.add("error");
  } else {
    els.scanStatus.textContent = "Idle";
    els.scanStatus.classList.add("idle");
  }
}

function renderConfig(config) {
  const venues = config.venues || {};
  const limits = config.limits || {};
  const filters = config.filters || {};
  const liquidity = config.liquidity || {};
  const categories = config.categories || [];

  els.configBody.innerHTML = `
    <div class="config-grid">
      <div class="config-item">
        <label>Venues</label>
        <div class="tag-list">
          ${["kalshi", "polymarket", "forecastex"].map((v) =>
            `<span class="tag ${venues[v] ? "on" : "off"}">${v}</span>`
          ).join("")}
        </div>
      </div>
      <div class="config-item">
        <label>Categories</label>
        <div class="tag-list">
          ${categories.map((c) => `<span class="tag on">${escapeHtml(c)}</span>`).join("")}
        </div>
      </div>
      <div class="config-item">
        <label>API Limits</label>
        <p>Kalshi ${limits.kalshi_max_markets ?? "—"} · Poly events ${limits.polymarket_max_events ?? "—"}</p>
      </div>
      <div class="config-item">
        <label>Horizons</label>
        <p>Scan ${limits.scan_horizon_days ?? "—"}d · Macro ${limits.macro_horizon_days ?? "—"}d · Politics ${limits.politics_horizon_days ?? "—"}d</p>
      </div>
      <div class="config-item">
        <label>Min Profit</label>
        <span>${fmtMoney(filters.min_profit)}</span>
      </div>
      <div class="config-item">
        <label>Min Annualized</label>
        <span>${fmtPct(filters.min_annualized_return)}</span>
      </div>
      <div class="config-item">
        <label>Liquidity</label>
        <p>Min fill ${liquidity.min_fillable_contracts ?? 0} · Min vol 24h ${liquidity.min_volume_24h ?? 0}</p>
      </div>
    </div>
  `;
}

function renderStatus(scan, resultsAvailable, funnel) {
  const lines = [
    `<p class="status-line"><strong>Results file:</strong> ${resultsAvailable ? "Available" : "None yet"}</p>`,
    `<p class="status-line"><strong>Last started:</strong> ${escapeHtml(scan.last_started || "—")}</p>`,
    `<p class="status-line"><strong>Last finished:</strong> ${escapeHtml(scan.last_finished || "—")}</p>`,
    `<p class="status-line"><strong>Mode:</strong> ${scan.use_cached ? "Cached" : scan.last_started ? "Fresh" : "—"}</p>`,
  ];
  if (scan.last_error) {
    lines.push(`<p class="status-line" style="color:var(--red-600)"><strong>Error:</strong> ${escapeHtml(scan.last_error)}</p>`);
  }
  if (funnel && funnel.raw_fetched != null) {
    lines.push(
      `<p class="status-line funnel-line"><strong>Kalshi funnel:</strong> ` +
      `raw ${funnel.raw_fetched} → clean ${funnel.clean_extracted ?? "—"} → ` +
      `category ${funnel.category_passed ?? "—"} ` +
      `(horizon −${funnel.dropped_horizon ?? 0}, book −${funnel.dropped_book_quality ?? 0}, cat −${funnel.dropped_category ?? 0})</p>`
    );
  }
  els.statusBody.innerHTML = lines.join("");
}

function renderMetrics(summary) {
  els.metricOpps.textContent = summary.opportunity_count ?? "0";
  els.metricPairs.textContent = summary.matched_pairs ?? "0";
  const counts = summary.market_counts || {};
  els.metricKalshi.textContent = counts.kalshi ?? "0";
  els.metricPoly.textContent = counts.polymarket ?? "0";
  const clean = counts.kalshi_clean;
  if (els.metricKalshiHint && clean != null) {
    els.metricKalshiHint.textContent = `${clean} clean · ${counts.kalshi ?? 0} in categories`;
  }
}

function renderLegDetail(leg) {
  const size = leg.size_at_price != null ? fmtSize(leg.size_at_price) : (leg.size_note || "—");
  const vol = leg.volume_24h != null ? fmtSize(leg.volume_24h) : "—";
  return `<div class="opp-detail-leg">` +
    `<strong>${escapeHtml(leg.platform)} ${escapeHtml(leg.side)}</strong> @ ${fmtMoney(leg.price)} · ` +
    `size ${size} · fee ${fmtMoney(leg.fee)} · vol 24h ${vol}` +
    (leg.market ? ` · ${escapeHtml(leg.market)}` : "") +
    `</div>`;
}

function renderOpportunityDetail(opp) {
  const legs = opp.liquidity?.legs || opp.buy_plan?.legs || [];
  if (!legs.length) {
    return `<div class="opp-detail-leg muted">No leg detail available.</div>`;
  }
  return `<div class="opp-detail-grid">${legs.map(renderLegDetail).join("")}</div>`;
}

function renderOpportunities(opps) {
  els.oppBadge.textContent = String(opps.length);
  if (!opps.length) {
    els.oppBody.innerHTML = `<tr><td colspan="11" class="empty-row">No opportunities passed filters.</td></tr>`;
    return;
  }

  els.oppBody.innerHTML = opps.map((opp, idx) => {
    const liq = opp.liquidity || {};
    const expanded = expandedOppIndex === idx;
    return `
    <tr class="opp-row ${expanded ? "expanded" : ""}" data-opp-index="${idx}">
      <td class="num">${idx + 1}</td>
      <td class="event-cell">${escapeHtml(opp.event_label || "—")}</td>
      <td>${escapeHtml(opp.platform_a)} × ${escapeHtml(opp.platform_b)}</td>
      <td class="num positive">${fmtMoney(opp.profit)}</td>
      <td class="num">${fmtSize(liq.max_fillable_contracts)}</td>
      <td class="num positive">${fmtMoney(liq.max_profit_usd)}</td>
      <td class="num">${fmtSize(liq.activity?.min_volume_24h)}</td>
      <td class="num">${fmtDays(opp.hold_days)}</td>
      <td class="num positive">${fmtPct(opp.annualized_return ?? opp.annualized_return_pct / 100)}</td>
      <td class="num">${Number(opp.score ?? 0).toFixed(2)}</td>
      <td class="market-cell">${escapeHtml(opp.buy_plan?.summary || "—")}</td>
    </tr>
    ${expanded ? `<tr class="opp-detail-row"><td colspan="11">${renderOpportunityDetail(opp)}</td></tr>` : ""}
  `;
  }).join("");

  els.oppBody.querySelectorAll(".opp-row").forEach((row) => {
    row.addEventListener("click", () => {
      const idx = Number(row.dataset.oppIndex);
      expandedOppIndex = expandedOppIndex === idx ? null : idx;
      renderOpportunities(opps);
    });
  });
}

function renderPairs(pairs, oppQuestions) {
  const watchlist = pairs.filter((pair) => {
    const key = `${pair.market_a}|${pair.market_b}`;
    return !oppQuestions.has(key);
  });

  els.pairsBadge.textContent = String(watchlist.length);
  if (!watchlist.length) {
    els.pairsBody.innerHTML = `<tr><td colspan="5" class="empty-row">No watchlist pairs.</td></tr>`;
    return;
  }

  els.pairsBody.innerHTML = watchlist.slice(0, 100).map((pair) => `
    <tr>
      <td class="event-cell">${escapeHtml(pair.event_label || "—")}</td>
      <td class="num">${Number(pair.confidence ?? 0).toFixed(2)}</td>
      <td>${escapeHtml(pair.match_method || "—")}</td>
      <td class="market-cell">${escapeHtml(pair.market_a || "—")}</td>
      <td class="market-cell">${escapeHtml(pair.market_b || "—")}</td>
    </tr>
  `).join("");
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || response.statusText);
  }
  return response.json();
}

async function refreshStatus() {
  const status = await fetchJson("/api/status");
  setScanUi(status.scan.running, status.scan.last_error);
  renderConfig(status.config);
  renderStatus(status.scan, status.results_available, status.summary?.kalshi_funnel);

  if (status.results_available) {
    try {
      const results = await fetchJson("/api/results");
      renderMetrics({
        ...status.summary,
        market_counts: {
          ...status.summary.market_counts,
          kalshi_clean: results.macro_market_counts?.kalshi_clean,
        },
        kalshi_funnel: results.kalshi_funnel,
      });
      const opps = results.opportunities || [];
      const pairs = results.matched_pair_summaries || [];
      const oppQuestions = new Set(
        opps.map((o) => `${o.market_a?.market_question}|${o.market_b?.market_question}`)
      );
      renderOpportunities(opps);
      renderPairs(pairs, oppQuestions);
    } catch (err) {
      console.warn("Results load failed", err);
    }
  } else {
    renderMetrics(status.summary);
  }

  if (status.scan.running) {
    if (!pollTimer) pollTimer = setInterval(refreshStatus, 3000);
  } else if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
    if (status.scan.last_finished) {
      els.scanStatus.className = "status-pill done";
      els.scanStatus.textContent = "Complete";
    }
  }
}

async function startScan(cached) {
  try {
    setScanUi(true, false);
    await fetchJson("/api/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cached }),
    });
    if (!pollTimer) pollTimer = setInterval(refreshStatus, 3000);
    await refreshStatus();
  } catch (err) {
    setScanUi(false, true);
    els.statusBody.innerHTML = `<p class="status-line" style="color:var(--red-600)">${escapeHtml(err.message)}</p>`;
  }
}

els.btnCached.addEventListener("click", () => startScan(true));
els.btnFresh.addEventListener("click", () => startScan(false));

refreshStatus().catch((err) => {
  els.statusBody.innerHTML = `<p class="status-line" style="color:var(--red-600)">Failed to load: ${escapeHtml(err.message)}</p>`;
});

setInterval(() => {
  if (!pollTimer) refreshStatus().catch(() => {});
}, 30000);
