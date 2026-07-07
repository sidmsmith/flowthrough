# Flowthrough Allocation Algorithms — Reference & Demo Examples

This document describes every allocation policy used in Flowthrough (CLI and web app), how they fit into the shared pipeline, and **worked results** from demo ASNs **FLOW001–FLOW006** using `data/facility_inventory.json` (ORG `SS-DEMO`, receiving at DM1).

For implementation details (remaining need after crossdock, residual sweep), see [ALLOCATION.md](ALLOCATION.md).

---

## Shared pipeline (all policies)

Every comparison column runs the same stages:

1. **Pallet pass** — If the item has a pallet UOM and the ASN can form at least one full pallet, assign full pallet(s) to the facility with the **largest shortage** that can accept a pallet. Only one crossdock recipient per line in the current engine.
2. **Remainder pass** — Split loose units using the selected policy. Weights use **remaining need** after the pallet pass: `max(0, shortage − already_allocated)`.
3. **UOM enforcement** — Round to full packs when `allow_split_pack` is false; cap at max inventory and shortage.
4. **Residual sweep** — Assign leftover ASN quantity in full packs to facilities that still have headroom.

**Facility eligibility:** `max_qty > 0` and `shortage > 0`, where:

```text
inventory_position = available_qty + inbound_qty − outbound_qty
shortage           = max(0, max_qty − inventory_position)
```

**Comparison columns in the UI / CLI:**

| Col | Key | Label |
|-----|-----|-------|
| 1 | `proportional` | Proportional |
| 2 | `fixed_priority` | Fixed Priority |
| 3 | `largest_shortage` | Largest Shortage |
| 4 | `weighted_score` | Weighted Score |
| 5 | `default` | Default — uses the part’s `default_algorithm` from config |

When total shortage across eligible facilities **exceeds ASN quantity**, greedy policies (2–4) may assign **zero** to some facilities. That is expected.

---

## Algorithm 1 — Proportional

**Behavior:** Split the ASN (or loose remainder after pallet pass) in proportion to each facility’s **remaining shortage**.

```text
facility_share = floor(remaining_asn × facility_remaining_need / sum_of_remaining_needs)
```

The last facility in the list receives any rounding remainder so all units are assigned. Each share is capped at that facility’s shortage and pack rules.

**Best demo:** FLOW001 — clear contrast with fixed priority when demand exceeds supply.

### FLOW001 — item 1000012, ASN 50

| Facility | Priority | Position | Max | Shortage |
|----------|----------|----------|-----|----------|
| DM2 | 1 | 75 | 100 | 25 |
| DM3 | 2 | 60 | 100 | 40 |
| DM4 | 3 | 70 | 100 | 30 |
| DM5 | — | — | 0 | (excluded) |

Total shortage **95**; ASN **50** → everyone gets something.

| Facility | Allocation |
|----------|------------|
| DM2 | **13** |
| DM3 | **21** |
| DM4 | **16** |
| **Total** | **50** |

---

## Algorithm 2 — Fixed Priority

**Behavior:** Fill facilities in **priority order** (DM2 → DM3 → DM4 → DM5) until the ASN is exhausted. Each facility receives up to its remaining shortage.

**Best demo:** FLOW001 — DM2 and DM3 consume the full ASN; DM4 gets nothing.

### FLOW001 — item 1000012, ASN 50

| Facility | Allocation |
|----------|------------|
| DM2 | **25** (full shortage) |
| DM3 | **25** (partial — only 25 units left) |
| DM4 | **0** |
| **Total** | **50** |

---

## Algorithm 3 — Largest Shortage

**Behavior:** Greedy fill — facilities sorted by **remaining shortage descending**. Each gets `min(remaining_shortage, remaining_asn)` until the ASN runs out.

**Best demo:** FLOW002 — all four core policies produce **different** splits on the same line.

### FLOW002 — item 1000013, ASN 60

| Facility | Priority | Position | Max | Shortage |
|----------|----------|----------|-----|----------|
| DM2 | 1 | 92 | 100 | 8 |
| DM3 | 2 | 88 | 100 | 12 |
| DM4 | 3 | 58 | 100 | 42 |

