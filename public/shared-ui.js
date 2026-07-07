/** Flowthrough UI — render helpers (production) */

const ALGO_OPTIONS = [
  { key: "proportional", label: "Proportional" },
  { key: "fixed_priority", label: "Fixed Priority" },
  { key: "largest_shortage", label: "Largest Shortage" },
  { key: "weighted_score", label: "Weighted Score" },
];

const facilityView = { showAll: false };

function getAsnData() {
  return window.APP_STATE?.asnData || null;
}

function getAsnLines() {
  return getAsnData()?.lines || [];
}

function needIsActive(n) {
  return n.shortage > 0 && n.max > 0;
}

function needRowClass(n) {
  return needIsActive(n) ? "" : " row-excluded";
}

function visibleNeeds(line) {
  if (facilityView.showAll) return line.needs;
  return line.needs.filter(needIsActive);
}

function hasHiddenFacilities(line) {
  return line.needs.some((n) => !needIsActive(n));
}

function renderFacilityNeedHeader(line) {
  if (!hasHiddenFacilities(line)) {
    return `<h6 class="form-label mt-2 mb-0">Facility need</h6>`;
  }
  const checked = facilityView.showAll ? " checked" : "";
  return `
    <div class="section-header mt-2">
      <h6 class="form-label mb-0">Facility need</h6>
      <label class="facility-toggle" for="show-all-${line.lineNum}">
        <input type="checkbox" class="form-check-input show-all-facilities-cb" id="show-all-${line.lineNum}"${checked} />
        Show all facilities
      </label>
    </div>`;
}

function bindFacilityToggle(container, onToggle) {
  if (!container || container.dataset.facilityToggleBound) return;
  container.dataset.facilityToggleBound = "1";
  container.addEventListener("change", (e) => {
    if (!e.target.matches(".show-all-facilities-cb")) return;
    facilityView.showAll = e.target.checked;
    onToggle();
  });
}

function algoLabel(key, defaultKey) {
  const opt = ALGO_OPTIONS.find((o) => o.key === key);
  const base = opt ? opt.label : key;
  return key === defaultKey ? `${base} (Default)` : base;
}

function renderAlgoOptions(line, selectedKey) {
  return ALGO_OPTIONS.map((o) => {
    const sel = o.key === selectedKey ? " selected" : "";
    return `<option value="${o.key}"${sel}>${algoLabel(o.key, line.defaultAlgo)}</option>`;
  }).join("");
}

function policyColClass(key) {
  const map = {
    proportional: "col-prop",
    fixed_priority: "col-fixed",
    largest_shortage: "col-largest",
    weighted_score: "col-weighted",
  };
  return map[key] || "";
}

function facilityLabel(need) {
  return need?.facilityLabel || need?.facility || "";
}

function truncateWithTooltip(text, maxLen = 48) {
  if (!text) return "";
  const t = String(text);
  if (t.length <= maxLen) return escapeHtml(t);
  const full = escapeHtml(t);
  return `<span class="truncate-text" title="${full}">${escapeHtml(t.slice(0, maxLen - 1))}…</span>`;
}

function renderItemTitle(line, maxDescLen = 56) {
  const idPart = `Part ${escapeHtml(line.itemId)}`;
  const desc = (line.itemDescription || "").trim();
  if (!desc) return idPart;
  return `${idPart} <span class="item-description">${truncateWithTooltip(desc, maxDescLen)}</span>`;
}

