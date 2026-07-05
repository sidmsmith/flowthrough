# Flowthrough — Postman ASN Setup

Create demo ASNs individually via `/receiving/api/receiving/asn/save` (bulk import is **not** supported).

## Option A: Use `create_asns.py` (recommended)

```bash
cd flowthrough
pip install -r requirements.txt
python create_asns.py --all
```

## Option B: Postman manually

**Endpoint:** `POST https://salep.sce.manh.com/receiving/api/receiving/asn/save`

**Headers:**
- `Authorization: Bearer <token>`
- `Content-Type: application/json`
- `selectedOrganization: SS-DEMO`
- `selectedLocation: SS-DEMO-DM1`

Replace `SS-DEMO` with your ORG.

Payloads are in [`postman_asns.json`](postman_asns.json) — post each `save_payload` separately.

Sample replenishment order payloads (after allocation): [`postman_order_FLOW005.json`](postman_order_FLOW005.json).

## Demo ASNs

| AsnId | Items | Qty | Highlights |
|-------|-------|-----|------------|
| FLOW001 | 1000012 | 50 | Proportional vs fixed priority |
| FLOW002 | 1000013 | 60 | All 4 policies differ (shortages 8/12/42) |
| FLOW003 | 1000014 | 25 | Pack 5 — all 4 policies differ |
| FLOW004 | 1000015 | 135 | Pallet 100 + remainder; default = fixed priority |
| FLOW005 | 1125145 + 1000015 | 25 + 135 | Multi-line; line 1 mirrors FLOW003 on item 1125145 |
| FLOW006 | 1125145 + 1000015 | 25 + 135 | Same structure as FLOW005 (alternate multi-line demo) |

Each ASN includes `EstimatedReceiptDate` and `VendorId` (`400975`) in the save payload.

## Verify / filter in MAWM

List all flowthrough ASNs:

```json
{ "Query": "AsnId like 'FLOW%'" }
```

Single ASN:

```json
{ "Query": "AsnId = 'FLOW001'" }
```

## WMS prerequisites (web app + order create)

- ASN status **In Transit (1000)** before load
- **Fast Flow** order type configured in MAWM (pipeline/status from order-type config — do not send `PipelineId` on order save)
- No existing outbound orders matching `FLOW-{AsnId}-%` for that ASN