Total shortage **62**; ASN **60**.

| Policy | DM2 | DM3 | DM4 | Total |
|--------|-----|-----|-----|-------|
| 1 Proportional | 7 | 11 | 42 | 60 |
| 2 Fixed priority | 8 | 12 | 40 | 60 |
| 3 Largest shortage | 6 | 12 | 42 | 60 |
| 4 Weighted | 8 | 10 | 42 | 60 |
| 5 Default (largest) | 6 | 12 | 42 | 60 |

Part **1000013** has `default_algorithm: largest_shortage`, so column 5 matches column 3.

---

## Algorithm 4 — Weighted Score

**Behavior:** Rank facilities by a blended score, then greedy fill in rank order (same as fixed priority, but order comes from score instead of static priority).

**Default formula:**

```text
score = 0.70 × (facility_shortage / max_shortage_in_set)
      + 0.30 × (priority_norm)
```

- **Shortage term** — larger gaps score higher.
- **Priority term** — lower priority number ranks higher (DM2 = 1 is best).
- Only facilities with `max_qty > 0` and `shortage > 0` participate.

### FLOW001 — weighted walkthrough (item 1000012, ASN 50)

| Facility | Shortage | Shortage norm | Priority norm | **Score** | Rank |
|----------|----------|---------------|---------------|-----------|------|
| DM3 | 40 | 1.000 | 0.667 | **0.900** | 1st |
| DM2 | 25 | 0.625 | 1.000 | **0.738** | 2nd |
| DM4 | 30 | 0.750 | 0.500 | **0.625** | 3rd |

Greedy fill: DM3 ← 40, DM2 ← 10 (ASN exhausted), DM4 ← 0.

| Facility | Allocation |
|----------|------------|
| DM2 | **10** |
| DM3 | **40** |
| DM4 | **0** |
| **Total** | **50** |

DM4 is skipped because the ASN runs out after higher-ranked stores — not because its shortage is ignored.

### FLOW001 — all policies compared

| Facility | Proportional | Fixed | Largest | Weighted |
|----------|--------------|-------|---------|----------|
| DM2 | 13 | 25 | 0 | 10 |
| DM3 | 21 | 25 | 40 | 40 |
| DM4 | 16 | 0 | 10 | 0 |

---

## Algorithm 5 — Default (per-part policy)

**Behavior:** Runs whichever of algorithms 1–4 is configured on the part (`default_algorithm` in `facility_inventory.json`), or the root config default (`proportional`).

| Item | Default policy | Demo ASN |
|------|----------------|----------|
| 1000012 | proportional | FLOW001 |
| 1000013 | largest_shortage | FLOW002 |
| 1000014 | proportional | FLOW003 |
| 1000015 | fixed_priority | FLOW004, FLOW005/006 line 2 |
| 1125145 | proportional | FLOW005/006 line 1 |

Column 5 header in the UI shows the resolved name, e.g. **5 Default (Fixed Pty)**.

---

## Pack rounding — FLOW003

**Item 1000014** — pack qty **5**, ASN **25** (5 packs). Shortages: DM2 **10**, DM3 **12**, DM4 **15**.

| Policy | DM2 | DM3 | DM4 | Notes |
|--------|-----|-----|-----|-------|
| Proportional | 5 (1pk) | 10 (2pk) | 10 (2pk) | Default for this part |
| Fixed priority | 10 (2pk) | 10 (2pk) | 5 (1pk) | Priority order before pack tie-break |
| Largest shortage | 0 | 10 (2pk) | 15 (3pk) | DM4 first; DM2 starved |
| Weighted | 10 (2pk) | 0 | 15 (3pk) | DM3 starved |

All four core policies produce **different** pack splits — use FLOW003 in the web app to compare columns side by side.

**FLOW005 / FLOW006 line 1** (item **1125145**, qty **25**, pack 5) produces the **same splits** as FLOW003 because facility positions and shortages for that item match item 1000014.

---

