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

function renderNeedTable(line) {
  const rows = visibleNeeds(line)
    .map(
      (n) => `<tr class="${needRowClass(n)}">
        <td>${n.facility}</td>
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
    const defaultTitle = o.key === line.defaultAlgo ? " (default for this item)" : "";
    return `<th class="${policyColClass(o.key)} algo-pick-cell${o.key === selectedKey ? " col-selected-h" : ""}" data-algo="${o.key}" role="button" tabindex="0" title="Apply ${o.label}${defaultTitle}">${o.label}${mark}</th>`;
  }).join("");

  const bodyRows = facilities
    .map((fac) => {
      const need = line.needs.find((n) => n.facility === fac);
      const ex = need ? needRowClass(need) : "";
      const cells = ALGO_OPTIONS.map((o) => {
        const val = line.policies[o.key]?.[fac] ?? "0";
        const sel = o.key === selectedKey ? " cell-selected" : "";
        return `<td class="${policyColClass(o.key)} algo-pick-cell${sel}" data-algo="${o.key}" role="button" tabindex="0" title="Apply ${o.label}">${val}</td>`;
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
        <td>${fac}</td>
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
  const parts = [`<span class="text-muted">ASN qty ${line.qty} ${line.uom}</span>`];
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
          <h2>Line ${line.lineNum} — Item ${line.itemId}</h2>
          <div class="line-badges">${renderLineBadges(line)}</div>
        </div>
        <div class="line-algo-picker">
          <label class="form-label" for="${selId}">Apply Algorithm for This Line</label>
          <select class="form-select algo-select" id="${selId}" data-line="${line.lineNum}">${renderAlgoOptions(line, selectedKey)}</select>
        </div>
      </div>
      ${renderFacilityNeedHeader(line)}
      ${renderNeedTable(line)}
      <h6 class="form-label mt-3 mb-2">Algorithm comparison <span class="text-muted fw-normal">(click a column to apply)</span></h6>
      ${renderComparisonTable(line, selectedKey)}
    </div>`;
}

function bindLineSelectors(container, selections, onChange) {
  container.querySelectorAll(".algo-select").forEach((sel) => {
    sel.addEventListener("change", () => {
      selections[sel.dataset.line] = sel.value;
      onChange();
    });
  });
}

function bindAlgoColumnPick(container, selections, onChange) {
  if (!container || container.dataset.algoPickBound) return;
  container.dataset.algoPickBound = "1";
  const applyAlgo = (linePanel, algoKey) => {
    const lineNum = linePanel?.dataset.line;
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
    const algo = selections[line.lineNum] || line.defaultAlgo;
    const units = line.units[algo] || {};
    Object.entries(units).forEach(([fac, qty]) => {
      if (qty > 0) facilities.add(fac);
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

function updateFooterSummary(selections, orderCount) {
  const el = document.getElementById("footerSummary");
  if (!el) return;
  const lines = getAsnLines();
  const count = orderCount ?? countFacilityOrders(lines, selections);
  el.textContent = `${lines.length} lines · ${count} order(s) on Create (based on selected algorithms)`;
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
          <p>This process will create <strong id="confirmOrderCount">0</strong> replenishment order(s) across all ASN lines.</p>
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
              <thead><tr><th>Order Id</th><th>Destination</th><th>Item</th><th>Qty</th><th>Status</th></tr></thead>
              <tbody id="resultsTableBody"></tbody>
            </table>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-primary" data-bs-dismiss="modal">Close</button>
        </div>
      </div>
    </div>
  </div>`;
}

function showResultsModal(message, orders) {
  const tbody = document.getElementById("resultsTableBody");
  if (!tbody) return;
  tbody.innerHTML = "";
  (orders || []).forEach((o) => {
    const ok = o.success !== false && o.status === "OK";
    tbody.innerHTML += `<tr>
      <td>${o.orderId}</td>
      <td>${o.destination}</td>
      <td>${o.itemId}</td>
      <td>${o.qty}</td>
      <td class="${ok ? "result-ok" : "text-danger"}"><i class="fa-solid fa-${ok ? "circle-check" : "circle-xmark"}"></i> ${o.status}</td>
    </tr>`;
  });
  document.getElementById("resultsSummary").textContent = message || "";
  new bootstrap.Modal(document.getElementById("resultsModal")).show();
}

function selectionsPayload(selections) {
  const out = {};
  Object.entries(selections).forEach(([k, v]) => {
    out[String(k)] = v;
  });
  return out;
}
