const cfg = window.ARB_CONFIG || {};
const $ = (id) => document.getElementById(id);

const els = {
  scanStatus: $("scan-status"),
  btnRefresh: $("btn-refresh"),
  metricOpps: $("metric-opps"),
  metricPairs: $("metric-pairs"),
  metricKalshi: $("metric-kalshi"),
  metricKalshiHint: $("metric-kalshi-hint"),
  metricPoly: $("metric-poly"),
  configBody: $("config-body"),
  statusBody: $("status-body"),
  historyBody: $("history-body"),
  historyBadge: $("history-count-badge"),
  oppBadge: $("opp-count-badge"),
  pairsBadge: $("pairs-count-badge"),
  oppBody: $("opportunities-body"),
  pairsBody: $("pairs-body"),
};

function dataUrl(filename) {
  const user = cfg.githubUser;
  const repo = cfg.githubRepo;
  const branch = cfg.dataBranch || "scan-data";
  const bust = Date.now();
  return `https://raw.githubusercontent.com/${user}/${repo}/${branch}/${filename}?t=${bust}`;
}

let expandedOppIndex = null;

function fmtSize(value) {
  if (value == null || Number.isNaN(value)) return "—";
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

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

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fmtTime(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toISOString().replace("T", " ").slice(0, 19);
  } catch {
    return iso;
  }
}

function todayUtcDate() {
  return new Date().toISOString().slice(0, 10);
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText} — ${url}`);
  }
  return response.json();
}

function renderConfig(config) {
  if (!config) {
    els.configBody.innerHTML = `<p class="muted">Config not available yet.</p>`;
    return;
  }
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
        <p>Kalshi ${limits.kalshi_max_markets ?? "—"} · Poly ${limits.polymarket_max_events ?? "—"}</p>
      </div>
      <div class="config-item">
        <label>Horizons</label>
        <p>Scan ${limits.scan_horizon_days ?? "—"}d · Macro ${limits.macro_horizon_days ?? "—"}d</p>
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

function renderStatus(meta) {
  if (!meta) {
    els.statusBody.innerHTML = `<p class="muted">No scan metadata yet. Trigger the GitHub Action manually.</p>`;
    return;
  }
  const lines = [
    `<p class="status-line"><strong>Last scan started:</strong> ${escapeHtml(fmtTime(meta.last_scan_started))}</p>`,
    `<p class="status-line"><strong>Last scan finished:</strong> ${escapeHtml(fmtTime(meta.last_scan_finished))}</p>`,
    `<p class="status-line"><strong>Mode:</strong> ${escapeHtml(meta.scan_mode || "—")}</p>`,
    `<p class="status-line"><strong>Scans logged:</strong> ${meta.scans_in_history ?? "—"}</p>`,
  ];
  if (meta.last_error) {
    lines.push(`<p class="status-line" style="color:var(--red-600)"><strong>Error:</strong> ${escapeHtml(meta.last_error)}</p>`);
  }
  if (meta?.kalshi_funnel?.raw_fetched != null) {
    const funnel = meta.kalshi_funnel;
    lines.push(
      `<p class="status-line funnel-line"><strong>Kalshi funnel:</strong> ` +
      `raw ${funnel.raw_fetched} → clean ${funnel.clean_extracted ?? "—"} → ` +
      `category ${funnel.category_passed ?? "—"}</p>`
    );
  }
  els.statusBody.innerHTML = lines.join("");
}

function renderMetrics(results) {
  els.metricOpps.textContent = results?.opportunity_count ?? "0";
  els.metricPairs.textContent = results?.matched_pairs ?? "0";
  const counts = results?.macro_market_counts || {};
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
  const list = opps || [];
  els.oppBadge.textContent = String(list.length);
  if (!list.length) {
    els.oppBody.innerHTML = `<tr><td colspan="11" class="empty-row">No opportunities passed filters.</td></tr>`;
    return;
  }
  els.oppBody.innerHTML = list.map((opp, idx) => {
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
      renderOpportunities(list);
    });
  });
}

function renderPairs(pairs, opps) {
  const oppQuestions = new Set(
    (opps || []).map((o) => `${o.market_a?.market_question}|${o.market_b?.market_question}`)
  );
  const watchlist = (pairs || []).filter((pair) => {
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

function renderHistory(history) {
  const today = todayUtcDate();
  const todayRows = (history || []).filter((row) => String(row.timestamp || "").startsWith(today));
  const rows = todayRows.length ? todayRows : (history || []).slice(-20).reverse();

  els.historyBadge.textContent = String(todayRows.length || rows.length);
  if (!rows.length) {
    els.historyBody.innerHTML = `<tr><td colspan="6" class="empty-row">No scans logged yet today.</td></tr>`;
    return;
  }

  els.historyBody.innerHTML = rows.slice().reverse().map((row) => `
    <tr>
      <td>${escapeHtml(fmtTime(row.timestamp))}</td>
      <td class="num">${row.opportunity_count ?? 0}</td>
      <td class="num">${row.matched_pairs ?? 0}</td>
      <td class="event-cell">${escapeHtml(row.top_event || "—")}</td>
      <td class="num ${row.top_profit ? "positive" : ""}">${row.top_profit != null ? fmtMoney(row.top_profit) : "—"}</td>
      <td>${row.error ? `<span style="color:var(--red-600)">Error</span>` : "OK"}</td>
    </tr>
  `).join("");
}

function setStatusPill(state, text) {
  els.scanStatus.className = `status-pill ${state}`;
  els.scanStatus.textContent = text;
}

async function refreshAll() {
  setStatusPill("running", "Loading…");
  els.btnRefresh.disabled = true;

  try {
    const [results, meta, config, history] = await Promise.all([
      fetchJson(dataUrl("macro_arb_latest.json")).catch(() => null),
      fetchJson(dataUrl("scan_meta.json")).catch(() => null),
      fetchJson(dataUrl("config_snapshot.json")).catch(() => null),
      fetchJson(dataUrl("scan_history.json")).catch(() => []),
    ]);

    if (!results && !meta) {
      throw new Error(
        "No scan data on scan-data branch yet. Push to GitHub and run the Scheduled Arb Scan workflow."
      );
    }

    renderConfig(config);
    const metaWithFunnel = {
      ...(meta || {}),
      kalshi_funnel: results?.kalshi_funnel || meta?.kalshi_funnel,
    };
    renderStatus(metaWithFunnel);
    renderMetrics(results);
    renderHistory(history);
    renderOpportunities(results?.opportunities);
    renderPairs(results?.matched_pair_summaries, results?.opportunities);

    if (meta?.last_error) {
      setStatusPill("error", "Last scan error");
    } else {
      setStatusPill("done", "Live");
    }
  } catch (err) {
    setStatusPill("error", "Load failed");
    els.statusBody.innerHTML = `<p class="status-line" style="color:var(--red-600)">${escapeHtml(err.message)}</p>`;
  } finally {
    els.btnRefresh.disabled = false;
  }
}

els.btnRefresh.addEventListener("click", () => refreshAll());
refreshAll();
setInterval(refreshAll, cfg.pollIntervalMs || 60000);