## Pallet crossdock — FLOW004

**Item 1000015** — pack **5**, pallet **100**, ASN **135**.

| Facility | Priority | Position | Max | Shortage |
|----------|----------|----------|-----|----------|
| DM2 | 1 | 90 | 200 | 110 |
| DM3 | 2 | 80 | 100 | 20 |
| DM4 | 3 | 82 | 100 | 18 |
| DM5 | 4 | 88 | 100 | 12 |

**Pallet pass:** 100 units → **DM2** (largest shortage that can take a full pallet). Loose remainder **35**.

**Remaining need after crossdock** (for remainder policies):

| Facility | Remaining need |
|----------|----------------|
| DM2 | 10 |
| DM3 | 20 |
| DM4 | 18 |
| DM5 | 12 |

### FLOW004 — results by policy

| Policy | DM2 | DM3 | DM4 | DM5 | Crossdock |
|--------|-----|-----|-----|-----|-----------|
| Proportional | 105 (21pk) | 15 (3pk) | 10 (2pk) | 5 (1pk) | 100 → DM2 |
| Fixed priority | 110 (22pk) | 20 (4pk) | 5 (1pk) | 0 | 100 → DM2 |
| Largest shortage | 100 (20pk) | 20 (4pk) | 15 (3pk) | 0 | 100 → DM2 |
| Weighted | 100 (20pk) | 20 (4pk) | 15 (3pk) | 0 | 100 → DM2 |
| Default (fixed) | 110 (22pk) | 20 (4pk) | 5 (1pk) | 0 | 100 → DM2 |

DM2 totals include the **100-unit pallet** plus loose remainder. Fixed priority (the part default) tops up DM2 to full shortage (110) before serving lower-priority stores.

**FLOW005 / FLOW006 line 2** duplicates FLOW004 (same item and qty).

---

## Multi-line ASNs — FLOW005 & FLOW006

Both ASNs are two-line demos; allocation is **independent per line**.

| Line | Item | ASN qty | What to compare |
|------|------|---------|-----------------|
| 1 | 1125145 | 25 | Same four-way pack split as FLOW003 |
| 2 | 1000015 | 135 | Pallet crossdock + remainder; default = fixed priority |

Use **FLOW005** or **FLOW006** in the web app stacked view to see both lines and pick a policy per line before creating orders.

---

## Demo ASN quick reference

| ASN | Item(s) | ASN qty | Highlight |
|-----|---------|---------|-----------|
| **FLOW001** | 1000012 | 50 | Proportional vs fixed priority; weighted walkthrough |
| **FLOW002** | 1000013 | 60 | All 4 policies differ (shortages 8 / 12 / 42) |
| **FLOW003** | 1000014 | 25 | Pack 5 — all 4 policies differ |
| **FLOW004** | 1000015 | 135 | Pallet 100 + remainder; default = fixed priority |
| **FLOW005** | 1125145 + 1000015 | 25 + 135 | Multi-line: pack demo + pallet demo |
| **FLOW006** | 1125145 + 1000015 | 25 + 135 | Same structure as FLOW005 |

Filter in MAWM: `{ "Query": "AsnId like 'FLOW%'" }`

---

## Reproduce these numbers

**CLI (preview, no MAWM writes for allocation math — still needs ASN in MAWM for live fetch):**

```bash
python run_flowthrough.py --mode preview --asn FLOW001 --token-file .token
```

**Web app:** [flowthrough.vercel.app](https://flowthrough.vercel.app) — load ASN, compare columns, select algorithm per line, create orders.

**Config:** Edit shortages and defaults in `data/facility_inventory.json` (`facility_parts[]` and `parts[].default_algorithm`).

---

## Related files

| File | Purpose |
|------|---------|
| `allocation/algorithms.py` | Policy implementations |
| `allocation/need.py` | Shortage and facility need |
| `allocation/uom.py` | Pack rounding and residual sweep |
| `ALLOCATION.md` | Design notes and crossdock remainder theory |
| `data/facility_inventory.json` | Demo inventory and per-part defaults |