function renderNeedTable(line) {
  const rows = visibleNeeds(line)
    .map(
      (n) => `<tr class="${needRowClass(n)}">
        <td>${escapeHtml(facilityLabel(n))}</td>
        <td>${n.position}</td>
        <td>${n.shortage}</td>
        <td>${n.max}</td>
        <td class="col-inventory-meta">${n.available ?? "—"}</td>
        <td class="col-inventory-meta">${n.inbound ?? "—"}</td>
        <td class="col-inventory-meta">${n.outbound ?? "—"}</td>
      </tr>`
    )
    .join("");
  return `<div class="table-wrap"><table class="ft-table need-table">
    <thead><tr>
      <th>Facility</th><th>Position</th><th>Shortage</th><th>Max</th>
      <th class="col-inventory-meta">Available</th>
      <th class="col-inventory-meta">Inbound</th>
      <th class="col-inventory-meta">Outbound</th>
    </tr></thead>
    <tbody>${rows}</tbody>
  </table></div>`;
}

function renderComparisonTable(line, selectedKey) {
  const facilities = visibleNeeds(line).map((n) => n.facility);
  const policyHeaders = ALGO_OPTIONS.map((o) => {
    const mark = o.key === line.defaultAlgo ? "*" : "";
    return `<th class="${policyColClass(o.key)} algo-pick-cell algo-expl-cell${o.key === selectedKey ? " col-selected-h" : ""}" data-algo="${o.key}" data-line="${line.lineNum}" role="button" tabindex="0">${o.label}${mark}</th>`;
  }).join("");

  const bodyRows = facilities
    .map((fac) => {
      const need = line.needs.find((n) => n.facility === fac);
      const ex = need ? needRowClass(need) : "";
      const cells = ALGO_OPTIONS.map((o) => {
        const val = line.policies[o.key]?.[fac] ?? "0";
        const sel = o.key === selectedKey ? " cell-selected" : "";
        return `<td class="${policyColClass(o.key)} algo-pick-cell algo-expl-cell${sel}" data-algo="${o.key}" data-line="${line.lineNum}" data-facility="${fac}" role="button" tabindex="0">${val}</td>`;
      }).join("");
      const shortage = need?.shortage ?? 0;
      const selectedUnits = line.units[selectedKey]?.[fac] ?? 0;
      const pct = shortage > 0 ? Math.min(100, Math.round((selectedUnits / shortage) * 100)) : 0;
      const bar =
        selectedUnits > 0 && shortage > 0
          ? `<div class="alloc-bar"><div class="alloc-bar-fill" style="width:${pct}%"></div></div>
             <div class="alloc-bar-label">${selectedUnits} of ${shortage} shortage</div>`
          : `<div class="alloc-bar-label">—</div>`;
      return `<tr class="${ex}">
        <td>${escapeHtml(facilityLabel(need))}</td>
        <td>${shortage}</td>
        <td>${need?.max ?? 0}</td>
        ${cells}
        <td class="alloc-bar-cell">${bar}</td>
      </tr>`;
    })
    .join("");

  const resCells = ALGO_OPTIONS.map((o) => {
    const r = line.residual[o.key] ?? 0;
    const sel = o.key === selectedKey ? " cell-selected" : "";
    return `<td class="${policyColClass(o.key)} algo-pick-cell${sel}" data-algo="${o.key}" role="button" tabindex="0" title="Apply ${o.label}">${r}</td>`;
  }).join("");

  return `<div class="table-wrap"><table class="ft-table comparison-table">
    <thead><tr>
      <th>Facility</th><th>Shortage</th><th>Max</th>
      ${policyHeaders}
      <th>Selected fill</th>
    </tr></thead>
    <tbody>${bodyRows}
      <tr><td><strong>Residual</strong></td><td></td><td></td>${resCells}<td></td></tr>
    </tbody>
  </table></div>`;
}

function renderLineBadges(line) {
  const parts = [`<span class="text-muted">ASN Qty ${line.qty} ${line.uom}</span>`];
  if (line.packQty) {
    parts.push(`<span class="badge-pill badge-pack"><i class="fa-solid fa-box"></i> Pack ${line.packQty}</span>`);
  }
  if (line.palletQty) {
    parts.push(`<span class="badge-pill badge-pallet"><i class="fa-solid fa-pallet"></i> Pallet ${line.palletQty}</span>`);
  }
  return parts.join(" ");
}

