/**
 * Algorithm explanation tooltips — pre-built on ASN load (~0.5s hover delay).
 */

const ALGO_EXPLAINER_DELAY_MS = 500;
const ALGO_EXPLAINER_HIDE_GRACE_MS = 180;

let explainerEl = null;
let explainerTimer = null;
let hideTimer = null;
let explainerAnchor = null;
let explainerContext = null;

function getAlgoExplanation(line, algoKey, facility) {
  const block = line?.explanations?.[algoKey];
  if (!block) return null;
  if (facility && block.facilities?.[facility]) {
    return block.facilities[facility];
  }
  return { summary: block.summary, details: block.details || [] };
}

function ensureExplainerElement() {
  if (explainerEl) return explainerEl;
  explainerEl = document.createElement("div");
  explainerEl.className = "algo-explainer hidden";
  explainerEl.setAttribute("role", "tooltip");
  document.body.appendChild(explainerEl);

  explainerEl.addEventListener("mouseenter", () => {
    cancelHideExplainer();
  });

  explainerEl.addEventListener("mouseleave", (e) => {
    const related = e.relatedTarget;
    if (related?.closest?.(".algo-expl-cell")) return;
    scheduleHideExplainer();
  });

  return explainerEl;
}

function escapeExplainerHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderExplainerContent(line, algoKey, facility, algoLabel) {
  const data = getAlgoExplanation(line, algoKey, facility);
  if (!data?.summary) {
    return `<div class="algo-explainer-empty">No explanation available for this cell.</div>`;
  }

  const scope = facility
    ? `<span class="algo-explainer-scope">${escapeExplainerHtml(facility)} · ${escapeExplainerHtml(algoLabel)}</span>`
    : `<span class="algo-explainer-scope">${escapeExplainerHtml(algoLabel)} · all facilities</span>`;

  const details = (data.details || []).filter(Boolean);
  const detailsHtml =
    details.length > 0
      ? `<details class="algo-explainer-details">
          <summary>Show calculation detail</summary>
          <ul>${details.map((d) => `<li>${escapeExplainerHtml(d)}</li>`).join("")}</ul>
        </details>`
      : "";

  return `
    ${scope}
    <p class="algo-explainer-summary">${escapeExplainerHtml(data.summary)}</p>
    ${detailsHtml}
    <div class="algo-explainer-foot">Click column to apply algorithm</div>`;
}

function positionExplainer(anchor) {
  const el = ensureExplainerElement();
  el.classList.remove("hidden");
  const rect = anchor.getBoundingClientRect();
  const margin = 4;
  let left = rect.left + rect.width / 2 - el.offsetWidth / 2;
  left = Math.max(margin, Math.min(left, window.innerWidth - el.offsetWidth - margin));
  let top = rect.bottom + margin;
  if (top + el.offsetHeight > window.innerHeight - margin) {
    top = rect.top - el.offsetHeight - margin;
    el.classList.add("algo-explainer-above");
  } else {
    el.classList.remove("algo-explainer-above");
  }
  el.style.left = `${left}px`;
  el.style.top = `${top}px`;
}

function cancelHideExplainer() {
  if (hideTimer) {
    clearTimeout(hideTimer);
    hideTimer = null;
  }
}

function scheduleHideExplainer() {
  cancelHideExplainer();
  hideTimer = setTimeout(() => {
    hideTimer = null;
    hideExplainer();
  }, ALGO_EXPLAINER_HIDE_GRACE_MS);
}

function hideExplainer() {
  if (explainerTimer) {
    clearTimeout(explainerTimer);
    explainerTimer = null;
  }
  cancelHideExplainer();
  explainerAnchor = null;
  explainerContext = null;
  if (explainerEl) explainerEl.classList.add("hidden");
}

function showExplainer(anchor, line, algoKey, facility, label) {
  const el = ensureExplainerElement();
  const ctx = { line, algoKey, facility, label };
  const sameAnchor = explainerAnchor === anchor;
  const sameCtx =
    explainerContext &&
    explainerContext.algoKey === algoKey &&
    explainerContext.facility === facility &&
    explainerContext.line?.lineNum === line.lineNum;

  if (!sameAnchor || !sameCtx) {
    el.innerHTML = renderExplainerContent(line, algoKey, facility, label);
  }

  explainerAnchor = anchor;
  explainerContext = ctx;
  positionExplainer(anchor);
}

function scheduleExplainer(anchor, line, algoKey, facility, label) {
  cancelHideExplainer();
  if (explainerTimer) clearTimeout(explainerTimer);
  explainerTimer = setTimeout(() => {
    explainerTimer = null;
    showExplainer(anchor, line, algoKey, facility, label);
  }, ALGO_EXPLAINER_DELAY_MS);
}

function isMovingToExplainer(related) {
  return related && explainerEl && !explainerEl.classList.contains("hidden") && explainerEl.contains(related);
}

function bindAlgoExplainer(container) {
  if (!container || container.dataset.algoExplainerBound) return;
  container.dataset.algoExplainerBound = "1";

  container.addEventListener(
    "mouseenter",
    (e) => {
      const cell = e.target.closest(".algo-expl-cell");
      if (!cell) return;
      const panel = cell.closest(".line-panel");
      if (!panel) return;
      const lineNum = parseInt(panel.dataset.line, 10);
      const line = getAsnLines().find((l) => l.lineNum === lineNum);
      if (!line?.explanations) return;
      const algoKey = cell.dataset.algo;
      const facility = cell.dataset.facility || null;
      const opt = ALGO_OPTIONS.find((o) => o.key === algoKey);
      const label = opt ? opt.label : algoKey;
      scheduleExplainer(cell, line, algoKey, facility, label);
    },
    true
  );

  container.addEventListener(
    "mouseleave",
    (e) => {
      const cell = e.target.closest(".algo-expl-cell");
      if (!cell) return;
      const related = e.relatedTarget;
      if (related && (cell.contains(related) || isMovingToExplainer(related))) return;
      scheduleHideExplainer();
    },
    true
  );

  document.addEventListener("scroll", hideExplainer, true);
  window.addEventListener("resize", hideExplainer);
}
