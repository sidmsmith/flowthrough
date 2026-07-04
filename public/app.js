/** Flowthrough production app — auth, ASN load, allocation UI */

window.APP_STATE = {
  token: null,
  org: null,
  location: null,
  asnData: null,
};

const APP_VERSION = "0.0.1";
const VIEW_KEY = "flowthrough-view";
const sessionId = `sess_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
const pageLoadTime = new Date().toISOString();
let authAttemptCount = 0;
let firstAuthSuccess = false;
let selections = {};
let activeLine = 1;
let asnLoaded = false;
let previewOrderCount = 0;

let orgInput;
let authBtn;
let orgSection;
let mainUI;
let statusEl;
let asnInput;
let loadBtn;
let previewWrapper;
let linesContainer;
let detailPane;
let viewSelect;
let createBtn;
let footerActions;

function status(msg, type) {
  if (!statusEl) return;
  statusEl.textContent = msg;
  statusEl.className = "status " + (type === "error" ? "text-danger" : type === "success" ? "text-success" : "");
}

async function api(action, body, showStatus = false) {
  try {
    const res = await fetch("/api/" + action, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const text = await res.text();
    let result;
    try {
      result = text ? JSON.parse(text) : {};
    } catch {
      return { success: false, error: `API returned non-JSON (${res.status})` };
    }
    if (!res.ok && result.success !== false) {
      result.success = false;
      result.error = result.error || `HTTP ${res.status}`;
    }
    if (showStatus && !result.success) {
      status(result.error || result.message || "Request failed", "error");
    }
    return result;
  } catch (e) {
    if (showStatus) status(e.message, "error");
    return { success: false, error: e.message };
  }
}

function getUrlParams() {
  return new URLSearchParams(window.location.search);
}

function getUrlAsnId(params) {
  for (const key of ["AsnId", "ASN", "asn", "asnid", "AsnID", "Asn"]) {
    const v = params.get(key);
    if (v?.trim()) return v.trim().toUpperCase();
  }
  return null;
}

function getCommonMetadata(extra = {}) {
  const params = getUrlParams();
  const urlParamsObj = {};
  params.forEach((v, k) => {
    urlParamsObj[k] = v;
  });
  return {
    page_title: "Flowthrough",
    ui_version: APP_VERSION,
    timestamp: new Date().toISOString(),
    session_id: sessionId,
    page_load_time: pageLoadTime,
    user_agent: navigator.userAgent,
    url_params: urlParamsObj,
    auto_authenticated: !!params.get("Organization"),
    auth_method: params.get("Organization") ? "url_param" : "manual",
    auth_attempt_count: authAttemptCount,
    first_auth_success: firstAuthSuccess,
    ...extra,
  };
}

async function trackEvent(eventName, metadata = {}) {
  try {
    await api("usage-track", { event_name: eventName, metadata: getCommonMetadata(metadata) }, false);
  } catch {
    /* non-blocking */
  }
}

function getOrg() {
  return orgInput.value.trim().toUpperCase();
}

function getLocation() {
  if (window.APP_STATE.location) return window.APP_STATE.location;
  const org = getOrg();
  return org ? `${org}-DM1` : null;
}

function currentView() {
  return viewSelect.value === "2" ? "main" : "stacked";
}

function applyViewMode() {
  const mainDetail = currentView() === "main";
  previewWrapper.classList.toggle("stacked-active", !mainDetail);
  previewWrapper.classList.toggle("main-detail-active", mainDetail);
  document.getElementById("stackedView").classList.toggle("hidden", mainDetail);
  document.getElementById("mainDetailView").classList.toggle("hidden", !mainDetail);
  sessionStorage.setItem(VIEW_KEY, viewSelect.value);
  if (asnLoaded) refreshActiveView();
}

function refreshStacked() {
  const lines = getAsnLines();
  linesContainer.innerHTML = lines.map((line) => renderLinePanel(line, selections[line.lineNum], "a")).join("");
  bindLineSelectors(linesContainer, selections, onSelectionsChange);
  updateFooterSummary(selections, previewOrderCount);
}

function renderNav() {
  const lines = getAsnLines();
  document.getElementById("lineNav").innerHTML = lines
    .map((line) => {
      const algo = selections[line.lineNum];
      const label = algoLabel(algo, line.defaultAlgo);
      const active = line.lineNum === activeLine ? " active" : "";
      return `<button type="button" class="line-nav-item${active}" data-line="${line.lineNum}">
        <strong>Line ${line.lineNum}</strong><br>
        <span class="small">${line.itemId} · qty ${line.qty}</span><br>
        <span class="small text-muted">${label}</span>
      </button>`;
    })
    .join("");
  document.querySelectorAll(".line-nav-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      activeLine = parseInt(btn.dataset.line, 10);
      renderNav();
      renderDetail();
    });
  });
  document.getElementById("navSummary").textContent = `${lines.length} ${pluralWord(lines.length, "line")}`;
}

function renderDetail() {
  const line = getAsnLines().find((l) => l.lineNum === activeLine);
  if (!line) return;
  detailPane.innerHTML = renderLinePanel(line, selections[line.lineNum], "a-md");
  bindLineSelectors(detailPane, selections, () => {
    renderNav();
    renderDetail();
    onSelectionsChange();
  });
}

function refreshMainDetail() {
  renderNav();
  renderDetail();
  updateFooterSummary(selections, previewOrderCount);
}

function refreshActiveView() {
  if (currentView() === "main") refreshMainDetail();
  else refreshStacked();
}

async function refreshPreviewCount() {
  if (!asnLoaded || !window.APP_STATE.token) return;
  const asn = getAsnData()?.asn;
  if (!asn?.asnId) return;
  const res = await api(
    "preview_orders",
    {
      org: getOrg(),
      token: window.APP_STATE.token,
      asn_id: asn.asnId,
      location: getLocation(),
      selections: selectionsPayload(selections),
    },
    false
  );
  previewOrderCount = res.success ? res.orderCount || 0 : 0;
  updateFooterSummary(selections, previewOrderCount);
}

function onSelectionsChange() {
  refreshActiveView();
  refreshPreviewCount();
}

async function authenticate() {
  const org = getOrg();
  authAttemptCount++;
  const start = Date.now();
  authBtn.disabled = true;
  await trackEvent("auth_attempt", { org: org || "unknown" });

  if (!org) {
    status("ORG required", "error");
    mainUI.style.display = "none";
    await trackEvent("auth_failed", { error: "ORG required", auth_duration_ms: Date.now() - start });
    authBtn.disabled = false;
    throw new Error("ORG required");
  }

  status("Authenticating...");
  const res = await api("auth", { org }, true);
  if (!res.success) {
    status("Authentication failed", "error");
    mainUI.style.display = "none";
    await trackEvent("auth_failed", { org, error: res.error, auth_duration_ms: Date.now() - start });
    authBtn.disabled = false;
    throw new Error(res.error || "Auth failed");
  }

  window.APP_STATE.token = res.token;
  window.APP_STATE.org = org;
  if (!window.APP_STATE.location) {
    window.APP_STATE.location = getUrlParams().get("Location")?.trim() || `${org}-DM1`;
  }

  status("Authenticated – ready!", "success");
  mainUI.style.display = "block";
  orgSection.style.display = "none";
  firstAuthSuccess = true;
  await trackEvent("auth_success", { org, auth_duration_ms: Date.now() - start, token_received: true });
  authBtn.disabled = false;
}

async function loadAsn(skipPrompt) {
  if (!window.APP_STATE.token) {
    status("Authenticate first", "error");
    return false;
  }

  const asnId = (asnInput.value || "").trim().toUpperCase();
  if (!asnId) {
    status("Enter an ASN Id", "error");
    return false;
  }

  const start = Date.now();
  await trackEvent("load_asn_attempt", { org: getOrg(), asn_id: asnId });

  loadBtn.disabled = true;
  status("Loading ASN...");
  const res = await api(
    "load_asn",
    {
      org: getOrg(),
      token: window.APP_STATE.token,
      asn_id: asnId,
      location: getLocation(),
    },
    true
  );
  loadBtn.disabled = false;

  if (!res.success) {
    setFooterVisible(false);
    asnLoaded = false;
    await trackEvent("load_asn_failed", {
      org: getOrg(),
      asn_id: asnId,
      error: res.error,
      duration_ms: Date.now() - start,
    });
    return false;
  }

  window.APP_STATE.asnData = {
    asn: res.asn,
    lines: res.lines,
    receivingFacility: res.receivingFacility,
  };
  const nextSelections = defaultSelections(res.lines);
  Object.keys(selections).forEach((k) => delete selections[k]);
  Object.assign(selections, nextSelections);
  asnInput.value = res.asn.asnId;

  document.getElementById("asnMeta").innerHTML = renderAsnMeta(res.asn);
  document.getElementById("asnMeta").classList.remove("hidden");
  previewWrapper.classList.remove("hidden");
  createBtn.disabled = false;
  asnLoaded = true;
  activeLine = 1;
  setFooterVisible(true);

  await refreshPreviewCount();
  refreshActiveView();

  status(`ASN ${res.asn.asnId} loaded`, "success");
  await trackEvent("load_asn_completed", {
    org: getOrg(),
    asn_id: res.asn.asnId,
    line_count: res.lines.length,
    duration_ms: Date.now() - start,
  });
  return true;
}

async function confirmCreateOrders() {
  const asn = getAsnData()?.asn;
  if (!asn?.asnId) return;

  const start = Date.now();
  await trackEvent("create_orders_attempt", {
    org: getOrg(),
    asn_id: asn.asnId,
    order_count: previewOrderCount,
  });

  createBtn.disabled = true;
  status(previewOrderCount === 1 ? "Creating order..." : "Creating orders...");
  const res = await api(
    "create_orders",
    {
      org: getOrg(),
      token: window.APP_STATE.token,
      asn_id: asn.asnId,
      location: getLocation(),
      selections: selectionsPayload(selections),
    },
    false
  );
  createBtn.disabled = false;

  const orders = res.orders || [];
  if (orders.length > 0) {
    const allOk = !!res.success;
    const partial = !allOk && (res.orderCount || 0) > 0;
    status(
      res.message ||
        (allOk
          ? res.orderCount === 1
            ? "Order created"
            : "Orders created"
          : partial
            ? "Some orders failed"
            : "Order creation failed"),
      allOk ? "success" : "error"
    );
    const eventPayload = {
      org: getOrg(),
      asn_id: asn.asnId,
      order_count: res.orderCount || 0,
      duration_ms: Date.now() - start,
    };
    if (allOk || partial) {
      await trackEvent("create_orders_completed", { ...eventPayload, had_failures: !allOk });
    } else {
      await trackEvent("create_orders_failed", { ...eventPayload, error: res.message || res.error });
    }
    showResultsModal(res.message, orders);
    return;
  }

  if (!res.success) {
    status(res.error || res.message || "Order creation failed", "error");
    await trackEvent("create_orders_failed", {
      org: getOrg(),
      asn_id: asn.asnId,
      error: res.error || res.message,
      duration_ms: Date.now() - start,
    });
    return;
  }

  status(res.message || (res.orderCount === 1 ? "Order created" : "Orders created"), "success");
  await trackEvent("create_orders_completed", {
    org: getOrg(),
    asn_id: asn.asnId,
    order_count: res.orderCount,
    duration_ms: Date.now() - start,
  });
  showResultsModal(res.message, orders);
}

function bindCreateFlow() {
  createBtn.addEventListener("click", () => {
    if (!asnLoaded) {
      status("Load an ASN first", "error");
      return;
    }
    updateConfirmModalCopy(previewOrderCount, getAsnLines().length);
    new bootstrap.Modal(document.getElementById("confirmModal")).show();
  });

  document.getElementById("confirmCreateBtn")?.addEventListener("click", () => {
    bootstrap.Modal.getInstance(document.getElementById("confirmModal"))?.hide();
    confirmCreateOrders();
  });
}

function bindDomRefs() {
  orgInput = document.getElementById("org");
  authBtn = document.getElementById("authBtn");
  orgSection = document.getElementById("orgSection");
  mainUI = document.getElementById("mainUI");
  statusEl = document.getElementById("status");
  asnInput = document.getElementById("asnInput");
  loadBtn = document.getElementById("loadBtn");
  previewWrapper = document.getElementById("previewWrapper");
  linesContainer = document.getElementById("linesContainer");
  detailPane = document.getElementById("detailPane");
  viewSelect = document.getElementById("viewSelect");
  createBtn = document.getElementById("createBtn");
  footerActions = document.getElementById("footerActions");
}

function setFooterVisible(visible) {
  if (!footerActions) return;
  footerActions.classList.toggle("hidden", !visible);
  document.body.classList.toggle("footer-visible", visible);
}

function initApp() {
  bindDomRefs();
  if (!orgInput || !authBtn || !statusEl) {
    throw new Error("Required DOM elements missing");
  }

  document.getElementById("modalsHost").innerHTML = renderModals();
  bindCreateFlow();

  viewSelect.addEventListener("change", applyViewMode);
  const savedView = sessionStorage.getItem(VIEW_KEY);
  if (savedView === "1" || savedView === "2") viewSelect.value = savedView;
  applyViewMode();

  bindFacilityToggle(previewWrapper, refreshActiveView);
  bindAlgoColumnPick(previewWrapper, selections, onSelectionsChange);

  loadBtn.addEventListener("click", () => loadAsn());
  asnInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") loadAsn();
  });

  authBtn.addEventListener("click", () => authenticate().catch(() => {}));
  orgInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") authenticate().catch(() => {});
  });

  mainUI.style.display = "none";
  setFooterVisible(false);
}

window.addEventListener("load", async () => {
  try {
    initApp();
  } catch (e) {
    console.error(e);
    const el = document.getElementById("status");
    if (el) {
      el.textContent = "Failed to initialize app: " + e.message;
      el.className = "status text-danger";
    }
    return;
  }

  const params = getUrlParams();
  await trackEvent("app_opened", { has_url_params: params.toString().length > 0 });

  const urlOrg = params.get("Organization")?.trim();
  const urlLocation = params.get("Location")?.trim();
  const urlAsn = getUrlAsnId(params);

  if (urlLocation) window.APP_STATE.location = urlLocation;

  if (urlOrg) {
    orgInput.value = urlOrg;
    if (params.get("Organization")) orgSection.style.display = "none";
    try {
      await authenticate();
      if (urlAsn) {
        asnInput.value = urlAsn;
        await loadAsn(true);
      }
    } catch {
      orgSection.style.display = "block";
    }
  } else {
    orgInput.value = "";
    orgInput.focus();
  }
});