function renderLinePanel(line, selectedKey, idPrefix) {
  const selId = `${idPrefix}-algo-${line.lineNum}`;
  return `
    <div class="card-panel line-panel" data-line="${line.lineNum}">
      <div class="line-header-row">
        <div class="line-header-main">
          <h2>Line ${line.lineNum} — ${renderItemTitle(line)}</h2>
          <div class="line-badges">${renderLineBadges(line)}</div>
        </div>
        <div class="line-algo-picker">
          <label class="form-label" for="${selId}">Apply Algorithm for This Line</label>
          <select class="form-select algo-select" id="${selId}" data-line="${line.lineNum}">${renderAlgoOptions(line, selectedKey)}</select>
        </div>
      </div>
      ${renderFacilityNeedHeader(line)}
      ${renderNeedTable(line)}
      <h6 class="form-label mt-3 mb-2">Algorithm comparison
        <span class="text-muted fw-normal">(click a column to apply · hover for why)</span>
      </h6>
      ${renderComparisonTable(line, selectedKey)}
    </div>`;
}

function bindLineSelectors(container, selections, onChange) {
  container.querySelectorAll(".algo-select").forEach((sel) => {
    sel.addEventListener("change", () => {
      const lineNum = parseInt(sel.dataset.line, 10);
      if (!lineNum) return;
      selections[lineNum] = sel.value;
      onChange();
    });
  });
}

function bindAlgoColumnPick(container, selections, onChange) {
  if (!container || container.dataset.algoPickBound) return;
  container.dataset.algoPickBound = "1";
  const applyAlgo = (linePanel, algoKey) => {
    const lineNum = parseInt(linePanel?.dataset.line, 10);
    if (!lineNum || !algoKey || selections[lineNum] === algoKey) return;
    selections[lineNum] = algoKey;
    onChange();
  };
  container.addEventListener("click", (e) => {
    const cell = e.target.closest(".algo-pick-cell");
    if (!cell) return;
    applyAlgo(cell.closest(".line-panel"), cell.dataset.algo);
  });
  container.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const cell = e.target.closest(".algo-pick-cell");
    if (!cell) return;
    e.preventDefault();
    applyAlgo(cell.closest(".line-panel"), cell.dataset.algo);
  });
}

function countFacilityOrders(lines, selections) {
  const facilities = new Set();
  lines.forEach((line) => {
    const algo = selections[line.lineNum] || selections[String(line.lineNum)] || line.defaultAlgo;
    const units = line.units[algo] || {};
    Object.entries(units).forEach(([fac, qty]) => {
      if (Number(qty) > 0) facilities.add(fac);
    });
  });
  return facilities.size;
}

function defaultSelections(lines) {
  const s = {};
  lines.forEach((l) => {
    s[l.lineNum] = l.defaultAlgo;
  });
  return s;
}

function pluralWord(n, singular, plural = `${singular}s`) {
  return n === 1 ? singular : plural;
}

function updateCreateButtonLabel(orderCount) {
  const btn = document.getElementById("createBtn");
  if (!btn) return;
  const label = orderCount === 1 ? "Create Order" : "Create Orders";
  btn.innerHTML = `<i class="fa-solid fa-file-circle-plus"></i> ${label}`;
}

function updateConfirmModalCopy(orderCount, lineCount) {
  const bodyEl = document.getElementById("confirmModalBody");
  const confirmBtn = document.getElementById("confirmCreateBtn");
  if (bodyEl) {
    const orderLabel = pluralWord(orderCount, "replenishment order");
    const lineLabel = pluralWord(lineCount, "ASN line");
    const linePhrase =
      lineCount === 1
        ? `for ${lineCount} ${lineLabel}`
        : `across all ${lineCount} ${lineLabel}`;
    bodyEl.innerHTML = `This process will create <strong>${orderCount}</strong> ${orderLabel} ${linePhrase}.`;
  }
  if (confirmBtn) {
    confirmBtn.textContent = orderCount === 1 ? "Yes, create order" : "Yes, create orders";
  }
}

function updateFooterSummary(selections, orderCount = null) {
  const el = document.getElementById("footerSummary");
  if (!el) return;
  const lines = getAsnLines();
  const count = orderCount !== null ? orderCount : countFacilityOrders(lines, selections);
  const lineLabel = pluralWord(lines.length, "line");
  const orderLabel = pluralWord(count, "order");
  el.textContent = `${lines.length} ${lineLabel} · ${count} ${orderLabel} on Create (based on selected algorithms)`;
  updateCreateButtonLabel(count);
}

function formatAsnStatus(code) {
  const labels = {
    0: "Un-Shipped",
    1000: "In Transit",
    2000: "Unloaded",
    3000: "In Receiving",
    8000: "Verified",
    9000: "Cancelled",
  };
  return labels[Number(code)] ?? String(code ?? "—");
}

function formatEstimatedReceiptDate(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function renderAsnMeta(asn) {
  if (!asn) return "";
  return `
    <div class="asn-meta-fields">
      <div class="asn-meta-item">
        <span class="form-label">Status</span>
        <span class="asn-meta-value">${formatAsnStatus(asn.asnStatus)}</span>
      </div>
      <div class="asn-meta-item">
        <span class="form-label">Estimated Receipt Date</span>
        <span class="asn-meta-value">${formatEstimatedReceiptDate(asn.estimatedReceiptDate)}</span>
      </div>
      <div class="asn-meta-item">
        <span class="form-label">Supplier</span>
        <span class="asn-meta-value">${asn.vendorId || "—"}</span>
      </div>
      <div class="asn-meta-item">
        <span class="form-label">Lines</span>
        <span class="asn-meta-value">${asn.lineCount ?? getAsnLines().length}</span>
      </div>
    </div>`;
}

function renderModals() {
  return `
  <div class="modal fade" id="confirmModal" tabindex="-1">
    <div class="modal-dialog modal-dialog-centered">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title"><i class="fa-solid fa-circle-question"></i> Confirm order creation</h5>
          <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
        </div>
        <div class="modal-body">
          <p id="confirmModalBody">This process will create <strong>0</strong> replenishment orders across all 0 ASN lines.</p>
          <p class="text-muted mb-0">Do you wish to continue?</p>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
          <button type="button" class="btn btn-success" id="confirmCreateBtn">Yes, create orders</button>
        </div>
      </div>
    </div>
  </div>
  <div class="modal fade" id="resultsModal" tabindex="-1">
    <div class="modal-dialog modal-lg modal-dialog-centered modal-dialog-scrollable">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title"><i class="fa-solid fa-clipboard-check"></i> Order creation summary</h5>
          <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
        </div>
        <div class="modal-body">
          <p id="resultsSummary" class="fw-semibold"></p>
          <div class="table-wrap">
            <table class="ft-table">
              <thead><tr><th>Order Id</th><th>Destination</th><th>Item</th><th>Lines</th><th>Status</th></tr></thead>
              <tbody id="resultsTableBody"></tbody>
            </table>
          </div>
        </div>
        <div class="modal-footer">
          <a class="btn btn-primary hidden" id="viewOrdersBtn" href="#" target="_blank" rel="noopener noreferrer">View Orders</a>
          <button type="button" class="btn btn-primary" data-bs-dismiss="modal">Close</button>
        </div>
      </div>
    </div>
  </div>`;
}

function manhOrdersScreenUrl(orderIds) {
  const org = window.APP_STATE?.org || "";
  const location = window.APP_STATE?.location || (org ? `${org}-DM1` : "");
  const params = new URLSearchParams({
    M_Screen: "orders",
    M_Organization: org,
    M_Location: location,
  });
  if (orderIds?.length) {
    params.set("OrderId", orderIds.join(","));
  }
  return `https://salep.sce.manh.com/udc/dm/linkTo?${params.toString()}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function aggregateOrderResults(orders) {
  const byOrder = new Map();
  (orders || []).forEach((o) => {
    if (!byOrder.has(o.orderId)) {
      byOrder.set(o.orderId, {
        orderId: o.orderId,
        destination: o.destination,
        lines: [],
        success: o.success,
        status: o.status,
      });
    }
    byOrder.get(o.orderId).lines.push({
      itemId: o.itemId,
      qty: o.qty,
      uom: o.uom,
    });
  });
  return [...byOrder.values()];
}

function renderResultsItemCell(lines) {
  if (lines.length === 1) {
    return escapeHtml(lines[0].itemId);
  }
  const tipHtml = lines
    .map((l) => `${escapeHtml(l.itemId)} — ${escapeHtml(l.qty)} ${escapeHtml(l.uom || "")}`)
    .join("<br>");
  return `<span class="mixed-item-label" tabindex="0" data-bs-toggle="tooltip" data-bs-html="true" data-bs-title="${tipHtml}">MIXED</span>`;
}

function disposeResultsTooltips() {
  document.querySelectorAll("#resultsTableBody .mixed-item-label").forEach((el) => {
    bootstrap.Tooltip.getInstance(el)?.dispose();
  });
}

function initResultsTooltips() {
  document.querySelectorAll("#resultsTableBody .mixed-item-label").forEach((el) => {
    new bootstrap.Tooltip(el, {
      html: true,
      customClass: "mixed-items-tooltip",
      container: "body",
      boundary: "viewport",
    });
  });
}

function showResultsModal(message, orders) {
  const tbody = document.getElementById("resultsTableBody");
  if (!tbody) return;
  disposeResultsTooltips();
  tbody.innerHTML = "";
  aggregateOrderResults(orders)
    .sort((a, b) => a.orderId.localeCompare(b.orderId))
    .forEach((order) => {
    const ok = order.success !== false && order.status === "OK";
    tbody.innerHTML += `<tr>
      <td>${escapeHtml(order.orderId)}</td>
      <td>${escapeHtml(order.destination)}</td>
      <td>${renderResultsItemCell(order.lines)}</td>
      <td>${order.lines.length}</td>
      <td class="result-status-cell ${ok ? "result-ok" : "result-fail"}"><i class="fa-solid fa-${ok ? "circle-check" : "circle-xmark"}"></i> ${escapeHtml(order.status)}</td>
    </tr>`;
  });
  initResultsTooltips();
  const summaryEl = document.getElementById("resultsSummary");
  if (summaryEl) {
    summaryEl.textContent = message || "";
    const anyFailed = (orders || []).some((o) => o.success === false || o.status === "FAILED");
    summaryEl.classList.toggle("text-danger", anyFailed);
    summaryEl.classList.toggle("text-success", !anyFailed && orders.length > 0);
  }
  const viewBtn = document.getElementById("viewOrdersBtn");
  if (viewBtn) {
    const successfulIds = [
      ...new Set(
        (orders || []).filter((o) => o.success !== false && o.status === "OK").map((o) => o.orderId)
      ),
    ].filter(Boolean);
    if (successfulIds.length >= 1) {
      viewBtn.href = manhOrdersScreenUrl(successfulIds);
      viewBtn.textContent = successfulIds.length === 1 ? "View Order" : "View Orders";
      viewBtn.classList.remove("hidden");
    } else {
      viewBtn.href = "#";
      viewBtn.classList.add("hidden");
    }
  }
  new bootstrap.Modal(document.getElementById("resultsModal")).show();
}

function selectionsPayload(selections) {
  const out = {};
  Object.entries(selections).forEach(([k, v]) => {
    out[String(k)] = v;
  });
  return out;
}
